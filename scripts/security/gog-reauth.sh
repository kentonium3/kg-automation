#!/usr/bin/env bash
# gog-reauth.sh — automate the gog OAuth two-step re-authorization flow.
#
# Why this exists: run this to (re)mint or repair the gog refresh token after a
# revocation (password change, 6+ months inactivity, Google security review, or
# manual revocation at myaccount.google.com/permissions). The gog OAuth app is
# published ('In production'), so tokens stay valid until revoked — there is no
# fixed re-auth cycle. Refs: kentonium3/kg-automation#572 (original expiry bug)
# and #731 (removed once the app was published). Canonical procedure:
# docs/runbooks/google-workspace-ops.md.
#
# Two interactive steps remain (cannot be automated):
#   - Operator clicks through the Google consent screen in their Mac browser.
#   - Operator copy-pastes the redirect URL back to the script.
#
# Everything else (env-var setup, path resolution, services list, account email,
# verification, liveness probe) is handled here.
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

# ---- self-update -----------------------------------------------------------

# Pull latest before running. Prevents the trap where a fix to this very
# script (e.g., the `cut -d= -f2-` fix in acc4c4da) doesn't take effect on
# the FIRST re-auth because the previous version was on disk at invocation
# time. Without this, operators silently keep running stale versions.
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -d "${REPO_ROOT}/.git" ]]; then
  echo "==> Pulling latest gog-reauth.sh from main..."
  git -C "${REPO_ROOT}" fetch origin main --quiet
  git -C "${REPO_ROOT}" pull --ff-only origin main
  # Re-exec the (potentially updated) script so any changes apply to THIS run.
  if [[ -z "${GOG_REAUTH_REEXECED:-}" ]]; then
    export GOG_REAUTH_REEXECED=1
    exec "${BASH_SOURCE[0]}" "$@"
  fi
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
    3. If "Google hasn't verified this app" appears → click Advanced → Continue.
    4. Grant the personal-data scopes. The consent screen expands the requested
       services into ~10 checkboxes: Google Drive; "Other contacts"; Contacts;
       Docs; Sheets; Calendar; and the three Gmail scopes (settings, filters,
       read/compose/send). Check those, then Continue.
         • LEAVE UNCHECKED the box "See and download your organization's Google
           Workspace directory" unless you specifically want Felix to read your
           org directory. Declining it does NOT break the token (gog's 'contacts'
           service is why that box appears). See kentonium3/kg-automation#731.
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

cat <<EOF

==> gog-reauth complete.
    The gog OAuth app is published ('In production'), so the token does not
    expire on a fixed cycle — it stays valid until revoked (password change,
    6+ months inactivity, Google security review, or manual revocation). Only
    re-run this script after such a revocation.
    See: docs/runbooks/google-workspace-ops.md + kentonium3/kg-automation#731.
EOF
