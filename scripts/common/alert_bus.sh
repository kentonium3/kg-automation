#!/usr/bin/env bash
# felix-alert bus — bash shim.
#
# Best-effort at the shell boundary: sources the topic env-file if present,
# env-anchors to the checkout, invokes the CLI, and ALWAYS exits 0 so
# cron/audit callers never fail regardless of `|| true` discipline. The
# `self-test` and `--strict` exit-code semantics are enforced inside the
# Python CLI, not here — this shim is deliberately non-fatal.
#
# NOT `set -e`: a delivery failure must not abort the caller.
set -uo pipefail

# Source the single topic env-file if present. This is what lets a
# cron-launched audit.sh (no systemd EnvironmentFile) resolve the topic.
if [ -f /home/claude/.config/felix/alert-bus/env ]; then
  # shellcheck disable=SC1091
  . /home/claude/.config/felix/alert-bus/env
fi

# Proven checkout-cd form (#658): office2 has only `python3`, never bare
# `python`. Invoking as `-m` keeps the `scripts.*` package importable.
cd /home/claude/kg-automation && python3 -m scripts.common.alert_bus "$@"

# Always succeed at the shell boundary (best-effort).
exit 0
