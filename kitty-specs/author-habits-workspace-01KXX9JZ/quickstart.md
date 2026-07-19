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

## 3. Content conservation (NFR-003)

Verify the `data-model.md` invariants by grep:
- `04-Growth/_private/` present in AGENTS.md + TOOLS.md, absent in SOUL.md
- weekly-out-of-scope statement present in AGENTS.md, absent in SOUL.md
- date-handling present in TOOLS.md, absent in USER.md
- no `id=13` / `14-20` in TOOLS.md
- no "report on patterns" reporting claim in USER.md
- `## Voice` present in SOUL.md; no `## Purpose` in SOUL.md

## 4. Behavior preservation (NFR-004)

Before editing, capture the morning-list helper output for a fixed date; after editing (prompt-only changes should not affect it), confirm identical. (Prompt files do not change helper output — this is a guard, not an expected diff.) Confirm the de-inline assumption from research.md Decision 3: the helper resolves the Habits project by name, not from a TOOLS literal.

## 5. Merge to main (operator)

Merge `feat/author-habits-workspace` → `main`. Record the rebaseline decision in the merge commit: `Rebaseline: not required — agent prompt content only; not a hashed audited surface (#621)`.

## 6. Confirm agent-prompt-sync deploy (operator)

agent-prompt-sync (`deploy_agent_prompts.py`) pulls main every ~5 min on office2 and copies the five workspace files. Confirm the sync tick ran post-merge:
```bash
ssh office2-claude 'tail -5 /data/services/openclaw/logs/agent-prompt-sync.jsonl'   # path confirmed at deploy
```

## 7. Verify deploy directory + md5 parity (FR-010, NFR-005)

**First confirm the habits deploy directory** (agent slug ≠ deploy dir):
```bash
ssh office2-claude 'find /data/services/openclaw -maxdepth 2 -name SOUL.md | grep -i habit'
```
Then compare md5 of each of the 5 files repo↔office2 at the merged commit.

## 8. Live smoke (Success Criterion 5)

Trigger / observe a habits morning check-in and confirm the message is Kent-voice and behaviorally unchanged (same habits listed, same completion-comment flow). No weekly-report behavior appears.

## 9. Close-out

- Close #582 with the merge commit hash.
- Confirm #409 stays closed with a pointer to this mission (FR-011).
- Update the resume-anchor memory; #586 tasker is next.

## Rollback

Revert the merge commit; agent-prompt-sync re-syncs the prior file contents on the next tick. No state migration to unwind.
