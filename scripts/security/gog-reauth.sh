#!/usr/bin/env bash
# gog-reauth.sh — automate the gog OAuth two-step re-authorization flow.
#
# Why this exists: the OAuth app is in External + Testing publishing status,
# so Google issues refresh tokens with a hard 7-day expiration. Every ~week
# this script needs to be run to re-mint the refresh token. Tracking issue:
# kentonium3/kg-automation#572. Canonical procedure:
# docs/runbooks/google-workspace-ops.md §2.8.
#
# Two interactive steps remain (cannot be automated):
#   - Operator clicks through the Google consent screen in their Mac browser.
#   - Operator copy-pastes the redirect URL back to the script.
#
# Everything else (env-var setup, path resolution, services list, account email,
# verification, liveness probe, next-due-date) is handled here.
#
# Usage (on office2 as the claude user):
#   /home/claude/kg-automation/scripts/security/gog-reauth.sh
#
# From Mac (one-shot, no manual ssh first):
#   ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh

set -euo pipefail

ACCOUNT="kentgale@gmail.com"
SERVICES="gmail,calendar,drive,contacts,docs,sheets"
GOG_BIN="/home/linuxbrew/.linuxbrew/bin/gog"
ENV_FILE="/data/services/openclaw/secrets/openclaw-gateway.env"

# ---- argv ------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --account) ACCOUNT="$2"; shift 2;;
    --services) SERVICES="$2"; shift 2;;
    -h|--help)
      cat <<EOF
Usage: $0 [--account EMAIL] [--services SVC,SVC,...]

Wraps the gog two-step OAuth re-auth flow (\`gog auth add ... --remote\`).

  --account   Google account email (default: $ACCOUNT)
  --services  Comma-separated services (default: $SERVICES)

Runs entirely as the claude user. Requires interactive TTY.
EOF
      exit 0;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2;;
  esac
done

# ---- preconditions ---------------------------------------------------------

if [[ ! -x "$GOG_BIN" ]]; then
  echo "ERROR: gog not found at $GOG_BIN" >&2
  exit 1
fi

if [[ ! -r "$ENV_FILE" ]]; then
  echo "ERROR: cannot read keyring-password env file at $ENV_FILE" >&2
  exit 1
fi

if [[ ! -t 0 ]]; then
  echo "ERROR: stdin is not a TTY — the redirect-URL prompt needs a real terminal." >&2
  echo "       From Mac, invoke with: ssh -t office2-claude $0" >&2
  exit 1
fi

# ---- env setup -------------------------------------------------------------

# The keyring password lives in the openclaw-gateway env file (single source
# of truth). Pulled inline so the script has no hard-coded secret.
GOG_KEYRING_PASSWORD="$(grep ^GOG_KEYRING_PASSWORD "$ENV_FILE" | cut -d= -f2-)"
if [[ -z "$GOG_KEYRING_PASSWORD" ]]; then
  echo "ERROR: GOG_KEYRING_PASSWORD missing from $ENV_FILE" >&2
  exit 1
fi
export GOG_KEYRING_BACKEND=file
export GOG_KEYRING_PASSWORD

# ---- step 1: print the authorization URL -----------------------------------

echo "==> gog-reauth"
echo "    account:  $ACCOUNT"
echo "    services: $SERVICES"
echo
echo "==> Step 1: requesting OAuth authorization URL..."
echo
"$GOG_BIN" auth add "$ACCOUNT" --services "$SERVICES" --remote

# ---- operator browser consent ---------------------------------------------

cat <<EOF

==> Browser-side steps:
    1. Open the URL above in your Mac browser.
    2. Sign in as $ACCOUNT.
    3. "Google hasn't verified this app" → click Advanced → Continue (unsafe).
    4. Check ALL six scope boxes (Gmail, Calendar, Drive, Contacts,
       Sheets, Docs), then Continue.
    5. You will land on http://localhost:...?state=...&code=... showing
       a "site can't be reached" page — that is expected.

==> Paste the full URL from the browser address bar below, then press Enter:
EOF
read -r REDIRECT_URL

if [[ -z "$REDIRECT_URL" ]]; then
  echo "ERROR: empty redirect URL — aborting." >&2
  exit 1
fi

# ---- step 2: exchange code for refresh token -------------------------------

echo
echo "==> Step 2: exchanging code for refresh token..."
"$GOG_BIN" auth add "$ACCOUNT" --remote --step 2 \
  --auth-url "$REDIRECT_URL" --services "$SERVICES"

# ---- verify ----------------------------------------------------------------

echo
echo "==> Registered accounts:"
"$GOG_BIN" auth list

echo
echo "==> Liveness probe (calendar list)..."
if "$GOG_BIN" --account "$ACCOUNT" calendar list -j >/dev/null 2>&1; then
  echo "OK: gog calendar API is live for $ACCOUNT"
else
  echo "ERROR: liveness probe failed — refresh token may not be saved correctly." >&2
  exit 1
fi

# ---- closing summary -------------------------------------------------------

NEXT_DUE="$(date -u -d '+7 days' '+%Y-%m-%d')"
cat <<EOF

==> gog-reauth complete.
    Next forced re-auth: ~$NEXT_DUE (External+Testing OAuth app 7-day cycle).
    Eliminate the cycle: publish the OAuth app or migrate to a Workspace-internal app.
    See: docs/runbooks/google-workspace-ops.md §2.4 + #572.
EOF
