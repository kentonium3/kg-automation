---
work_package_id: WP01
title: AGENTS.md rewrite + arch-doc update
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- FR-014
- FR-015
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
agent: claude
history: []
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
mission_id: 01KTMY86X63W50FF36GWPWADH2
mission_slug: capture-agents-md-rewrite-01KTMY86
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- docs/design/architecture/data/service-inventory.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

Curator posture: voice-aware, structurally clear, no aspirational claims, no speculative descriptions. This rewrite preserves Kent's first-person voice in judgment surfaces.

## Objective

Rewrite `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` from 1,215 lines (52,942 chars) to 250-400 lines (target 4,500-8,500 chars; hard ceiling 14,000) by:
1. Replacing deterministic Step 1-7 recipes with `python3 -m scripts.inbox.<helper>` invocation references.
2. Keeping ALL LLM-judgment surfaces (Output Discipline Hard Rules verbatim, Goal declaration validation, Privacy absolute rule, Edge cases, Task delegation framing).
3. Moving the Step 5 invariant ("do NOT delete the original file") to the first 8,000 chars of the file.

Then update `docs/design/architecture/data/service-inventory.json` to record this change.

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § Structural map | The section-by-section rewrite plan (current source → target lines) |
| [../spec.md](../spec.md) § Functional Requirements | FR-001..014 (size, invariant location, helper-reference patterns) |
| `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` | The current 1,215-line file to rewrite |
| `kitty-specs/capture-d6-helpers-extraction-01KTMS5Q/contracts/helper-cli.md` | The CLI contracts for the 6 new helpers (invocation reference) |
| `scripts/inbox/` (8 existing helpers) | Read each helper's docstring/`--help` output to understand what it does — but DON'T narrate that in the prompt |

## Subtask Guidance

### T001 — Rewrite AGENTS.md per structural map

Read the current file end-to-end first to understand each section. Then rewrite per the structural map in spec.md, applying these rules:

**KEEP verbatim** (do not edit these):
- `## Governance` block (lines ~1-9)
- `## Authority` (lines ~13-17)
- `## Message identity` (lines ~18-26)
- `## Output discipline` (lines ~27-83) — load-bearing Hard Rules per `[[reference_felix_output_discipline_pattern]]`
- `## Privacy — absolute rule` (lines ~763-769)

**KEEP with light compression** (preserve judgment + voice; trim redundancies only):
- `## Edge cases` (~22 lines → ~15-20 lines)
- `## Goal declaration handling` (~63 lines → ~40 lines)

**COMPRESS to terse invocation references** (these are deterministic recipes being replaced):
- Step 1 prescan → `python3 -m scripts.inbox.prescan` (5-line section)
- Step 1a sweep → `python3 -m scripts.inbox.handle_clarification_state sweep` (3-line section)
- Step 2 parse → 5-line framing
- Step 3 classify+route → invoke `python3 -m scripts.inbox.classify_content --content-file <note>`, consume `ClassificationOutput` JSON, per block: route via the per-kind helper. Ambiguous blocks (kind: `"ambiguous"`, flag: `"needs-llm-disambiguation"`): disambiguate via LLM judgment. Target: ~30-40 lines total
- Step 4 file ops → 5-10 lines
- **Step 5 mark processed** → **Step 5 invariant FIRST (this is FR-004; it MUST land in the first 8,000 chars of the file)**: "do NOT delete the original file — preserve it as a record of what came in". Then `python3 -m scripts.inbox.mark_processed --path <note>`. Then `python3 -m scripts.inbox.append_routing_entry`. Target: ~10-15 lines.
- Step 6 parse failures → `python3 -m scripts.inbox.handle_parse_failures` (5-line section)
- Step 7 processing log → 10-line framing
- `## Action Logging` → compress to ~20 lines (drop per-action-type rows)
- `## Task delegation to felix-admin-tasker` → compress to ~30 lines (keep WHEN-to-delegate; drop payload prose)
- `## Task bridge — Vikunja task creation (fallback)` → compress to ~15-20 lines (`route_someday` makes payload prose redundant)
- `## File operation standards` → compress to ~25-30 lines (drop atomic-write recipe; helpers handle it)

**REWRITE for FR-004 ordering** — the Step 5 invariant ("do NOT delete the original file") MUST appear within the first 8,000 chars of the file. Verify by inspection.

**Voice preservation in judgment surfaces** — keep Kent's first-person framing in: Edge cases, Goal declaration, Output Discipline Hard Rules, Privacy, Task delegation framing.

**Helper invocation form** — every helper reference MUST be `python3 -m scripts.inbox.<helper>` (NEVER `python3 scripts/inbox/<helper>.py`). Production failures TWICE per `[[feedback_helper_m_invocation_form]]`.

### T002 — Verify hard-ceiling + mid-target

```bash
wc -c scripts/openclaw/agents/felix-admin-capture/AGENTS.md
```

Must be ≤14,000 (hard ceiling per NFR-001). Ideal range: 4,500-8,500 chars (mid-target). If above 14,000: shrink further.

### T003 — Verify Step 5 invariant placement + `-m` form + no helper-reference regression

```bash
# FR-004: Step 5 invariant in first 8,000 chars
head -c 8000 scripts/openclaw/agents/felix-admin-capture/AGENTS.md | grep -i "do NOT delete\|preserve"

# NFR-002: no script-path form
grep -E "python3 scripts/inbox/" scripts/openclaw/agents/felix-admin-capture/AGENTS.md
# (must return zero matches)

# FR-005: at least 6 -m invocations (one per new helper minimum)
grep -c "python3 -m scripts.inbox" scripts/openclaw/agents/felix-admin-capture/AGENTS.md
# (must return >= 6; ideally 12-14 for all helpers referenced)

# Each new helper from half-1 is referenced
for h in mark_processed route_journal_entry route_someday route_calendar_event handle_clarification_state classify_content; do
  matches=$(grep -c "$h" scripts/openclaw/agents/felix-admin-capture/AGENTS.md)
  echo "$h: $matches"
done
# (each must be >= 1)

# No existing-helper invocation regression: each of the 8 existing helpers is still referenced where the current file references it
for h in append_routing_entry file_inbox_quality_issue handle_marker_cleanup handle_parse_failures inject_parse_error_marker prescan strip_parse_error_marker; do
  matches=$(grep -c "$h" scripts/openclaw/agents/felix-admin-capture/AGENTS.md)
  echo "$h: $matches"
done
# (each must be >= 1; routing_log is a module not a CLI so it may not appear directly)
```

### T004 — Update `service-inventory.json` capture entry

Locate `services[?(@.name=="openclaw-gateway")].agents.felix-admin-capture` in `docs/design/architecture/data/service-inventory.json`. Update:

- `updated_by`: prepend `"capture-agents-md-rewrite-01KTMY86 (#566) + "` to the existing value
- `updated_at`: bump to today (2026-06-08)
- `notes`: append a sentence describing the structural rewrite — e.g., "Post-mission `capture-agents-md-rewrite-01KTMY86` (2026-06-08): AGENTS.md rewritten from 52,942 chars → ~XXXX chars per Felix Constitution Directive 6; deterministic recipes extracted to `scripts/inbox/` helpers (6 new from `capture-d6-helpers-extraction-01KTMS5Q` + 8 existing); Step 5 invariant ('do NOT delete the original file') now visible in the first 8K chars."
- Bump top-level `last_updated` to today.
- Prepend this mission to top-level `updated_by`.

Verify JSON validity:

```bash
python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json')); print('OK')"
```

## Definition of Done

- [ ] `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` rewritten per structural map
- [ ] `wc -c AGENTS.md` returns ≤14,000 (hard ceiling); ideally ≤8,500
- [ ] Step 5 invariant present in first 8,000 chars (FR-004)
- [ ] All 6 new helpers from half-1 referenced by `-m` form (FR-005, FR-008)
- [ ] No script-path-form helper references (NFR-002)
- [ ] All 8 existing helpers still referenced where the current file uses them (no regression)
- [ ] Output Discipline Hard Rules block preserved verbatim (FR-003)
- [ ] Privacy absolute rule preserved verbatim (C-004)
- [ ] Goal declaration handling section retained (judgment-heavy; FR-013)
- [ ] `service-inventory.json` updated and parses cleanly (T004)
- [ ] `pytest tests/inbox/` still returns 139 passing (regression sanity)
- [ ] Lane committed; WP moved to `for_review`

## Risks

- **Voice drift**: be especially careful in compressed sections to keep Kent's first-person framing intact wherever judgment + voice were intertwined.
- **Invariant location**: the Step 5 invariant MUST land in the first 8,000 chars. If your rewrite has the invariant at line 200 but the file is 12K chars at that point, you're at risk. Restructure if needed.
- **Over-compression**: don't sacrifice operator readability (NFR-005) for size. The mid-target (4,500-8,500) leaves headroom for clarity.

## Reviewer expectations (for the review WP)

- Confirm hard-ceiling met
- Confirm Step 5 invariant location
- Spot-check 3 judgment surfaces for voice preservation
- Verify `-m` form for every helper reference
- Verify no judgment surface inadvertently trimmed
- Confirm JSON validity post-edit
