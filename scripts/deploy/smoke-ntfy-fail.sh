#!/usr/bin/env bash
# smoke-ntfy-fail.sh — deliberate-failure entrypoint for the
# felix-deployer-ntfy-failure-notifications-01KTZ76F (#595) post-merge
# smoke test.
#
# Behavior:
#   --dry-run  exit 0 (so the applier reaches the apply phase)
#   --apply    exit 1 (force the applier into the failure path so notify.py
#              dispatches an ntfy.sh push to the operator)
#
# This file ships ONLY to verify the production ntfy substrate works.
# Once the smoke succeeds, remove this script + the matching manifest
# under deploys/queued/ (or deploys/failed/ if it already failed) in a
# follow-up commit.
set -euo pipefail

case "${1:-}" in
  --dry-run)
    echo "smoke-ntfy-fail.sh: --dry-run OK (would fail on --apply for ntfy substrate verification)"
    exit 0
    ;;
  --apply)
    echo "smoke-ntfy-fail.sh: deliberate failure to verify ntfy.sh failure-notification substrate" >&2
    exit 1
    ;;
  *)
    echo "smoke-ntfy-fail.sh: unknown arg ${1:-(none)}" >&2
    exit 2
    ;;
esac
