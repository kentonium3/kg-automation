#!/usr/bin/env python3
"""Post-soak cleanup helper: revoke any remaining kent-attributed Vikunja API
tokens, leaving felix-bot as the sole API identity.

This is the fourth helper of ADR-0002 Phase 1 (issue #304), implementing
Phase 6 of the mission runbook. It runs AFTER the 7-day soak passes — never
earlier — because keeping kent's tokens alive during the soak preserves the
rollback path.

Authentication
--------------
Kent's existing API token may already have been rotated out by
``swap_vikunja_secrets.py`` (WP03), so this helper supports two
mutually-exclusive auth modes:

1. ``--kent-password-from-stdin`` (preferred) — operator pastes the kent
   password from 1Password on stdin. Helper POSTs ``/login`` to obtain a fresh
   JWT, then uses it for the revocation calls. The password is never echoed,
   never logged, and never stored.
2. ``--kent-token`` — if a residual kent token still exists, use it directly
   for the revocation calls. Skips the login step.

Behaviour
---------
The helper enumerates kent-owned tokens via ``GET /api/v1/tokens`` and deletes
each one via ``DELETE /api/v1/tokens/{id}``. If Vikunja v0.24.6 does not expose
these endpoints (``404`` on enumeration), the helper falls back to printing
step-by-step UI revocation instructions for the operator.

Invocation
----------

    # API path — password auth (most common; works after WP03 rotation)
    python3 scripts/vikunja/revoke_kent_tokens.py \\
        --kent-password-from-stdin

    # API path — residual token auth
    python3 scripts/vikunja/revoke_kent_tokens.py \\
        --kent-token "<token>"

    # UI fallback only — skip the API path and print operator instructions
    python3 scripts/vikunja/revoke_kent_tokens.py --ui-fallback-only

    # Dry-run — enumerate but do not delete
    python3 scripts/vikunja/revoke_kent_tokens.py \\
        --kent-password-from-stdin --dry-run

Exit codes
----------
    0 — kent has zero API tokens (goal achieved) OR all tokens revoked OR
        UI fallback instructions printed
    1 — operational error (auth rejected, delete failed, network error)
    2 — usage error (conflicting/missing auth flags)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1/"
HTTP_TIMEOUT_SECONDS = 30


class EndpointUnavailable(Exception):
    """Raised when Vikunja v0.24.6 does not expose the token API.

    Signals the caller to fall back to the UI revocation path.
    """


def _normalize_base_url(base_url: str) -> str:
    """Strip trailing slash for consistent URL composition."""
    return base_url.rstrip("/")


def _http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Issue an HTTP request via urllib. Returns (status_code, body_text).

    Never raises for non-2xx status — returns the status so callers can
    branch on it. Raises ``urllib.error.URLError`` for network failures.
    """
    data: bytes | None = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # urllib raises HTTPError for 4xx/5xx; we want the status, not an
        # exception, so callers can decide what to do.
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return exc.code, body_text


def obtain_kent_jwt(username: str, password: str, base_url: str) -> str:
    """POST /login with kent credentials; return the JWT.

    Exits 1 on 401 (bad credentials) or 5xx (service unavailable). Never
    logs or echoes the password or the JWT.
    """
    url = f"{_normalize_base_url(base_url)}/login"
    try:
        status, body = _http_request(
            "POST",
            url,
            body={"username": username, "password": password},
        )
    except urllib.error.URLError as exc:
        print(f"ERROR: network error during login: {exc}", file=sys.stderr)
        sys.exit(1)

    if status == 401:
        print(
            "ERROR: kent credentials rejected — verify password from 1Password",
            file=sys.stderr,
        )
        sys.exit(1)
    if status >= 500:
        print(
            f"ERROR: Vikunja login returned {status} — service unavailable",
            file=sys.stderr,
        )
        sys.exit(1)
    if status != 200:
        print(
            f"ERROR: unexpected status {status} from login endpoint",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print("ERROR: login response was not valid JSON", file=sys.stderr)
        sys.exit(1)

    token = payload.get("token")
    if not token or not isinstance(token, str):
        print("ERROR: login response did not contain a token", file=sys.stderr)
        sys.exit(1)
    return token


def enumerate_kent_tokens(
    auth_token: str,
    base_url: str,
    kent_username: str,
) -> list[dict[str, Any]]:
    """GET /tokens; return the list of kent-owned tokens.

    Raises ``EndpointUnavailable`` on 404 so the caller can fall back to UI.
    Exits 1 on 401 (auth failure) or other non-success status.
    """
    url = f"{_normalize_base_url(base_url)}/tokens"
    headers = {"Authorization": f"Bearer {auth_token}"}
    try:
        status, body = _http_request("GET", url, headers=headers)
    except urllib.error.URLError as exc:
        print(f"ERROR: network error during token enumeration: {exc}", file=sys.stderr)
        sys.exit(1)

    if status == 404:
        raise EndpointUnavailable(
            "GET /api/v1/tokens not available on this Vikunja version"
        )
    if status == 401:
        print(
            "ERROR: authentication rejected when enumerating tokens — JWT/token may be expired",
            file=sys.stderr,
        )
        sys.exit(1)
    if status != 200:
        print(
            f"ERROR: unexpected status {status} from token enumeration",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(
            "ERROR: token enumeration response was not valid JSON",
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(payload, list):
        print(
            "ERROR: token enumeration response was not a JSON array",
            file=sys.stderr,
        )
        sys.exit(1)

    # Filter to kent-owned tokens. Vikunja may return tokens scoped to the
    # caller already (the JWT/token is kent's), but we still filter defensively
    # on username when present.
    kent_tokens: list[dict[str, Any]] = []
    for tok in payload:
        if not isinstance(tok, dict):
            continue
        # If the token record carries owner metadata, only keep kent's. If it
        # does not (Vikunja already scoped the response), keep everything.
        owner = tok.get("created_by") or tok.get("owner") or {}
        owner_username = (
            owner.get("username") if isinstance(owner, dict) else None
        )
        if owner_username is not None and owner_username != kent_username:
            continue
        kent_tokens.append(tok)
    return kent_tokens


def delete_token(token_id: int, auth_token: str, base_url: str) -> bool:
    """DELETE /tokens/{id}. Return True on success, False if already gone.

    Exits 1 on any other failure status. A 404 in mid-sequence is tolerated
    (some other operator/automation may have deleted it concurrently).
    """
    url = f"{_normalize_base_url(base_url)}/tokens/{token_id}"
    headers = {"Authorization": f"Bearer {auth_token}"}
    try:
        status, _ = _http_request("DELETE", url, headers=headers)
    except urllib.error.URLError as exc:
        print(
            f"ERROR: network error deleting token {token_id}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if status in (200, 204):
        return True
    if status == 404:
        print(
            f"NOTE: token {token_id} already revoked (404) — continuing",
            file=sys.stderr,
        )
        return False
    if status == 401:
        print(
            f"ERROR: authentication rejected deleting token {token_id} — JWT may have expired mid-sequence",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"ERROR: delete token {token_id} returned status {status}",
        file=sys.stderr,
    )
    sys.exit(1)


def ui_fallback_instructions() -> None:
    """Print step-by-step UI revocation instructions for the operator."""
    print(
        "\n"
        "=== Manual UI revocation steps (Vikunja v0.24.6) ===\n"
        "\n"
        "The Vikunja token API is not available, or you passed\n"
        "--ui-fallback-only. Revoke kent's remaining API tokens via the UI:\n"
        "\n"
        "  1. Open https://office2.tail0f5f56.ts.net/ in a browser.\n"
        "  2. Log in as 'kent' using the password stored in 1Password.\n"
        "  3. Click your avatar (top-right) -> 'Settings'.\n"
        "  4. In the left-hand menu, click 'API Tokens'.\n"
        "  5. For every token in the list, click the trash icon and confirm\n"
        "     the deletion. Repeat until the list is empty.\n"
        "  6. Log out and close the browser tab.\n"
        "\n"
        "After completing the steps above, run:\n"
        "  python3 scripts/vikunja/revoke_kent_tokens.py \\\n"
        "      --kent-password-from-stdin\n"
        "again to confirm zero kent-owned tokens remain (SC-007).\n"
        "\n"
        "SUMMARY: ui_fallback_instructions printed (operator action required)"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Revoke kent's remaining Vikunja API tokens after the 7-day soak."
        ),
    )
    parser.add_argument(
        "--kent-username",
        default="kent",
        help="Vikunja username for kent (default: kent).",
    )
    parser.add_argument(
        "--kent-password-from-stdin",
        action="store_true",
        help=(
            "Read kent's password from stdin (no echo). Mutually exclusive "
            "with --kent-token."
        ),
    )
    parser.add_argument(
        "--kent-token",
        default=None,
        help=(
            "Residual kent API token (mutually exclusive with "
            "--kent-password-from-stdin)."
        ),
    )
    parser.add_argument(
        "--vikunja-base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vikunja API base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate tokens but do not delete; no destructive HTTP calls.",
    )
    parser.add_argument(
        "--ui-fallback-only",
        action="store_true",
        help=(
            "Skip the API path entirely; print UI revocation instructions "
            "and exit 0. Useful when the operator already knows the API "
            "endpoint is unavailable on this Vikunja version."
        ),
    )
    return parser


def _read_password_from_stdin() -> str:
    """Read a single line from stdin and strip the trailing newline.

    Used when the caller passes --kent-password-from-stdin. Never echoes the
    password (the caller is expected to pipe it in non-interactively, e.g.
    via 1Password's CLI).
    """
    password = sys.stdin.readline()
    if password.endswith("\n"):
        password = password[:-1]
    if not password:
        print(
            "ERROR: --kent-password-from-stdin set but stdin was empty",
            file=sys.stderr,
        )
        sys.exit(1)
    return password


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # --- UI-fallback-only short-circuit ---

    if args.ui_fallback_only:
        ui_fallback_instructions()
        return 0

    # --- Mutually-exclusive auth-mode check ---

    if args.kent_password_from_stdin and args.kent_token:
        print(
            "ERROR: --kent-password-from-stdin and --kent-token are mutually "
            "exclusive; pass exactly one",
            file=sys.stderr,
        )
        return 2
    if not args.kent_password_from_stdin and not args.kent_token:
        print(
            "ERROR: exactly one of --kent-password-from-stdin or --kent-token "
            "is required (use --ui-fallback-only to skip API entirely)",
            file=sys.stderr,
        )
        return 2

    # --- Dry-run short-circuit (MUST come before any network operation) ---
    #
    # T019 mandates that --dry-run performs ZERO network calls. We check
    # here, immediately after arg validation, so we never POST /login or
    # GET /tokens when --dry-run is set. This intentionally means dry-run
    # cannot report the actual number of tokens that would be revoked —
    # that would require a network call. Instead we describe the intended
    # actions based on the auth mode the operator selected.

    if args.dry_run:
        auth_mode = (
            "password (POST /login)"
            if args.kent_password_from_stdin
            else "residual token (no login)"
        )
        print(
            "DRY-RUN: no network calls will be made. Intended actions:\n"
            f"  1. Obtain kent JWT via {auth_mode}.\n"
            f"  2. GET {_normalize_base_url(args.vikunja_base_url)}/tokens "
            f"to enumerate kent-owned tokens (filter by username "
            f"{args.kent_username!r}).\n"
            f"  3. For each token, DELETE "
            f"{_normalize_base_url(args.vikunja_base_url)}/tokens/{{id}}.\n"
            "  4. Print SUMMARY with revoked/skipped counts."
        )
        print("SUMMARY: dry-run — no network calls issued; no changes made.")
        return 0

    # --- Obtain the auth token ---

    if args.kent_password_from_stdin:
        password = _read_password_from_stdin()
        auth_token = obtain_kent_jwt(
            args.kent_username, password, args.vikunja_base_url
        )
        # Drop the password reference immediately after use.
        del password
    else:
        auth_token = args.kent_token

    # --- Enumeration + per-token delete; UI fallback on 404 ---

    try:
        tokens = enumerate_kent_tokens(
            auth_token, args.vikunja_base_url, args.kent_username
        )
    except EndpointUnavailable:
        print(
            "API endpoint for token enumeration/deletion not available on "
            "this Vikunja version; falling back to UI instructions.",
            file=sys.stderr,
        )
        ui_fallback_instructions()
        return 0

    if not tokens:
        print(
            "SUMMARY: kent has zero API tokens — nothing to revoke. "
            "Goal achieved (SC-007)."
        )
        return 0

    revoked = 0
    skipped = 0
    for tok in tokens:
        token_id = tok.get("id")
        if not isinstance(token_id, int):
            print(
                f"WARN: skipping token with non-integer id: {token_id!r}",
                file=sys.stderr,
            )
            skipped += 1
            continue
        if delete_token(token_id, auth_token, args.vikunja_base_url):
            revoked += 1
        else:
            skipped += 1

    print(
        f"SUMMARY: revoked {revoked} kent API token(s); "
        f"{skipped} already-gone/skipped"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
