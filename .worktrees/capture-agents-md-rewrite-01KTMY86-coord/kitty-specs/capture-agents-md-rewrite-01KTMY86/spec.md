# Specification: Capture AGENTS.md Rewrite (Directive-6 half-2)

**Mission**: `capture-agents-md-rewrite-01KTMY86`
**Mission ID**: `01KTMY86X63W50FF36GWPWADH2`
**Target branch**: `main`
**Mission type**: `software-dev`
**Issue**: kentonium3/kg-automation#566 (closes; parent epic #563); follows half-1 `capture-d6-helpers-extraction-01KTMS5Q` (merge `ea52ad0e`)
**Created**: 2026-06-08

## Purpose (Stakeholder Summary)

`felix-admin-capture`'s deployed `AGENTS.md` is 52,942 chars (1,215 lines) — well over openclaw's 12,000-char workspace-bootstrap budget. Every cron tick silently truncates the load-bearing Step 5 routing/preserve instructions, which is the root cause of the silent inbox content loss tracked in epic #563. Half-1 of #566 shipped six new stdlib helpers under `scripts/inbox/` (`mark_processed`, `route_journal_entry`, `route_someday`, `route_calendar_event`, `handle_clarification_state`, `classify_content`) and verified them live on office2 via #567's deploy pipeline.

This mission ships **half-2**: rewrite `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` to invoke the new + existing helpers via `python3 -m scripts.inbox.<module>` form, drop the deterministic recipe prose they replace, and keep only the LLM-judgment surfaces (multi-topic note splitting, ambiguous-block disambiguation consuming `classify_content`'s flagged outputs, calendar clarification message authoring + reply interpretation, Output Discipline Hard Rules, identity + scope + lane assignments). Target prompt size: 250-400 lines (4,500-8,500 source chars), comfortably under openclaw's 12,000-char bootstrap budget AND the ~14,000-char effective budget (per `[[reference_openclaw_gotchas]]` ~26% rawChars inflation).

**Closes #566** (half-1 + half-2 together).
**Closes structural fix from #563** by making Step 5 routing/preserve instructions VISIBLE again on every openclaw session-init.

## User Scenarios & Testing

### Primary scenario: capture cron tick at 7am ET

1. felix-admin-capture cron fires. openclaw loads workspace; AGENTS.md is BELOW the 12,000-char bootstrap budget — no truncation.
2. Agent reads ALL of AGENTS.md including the Step 5 invariant "do NOT delete the original file — preserve it as a record".
3. Agent invokes `python3 -m scripts.inbox.prescan` (Step 1) — existing helper, gets the inbox state.
4. For each note: invokes `python3 -m scripts.inbox.classify_content --content-file <note>` (Step 3) — gets structured `ClassificationOutput` JSON.
5. Per block: invokes one of `route_journal_entry` / `route_someday` / `route_calendar_event` (Step 3 routes).
6. For ambiguous blocks (kind: `ambiguous`, flag: `needs-llm-disambiguation`): disambiguates via prompt judgment, then routes per the disambiguated kind.
7. Invokes `python3 -m scripts.inbox.mark_processed --path <note>` (Step 5c) — atomic frontmatter write; ORIGINAL FILE STAYS at `01-Inbox/<note>.md`.
8. Invokes `python3 -m scripts.inbox.append_routing_entry` (Step 5b, existing helper) — records the route.

### Scenario: openclaw bootstrap budget telemetry

1. openclaw session-init logs the workspace bootstrap line.
2. Before this mission: `workspace bootstrap file AGENTS.md is 39843 chars (limit 12000); truncating in injected context`
3. After this mission: NO truncation warning. The deployed AGENTS.md size is below the 12,000-char limit.

### Scenario: classify_content emits an ambiguous block

1. classify_content returns a block with `kind: "ambiguous"` and `flag: "needs-llm-disambiguation"`.
2. Agent (prompt) reads the block's `content` field plus surrounding context.
3. Agent disambiguates to one of: `journal`, `calendar`, `someday`, `github_issue`, `vikunja_task`, or `parse_failure`.
4. Agent invokes the appropriate route helper per the disambiguated kind.
5. If still ambiguous after disambiguation, agent falls back to `parse_failure` handling.

### Scenario: calendar clarification flow

1. Calendar payload incomplete → `route_calendar_event` exits non-zero with structured stderr listing missing fields.
2. Agent invokes `python3 -m scripts.inbox.handle_clarification_state add --note-filename <name> --partial-payload <json>`.
3. Agent authors a single WhatsApp clarification prompt (prompt-driven judgment + voice; the message text is NOT in a helper).
4. On Kent's reply: agent invokes `python3 -m scripts.inbox.handle_clarification_state match --reply-content <text>` to find the pending entry; assembles the completed payload; re-invokes `route_calendar_event`; on success delegates to Felix main for `gog calendar create`.

### Operator scenario: bootstrap budget sanity post-deploy

After mission merge + #567's 5-min deploy tick: `ssh office2-claude 'grep "bootstrap file AGENTS.md.*truncating" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log'` returns NO matches for `felix-admin-capture` ticks within the next 24 hours.

## Domain Language

| Term | Definition |
|---|---|
| **Bootstrap budget** | openclaw's 12,000-char limit on workspace-bootstrap file injection. Files over this limit are silently truncated. Effective budget is ~14,000 chars due to ~26% rawChars inflation (per `[[reference_openclaw_gotchas]]`). |
| **Step 5 invariant** | The "do NOT delete the original file — preserve it as a record" rule that's been silently truncated since at least #185. The rewrite makes this VISIBLE in the bootstrapped prompt. |
| **Judgment surface** | A section of AGENTS.md that requires LLM reasoning (classification of ambiguous blocks, authoring clarification messages, applying edge-case rules). STAYS in the prompt. |
| **Deterministic recipe** | A section of AGENTS.md that describes file mutations, format strings, JSON construction, or other mechanically-verifiable steps. REPLACED by helper invocation. |
| **`-m` invocation form** | `python3 -m scripts.inbox.<helper>` — mandatory per NFR-002 and `[[feedback_helper_m_invocation_form]]`. |
| **Helper inventory** | The 14 helpers under `scripts/inbox/` available to the rewritten prompt: 8 existing (`append_routing_entry`, `file_inbox_quality_issue`, `handle_marker_cleanup`, `handle_parse_failures`, `inject_parse_error_marker`, `prescan`, `routing_log` *(module)*, `strip_parse_error_marker`) + 6 new from half-1 (`mark_processed`, `route_journal_entry`, `route_someday`, `route_calendar_event`, `handle_clarification_state`, `classify_content`). |
| **Output Discipline Hard Rules** | The 60-line block under `## Output discipline` in the current AGENTS.md. Load-bearing for inter-agent + WhatsApp surfaces. KEPT verbatim. |

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | The rewritten `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` is ≤14,000 source chars (target: 4,500-8,500 chars / 250-400 lines). Verifies via `wc -c scripts/openclaw/agents/felix-admin-capture/AGENTS.md`. | Specified |
| FR-002 | Every Step 1-7 deterministic recipe in the current AGENTS.md is replaced with a `python3 -m scripts.inbox.<helper>` invocation reference (not a recipe rewrite, not inline prose narration of the helper's internals). | Specified |
| FR-003 | The Output Discipline Hard Rules block (current lines 27-83) is preserved verbatim — load-bearing for inter-agent + WhatsApp output. | Specified |
| FR-004 | The Step 5 invariant ("do NOT delete the original file") is present in the rewritten prompt under a heading that lands within the first 8,000 source chars (NOT at the bottom; reading-order safety). | Specified |
| FR-005 | The rewritten prompt instructs the agent to invoke `classify_content` first (per note), then route per-block. Ambiguous blocks (`kind: "ambiguous"`, `flag: "needs-llm-disambiguation"`) get LLM disambiguation in the prompt; non-ambiguous blocks go directly to their route helpers. | Specified |
| FR-006 | The calendar clarification flow uses `handle_clarification_state add` + WhatsApp prompt (authored by the LLM via prompt judgment + voice; NOT a helper); on reply, `handle_clarification_state match` finds the pending entry; assembled payload re-validates via `route_calendar_event`. | Specified |
| FR-007 | Sibling files (`IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`) under the same agent dir are LEFT UNCHANGED unless a specific inconsistency with the rewritten AGENTS.md requires a one-line tweak. | Specified |
| FR-008 | The rewritten prompt references each helper by its EXACT module path (e.g., `python3 -m scripts.inbox.classify_content`, NOT `python3 scripts/inbox/classify_content.py`). Per `[[feedback_helper_m_invocation_form]]` (production failures TWICE). | Specified |
| FR-009 | The rewritten prompt removes ALL prose narration of helper-internal behavior. Helpers self-document via `--help` and module docstrings; the prompt only describes WHEN to invoke and HOW to interpret the output. | Specified |
| FR-010 | The rewritten prompt's classification taxonomy section (currently ~80 lines in Step 3) is replaced with a 5-10 line "consume `classify_content` output" instruction plus the disambiguation rule for `ambiguous` kind. | Specified |
| FR-011 | The Task delegation to felix-admin-tasker section (current lines 866-960) is COMPRESSED but not removed — it represents a delegation surface, not a deterministic recipe. Target compression: ~30 lines (from ~95). | Specified |
| FR-012 | The Task bridge — Vikunja task creation (fallback) section (current lines 961-end) is COMPRESSED — the new `route_someday` helper makes the inline Vikunja-create-payload prose redundant. Target compression: ~15-20 lines (from ~55). | Specified |
| FR-013 | The Goal declaration handling section (current lines 633-695) STAYS substantially intact — it's judgment-heavy (validation rules, edge cases). Minor compression where prose is redundant. | Specified |
| FR-014 | Action Logging section is COMPRESSED — replace per-action-type recipe rows with a "log action via `<existing-helper-or-pattern>`" reference. Target: ~20 lines (from ~80). | Specified |
| FR-015 | The prompt is VERIFIED to load under the openclaw 12K budget on office2 post-deploy: `grep "bootstrap file AGENTS.md.*truncating" /tmp/openclaw/openclaw-*.log` returns NO matches for `felix-admin-capture` ticks in the 24h post-deploy. (Operator post-merge verification.) | Specified |

## Non-Functional Requirements

| ID | Description | Status |
|---|---|---|
| NFR-001 | The rewritten AGENTS.md is ≤8,500 source chars (mid-target) AND ≤14,000 source chars (hard ceiling). Measured by `wc -c`. | Specified |
| NFR-002 | All helper invocations in the prompt use `python3 -m scripts.inbox.<module>` form. Script-path form forbidden per `[[feedback_helper_m_invocation_form]]`. | Specified |
| NFR-003 | The deployed file size on office2 (after #567's sync) matches the repo size. Verifies via `md5sum` parity check. | Specified |
| NFR-004 | No regression in the existing helper invocation patterns. Existing prose that already invokes a helper (e.g., Step 1 prescan invocation) is preserved or compressed but not removed. | Specified |
| NFR-005 | Operator-readable. A new operator should be able to read the rewritten AGENTS.md once and understand the inbox processing flow without needing to read any helper source. Helpers self-document via `--help`. | Specified |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | This mission MUST NOT modify any helper under `scripts/inbox/`. The 14 helpers (8 existing + 6 from half-1) are immutable inputs to this mission. | Specified |
| C-002 | This mission MUST NOT modify any other openclaw agent prompt (`scripts/openclaw/agents/felix-admin-habits/`, `felix-admin-escalation/`, `felix-admin-tasker/`, `main/`, `felix-doc-auditor/`). Scope is felix-admin-capture only. | Specified |
| C-003 | This mission's diff is on `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` only (plus optional one-line tweaks to sibling IDENTITY/SOUL/TOOLS/USER if consistency requires). NO `scripts/inbox/` changes. NO `service-inventory.json` change (the agent's source_in_repo already covers the file). | Specified |
| C-004 | Per the Felix Constitution Privacy Boundary: the rewritten prompt MUST preserve the `~/second-brain/notes/04-Growth/_private/` absolute-no-read rule verbatim. | Specified |
| C-005 | Per `[[reference_office2_agent_deploy_paths]]`: felix-admin-capture deploys to `/data/services/openclaw/inbox-agent/`. Verification commands in the runbook use that path. | Specified |
| C-006 | Risk tier 3 (Standard). Single-file logic change; no system config, no credentials, no service-inventory schema change. | Specified |
| C-007 | Per `[[feedback_speckitty_split_code_and_deploy_missions]]`: helpers from half-1 MUST be live on office2 BEFORE this mission's AGENTS.md change is deployed. Verified: half-1 merged 2026-06-08; helpers smoke-passed `python3 -m` on office2 the same day. | Specified |

## Success Criteria

1. `wc -c scripts/openclaw/agents/felix-admin-capture/AGENTS.md` returns ≤14,000 (hard ceiling), ideally 4,500-8,500.
2. After mission merge + #567's 5-min deploy tick: `ssh office2-claude 'md5sum /data/services/openclaw/inbox-agent/AGENTS.md /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-capture/AGENTS.md'` shows matching hashes.
3. After mission merge: at least one felix-admin-capture cron tick produces NO `bootstrap file AGENTS.md.*truncating` warning in `/tmp/openclaw/openclaw-<date>.log`.
4. The Step 5 invariant ("do NOT delete the original file") IS present in the rewritten prompt within the first 8,000 source chars (head -50 of the file shows it).
5. A grep over the rewritten prompt: `grep "python3 -m scripts.inbox" AGENTS.md | wc -l` returns ≥6 (one per new helper minimum, more for existing-helper invocations).
6. No regression in the 139 tests of half-1 (`pytest tests/inbox/` still passes).
7. No prose narration of helper internals: `grep -c "atomic write\|write-temp\|os.replace\|frontmatter parse" AGENTS.md` shrinks substantially (specifics-of-implementation prose moved out).

## Key Entities

| Entity | Fields | Notes |
|---|---|---|
| **Rewritten AGENTS.md** | header + sections per the structural map below | Single file deliverable |
| **ClassificationOutput** (from `classify_content`) | `note_filename`, `blocks: [{index, kind, content, confidence, flag?}]` | The prompt consumes this JSON output to route per-block |
| **Routing decision** (in-prompt judgment) | for each block: read `kind`, route via the per-kind helper; if `ambiguous`, disambiguate via prompt then route | Replaces ~80 lines of taxonomy prose |

## Structural map for the rewritten AGENTS.md

| Section | Source (current) | Target lines | Notes |
|---|---|---|---|
| Governance | lines 1-9 | KEEP | Small, unchanged |
| Header + identity | lines 11-26 | KEEP | Small |
| Output discipline Hard Rules | lines 27-83 | KEEP VERBATIM | Load-bearing |
| Processing workflow header | lines 85-89 | KEEP brief | 5 lines |
| Step 1: prescan | lines 90-178 | COMPRESS to ~5 lines | "Invoke `prescan`; consume JSON" |
| Step 1a: 24h sweep | lines 179-216 | COMPRESS to ~3 lines | Invoke `handle_clarification_state sweep` |
| Step 2: parse per file | lines 217-234 | COMPRESS to ~5 lines | Brief framing |
| Step 3: classify and route | lines 235-450 | REWRITE to ~30-40 lines | Invoke `classify_content`; per-block route via helpers; LLM disambiguates `ambiguous` |
| Step 4: file ops | lines 451-481 | COMPRESS to ~5-10 lines | Atomic-write pattern is in helpers now |
| Step 5: mark processed | lines 482-564 | REWRITE to ~10-15 lines | Invariant FIRST (FR-004), then `mark_processed` invocation, then `append_routing_entry` |
| Step 6: parse failures | lines 565-596 | COMPRESS to ~5 lines | Existing helper invocation |
| Step 7: processing log | lines 597-632 | COMPRESS to ~10 lines | Brief log surface |
| Goal declaration handling | lines 633-695 | LIGHTLY COMPRESS to ~40 lines | Judgment-heavy; small redundancies trimmed |
| File operation standards | lines 696-762 | COMPRESS to ~25-30 lines | Drop recipe details; keep structural rules |
| Privacy — absolute rule | lines 763-769 | KEEP verbatim | 7 lines |
| Edge cases | lines 770-791 | KEEP | Judgment surface |
| Action Logging | lines 792-865 | COMPRESS to ~20 lines | Drop per-action-type rows; replace with terse "log via …" pattern |
| Task delegation to tasker | lines 866-960 | COMPRESS to ~30 lines | Drop payload-shape prose; keep WHEN-to-delegate |
| Task bridge — Vikunja fallback | lines 961-end | COMPRESS to ~15-20 lines | `route_someday` makes payload prose redundant |

Estimated target total: ~250-350 lines / ~5,500-7,500 chars. Well under FR-001's ≤14,000 hard ceiling.

## Assumptions

- Helpers from half-1 are live + correct on office2 (verified by `python3 -m` smoke this session).
- openclaw bootstrap budget is 12,000 chars with ~26% rawChars inflation (~9,500 effective). Per `[[reference_openclaw_gotchas]]`.
- The agent has read the helper docstrings (or can `--help` them) for invocation-time reference; we don't need to re-document helper internals in the prompt.
- Existing helpers (8 of them) STAY untouched in this mission; the prompt continues to reference them as it does today.
- The prompt's voice (Kent's first-person framing) is preserved through judgment surfaces — voice is part of `[[reference_felix_output_discipline_pattern]]`.
- Re-deployment to office2 happens automatically via #567's 5-min agent-prompt-sync pipeline after merge to main.

## Out of Scope

- Modifying any of the 14 helpers under `scripts/inbox/` (C-001).
- Modifying other openclaw agent prompts (C-002).
- Changes to `service-inventory.json` beyond updating `last_updated` and `updated_by`.
- Changes to `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md` beyond one-line consistency tweaks.
- New helpers or new functionality. This is a PROSE → INVOCATION rewrite.
- The defensive prescan inverse check (#568 — separate mission, P2).
- Changes to felix-admin-tasker or main agent prompts.

## Architecture Documentation Updates (DIR-005)

| File | Update |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Update `services[openclaw-gateway].agents.felix-admin-capture.updated_by` to prepend this mission; bump `updated_at` to today. Update the `notes` field to reflect the post-rewrite Step 5 invariant visibility. |

This mission is intentionally narrow; no new helper components, no new state files, no new schema. The half-1 component entries (added by `capture-d6-helpers-extraction-01KTMS5Q`) accurately describe the helpers the rewritten prompt now invokes; no further entry updates needed.

## Reference Index

- Issue: kentonium3/kg-automation#566 (closes; half-1 + half-2 together)
- Parent epic: kentonium3/kg-automation#563
- Sibling sub-issues: #567 (deploy pipeline, CLOSED), #568 (prescan inverse, P2 — separate)
- Predecessor mission: `capture-d6-helpers-extraction-01KTMS5Q` (merge `ea52ad0e`, mission_number=70)
- Memory references:
  - `[[feedback_helper_m_invocation_form]]` — `-m` form mandatory; production failures TWICE
  - `[[feedback_scripts_vs_llm]]` — Directive 6 split rationale; this mission IS the canonical "drop the prose" example
  - `[[feedback_speckitty_split_code_and_deploy_missions]]` — mission boundary rationale (why split into half-1 + half-2)
  - `[[reference_openclaw_gotchas]]` — 12K bootstrap budget + ~26% rawChars inflation
  - `[[reference_office2_agent_deploy_paths]]` — felix-admin-capture → inbox-agent dir
  - `[[reference_felix_output_discipline_pattern]]` — Output Discipline Hard Rules (keep verbatim)
  - `[[reference_speckitty_3_2_rc41_quirks]]` — workflow workarounds expected on rc41
- Existing AGENTS.md: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (1215 lines / 52,942 chars at mission start)
- Half-1 helpers: `scripts/inbox/{mark_processed,route_journal_entry,route_someday,route_calendar_event,handle_clarification_state,classify_content}.py`
- Half-1 contracts: `kitty-specs/capture-d6-helpers-extraction-01KTMS5Q/contracts/helper-cli.md`
