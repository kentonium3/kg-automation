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
- **OpenClaw workspace:** `~/.openclaw/workspace/` — home of `MEMORY.md`,
  `memory/YYYY-MM-DD.md`, `HEARTBEAT.md`.
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

## Intake-triage reply — apply_reply mechanics

`felix-admin-capture` (inbox cron) sends a numbered **inbox-triage digest**
(`Inbox triage — N tasks need info:`, one `<n>. <title> — needs: <fields>` line
per task) when a Vikunja Inbox task is missing Tier-1 fields (real project + a
schedulable `f:1/2/3` + a `q:` quadrant). Kent's later reply is numbered
**compact shorthand**, one line per digest number, supplying only the missing
field(s): full form `<n> <project> f<1-3> <quadrant>` + optional Tier-2
(`due:<when>`, `habit`, `loe:<s|m|l>`). Examples: `1 personal`, `2 f2 schedule`,
`3 clients f3 do due:fri`.

**Correlation is content-based** — WhatsApp quote-reply metadata is NOT plumbed
to the agent (habits precedent, research R1), so recognize the reply by its
numbered compact-shorthand shape; the helper matches it to the most-recent
digest within the window. Apply it by piping the reply text VERBATIM on stdin
(never re-author it):

```bash
cd /home/claude/kg-automation && printf '%s' "<Kent's reply text VERBATIM>" \
  | python3 -m scripts.intake.apply_reply --reply - --json
```

The helper is deterministic: it correlates to the right digest, resolves every
token through the #748 seam, and writes with the **kent** token (read-modify-write
+ family-replace, so a new `q:`/`f:` replaces the same-family label and unrelated
labels/fields are preserved). It emits
`{digest_id, results:[{line, task_id, status, applied, notes, understood, failed}], aggregates:{…}}`.
Relay each line's `status` back to Kent in ONE message:

- `applied` — fields set (cite `applied`); `noop` — live values already matched.
- `overload_flagged` — `f:4`, decomposition-pending, deliberately NOT scheduled (stops re-prompting).
- `echoed_back` — a token could not be resolved (`understood` vs `failed`) — see fallback.
- `not_found` / `already_done` / `moved_conflict` / `access_denied` / `failed` — a per-line
  problem; other lines in the same reply are still applied (one failing line never blocks the rest).
- `notes` carry deterministic confirmations (e.g. a non-blocking due-date follow-up on a
  `q:do`/`q:schedule` with no `due:`, or an ignore-with-note for incompatible Tier-2).

**Constrained LLM fallback (Directive-6 boundary).** ONLY when a line returns
`echoed_back` with an unresolved token in `failed` may you propose a **canonical
name** for that token — never a raw id, a label/project id, or a free-form value.
Re-run with the constrained map (canonical name only):

```bash
cd /home/claude/kg-automation && printf '%s' "<same reply text VERBATIM>" \
  | python3 -m scripts.intake.apply_reply --reply - --json \
    --unresolved '[{"line":<n>,"token":"<raw>","position":<i>,"canonical_name":"<canonical>"}]'
```

The helper **re-resolves** each `canonical_name` through the seam and rejects ids
or free-form values outright. A token you cannot confidently map to a canonical
name stays `echoed_back` — surface it to Kent, never guess.

### Intake key — shorthand reference on demand

When Kent asks for the shorthand reference — e.g. **"intake key"**, "show key",
"shorthand key", "intake help", or "what's the intake syntax" — run the
deterministic helper and relay its output **verbatim** in one message (do NOT
re-author or summarize it — it is derived from the parser's alias tables so it
always matches what a reply can use):

```bash
cd /home/claude/kg-automation && python3 -m scripts.intake.shorthand_key
```

(The digest itself also carries a one-line format hint as its footer, so the
syntax is visible without asking.)
