#!/usr/bin/env python3
"""
One-time Google Calendar OAuth2 authorization script.
Reads client credentials from office2 credential store,
generates an authorization URL, and exchanges the code
for a refresh token stored in the credential store.

Run on office2 as the claude user:
  python3 scripts/google/authorize-calendar.py
"""

import json
import urllib.parse
import urllib.request
import urllib.error
import sys
import os

SECRETS_DIR = "/data/services/openclaw/secrets"
CLIENT_ID_FILE = os.path.join(SECRETS_DIR, "google-calendar-client-id")
CLIENT_SECRET_FILE = os.path.join(SECRETS_DIR, "google-calendar-client-secret")
REFRESH_TOKEN_FILE = os.path.join(SECRETS_DIR, "google-calendar-refresh-token")

SCOPE = "https://www.googleapis.com/auth/calendar"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost"  # Desktop app flow — code appears in URL bar


def read_secret(path):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"ERROR: Credential file not found: {path}")
        sys.exit(1)
    except PermissionError:
        print(f"ERROR: Cannot read credential file (permission denied): {path}")
        sys.exit(1)


def write_secret(path, value):
    with open(path, "w") as f:
        f.write(value)
    os.chmod(path, 0o600)


def main():
    print("=== Google Calendar OAuth2 Authorization ===\n")

    client_id = read_secret(CLIENT_ID_FILE)
    client_secret = read_secret(CLIENT_SECRET_FILE)

    # Build authorization URL
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # Force refresh token to be issued
    }
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("Step 1: Open this URL in your browser and sign in with the")
    print("Google account whose calendar you want Felix to access:\n")
    print(auth_url)
    print()
    print("Step 2: After approving access, your browser will redirect to a")
    print("page that won't load (http://localhost?code=...). That's expected.")
    print("Copy the ENTIRE URL from your browser's address bar and paste it here,")
    print("or just paste the 'code' parameter value.\n")

    raw = input("Paste URL or code: ").strip()
    # Extract code from full URL if pasted
    if raw.startswith("http"):
        parsed = urllib.parse.urlparse(raw)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            print("ERROR: Could not find 'code' parameter in the URL.")
            sys.exit(1)
    else:
        code = raw
    if not code:
        print("ERROR: No code entered.")
        sys.exit(1)

    # Exchange code for tokens
    print("\nExchanging code for tokens...")
    token_data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }).encode("utf-8")

    req = urllib.request.Request(TOKEN_URL, data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            token_response = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"ERROR: Token exchange failed (HTTP {e.code}): {error_body}")
        sys.exit(1)

    refresh_token = token_response.get("refresh_token")
    if not refresh_token:
        print("ERROR: No refresh token in response. This can happen if the account")
        print("was already authorized. Try revoking access at:")
        print("  https://myaccount.google.com/permissions")
        print("Then run this script again.")
        sys.exit(1)

    write_secret(REFRESH_TOKEN_FILE, refresh_token)
    print(f"\nRefresh token saved to {REFRESH_TOKEN_FILE}")
    print("Authorization complete. Felix can now access Google Calendar.")


if __name__ == "__main__":
    main()
