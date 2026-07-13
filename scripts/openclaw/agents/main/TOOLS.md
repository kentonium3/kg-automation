# TOOLS.md — Local Notes & Mechanics

Skills define _how_ tools work. This file holds main's specifics — the real
environment surface, the delegation/helper mechanics, and the enforceable
privacy path. `AGENTS.md` states the *rules*; this file states the *commands*.

## Privacy path (enforceable rule)

`04-Growth/_private/` does not exist as far as you are concerned. Never read,
write, reference, or log it under any circumstance. No exceptions. (Path
renumbered from `02-Growth/_private/` in mission 026 / #152; the constitutional
boundary is unchanged — only the parent folder ordinal moved.)

## Environment surface

- **Host:** office2 (Ubuntu 24.04 LTS), reached over Tailscale. Repo checkout at
  `/home/claude/kg-automation`; Obsidian vault at `/home/kgale/second-brain`.
- **OpenClaw workspace:** `~/.openclaw/workspace/` — home of `GOVERNANCE.md`,
  `MEMORY.md`, `memory/YYYY-MM-DD.md`, `HEARTBEAT.md`.
- **State files:** `/data/services/openclaw/state/pending-calendar-clarifications.jsonl`
  (calendar clarification round-trips), `memory/heartbeat-state.json` (heartbeat
  check tracking).
- **Timelog venv:** `/data/services/openclaw/felix-calendar/venv/bin/python`.
- **Platform formatting:** Discord/WhatsApp — no markdown tables, use bullet
  lists. Discord links — wrap multiples in `<>` to suppress embeds. WhatsApp — no
  headers; use **bold**/CAPS.
- **TTS:** with `sag` (ElevenLabs), use voice for stories/summaries/"storytime".

## Delegation mechanics

Delegate to a specialist with:

```bash
openclaw agent --agent <name> --message "<Kent's exact text — VERBATIM>" --json --timeout <seconds>
```

Timeouts by specialist: capture `300`, habits `120`, calendar `120`, escalation
`120`, tasker `120`. Forward Kent's reply text VERBATIM (see AGENTS Verbatim
pass-through) — the sub-agents' deterministic parsers need exact phrasing.

**Inbox processing** — `felix-admin-capture` owns standing orders; do NOT process
the inbox yourself. Trigger it, then read the latest log:

```bash
openclaw agent --agent felix-admin-capture --message "Process the inbox now. Read all unprocessed files in 00-Inbox/, classify and route content per your standing orders, create Vikunja tasks for action items and research requests, route valid goal declarations, and write the processing log." --json --timeout 300
```
```bash
ls -t /home/kgale/second-brain/agents/logs/inbox-processing-*.md | head -1
```

**Calendar** — forward the `create_calendar_event` payload (or Kent's verbatim
request / clarification reply) to `felix-admin-calendar`. NEVER create calendar
events yourself (#679). Contract:
`kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/contracts/capture_to_main_calendar_payload.md`.

The **time-logging** helper (option A — main calls it directly, not a sub-agent)
is owned by `AGENTS.md` `## Time-logging` (recognizer, anchored venv-python
invocation, and the typed-status relay rules) so the fleet guard test keeps the
mechanics beside main's SOP. Don't duplicate it here.

## Filing issues — felix-file-issue.py

Don't compose `gh issue create` from scratch — use the helper (verifies
kg-felix-bot identity, applies labels, emits `{issue_number, issue_url}` JSON):

```bash
echo "<problem paragraph>" > /tmp/felix-issue-problem.txt
echo "<logs/diffs/output>" > /tmp/felix-issue-context.txt   # optional

cd /home/claude/kg-automation && python3 scripts/openclaw/agents/main/felix-file-issue.py \
    --type {bug|feature|infra|research} \
    --title "<short title without prefix>" \
    --problem-statement-file /tmp/felix-issue-problem.txt \
    --tier-hypothesis {0|1|2|3|4|unknown} \
    --area {felix-core|security|biz-ops|tooling|ea} \
    --priority {P1|P2} \
    [--observed-context-file /tmp/felix-issue-context.txt] \
    [--related-issues "#270, #285"] \
    [--spec-ready-eval brief]
```

Default `--spec-ready-eval brief`; add `--dry-run` if uncertain. Tell Kent the
number (#291). The GitHub label taxonomy is authoritative in the issue templates
and `felix-file-issue.py` — don't inline a copy here.
