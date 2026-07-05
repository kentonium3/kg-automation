# Quickstart: verifying the felix-admin cron path fix

Post-deploy verification on office2, mapped to the spec's Success Criteria.
Run as `ssh office2-claude` unless noted. Read-only checks; no sudo.

## SC-1 — helpers resolve from any cwd

```
ssh office2-claude 'cd /data/services/openclaw/escalation-agent && python3 -m scripts.escalation.derive_state --help >/dev/null && echo OK-escalation'
ssh office2-claude 'cd /home/kgale/second-brain && python3 -m scripts.inbox.prescan --help >/dev/null && echo OK-inbox'
```
Both print `OK-…` (previously `ModuleNotFoundError`). Confirms the gateway
`PYTHONPATH` env is inherited (these shells inherit it the same way agent
subprocesses do).

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

## SC-6 — stale checkout ref removed

```
grep -rn "~/repos/kg-automation" scripts/openclaw/agents/ || echo "no stale ref"
```
Run against the deployed prompts; expect none.

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
