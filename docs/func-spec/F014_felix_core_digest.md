---
title: "F014: Felix Core Digest — Agent Log Format Standard and Observation Intelligence Layer"
doc_type: func-spec
status: draft
feature: F014
---

# F014: Felix Core Digest — Agent Log Format Standard and Observation Intelligence Layer

**Version**: 1.1
**Priority**: HIGH
**Type**: Infrastructure

---

## Executive Summary

The Felix Constitution (F012) mandates that every agent log every action
and that a centralized intelligence layer reads those logs to produce a
consolidated daily digest. The observation module (`summarize.py`) was
written during F012 as the intelligence layer implementation, but it was
never wired to a trigger, never deployed as a running service, and has
a fundamental design flaw: it relies on regex parsing of free-form
Markdown written by Claude. This is fragile — Claude can produce
inconsistent formatting, miss tags, or vary wording across runs.

The correct architecture separates the stochastic concern (the agent
determining what happened) from the deterministic concern (writing a
well-formed, machine-readable log entry). A narrow Python helper
(`log_action.py`) receives structured arguments from the agent and owns
all file I/O, schema enforcement, and JSONL serialization. The agent
never writes raw structured data directly.

Current gaps:
- ❌ No canonical log format — agents define their own, summarize.py
  expects yet another; the system has never had a single standard
- ❌ summarize.py relies on regex parsing of agent-written Markdown —
  fragile and already inconsistent across agents
- ❌ No Python log writer — agents write log files directly; there is
  no deterministic enforcement layer between the agent and the file
- ❌ summarize.py not deployed — no cron, no trigger, no active observation
- ❌ Log output structure is flat; approved design is per-agent
  subdirectories with 5-day retention
- ❌ `~/second-brain/agents/logs/` not gitignored in second-brain repo
- ❌ No verbosity levels — brief/standard/verbose undefined
- ❌ No rule for generative output (proposal text, drafted messages) —
  embed or cross-reference undefined

This spec delivers `log_action.py` as the authoritative log writer, JSONL
as the raw log format, updated summarize.py JSONL parsing to replace the
Markdown regex, corrected output structure, cron trigger wiring, and
gitignore protection. It replaces the fragile Markdown parsing architecture
with a deterministic Python boundary consistent with how the rest of the
system handles stochastic/deterministic separation.

**A note on prescriptiveness**: This spec is more detailed than the
project standard in places — particularly around the JSONL schema, the
log_action.py interface, and the summarize.py rewrite. That detail
reflects significant design thinking that should not be discarded. Treat
it as strong, considered guidance. The specify and planning phases may
refine or deviate from specific implementation choices if technical
discovery reveals a better approach — but any deviation must preserve the
architectural intent: deterministic Python owns file I/O and schema
enforcement; agents own only the judgment of what to log.

---

## Problem Statement

**Current State:**
```
Agent (Claude, stochastic)
└── Writes free-form Markdown log directly to ~/second-brain/agents/logs/
    └── ❌ Format varies by agent
    └── ❌ No schema enforcement
    └── ❌ Inconsistent category tags

summarize.py
└── ✅ Core digest logic implemented
└── ✅ Test suite exists
└── ❌ Parses Markdown with regex — fragile
└── ❌ Never deployed — no cron, no trigger
└── ❌ Output: flat files at 00-System/agent-activity/
└── ❌ No 5-day retention
└── ❌ WhatsApp send is a stub only

~/second-brain/agents/logs/
└── ❌ Not gitignored — logs would be committed on git add .

Observation Mode (Constitution Directive 3)
└── ❌ Not operational
└── ❌ No verbosity model
└── ❌ No generative output rule
```

**Target State:**
```
Agent (Claude, stochastic)
└── Calls log_action.py with structured arguments
    └── Determines WHAT and WHY — never writes raw structured data

log_action.py (Python, deterministic)
└── ✅ Receives structured arguments from agent
└── ✅ Owns JSONL schema, file path, timestamp, run_id
└── ✅ Appends valid JSONL entry — fast-fails on invalid calls
└── ✅ Single source of truth for log format

summarize.py (Python, deterministic)
└── ✅ Parses JSONL (replaces Markdown regex)
└── ✅ Deployed on office2 as cron job (every 15 minutes)
└── ✅ Output: per-agent subdirectories, date-stamped files
└── ✅ 5-day retention enforced on each run
└── ✅ Digest notes appear in Obsidian via existing vault sync

~/second-brain/agents/logs/
└── ✅ Gitignored in second-brain repo

Observation Mode (Constitution Directive 3)
└── ✅ Operational for all deployed agents
└── ✅ Verbosity model defined and enforced by log_action.py
└── ✅ Generative outputs cross-referenced, not embedded
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read:

1. **The existing observation module — understand what exists and what changes**
   - `scripts/openclaw/observation/summarize.py` — the full implementation;
     the Markdown parsing logic (CATEGORY_PATTERN, AGENT_PATTERN,
     RUN_TIME_PATTERN, SUMMARY_LINE_PATTERN regexes and parse_log_file())
     is what this spec replaces with JSONL parsing
   - `scripts/openclaw/observation/config.py` — path resolution and registry
     loading; `autonomy_level()` is the exact pattern `log_verbosity()` must follow
   - `scripts/openclaw/observation/tests/test_summarize.py` — test structure
     to preserve; fixture format changes from Markdown to JSONL
   - `scripts/openclaw/observation/tests/fixtures/` — all fixture files;
     these are rewritten as JSONL; map each fixture to its JSONL equivalent
     before deleting any Markdown file

2. **All agent AGENTS.md Action Logging sections — map old fields to new schema**
   - `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` — Action
     Logging section defines a multi-field Markdown format; planning phase
     must map every recorded field to a log_action.py argument so no data
     is silently dropped
   - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — same
   - `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — same

3. **Whether OpenClaw supports agents calling external Python scripts —
   this is the critical first-step research question**
   - Study the OpenClaw agent runtime and TOOLS.md for all deployed agents
   - Determine whether an agent can execute a shell command or subprocess
     call (e.g., `python log_action.py --agent ... --category ...`) during
     a run
   - If yes: proceed with log_action.py as the agent-facing CLI interface
   - If no: agents write constrained single-line JSONL directly (fallback
     defined in FR-1); log_action.py still exists as a library used by
     summarize.py for schema validation
   - Document the finding before writing any code — it determines the
     primary vs. fallback path for the entire feature

4. **Existing office2 scheduling pattern**
   - `scripts/office2/vault-snapshot.timer` and `vault-snapshot.service` —
     the canonical systemd timer/service pattern; replicate for summarize.py
   - Confirm whether crontab or systemd timer is the established pattern

5. **Second-brain repo .gitignore and current output path**
   - Check whether `agents/logs/` gitignore entry already exists
   - Determine whether any files currently exist at
     `~/second-brain/notes/00-System/agent-activity/`; document the
     migration or leave-in-place decision before changing the output path

---

## Functional Requirements

### FR-1: log_action.py — Deterministic Log Writer

**What it must do:**
- Create `log_action.py` as the sole writer of agent log entries
- Accept structured arguments, serialize a valid JSONL entry, and append
  it to the correct log file
- Fast-fail with a clear error on missing required fields or invalid
  category values — never write a partial or malformed entry

**JSONL entry schema:**

Required fields (every entry, every verbosity level):
```json
{
  "ts": "2026-04-03T07:12:04Z",
  "run_id": "felix-admin-tasker-20260403-0712",
  "agent": "felix-admin-tasker",
  "autonomy_level": "assisted",
  "category": "routine",
  "action": "task_proposed",
  "target": "Schedule car for oil change",
  "outcome": "awaiting_confirmation"
}
```

Optional context block (standard verbosity — written when `log_verbosity`
is `"standard"` or `"verbose"`):
```json
{
  "...required fields...",
  "context": {
    "project": "Personal",
    "due": "2026-04-11",
    "priority": "medium",
    "vikunja_task_id": null
  }
}
```

Optional trace block (verbose verbosity only — written when `log_verbosity`
is `"verbose"`):
```json
{
  "...required + context fields...",
  "trace": {
    "confidence": {"project": 0.94, "due_date": 0.71},
    "clarification_asked": ["repeat_interval"],
    "api_calls": [
      {"endpoint": "GET /projects", "status": 200, "latency_ms": 87}
    ]
  }
}
```

**Valid category values:** `routine`, `flagged`, `error`, `security`

**Generative output rule:**
When an agent produces stochastic output (a task proposal, a drafted
message, a generated summary), the log entry must not embed the full
generated text. The agent passes a cross-reference:

```json
{
  "action": "task_proposal_sent",
  "context": {
    "proposal_ref": "vikunja:task:pending",
    "channel": "whatsapp"
  }
}
```

If no persistent cross-reference exists, `log_action.py` enforces a
maximum of 120 characters on any string field value and appends
`[truncated]` if exceeded. This is enforced in the Python — not left
to the agent.

**Log file path:**
```
~/second-brain/agents/logs/{agent-name}/YYYY-MM-DD.jsonl
```

`log_action.py` creates the agent subdirectory on first write. Multiple
runs per day append to the same file.

**Fallback (if OpenClaw does not support subprocess calls):**
Agents write a single-line JSON object directly to the log file — no
free-form text, no multi-line formatting, no deviation from the schema.
`log_action.py` still exists and is used by `summarize.py` for schema
validation of entries. Enforcement is by instruction rather than by code;
the operational implications must be documented in the runbook. The
planning phase must document which path was taken and why.

**Success criteria:**
- [ ] `log_action.py` exists, accepts structured arguments, writes valid JSONL
- [ ] Fast-fails on missing required fields or invalid category values
- [ ] Creates agent subdirectory on first write; appends to existing daily file
- [ ] Enforces 120-character truncation on string fields
- [ ] Planning phase documents primary vs. fallback path decision with rationale

---

### FR-2: Rewrite summarize.py to Parse JSONL

**What it must do:**
- Replace Markdown regex parsing in `summarize.py` with JSONL parsing
- Preserve all digest generation behavior — only the input parsing changes

**What is removed:**
- `CATEGORY_PATTERN`, `AGENT_PATTERN`, `RUN_TIME_PATTERN`,
  `SUMMARY_LINE_PATTERN` regex constants
- `parse_log_file()` Markdown parsing function and its line-state logic

**What replaces it:**
- `parse_jsonl_log(path)` — reads a `.jsonl` file, deserializes each
  line, returns a list of action dicts matching the FR-1 schema
- Invalid or malformed lines are logged to stderr and skipped; they
  do not halt the run

`find_log_files()` must walk per-agent subdirectories to locate
`YYYY-MM-DD.jsonl` files rather than scanning a flat directory.

**Test fixtures:**
All fixtures in `tests/fixtures/` are rewritten as JSONL. The planning
phase maps every existing fixture to its JSONL equivalent before
deleting any Markdown file. New fixtures must cover: multi-run days
(multiple JSON objects in one file), verbose entries with trace fields,
malformed line handling, and truncated generative output cross-references.

**Success criteria:**
- [ ] Markdown regex parsing removed; JSONL parsing in place
- [ ] All existing tests pass against new JSONL fixtures
- [ ] Malformed lines skipped with stderr logging — no crash
- [ ] Test coverage for verbose trace fields, multi-run files, and
  truncated generative output references

---

### FR-3: Update Agent AGENTS.md Action Logging Sections

**What it must do:**
- Replace Action Logging sections in all three deployed agents' AGENTS.md
  with instructions to call `log_action.py` (or write constrained JSONL
  per the fallback path)
- Map every field currently recorded by each agent to its log_action.py
  argument equivalent — no data silently dropped

**Business rules:**
- AGENTS.md never defines a log schema; it references log_action.py and
  lists the action types and categories relevant to that agent
- Updated workspace files must be deployed to office2

**Success criteria:**
- [ ] All three agents' AGENTS.md reference log_action.py
- [ ] Per-agent action type and category lists documented
- [ ] No previously-recorded log fields silently dropped
- [ ] Updated workspace files deployed to office2

---

### FR-4: Corrected Digest Output Structure with 5-Day Retention

**What it must do:**
- Update `summarize.py` to write per-agent subdirectory Markdown digest
  files with date-stamped names and enforce 5-day retention

**Output structure:**
```
{vault_path}/Agent-Logs/
  overview.md                      ← regenerated each run; always current day
  felix-admin-capture/
    2026-04-03-log.md
    2026-04-02-log.md              ← maximum 5 files per agent directory
    ...
  felix-admin-habits/
    2026-04-03-log.md
    ...
  felix-admin-tasker/
    2026-04-03-log.md
    ...
```

Each per-agent daily file consolidates all runs for that day (existing
`generate_agent_detail()` multi-run behavior preserved). Digest files
are human-readable Markdown — appropriate for human consumption in Obsidian.

**Retention:** After writing today's file, delete any file in the same
agent subdirectory older than 5 calendar days. Age is determined by
parsing the date from filenames — not filesystem mtime.

**Idempotency:** If no new JSONL entries exist since the last run, skip
the file write. Planning phase determines the specific mechanism
(content-hash or entry-count-plus-mtime). Goal: 15-minute cron does not
generate meaningless writes when agents are idle.

**Success criteria:**
- [ ] summarize.py writes per-agent subdirectory Markdown files
- [ ] Date-stamped filenames; 5-day retention enforced on each run
- [ ] overview.md at `Agent-Logs/overview.md`
- [ ] No write when no new log content since last run
- [ ] Digest files confirmed visible in Obsidian on Mac
- [ ] Tests cover retention logic and idempotency behavior

---

### FR-5: Verbosity Flag in Agent Registry

**What it must do:**
- Add `log_verbosity` to each agent entry in `agent-registry.json`
- Expose via `log_verbosity(agent_name)` in `config.py`, following the
  exact pattern of `autonomy_level()`
- `log_action.py` reads this to determine which optional blocks to write
- All deployed agents start at `"standard"`

**Valid values:** `"brief"`, `"standard"`, `"verbose"` — default: `"standard"`

**Success criteria:**
- [ ] `log_verbosity` field present for all agents in `agent-registry.json`
- [ ] `config.py` exposes `log_verbosity(agent_name)` method
- [ ] `log_action.py` reads verbosity from registry before writing
- [ ] Test coverage for verbosity lookup

---

### FR-6: Gitignore Raw Logs

**What it must do:**
- Add `agents/logs/` to the second-brain repo `.gitignore`

**Success criteria:**
- [ ] Entry present in second-brain repo `.gitignore`
- [ ] `git status` confirms log files are untracked

---

### FR-7: Cron Trigger Deployment

**What it must do:**
- Deploy a scheduled trigger on office2 that runs `summarize.py` every
  15 minutes, following the established office2 scheduling pattern,
  under the `claude` service account, surviving reboots

**Success criteria:**
- [ ] summarize.py runs automatically every 15 minutes on office2
- [ ] Follows established office2 scheduling pattern
- [ ] Runs under `claude` service account; survives reboots
- [ ] Digest files appear in Obsidian within 15 minutes of an agent run

---

### FR-8: Operations Runbook

**What it must do:**
- Create `docs/handbooks/observation-ops.md` covering: how to read digest
  files in Obsidian, how to access raw JSONL logs on office2, how to
  change verbosity level, how to verify the trigger is running, how to
  run summarize.py manually with `--dry-run`, troubleshooting (missing
  digests, parse errors, stale output), and fallback architecture
  implications if applicable

**Success criteria:**
- [ ] Runbook exists and covers all listed topics

---

## Architecture Documentation Updates

### JSON Updates Required

| File | Change |
|---|---|
| `data/service-inventory.json` | Add felix-core-digest as scheduled service; add log_action.py as system utility; set `updated_by: "F014"` |
| `data/data-flows.json` | Add flow: agent → log_action.py → JSONL → summarize.py → vault digest |

### Markdown Updates Required

| File | Change |
|---|---|
| `service-inventory.md` | Add felix-core-digest under Scheduled Services |
| `data-flows.md` | Add observation intelligence layer data flow |

**Success criteria:**
- [ ] `service-inventory.json` updated with `updated_by: "F014"`
- [ ] Markdown views match JSON sources

---

## Out of Scope

- ❌ WhatsApp critical alert delivery — send stub remains; activation
  deferred until DM policy is re-enabled
- ❌ Escalation engine — deferred to F015
- ❌ Daily briefing (F017) — consumes digest output; this spec produces it
- ❌ Security agent or adversarial monitoring — Core Hub / D06 scope
- ❌ New agent behavior changes — F014 changes how agents log, not what they do

---

## Success Criteria

**Complete when:**

### Log Writer
- [ ] `log_action.py` exists, schema-enforces JSONL, fast-fails on invalid input
- [ ] Agents call log_action.py or write constrained JSONL per documented path
- [ ] Planning phase documents primary vs. fallback decision with rationale

### summarize.py
- [ ] Markdown regex parsing replaced with JSONL parsing
- [ ] All tests pass against new JSONL fixtures
- [ ] Per-agent subdirectory output; 5-day retention; idempotent on no-new-content

### Registry and Config
- [ ] `log_verbosity` in all registry entries; `config.py` exposes lookup

### Infrastructure
- [ ] `agents/logs/` gitignored; cron/timer deployed; digests visible in Obsidian

### Documentation
- [ ] All three agents' AGENTS.md updated and deployed to office2
- [ ] `docs/handbooks/observation-ops.md` complete
- [ ] Architecture docs updated

---

## Architecture Principles

### Deterministic Boundary Between Agent and File

Agents determine what happened — a stochastic judgment. Writing a
schema-valid log entry is deterministic. `log_action.py` sits at the
boundary: the agent passes structured arguments; the Python owns
everything after. This is the same pattern as the Vikunja API skill —
the agent decides what to do; the skill executes it correctly.

### JSONL for Machine Consumption; Markdown for Human Consumption

Raw logs are consumed by Python — they are JSONL. Digest notes are
consumed by Kent in Obsidian — they are Markdown. The format matches
the consumer. summarize.py is the translation layer between them.

### Fallback Is a Real Contract

If OpenClaw does not support subprocess calls, the constrained JSONL
fallback is a legitimate operating mode — not a temporary workaround.
The schema is identical; only enforcement mechanism differs. The fallback
is documented with the same precision as the primary path.

### Verbose Is a Debugging Mode, Not a Default

Stable agents run at Standard. Verbose is activated in the registry
for a specific agent during active debugging and returned to Standard
when the investigation is complete.

---

## Constitutional Compliance

✅ **Directive 3 — Central Action Logging**: This spec makes Directive 3
operational. Every agent action produces a JSONL entry. The intelligence
layer reads those entries and produces digest notes.

✅ **Deterministic over stochastic for infrastructure**: log_action.py
owns the file format; summarize.py owns the digest format. Agents own
only the judgment of what to log.

✅ **Narrow scope**: felix-core-digest reads raw logs and writes digest
files. It does not take actions, manage tasks, or communicate with Kent.

✅ **Privacy boundary**: summarize.py reads only from
`~/second-brain/agents/logs/`. It never reads the vault or any private
directory.

---

## Risk Considerations

**Risk: OpenClaw does not support subprocess calls**
- Mitigation: Constrained JSONL fallback defined in FR-1 with equal
  precision. First-step research question for planning phase.

**Risk: JSONL fixture rewrite introduces test coverage gaps**
- Mitigation: Planning phase maps every existing fixture to JSONL
  equivalent before deleting any Markdown file.

**Risk: AGENTS.md update creates a gap period on office2**
- Mitigation: Deploy updated AGENTS.md to office2 before activating
  JSONL-parsing summarize.py. Implementation sequence enforces this order.

**Risk: 15-minute cron generates excessive writes during idle periods**
- Mitigation: FR-4 idempotency requirement is hard — no write when no
  new content exists.

---

## Notes for Implementation

**Implementation latitude:**
Where this spec is more prescriptive than the project standard, treat
it as strong guidance informed by deliberate design thinking — not a
rigid contract. If the specify or planning phase uncovers a technically
superior approach to any implementation detail, take it. The architectural
intent that must be preserved: deterministic Python owns file I/O and
schema enforcement; agents own only the judgment of what to log; raw
logs are JSONL; digest notes are human-readable Markdown.

**Critical first step:**
Research whether agents can call external Python scripts during an
OpenClaw run. This single answer determines the primary vs. fallback
path. Document before writing any code.

**Implementation sequence:**
1. OpenClaw subprocess research (determines FR-1 path)
2. Check second-brain .gitignore; add `agents/logs/` if missing (FR-6)
3. Write `log_action.py` (FR-1)
4. Map all existing fixture Markdown formats to JSONL equivalents
5. Rewrite summarize.py JSONL parsing; rewrite test fixtures (FR-2)
6. Diff each agent's Action Logging section; update AGENTS.md (FR-3)
7. Deploy updated AGENTS.md to office2
8. Update summarize.py output structure and retention (FR-4)
9. Add `log_verbosity` to registry and config.py (FR-5)
10. Run full test suite — confirm all pass
11. Wire cron/timer trigger (FR-7)
12. Verify end-to-end: agent run → JSONL written → summarize.py fires →
    digest appears in Obsidian
13. Write operations runbook (FR-8)
14. Update architecture docs

**Pattern references:**
- `config.py` `autonomy_level()` → exact pattern for `log_verbosity()`
- `scripts/office2/vault-snapshot.timer` / `vault-snapshot.service` →
  replicate for summarize.py systemd timer

---

**END OF SPECIFICATION**
