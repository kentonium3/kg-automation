#!/usr/bin/env bash
# felix-alert bus — bash shim.
#
# At the shell boundary: sources the topic env-file if present, env-anchors to
# the checkout, and invokes the CLI. Exit-code policy:
#   * A plain best-effort `emit` ALWAYS exits 0 so cron/audit callers never fail
#     on a delivery hiccup.
#   * A `self-test` subcommand OR any `--strict` emit propagates the CLI's real
#     exit code, so callers that need a hard delivery signal (e.g. the deploy
#     entrypoint's self-test) get it directly through the shim.
#
# NOT `set -e`: a best-effort delivery failure must not abort the caller.
set -uo pipefail

# Source the single topic env-file if present. This is what lets a
# cron-launched audit.sh (no systemd EnvironmentFile) resolve the topic.
if [ -f /home/claude/.config/felix/alert-bus/env ]; then
  # shellcheck disable=SC1091
  . /home/claude/.config/felix/alert-bus/env
fi

# Decide the exit-code policy from the args BEFORE invoking: self-test or a
# --strict emit must surface the CLI's real exit code; everything else is
# best-effort (exit 0).
propagate_rc=0
for arg in "$@"; do
  if [ "$arg" = "self-test" ] || [ "$arg" = "--strict" ]; then
    propagate_rc=1
    break
  fi
done

# Proven checkout-cd form (#658): office2 has only `python3`, never bare
# `python`. Invoking as `-m` keeps the `scripts.*` package importable.
cd /home/claude/kg-automation && python3 -m scripts.common.alert_bus "$@"
cli_rc=$?

if [ "$propagate_rc" -eq 1 ]; then
  exit "$cli_rc"
fi

# Plain best-effort emit: always succeed at the shell boundary.
exit 0
