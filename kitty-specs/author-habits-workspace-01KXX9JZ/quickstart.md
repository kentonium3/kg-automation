# Quickstart: Author felix-admin-habits workspace

Operator + implementer runbook. Steps 1–4 are in-mission (the WP). Steps 5–9 are operator-owned post-merge acceptance (excluded from the acceptance matrix, C-006).

## 1. Author the three files (IC-01)

Apply the `data-model.md` move-table to:
- `scripts/openclaw/agents/felix-admin-habits/SOUL.md` — voice + one-line privacy stance (FR-001..004)
- `scripts/openclaw/agents/felix-admin-habits/USER.md` — filtered person-view; remove date-handling; correct scope claim (FR-005, FR-006)
- `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` — de-inline IDs; receive date-handling; keep completion contract (FR-007, FR-008)
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — only if it names SOUL as a privacy-enforcement home (FR-009); else untouched
- Do **not** edit `IDENTITY.md`.

## 2. Validate the invariants (NFR-001)

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```
Assert the `felix-admin-habits` object has `ok: true` (habits-scoped; do NOT rely on whole-fleet exit code — calendar/#635 fails Invariant B).

## 3. Content conservation — row-by-row (NFR-003, Finding 3)

Grep alone is too coarse (it would pass even if a substantive sub-block were dropped). Walk the `data-model.md` move-table row by row and confirm each:

**SOUL.md**
- [ ] `## Voice — write as Kent` retained: Principles list, "Words and phrases to avoid", "Words and phrases that are Kent" all present
- [ ] "Structured and chunked" style rule retained; only the "Kent has ADD…" justification trimmed
- [ ] `## Purpose` gone; no role text remains
- [ ] `## Weekly report — out of scope` block gone (single copy now only in AGENTS)
- [ ] `## Privacy boundary` reduced to a one-line stance; enforceable rule + path + mission-026/#152 changelog gone from SOUL

**USER.md**
- [ ] Name / call / timezone / Notes (incl. "ADD (managed)") retained
- [ ] `## Context` retained but the "report on patterns over time" claim removed; concise-WhatsApp guidance retained
- [ ] `## Date handling` gone from USER

**TOOLS.md**
- [ ] `## Vikunja API` (skill pointer) retained; `id=13` and `14-20` literals gone; `vikunja_refs.json` named as canonical id source
- [ ] `## Habit completion storage` (one-task-per-habit, comment format, idempotent) retained verbatim in substance
- [ ] `## Privacy` (enforceable path) retained byte-unchanged
- [ ] date-handling section received from USER

**AGENTS.md**
- [ ] Unchanged except FR-009 (only if it named SOUL as a privacy-enforcement home)

**Cross-file invariants**
- [ ] `04-Growth/_private/` present in AGENTS.md + TOOLS.md, absent in SOUL.md
- [ ] weekly-out-of-scope present in AGENTS.md, absent in SOUL.md
- [ ] date-handling present in TOOLS.md, absent in USER.md

## 4. Behavior preservation — two guards (NFR-004, Finding 2)

**(a) Scope-creep guard (NOT a prompt-behavior gate):** capture morning-list helper output for a fixed date before and after; confirm identical. A prompt-only edit *cannot* change deterministic helper output, so this only proves no helper/config file was accidentally touched.

**(b) Prompt-behavior guard (the real check):** static-diff the AGENTS.md tick/reply workflow — confirm the workflow commands, the relay-verbatim rule, the Output Discipline block, the completion-marking flow, and the habit-management rules are byte-identical (AGENTS is not edited except FR-009). Then the **live smoke** (step 8) is the actual prompt-mediated behavior verification.

Note (research.md Decision 3, corrected): the deterministic helpers resolve the Habits project via `scripts/common/vikunja_refs.json` and the task set via sync-cache + `phase3-schedule.yaml` + morning artifact — they do NOT read TOOLS — so the de-inline is safe.

## 4b. Repo-wide weekly-report doc coherence (FR-012, Finding 4)

Correct the weekly-report rows of `docs/design/architecture/service-inventory.md` (the rows describing a weekly OpenClaw cron via `felix-admin-habits`) to match `service-inventory.json`, which correctly attributes weekly reporting to the `felix-habits-weekly` timer (#723). Bounded to the weekly-report lines. Re-run `validate_architecture_data` (pre-commit runs it) to confirm JSON↔MD coherence.

## 5. Merge to main (operator)

Merge `feat/author-habits-workspace` → `main`. Record the rebaseline decision in the merge commit: `Rebaseline: not required — agent prompt content only; not a hashed audited surface (#621)`.

## 6. Confirm agent-prompt-sync deploy (operator)

agent-prompt-sync (`deploy_agent_prompts.py`) pulls main every ~5 min on office2 and copies the five workspace files. Confirm the sync tick ran post-merge (Finding 5 — correct audit path):
```bash
ssh office2-claude 'tail -5 /data/services/openclaw/deploy/agent-prompt-sync.jsonl'
```

## 7. Verify deploy directory + md5 parity (FR-010, NFR-005)

The habits deploy directory is **`/data/services/openclaw/habits-agent/`** (per `service-inventory.json`; agent slug ≠ deploy dir — Finding 5). Confirm, then compare md5 of each of the 5 files repo↔office2 at the merged commit:
```bash
ssh office2-claude 'ls /data/services/openclaw/habits-agent/'
```

## 8. Live smoke (Success Criterion 5)

Trigger / observe a habits morning check-in and confirm the message is Kent-voice and behaviorally unchanged (same habits listed, same completion-comment flow). No weekly-report behavior appears.

## 9. Close-out

- Close #582 with the merge commit hash.
- Confirm #409 stays closed with a pointer to this mission (FR-011).
- Update the resume-anchor memory; #586 tasker is next.

## Rollback

Revert the merge commit; agent-prompt-sync re-syncs the prior file contents on the next tick. No state migration to unwind.
