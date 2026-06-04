---
affected_files: []
cycle_number: 2
mission_slug: felix-vikunja-sync-architecture-research-01KT7Q15
reproduction_command:
reviewed_at: '2026-06-04T00:07:33Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

# WP01 Review — Cycle 1

**Verdict**: Changes requested.

**Reviewer**: claude:opus:reviewer:reviewer
**Reviewed**: 2026-06-03

---

## What's working

- **Probe transcripts (probe-transcripts.md)**: All 12 probes (info, tasks/all, tasks/{id}, projects, 5 filter probes, batch, webhook, updated_since) are raw, paginated, and reproducible. Token correctly redacted. This is the strongest deliverable.
- **RQ-1 stable-identifier matrix** (rq-1-vikunja-api.md §4): Fully populated across all 5 columns (candidate / stability_under_edit / stability_under_delete_recreate / cross_project_uniqueness / surfaced_in_ui / verdict) for 4 candidates with clear verdicts and rationale. Hits FR-001 and data-model.md cleanly.
- **G6/G7 filter status update** (rq-1 §5.2): Live re-probes confirm single-clause filters work; G7 compound rejection scoped correctly. Good update to memory `reference_vikunja_filter_gotchas`.
- **RQ-5 pattern fit** (rq-5-pattern-fit.md): All 4 patterns have explicit `extend` verdicts with structural-shape + mapping-table + rationale. Summary matrix at the end is operator-readable cold. Cross-pattern observation ("no pattern requires replacement") is well-supported.
- **CSV discipline**: source-register.csv has 48 rows; evidence-log.csv has 32 rows with confidence levels and notes. Header comments document conventions cleanly. NFR-001 (sourcing) is strong for the claims that ARE inventoried.
- **Deferred-to-implementation sections**: All 3 RQ files have them, with substantive parking-lot items (batch-write semantics, in-prompt agent callsites, state_log schema extension, etc.). Not hand-waved.
- **Grep 1 verbatim + reproducible** (rq-2 §Grep 1): Re-ran by reviewer — same 23 files matched. FR-004 satisfied for the broad sweep itself.

---

## Required changes (must-fix to approve)

### Required-1: FR-004 — missing inventory or exclusion for 2 files from broad grep

The acceptance gate (plan.md § RQ-2 / task prompt T003) is explicit: **"Every file from the broad grep is either inventoried or explicitly excluded with reason."** Two files from Grep 1's 23-file output are neither inventoried as a TP- row nor explicitly excluded:

- **`scripts/escalation/hard_fail.py`** — appears in Grep 1 output (rq-2-touchpoints.md line 32). The only match is a comment-string reference at line 339 (`https://office2.tail0f5f56.ts.net/tasks/1234`); no HTTP calls. **Action**: add an explicit exclusion entry in rq-2 § Notes naming the file and the reason ("comment-only mention; no runtime API call").
- **`scripts/habits/query_active_habits.py`** (v1) — appears in Grep 1 output (rq-2-touchpoints.md line 40). This file IS an active Vikunja touchpoint: imports `urllib.request`, defines `_http_get`, calls `GET /projects` (line 118) and `GET /projects/{id}/tasks` (line 133), uses the canonical `DEFAULT_BASE_URL` constant. It is mentioned only obliquely in the Deferred-to-implementation section ("may be superseded by `_v2` counterparts"). **Action**: either add a TP- row for this file (preferred — it's a real touchpoint), or move it to an explicit exclusion entry naming the deployment status that justifies exclusion. "Active status deferred to implementation" is not an exclusion reason — it's an inventory question the implementer of WP02 still needs answered.

Why this matters: WP02 reads this substrate to build RQ-4 (use-case → layer mapping). An active read-touchpoint absent from the inventory undercounts the habits-agent's task-layer surface area and risks RQ-4 missing a polling-cadence dependency.

### Required-2: FR-004 — "one row per callsite, not per file" violated at TP-17

TP-17 bundles **three** distinct provisioning scripts into a single row:
- `scripts/vikunja/provision_felix_bot.py`
- `scripts/vikunja/validate_felix_bot.py`
- `scripts/vikunja/swap_vikunja_secrets.py`

`data-model.md` § Touchpoint says "One row per callsite, not per file" — three files with combined ~28 functions cannot be one touchpoint. The bundled row also conflates verbs (`GET, PUT, POST`) and endpoints (`/projects/{id}/users`, `/api/v1/register`) such that the row is no longer queryable as a touchpoint record.

**Action**: split TP-17 into separate rows per file (and per distinct callsite within a file, if functions touch distinct endpoints). At minimum:
- `provision_felix_bot.py`: separate row(s) for registration vs project-sharing callsites.
- `validate_felix_bot.py`: row for the verification callsite(s).
- `swap_vikunja_secrets.py`: row for the secret-rotation callsite(s).

Bonus observation: the numbering skips TP-16 with no explanation. Either re-number for contiguity or note the skip.

### Required-3: FR-004 — Grep 3 output labeled "representative", not exhaustive

rq-2-touchpoints.md § Grep 3 says: **"Output (key findings, representative)"**. FR-004 requires exhaustive enumeration. "Representative" is the opposite of "exhaustive."

**Action**: either (a) capture the verbatim Grep 3 output in full (matching the Grep 1 treatment), or (b) re-frame Grep 3 as a per-file confirmation step (not a discovery step) and remove the "representative" label. The discovery work happened in Grep 1; if Grep 3 is just confirming endpoints already covered, say that and remove the truncation.

### Required-4: NFR-006 — Auth Model claim has no probe support

rq-1-vikunja-api.md §8 says: "Token type: long-lived Bearer token (prefix `tk_`, 43 characters). Stored at `/data/services/openclaw/secrets/vikunja-api`. observed (probe session token length)"

There is no probe in probe-transcripts.md that captures this. The transcripts intro mentions the token length as context for the session, but that is not a probe row. NFR-006 requires API claims tagged `observed (probe transcript row)` or `documented (URL)`.

**Action**: either (a) re-tag this as `documented (source-register row mem-... or doc-...)` if it traces to a memory/doc, or (b) add a probe transcript that captures the token format verifiably (e.g., a GET /tokens listing the bot's token metadata — read-only, in scope), or (c) downgrade the specificity (drop the 43-character claim if it's not load-bearing).

---

## Suggested changes (optional polish; do not block approval on these)

- **Suggested-1**: TP-17 numbering skip (TP-16 absent). If you re-split TP-17 anyway (Required-2), close this gap as a side effect.
- **Suggested-2**: evidence-log.csv row at line 46 has `source_type=api_probe` but the citation describes a JSONL file read on office2 (`habits-history.jsonl head -2 on 2026-06-03`). Source type should probably be `code` or a new `file` type — the field doesn't trace to an API endpoint. Minor consistency.
- **Suggested-3**: rq-1 §5.1 row "Combined AND" tagged `documented (verified task #63)` — "verified task #63" is opaque. Consider citing the specific evidence-log row or source-register entry that demonstrates this.
- **Suggested-4**: rq-2 § Cross-Agent Touchpoint Summary table is a great synthesis, but the "inbox/capture-agent" row has no corresponding TP- row in the inventory (it is referenced as "via tasker"). If capture-agent touches Vikunja indirectly via the tasker, the summary should say "indirect" or omit the row to avoid confusion when re-deriving touchpoint counts from the TP- rows.

---

## Notes for re-implementation

- The substrate is **substantively strong**. The required changes are inventory-rigor fixes (FR-004 enforcement), not structural rewrites. None of the existing tables, probes, or pattern verdicts need to be discarded.
- After re-inventory, also re-validate the `read_touchpoints_count` / `write_touchpoints_count` derivable from the inventory — these populate the Sync Layer entity in data-model.md and WP02 reads them.
- The CSV append-only rule is satisfied (no rows from other WPs exist yet to overwrite). Continue the discipline in the re-implementation: append only.
