#!/usr/bin/env python3
"""Provision the felix-bot Vikunja user — ADR-0002 Phase 1 (issue #304).

This helper is the first-phase operator-driven helper for the
felix-bot-vikunja-provisioning mission. It:

1. Verifies kent's existing Vikunja API token is present and mode 600
   (identity gate).
2. Registers a new Vikunja user `felix-bot` via POST /api/v1/register.
3. Enumerates the 12 real Vikunja projects via GET /api/v1/projects
   (filters `id > 0 AND is_archived != True`).
4. Shares each real project with felix-bot at read/write (right=1) via
   PUT /api/v1/projects/{id}/users.
5. Verifies each share was applied by reading back the share list via
   GET /api/v1/projects/{id}/users.
6. Captures the operator-supplied felix-bot API token (operator pastes
   on stdin after generating in the Vikunja UI as felix-bot) and writes
   it to --token-output-file with mode 600 set BEFORE the file is
   closed (no permission-window race).

This helper authenticates to Vikunja using kent's still-active API
token (the secrets-file rotation does not happen until WP03/Phase 1.5).
It is invoked exactly once during the provisioning run-book on office2.
No callers other than the run-book exist; the helper is operator-driven
per research finding R-006.

Invocation:

    python3 scripts/vikunja/provision_felix_bot.py \\
        --username felix-bot \\
        --email kentgale+felix-bot@gmail.com \\
        --password-from-stdin \\
        --kent-token-file /data/services/openclaw/secrets/vikunja-api \\
        --token-output-file /data/services/openclaw/secrets/felix-bot-token.new \\
        [--vikunja-base-url https://office2.tail0f5f56.ts.net/api/v1/] \\
        [--dry-run]

Stdin protocol (when --password-from-stdin is set):

    First line: the felix-bot password (from 1Password)
    Second line: the felix-bot API token (operator generates via UI
                 after registration succeeds)

The helper prints separator markers prompting the operator before
reading each line.

Output (stdout):

    Per-project SUMMARY lines as each share applies and verifies.
    Final line:
        SUMMARY: felix-bot registered (uid=<N>), 12 projects shared, \\
            token captured to <path>

Exit codes:
    0 — provisioning succeeded (or --dry-run preview rendered)
    1 — operational error (HTTP failure, share rejected, verification
        mismatch, token write failure)
    2 — usage error (missing args, identity gate fails, empty stdin)

API contracts: see kitty-specs/felix-bot-vikunja-provisioning-01KRT3N4/
contracts/vikunja-api-endpoints.md sections C-1, C-2, C-3, C-4, C-5.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from scripts.common.vikunja_config import get_vikunja_base_url


#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_BASE_URL: str = ""
DEFAULT_USERNAME = "felix-bot"
DEFAULT_EMAIL = "kentgale+felix-bot@gmail.com"
SHARE_RIGHT_READ_WRITE = 1  # per ADR-0002 Q3 / spec C-004
EXPECTED_REAL_PROJECT_COUNT = 12
HTTP_TIMEOUT_SECONDS = 30
MIN_TOKEN_LENGTH = 20


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Provision the felix-bot Vikunja user: register, share 12 "
            "projects, capture API token. ADR-0002 Phase 1."
        ),
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help=f"Vikunja username for the new user (default: {DEFAULT_USERNAME})",
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Registration email (default: {DEFAULT_EMAIL})",
    )
    parser.add_argument(
        "--password-from-stdin",
        action="store_true",
        help=(
            "Read the felix-bot password from stdin (first line, no echo "
            "expected — the operator pastes from 1Password)."
        ),
    )
    parser.add_argument(
        "--kent-token-file",
        type=Path,
        required=True,
        help=(
            "Path to a file containing kent's existing Vikunja API token. "
            "Must exist and be mode 600. Identity gate."
        ),
    )
    parser.add_argument(
        "--token-output-file",
        type=Path,
        required=True,
        help=(
            "Path where the captured felix-bot API token will be written "
            "(mode 600 set BEFORE close)."
        ),
    )
    parser.add_argument(
        "--vikunja-base-url",
        default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform no network calls and no token writes; print plan only.",
    )
    parser.add_argument(
        "--felix-bot-user-id",
        type=int,
        default=None,
        help=(
            "Skip registration and proceed directly to project sharing using "
            "the supplied existing felix-bot user_id. Used to recover from a "
            "partial Phase 1 run where registration succeeded but a later "
            "step failed."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Identity gate
# ---------------------------------------------------------------------------


def identity_gate(kent_token_file: Path) -> str:
    """Verify --kent-token-file exists, is mode 600, and is non-empty.

    Returns the token content (stripped). Exits 2 on failure.
    """
    if not kent_token_file.exists():
        print(
            f"ERROR: kent token file not readable: {kent_token_file} (does not exist)",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        st = kent_token_file.stat()
    except PermissionError:
        print(
            f"ERROR: kent token file not readable: {kent_token_file} (permission denied)",
            file=sys.stderr,
        )
        sys.exit(2)
    if not stat.S_ISREG(st.st_mode):
        print(
            f"ERROR: kent token file not a regular file: {kent_token_file}",
            file=sys.stderr,
        )
        sys.exit(2)
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        print(
            f"ERROR: kent token file has unsafe mode {oct(mode)} "
            f"(expected 0o600): {kent_token_file}",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        content = kent_token_file.read_text(encoding="utf-8").strip()
    except PermissionError:
        print(
            f"ERROR: kent token file not readable: {kent_token_file} (permission denied on read)",
            file=sys.stderr,
        )
        sys.exit(2)
    if not content:
        print(
            f"ERROR: kent token file is empty: {kent_token_file}",
            file=sys.stderr,
        )
        sys.exit(2)
    return content


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    bearer_token: str | None = None,
) -> tuple[int, Any, str]:
    """Issue an HTTP request via urllib. Returns (status, parsed_json, raw_text).

    parsed_json is None if the body is empty or not JSON-decodable.
    raw_text is always provided for error reporting.
    On network/URL errors, raises urllib.error.URLError to the caller.
    """
    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
    try:
        parsed = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed, raw


# ---------------------------------------------------------------------------
# Step 1: Registration (C-1)
# ---------------------------------------------------------------------------


def register_felix_bot(
    username: str,
    email: str,
    password: str,
    base_url: str,
    *,
    dry_run: bool,
) -> dict:
    """Register a new user via POST /register. Returns dict with at least
    {"user_id": int, "username": str}. Exits 1 on failure."""
    if dry_run:
        print(
            f"DRY-RUN: would POST {_join_url(base_url, 'register')} "
            f"username={username!r} email={email!r} password=<redacted>",
            file=sys.stderr,
        )
        return {"user_id": 99999, "username": username, "dry_run": True}

    url = _join_url(base_url, "register")
    body = {"username": username, "email": email, "password": password}
    try:
        status, parsed, raw = _http_request("POST", url, body=body)
    except urllib.error.URLError as e:
        print(f"ERROR: network failure on POST /register: {e}", file=sys.stderr)
        sys.exit(1)

    if status in (200, 201):
        if not isinstance(parsed, dict):
            print(
                f"ERROR: POST /register returned 2xx but body was not a JSON object: {raw!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        user_id = parsed.get("id")
        if not isinstance(user_id, int):
            print(
                f"ERROR: POST /register response missing integer 'id' field: {parsed!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        return {"user_id": user_id, "username": username, "raw": parsed}

    if status == 400:
        print(
            f"ERROR: Vikunja rejected registration (HTTP 400): {raw}",
            file=sys.stderr,
        )
        sys.exit(1)
    if status == 409:
        print(
            f"ERROR: Vikunja registration conflict (HTTP 409). "
            f"User {username!r} may already exist from a prior attempt. "
            f"Investigate before retrying. Body: {raw}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"ERROR: POST /register returned unexpected HTTP {status}: {raw}",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 2: Enumerate real projects (C-2)
# ---------------------------------------------------------------------------


def enumerate_real_projects(
    base_url: str,
    kent_token: str,
    *,
    dry_run: bool,
) -> list[dict]:
    """GET /projects and filter to real projects (id > 0, not archived).

    Returns a list of {"id": int, "title": str}. Exits 1 on HTTP failure or
    when the count is below the expected minimum.
    """
    if dry_run:
        print(
            f"DRY-RUN: would GET {_join_url(base_url, 'projects?per_page=50')} "
            f"with kent token; mocking 12 real projects.",
            file=sys.stderr,
        )
        return [{"id": pid, "title": f"DRY Project {pid}"} for pid in [1, 2] + list(range(4, 14))]

    url = _join_url(base_url, "projects?per_page=50")
    try:
        status, parsed, raw = _http_request("GET", url, bearer_token=kent_token)
    except urllib.error.URLError as e:
        print(f"ERROR: network failure on GET /projects: {e}", file=sys.stderr)
        sys.exit(1)

    if status != 200:
        print(
            f"ERROR: GET /projects returned HTTP {status}: {raw}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(parsed, list):
        print(
            f"ERROR: GET /projects body was not a JSON array: {raw!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    real: list[dict] = []
    for proj in parsed:
        if not isinstance(proj, dict):
            continue
        pid = proj.get("id")
        is_archived = proj.get("is_archived", False)
        title = proj.get("title", "")
        if isinstance(pid, int) and pid > 0 and not is_archived:
            real.append({"id": pid, "title": title})

    if len(real) < EXPECTED_REAL_PROJECT_COUNT:
        print(
            f"ERROR: expected ≥ {EXPECTED_REAL_PROJECT_COUNT} real projects, "
            f"found {len(real)}. Vikunja state may have changed since spec was "
            f"written. Investigate before proceeding. Projects: {real!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(real) > EXPECTED_REAL_PROJECT_COUNT:
        print(
            f"WARN: found {len(real)} real projects (expected "
            f"{EXPECTED_REAL_PROJECT_COUNT}). A project was added since the "
            f"spec was written. Sharing all of them with felix-bot.",
            file=sys.stderr,
        )

    return real


# ---------------------------------------------------------------------------
# Step 3: Share each project (C-3)
# ---------------------------------------------------------------------------


def share_project_with_user(
    project_id: int,
    project_title: str,
    username: str,
    base_url: str,
    kent_token: str,
    *,
    dry_run: bool,
) -> bool:
    """PUT /projects/{id}/users with {"user_id": <username>, "right": 1}.

    The `user_id` field in the request body takes the target user's USERNAME
    string, not the numeric user id (see body comment below).

    Returns True on success or treats 409 (already shared) as success.
    Exits 1 on 403 (kent lacks admin) or 5xx/network error.
    """
    if dry_run:
        print(
            f"DRY-RUN: would PUT {_join_url(base_url, f'projects/{project_id}/users')} "
            f"body={{user_id:{username!r}, right:{SHARE_RIGHT_READ_WRITE}}} "
            f"(project #{project_id} '{project_title}')",
            file=sys.stderr,
        )
        return True

    url = _join_url(base_url, f"projects/{project_id}/users")
    # Vikunja v0.24.6 PUT /projects/{id}/users semantics (observed 2026-05-17
    # against the live office2 instance):
    # - The `user_id` field name is a misnomer — it expects the target user's
    #   USERNAME string, not the numeric user id.
    # - Passing the numeric id (even as a string like "2") returns
    #   {"code":1005,"message":"The user does not exist."} because no user is
    #   named "2".
    # - Passing the username ("felix-bot") succeeds and the create-response
    #   echoes user_id back as the username.
    body = {"user_id": username, "right": SHARE_RIGHT_READ_WRITE}
    try:
        status, parsed, raw = _http_request(
            "PUT", url, body=body, bearer_token=kent_token
        )
    except urllib.error.URLError as e:
        print(
            f"ERROR: network failure sharing project #{project_id} "
            f"'{project_title}': {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    if status in (200, 201):
        return True
    if status == 409:
        # Treat as success: share already exists from a prior partial run.
        print(
            f"NOTE: project #{project_id} '{project_title}' was already shared "
            f"(HTTP 409); treating as success.",
            file=sys.stderr,
        )
        return True
    if status == 403:
        print(
            f"ERROR: kent's token lacks admin on project #{project_id} "
            f"'{project_title}' (HTTP 403). Cannot share this project. "
            f"Body: {raw}",
            file=sys.stderr,
        )
        sys.exit(1)
    if status == 404:
        print(
            f"ERROR: project #{project_id} '{project_title}' not found "
            f"(HTTP 404). Enumeration may be stale. Body: {raw}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"ERROR: PUT /projects/{project_id}/users returned unexpected "
        f"HTTP {status} for '{project_title}': {raw}",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 4: Verify shares applied (C-4)
# ---------------------------------------------------------------------------


def verify_shares_applied(
    projects: list[dict],
    felix_bot_username: str,
    base_url: str,
    kent_token: str,
    *,
    dry_run: bool,
) -> dict:
    """For each project, GET /projects/{id}/users and confirm felix-bot is
    present with right=1. Matches each share entry by `username` field — in
    Vikunja v0.24.6 the GET response returns USER objects with `id`, `name`,
    `username`, ..., plus `right`. There is NO `user_id` field in this
    response (the LIST shape differs from the share-CREATE response).
    Returns {"verified": [...], "missing": [...]}.
    Exits 1 if any project is missing the felix-bot grant.
    """
    if dry_run:
        return {"verified": [p["id"] for p in projects], "missing": []}

    verified: list[int] = []
    missing: list[int] = []
    for proj in projects:
        pid = proj["id"]
        url = _join_url(base_url, f"projects/{pid}/users")
        try:
            status, parsed, raw = _http_request(
                "GET", url, bearer_token=kent_token
            )
        except urllib.error.URLError as e:
            print(
                f"ERROR: network failure verifying project #{pid}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)
        if status != 200:
            print(
                f"ERROR: GET /projects/{pid}/users returned HTTP {status}: {raw}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not isinstance(parsed, list):
            print(
                f"ERROR: GET /projects/{pid}/users body was not a JSON array: {raw!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        present = False
        for share in parsed:
            if not isinstance(share, dict):
                continue
            if share.get("username") == felix_bot_username and share.get("right") == SHARE_RIGHT_READ_WRITE:
                present = True
                break
        if present:
            verified.append(pid)
        else:
            missing.append(pid)

    if missing:
        print(
            f"ERROR: post-share verification failed. felix-bot "
            f"(username={felix_bot_username!r}) is missing from the following "
            f"project share lists: {missing}. Investigate before capturing "
            f"the token.",
            file=sys.stderr,
        )
        sys.exit(1)

    return {"verified": verified, "missing": missing}


# ---------------------------------------------------------------------------
# Step 5: Capture operator-supplied API token (C-5)
# ---------------------------------------------------------------------------


def _is_plausible_token(token: str) -> bool:
    if len(token) < MIN_TOKEN_LENGTH:
        return False
    # All bytes printable ASCII (no embedded NULs, control chars, or whitespace inside).
    for ch in token:
        if not (0x21 <= ord(ch) <= 0x7E):
            return False
    return True


def capture_felix_bot_token(
    token_output_file: Path,
    stdin_source,
    *,
    dry_run: bool,
) -> str:
    """Read a token from stdin (one line), validate, and write to
    token_output_file with mode 600 BEFORE close.

    Returns the captured token. Exits 2 if stdin is empty or token is
    implausible. Exits 1 on file-write failure.
    """
    print(
        "\nINSTRUCTIONS: Open the Vikunja UI at "
        "https://office2.tail0f5f56.ts.net/, log in as felix-bot with the "
        "password from 1Password, navigate to Settings → API Tokens, and "
        "generate a new token (no expiry, full scope, name "
        "'felix-provisioning-<date>'). Paste the token now and press Enter.",
        file=sys.stderr,
    )
    raw_line = stdin_source.readline()
    token = raw_line.rstrip("\r\n").strip()
    if not token:
        print(
            "ERROR: empty stdin — operator did not provide a token.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not _is_plausible_token(token):
        print(
            f"ERROR: token does not look plausible (length "
            f"{len(token)} < {MIN_TOKEN_LENGTH} or contains non-printable "
            f"characters).",
            file=sys.stderr,
        )
        sys.exit(2)

    if dry_run:
        print(
            f"DRY-RUN: would write token (length {len(token)}) to "
            f"{token_output_file} with mode 600.",
            file=sys.stderr,
        )
        return token

    # Write atomically: create with mode 600 BEFORE writing content, write,
    # fsync, close, then rename. This guarantees there is no window where
    # the file is world-readable.
    try:
        token_output_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"ERROR: could not create parent directory for "
            f"{token_output_file}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    tmp_path = token_output_file.with_name(token_output_file.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    try:
        fd = os.open(str(tmp_path), flags, 0o600)
    except OSError as e:
        print(
            f"ERROR: could not open {tmp_path} for writing: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        # Explicit chmod in case the open() mode was masked by umask.
        os.fchmod(fd, 0o600)
        os.write(fd, token.encode("utf-8"))
        os.write(fd, b"\n")
        os.fsync(fd)
    except OSError as e:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp_path.unlink()
        except OSError:
            pass
        print(
            f"ERROR: could not write token to {tmp_path}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.replace(str(tmp_path), str(token_output_file))
    except OSError as e:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        print(
            f"ERROR: could not rename {tmp_path} → {token_output_file}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    # Belt-and-suspenders: re-assert mode on the final path.
    try:
        os.chmod(str(token_output_file), 0o600)
    except OSError as e:
        print(
            f"ERROR: could not enforce mode 600 on {token_output_file}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    args.vikunja_base_url = args.vikunja_base_url or get_vikunja_base_url()

    # --- Identity gate ---
    kent_token = identity_gate(args.kent_token_file)

    # --- Read password from stdin (if requested) ---
    # --- Register felix-bot (or skip if --felix-bot-user-id provided) ---
    if args.felix_bot_user_id is not None:
        felix_bot_uid = args.felix_bot_user_id
        print(
            f"SUMMARY: skipping registration; using existing felix-bot "
            f"uid={felix_bot_uid} (per --felix-bot-user-id)",
            file=sys.stderr,
        )
    else:
        password: str
        if args.password_from_stdin:
            print(
                "\nPaste the felix-bot password (from 1Password) and press Enter:",
                file=sys.stderr,
            )
            first_line = sys.stdin.readline()
            password = first_line.rstrip("\r\n")
            if not password:
                print(
                    "ERROR: empty password on stdin — operator did not provide a password.",
                    file=sys.stderr,
                )
                return 2
        else:
            # In dry-run we do not need a real password; supply a placeholder
            # so registration's body construction has a value to log.
            if not args.dry_run:
                print(
                    "ERROR: --password-from-stdin is required when not in --dry-run.",
                    file=sys.stderr,
                )
                return 2
            password = "<DRY-RUN-PLACEHOLDER>"

        reg = register_felix_bot(
            username=args.username,
            email=args.email,
            password=password,
            base_url=args.vikunja_base_url,
            dry_run=args.dry_run,
        )
        felix_bot_uid = reg["user_id"]
        print(
            f"SUMMARY: registered felix-bot uid={felix_bot_uid} "
            f"username={args.username!r}",
            file=sys.stderr,
        )

    # --- Enumerate real projects ---
    projects = enumerate_real_projects(
        base_url=args.vikunja_base_url,
        kent_token=kent_token,
        dry_run=args.dry_run,
    )
    print(
        f"SUMMARY: enumerated {len(projects)} real projects.",
        file=sys.stderr,
    )

    # --- Share each project ---
    shared: list[int] = []
    for proj in projects:
        ok = share_project_with_user(
            project_id=proj["id"],
            project_title=proj["title"],
            username=args.username,
            base_url=args.vikunja_base_url,
            kent_token=kent_token,
            dry_run=args.dry_run,
        )
        if ok:
            shared.append(proj["id"])
            print(
                f"SUMMARY: shared project #{proj['id']} '{proj['title']}' "
                f"with felix-bot at right={SHARE_RIGHT_READ_WRITE}.",
                file=sys.stderr,
            )

    # --- Verify shares applied ---
    verify = verify_shares_applied(
        projects=projects,
        felix_bot_username=args.username,
        base_url=args.vikunja_base_url,
        kent_token=kent_token,
        dry_run=args.dry_run,
    )
    print(
        f"SUMMARY: verified {len(verify['verified'])} share grants, "
        f"{len(verify['missing'])} missing.",
        file=sys.stderr,
    )

    # --- Capture felix-bot token ---
    token = capture_felix_bot_token(
        token_output_file=args.token_output_file,
        stdin_source=sys.stdin,
        dry_run=args.dry_run,
    )

    # --- Final structured output ---
    output = {
        "user_id": felix_bot_uid,
        "username": args.username,
        "projects_shared": shared,
        "projects_verified": verify["verified"],
        "token_output_file": str(args.token_output_file),
        "token_length": len(token),
        "dry_run": args.dry_run,
    }
    print(json.dumps(output))
    print(
        f"SUMMARY: felix-bot registered (uid={felix_bot_uid}), "
        f"{len(shared)} projects shared, token captured to "
        f"{args.token_output_file}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
