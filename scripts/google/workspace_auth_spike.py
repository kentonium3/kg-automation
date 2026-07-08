#!/usr/bin/env python3
"""RFC #681 Q1 auth spike — prove Felix can reach Google Calendar directly.

SPIKE, NOT PRODUCTION. This validates the Internal-app OAuth path decided in
docs/design/research/felix-workspace-api-vs-gog-681.md (D1). It is intentionally
self-contained and dependency-light so Kent can run it on the Mac.

What it proves:
  Stage A  — OAuth (Internal app) -> refresh token -> create+read an event on
             the AUTHORIZING account's own primary calendar.  (SC-A)
  Stage B  — create an event on a SHARED calendar owned by another account
             (kentgale@gmail.com), from the in-org token.      (SC-B)
             This is the cross-account bridge that lets an intentional.biz
             identity drive the personal calendar -> removes gog from that path.
  --refresh-only — load the saved token and force a refresh grant. Re-run daily
             past day 7; if it still succeeds (no invalid_grant) the Internal-app
             token is long-lived.                              (SC-F6)

Prereqs (Mac, one-time):
  python3 -m venv /tmp/felix-gspike && source /tmp/felix-gspike/bin/activate
  pip install google-api-python-client google-auth-oauthlib

Then follow docs/design/research/felix-workspace-api-vs-gog-681.md runbook to
obtain client_secret.json (Desktop-app OAuth client on an Internal app).

Credentials home: ~/.config/felix/ (0700), override with FELIX_GOOGLE_DIR.
Place client_secret.json there and --client-secret becomes optional. The minted
token.json is written there too — never in ~/Downloads (macOS TCC blocks CLI
reads) or /tmp (world-readable + wiped on reboot).

Usage:
  # one-time: mkdir -p ~/.config/felix && mv client_secret.json ~/.config/felix/
  python workspace_auth_spike.py --stage a
  python workspace_auth_spike.py --stage b --target-calendar kentgale@gmail.com
  python workspace_auth_spike.py --refresh-only

Nothing here is destructive: created events are tagged and can be deleted with
--cleanup. No secrets are printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    sys.exit(
        "Missing deps. In a venv run:\n"
        "  pip install google-api-python-client google-auth-oauthlib"
    )

# Least-privilege for the calendar proof. Add more scopes per phase later.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
# Credentials live in a user-only dir OUTSIDE any git repo (override w/ FELIX_GOOGLE_DIR).
# Never ~/Downloads (macOS TCC blocks CLI reads) or /tmp (world-readable + wiped on reboot).
SECRETS_DIR = Path(os.environ.get("FELIX_GOOGLE_DIR", Path.home() / ".config" / "felix"))
TOKEN_PATH = SECRETS_DIR / "token.json"
DEFAULT_CLIENT_SECRET = SECRETS_DIR / "client_secret.json"
EVENT_TAG = "[felix-681-spike]"


def _write_token(creds: Credentials) -> None:
    """Persist the token to the user-only secrets dir (0700 dir, 0600 file)."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_DIR.chmod(0o700)
    TOKEN_PATH.write_text(creds.to_json())
    TOKEN_PATH.chmod(0o600)


def _load_or_mint(client_secret: Path | None) -> Credentials:
    """Return valid Credentials, refreshing or running the consent flow."""
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())  # exercises the refresh grant (F6 check)
        _write_token(creds)
        return creds
    if not client_secret and DEFAULT_CLIENT_SECRET.exists():
        client_secret = DEFAULT_CLIENT_SECRET  # default home, no flag needed
    if not client_secret:
        sys.exit(
            f"No usable {TOKEN_PATH} and no client_secret to mint one. "
            f"Pass --client-secret or place it at {DEFAULT_CLIENT_SECRET}, "
            "then run stage a first."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    # Loopback consent on the Mac; access_type=offline to get a refresh token.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _write_token(creds)
    return creds


def _create_and_read(service, calendar_id: str) -> str:
    start = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    end = start + dt.timedelta(minutes=30)
    body = {
        "summary": f"{EVENT_TAG} auth spike",
        "description": "RFC #681 Q1 spike — safe to delete.",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    created = service.events().insert(calendarId=calendar_id, body=body).execute()
    eid = created["id"]
    got = service.events().get(calendarId=calendar_id, eventId=eid).execute()
    print(f"  created event id={eid}")
    print(f"  read back summary={got.get('summary')!r} link={got.get('htmlLink')}")
    return eid


def _cleanup(service, calendar_id: str) -> None:
    resp = service.events().list(
        calendarId=calendar_id, q=EVENT_TAG, maxResults=50
    ).execute()
    for ev in resp.get("items", []):
        service.events().delete(calendarId=calendar_id, eventId=ev["id"]).execute()
        print(f"  deleted {ev['id']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="RFC #681 Google Calendar auth spike")
    ap.add_argument("--client-secret", type=Path, help="Desktop-app client_secret.json")
    ap.add_argument("--stage", choices=["a", "b"], help="a=own calendar, b=shared target")
    ap.add_argument("--target-calendar", default="primary",
                    help="calendar id for stage b (e.g. kentgale@gmail.com)")
    ap.add_argument("--refresh-only", action="store_true",
                    help="load token.json, force a refresh grant, report (F6 check)")
    ap.add_argument("--cleanup", action="store_true", help="delete spike-tagged events")
    args = ap.parse_args()

    if args.refresh_only:
        creds = _load_or_mint(None)
        # _load_or_mint already refreshed if expired; force one regardless.
        creds.refresh(Request())
        _write_token(creds)
        print("SC-F6 OK: refresh grant succeeded — token still valid "
              f"({dt.datetime.now(dt.timezone.utc).isoformat()}).")
        return 0

    if not args.stage:
        ap.error("one of --stage {a,b} or --refresh-only is required")

    creds = _load_or_mint(args.client_secret)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    calendar_id = "primary" if args.stage == "a" else args.target_calendar

    if args.cleanup:
        print(f"cleanup on {calendar_id}:")
        _cleanup(service, calendar_id)
        return 0

    print(f"Stage {args.stage.upper()} — calendar={calendar_id}")
    _create_and_read(service, calendar_id)
    print(f"SC-{'A' if args.stage == 'a' else 'B'} OK. "
          f"Refresh token saved to {TOKEN_PATH} "
          f"(refresh_token present={'refresh_token' in TOKEN_PATH.read_text()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
