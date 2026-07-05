# Quickstart: verifying the felix-admin cron path fix

Post-deploy verification on office2, mapped to the spec's Success Criteria.
Run as `ssh office2-claude` unless noted. Read-only checks; no sudo.

## SC-1 — helpers resolve from any cwd

```
ssh office2-claude 'cd /data/services/openclaw/escalation-agent && python3 -m scripts.escalation.derive_state --help >/dev/null && echo OK-escalation'
ssh office2-claude 'cd /home/kgale/second-brain && python3 -m scripts.inbox.prescan --help >/dev/null && echo OK-inbox'
```
Both print `OK-…` (previously `ModuleNotFoundError`).

> ⚠️ **SSH shells are NOT the acceptance surface (Codex #1 C1).** An SSH login
> shell inherits env from the login profile, not from the gateway service. The
> authoritative check (SC-10) is that `PYTHONPATH` is present inside a **real
> agent/cron subprocess** — run a one-off agent/cron payload that executes
> `python3 -c 'import os;print(os.environ.get("PYTHONPATH"))'` from a non-repo cwd
> and confirm it prints `/home/claude/kg-automation`. Also:
> `systemctl --user show openclaw-gateway.service -p Environment` shows the
> drop-in value — necessary but not sufficient on its own.

## SC-2 — consecutive clean cron runs

```
ssh office2-claude 'openclaw cron runs --json' | \
  python3 -c "import json,sys; r=json.load(sys.stdin); \
  print([ (x['name'],x['status']) for x in r if x['name'].startswith(('inbox-','escalation-')) ][:8])"
```
Expect the latest ≥5 inbox/escalation runs `status=success`, no
`ModuleNotFoundError` in run output.

## SC-3 — dedup ledger served from `/data`, no re-routing

```
ssh office2-claude 'test -s /data/services/openclaw/state/inbox-routing.jsonl && echo ledger-present'
ssh office2-claude 'wc -l /data/services/openclaw/state/inbox-routing.jsonl'
```
Line count ≥ the pre-migration count; a subsequent inbox tick routes no
already-routed note (spot-check the tick log).

## SC-4 — forensic logs in the synced vault

```
ssh office2-claude 'ls -t /home/kgale/second-brain/agents/logs/inbox-prescan-*.md | head -1'
```
A fresh dated log exists under the vault; confirm it appears in Obsidian on phone/Mac.

## SC-5 — stray dir decommissioned, not recreated

```
ssh office2-claude 'test ! -e /home/claude/second-brain && echo stray-gone'
# after a full inbox tick + a calendar clarification cycle, re-check:
ssh office2-claude 'test ! -e /home/claude/second-brain && echo stray-still-gone'
```

## SC-6 — stale/stray refs removed (broadened, Codex #1 M1)

```
grep -rn "~/repos/kg-automation" scripts/openclaw/agents/ || echo "no stale checkout ref"
grep -rn "/home/claude/second-brain" scripts/openclaw/agents/ scripts/inbox/ || echo "no stray-dir ref"
# ~/second-brain write/log targets should be gone EXCEPT the _private read-prohibition lines:
grep -rn "~/second-brain" scripts/openclaw/agents/ | grep -v "_private" || echo "no ~/second-brain write refs"
```
Run against the deployed prompts; expect none outside the `_private` boundary lines.

## SC-8 — dedup active from any cwd (FR-011)

```
ssh office2-claude 'cd /tmp && python3 -m scripts.inbox.prescan --self-check 2>&1 | grep -i "dedup-disabled" && echo "FAIL: dedup disabled" || echo "OK: dedup active"'
```
Expect `OK: dedup active` — the routing-log reader import resolves under the guardrail.

## SC-9 — state dir ownership/modes (FR-012)

```
ssh office2-claude 'stat -c "%U:%G %a %n" /data/services/openclaw/state /data/services/openclaw/state/inbox-routing.jsonl'
```
Expect `claude:secondbrain 750 …/state` and `claude:secondbrain 640 …/inbox-routing.jsonl`.

## SC-7 — no routing/escalation regression

- Inbox: one full tick processes new notes and skips processed ones (frontmatter
  `status: processed` + ledger both consulted).
- Escalation: `escalation-daily` produces its overdue-task alert on the next run.

## NFR-002 — path independence (local, pre-deploy)

```
cd /Users/kentgale/repos/kg-automation && python3 -m pytest tests/inbox -k "path or resolve or cwd or home" -q
```
Tests assert the state/log paths are unchanged under monkeypatched `HOME`/cwd,
and that helper import does not depend on `os.getcwd()`.
