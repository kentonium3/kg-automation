# Contract: Driver Invocation

**Mission**: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
**Realizes**: spec FR-001, FR-003, FR-007; research.md D6, D10
**Applies to**: systemd `ExecStart`, manual operator invocation, test runs

## Entry point

```
/home/claude/kg-automation/scripts/doc_audit/run.py
```

Python 3.10+. Stand-alone executable (`#!/usr/bin/env python3` shebang + `chmod +x`).

## CLI surface

```
python3 scripts/doc_audit/run.py [options]

Options:
  --dry-run             Print intended actions; do not mutate GH issues or repo files.
  --once                Default. Process the queue once and exit. (Reserved for future
                        `--daemon` mode.)
  --source <name>       Restrict to one signal source. Choices: gh_issue, drift_event.
                        Useful for incremental testing; omit for production.
  --config <path>       Override config path. Default: scripts/doc_audit/config.toml
  --version             Print driver version and exit.
  --help                Print help and exit.
```

Args are parsed by `argparse`. Unknown args cause exit 2 (invalid invocation).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. All signals processed cleanly OR queue was empty. |
| `1` | Unrecoverable error before any signal could be processed (config invalid, API key unreadable, network unreachable, etc.). |
| `2` | Partial success. Some signals processed, some failed. Details in `last-tick.json` `errors[]`. |
| `64-78` | Reserved (sysexits.h conventions). |

systemd interprets `0` as `success`, `1` as `failure`, `2` as `partial failure` (still surfaces non-zero status). Future #327 alerting can map exit codes to severities.

## Environment

| Variable | Required | Source |
|---|---|---|
| `HOME` | yes | systemd sets to `/home/claude` |
| `PATH` | yes | systemd inherits default |
| `ANTHROPIC_API_KEY` | NO | driver reads from `/data/services/openclaw/secrets/anthropic` |
| `GH_TOKEN` | NO | `gh` CLI uses `/home/claude/.config/gh/hosts.yml` |

The driver is self-contained on credentials — no extra env wiring needed for the systemd unit.

## systemd unit (new ExecStart)

```ini
[Unit]
Description=felix-doc-auditor driver — scripts-first audit processing
After=network-online.target openclaw-gateway.service

[Service]
Type=oneshot
TimeoutStartSec=30min
ExecStart=/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py
WorkingDirectory=/home/claude/kg-automation
Environment=HOME=/home/claude

[Install]
WantedBy=default.target
```

The `WantedBy` is unchanged from today. The `Description` is updated. The `After=` keeps the existing dependency on `openclaw-gateway.service` (the gateway still hosts other agents) but the driver itself does NOT call into openclaw.

## Operating contract — what the driver promises

1. **One tick per invocation.** Default `--once` behavior. The driver does not background, fork, or daemonize.
2. **Atomic state writes.** `last-tick.json` is written via tempfile-then-rename. The activity log entry is appended atomically (single `write()` call per entry). The cursor file is written atomically.
3. **Lock recovery.** Stale `status:in-progress` labels from prior crashed ticks are recovered per data-model E-002 transitions.
4. **Idempotent on no work.** Re-running the driver back-to-back with no new signals is a no-op (no new commits, no new issues, no spurious activity log entries — well, ONE log entry per tick per spec C-005, recording the no-op).
5. **Bounded duration.** A typical tick completes in ≤30 seconds. Longer ticks (backlogs, retries) MAY exceed but MUST stay under the 30-min systemd timeout.
6. **Structured signal always written.** Even on crash, the `try/finally` wrapper ensures `last-tick.json` is updated.

## Operator manual invocation patterns

```bash
# Dry-run on office2 to preview what the next tick would do:
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/run.py --dry-run'

# Force one tick now (same as the systemd timer firing):
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'

# Tail last-tick result:
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq'

# Tail journal:
ssh office2-claude 'journalctl --user -u felix-doc-auditor -f'
```

## Non-goals (out of scope for this contract)

- Daemon / long-running mode
- Per-tick CLI arguments to override LLM model or judgment behavior
- Operator-side queue manipulation (label changes, issue closing) — those are gh CLI operations, not driver operations
