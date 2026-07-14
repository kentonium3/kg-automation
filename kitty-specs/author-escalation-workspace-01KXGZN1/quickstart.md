# Quickstart: Author felix-admin-escalation workspace

Operator + implementer runbook. Sections §1–§3 are in-mission (WP); §4–§9 are **post-merge, operator-owned** acceptance (excluded from the acceptance matrix per C-006).

## §1. Author (in-lane)

Edit only these files:

- `scripts/openclaw/agents/felix-admin-escalation/SOUL.md` — voice/stance only; trim `## Purpose` role (keep a one-line insistence stance), reduce `## Privacy boundary` to a one-line stance (drop path + mission-026 changelog), trim the "Kent has ADD…" justification off the chunked bullet.
- `scripts/openclaw/agents/felix-admin-escalation/USER.md` — remove `## Date handling`; keep the person-view + `## Context`.
- `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md` — add the moved `## Date handling`; change `project_id NOT IN (11, 13)` → `NOT IN (13)`; drop the `11 | Goals` row; leave the `_private` path line unchanged.
- `scripts/vikunja/setup_vikunja.py` — delete the "Goals" saved-filter block (`project = 11 && done = false`).

Do NOT touch AGENTS.md, IDENTITY.md, the `_private` path, or any other agent.

## §2. Validate (in-lane)

```bash
cd /Users/kentgale/repos/kg-automation
python3 -m scripts.openclaw.agents.validate_workspace --json
```

Expect `felix-admin-escalation` → `ok: true` (both invariants pass).

Run the openclaw agent suite:

```bash
python3 -m pytest scripts/openclaw/agents/tests tests/openclaw -q
```

## §3. Conservation + scope check (in-lane)

```bash
# Date-handling landed in TOOLS, gone from USER:
grep -n "America/New_York\|-04:00\|no Z\|Z (UTC)" scripts/openclaw/agents/felix-admin-escalation/TOOLS.md
grep -c "Date handling" scripts/openclaw/agents/felix-admin-escalation/USER.md   # expect 0

# Goals(11) gone from TOOLS + setup script:
grep -n "11" scripts/openclaw/agents/felix-admin-escalation/TOOLS.md | grep -i "goal\|NOT IN"   # expect no 11
grep -in "goals\|project = 11\|project_id.*11" scripts/vikunja/setup_vikunja.py   # expect none

# Enforceable privacy rule still in AGENTS + TOOLS:
grep -l "_private" scripts/openclaw/agents/felix-admin-escalation/AGENTS.md scripts/openclaw/agents/felix-admin-escalation/TOOLS.md

# Scope: only the four files (+ mission artifacts) changed:
git diff --name-only main...HEAD -- scripts/
```

## §4. Baseline BEFORE merge (operator)

agent-prompt-sync deploys on merge-to-main. Record the current deployed md5s first (for parity comparison):

```bash
ssh office2-claude 'md5sum /data/services/openclaw/data/felix-admin-escalation/{SOUL,USER,TOOLS,AGENTS,IDENTITY}.md'
```

## §5. Merge feat → main (operator)

After the mission `spec-kitty merge` lands WPs on `feat/author-escalation-workspace` and the post-merge Codex review is clean:

```bash
git switch main && git merge --no-ff feat/author-escalation-workspace \
  -m "feat: author felix-admin-escalation workspace to #587 standard (#585)

Closes #585. Closes #724.
Rebaseline: not required — #621 (agent prompt files not hashed by audit.sh)"
git push origin main
```

## §6. Verify agent-prompt-sync deploy (operator)

```bash
ssh office2-claude 'tail -5 /data/services/openclaw/logs/agent-prompt-sync.jsonl'   # expect a sync at the merged git_head, files_copied includes escalation
ssh office2-claude 'md5sum /data/services/openclaw/data/felix-admin-escalation/{SOUL,USER,TOOLS}.md'
```

Compare each to the repo copy's md5 at the merged commit (NFR-005 parity). SOUL/USER/TOOLS md5s must change from §4; AGENTS/IDENTITY must NOT change.

## §7. Session rotation + gateway restart (operator, if used) — C-007

If a session rotation is performed to pick up the new prompt, pair it with a gateway restart (rotation can wedge the live WhatsApp DM lane — #583 gotcha #11). Note: the restart flushes the in-memory queue, so re-run the smoke fresh afterward.

## §8. Live smoke test (operator) — NFR-004

Trigger an escalation tick (or wait for the daily cron) and confirm:
- the message shape is correct (identity line `Sent by felix-admin-escalation:<model>`, or the `[felix-admin-escalation]: IDLE` marker on a no-op tick);
- the candidate set is unchanged (Goals(11) exclusion was already a no-op post-#717);
- date handling still resolves in America/New_York (ET offset, no Z suffix).

## §9. Close out (operator)

- Close #585 and #724 with the merge commit hash (auto-closed by the merge message).
- Confirm #732 remains open (deferred fleet path cleanup).
- Update the #167 active-threads memory: escalation done → next child is tasker #586.

## Rollback

If the deploy misbehaves: `git revert` the feat→main merge and push; agent-prompt-sync re-syncs the prior files on the next tick. No manifest / rebaseline to unwind (rebaseline was "not required").
