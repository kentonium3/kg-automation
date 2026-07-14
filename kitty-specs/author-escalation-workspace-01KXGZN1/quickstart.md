# Quickstart: Author felix-admin-escalation workspace

Operator + implementer runbook. §1–§3 are in-mission (WP); §4–§9 are **post-merge, operator-owned** acceptance (excluded from the acceptance matrix per C-006). Updated after the post-plan Codex review (see `contracts/post-plan-review-resolutions.md`).

## §1. Author (in-lane)

Edit exactly this file set (NFR-002):

- `scripts/openclaw/agents/felix-admin-escalation/SOUL.md` — voice/stance only; trim `## Purpose` role (keep a one-line insistence stance), reduce `## Privacy boundary` to a one-line stance (drop path + mission-026 changelog), trim the "Kent has ADD…" justification off the chunked bullet.
- `.../USER.md` — remove `## Date handling`; keep the person-view + `## Context`.
- `.../TOOLS.md` — add the moved `## Date handling`; change `project_id NOT IN (11, 13)` → `NOT IN (13)`; drop the `11 | Goals` row; **fix the reschedule example** `"...T00:00:00Z"` → ET-offset form `"...T00:00:00-04:00"` (note: `-05:00` during EST); leave the `_private` path line unchanged.
- `.../AGENTS.md` — **two narrow edits only**: (1) reschedule example `"<YYYY-MM-DD>T00:00:00Z"` → ET-offset form; (2) the sentence "…enforced in SOUL.md, AGENTS.md, and TOOLS.md" → "…enforced in AGENTS.md and TOOLS.md (SOUL carries only a behavioral stance)". No other AGENTS change.
- `scripts/openclaw/skills/escalation/SKILL.md` — remove the Goals(11) refs (`:50` "NOT 11 (Goals)", `:60` "Goals project (ID 11)").
- `docs/runbooks/escalation-ops.md` — remove Goals/id=11 from the excluded-projects prose (`:31, :34`).
- `scripts/vikunja/setup_vikunja.py` — delete the "Goals" saved-filter block (`project = 11 && done = false`).
- `tests/escalation/test_enumerate_candidates.py` — switch the generic exclusion test off `project_id=11`/`[11, 13]` to a non-Goals excluded id (preserve the assertion).

Do NOT touch IDENTITY.md, the `_private` path (→ #732), or any other agent.

## §2. Validate — escalation-SCOPED (in-lane)

Whole-fleet `validate_workspace.py` exits 1 today (calendar/#635 fails Invariant B, out of scope). Assert escalation specifically:

```bash
cd /Users/kentgale/repos/kg-automation
python3 -m scripts.openclaw.agents.validate_workspace --json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); w=next(x for x in d['workspaces'] if x['workspace']=='felix-admin-escalation'); print('escalation ok:', w['ok']); sys.exit(0 if w['ok'] else 1)"
```

Expect `escalation ok: True` (exit 0). Then the openclaw suite:

```bash
python3 -m pytest scripts/openclaw/agents/tests tests/openclaw tests/escalation -q
```

## §3. Conservation + scope checklist (in-lane) — row-by-row (NFR-003)

```bash
E=scripts/openclaw/agents/felix-admin-escalation
# SOUL is voice/stance only:
grep -q "^## Voice" $E/SOUL.md && echo "OK: Voice kept"
! grep -q "^## Purpose" $E/SOUL.md && echo "OK: Purpose removed from SOUL"
! grep -qi "Kent has ADD" $E/SOUL.md && echo "OK: ADD justification trimmed"
grep -qi "insisten" $E/SOUL.md && echo "OK: insistence stance present"
# Privacy: enforceable token in BOTH AGENTS+TOOLS, ABSENT from SOUL (MED-6):
grep -q "_private" $E/AGENTS.md && grep -q "_private" $E/TOOLS.md && ! grep -q "_private" $E/SOUL.md \
  && echo "OK: privacy in AGENTS+TOOLS, absent from SOUL"
# Date-handling moved to TOOLS, gone from USER:
grep -q "America/New_York" $E/TOOLS.md && ! grep -qi "Date handling" $E/USER.md && echo "OK: date-handling moved"
# No-Z coherence: no due_date Z-example remains in TOOLS or AGENTS:
! grep -qE 'due_date.*T00:00:00Z' $E/TOOLS.md $E/AGENTS.md && echo "OK: Z reschedule examples fixed"
# AGENTS enforcement sentence corrected:
! grep -q "enforced in SOUL.md, AGENTS.md, and TOOLS.md" $E/AGENTS.md && echo "OK: enforcement sentence fixed"
# Goals(11) fully gone from all active surfaces:
! grep -rn "11" $E/TOOLS.md | grep -qi "goal\|NOT IN" && echo "OK: TOOLS Goals(11) gone"
! grep -qi "goals\|project = 11" scripts/vikunja/setup_vikunja.py && echo "OK: setup_vikunja Goals gone"
! grep -qi "11 (Goals)\|Goals project (ID 11)" scripts/openclaw/skills/escalation/SKILL.md && echo "OK: SKILL Goals(11) gone"
! grep -qi "Goals project (id=11)\|Goals project (id 11)" docs/runbooks/escalation-ops.md && echo "OK: runbook Goals(11) gone"
# IDENTITY untouched:
git diff --quiet main...HEAD -- $E/IDENTITY.md && echo "OK: IDENTITY unchanged"
# Scope: only the expected files changed under scripts/ + docs/ + tests/:
git diff --name-only main...HEAD -- scripts/ docs/ tests/
```

## §4. Baseline BEFORE merge (operator) — correct dest

agent-prompt-sync deploys the 5 workspace files on merge-to-main. Record current md5s at the **correct** dest (`escalation-agent/`, NOT `data/felix-admin-escalation/` — Codex HIGH-3):

```bash
ssh office2-claude 'md5sum /data/services/openclaw/escalation-agent/{SOUL,USER,TOOLS,AGENTS,IDENTITY}.md'
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

## §6. Verify agent-prompt-sync deploy (operator) — NFR-005

```bash
ssh office2-claude 'tail -5 /data/services/openclaw/logs/agent-prompt-sync.jsonl'   # sync at merged git_head, escalation among files_copied
ssh office2-claude 'md5sum /data/services/openclaw/escalation-agent/{SOUL,USER,TOOLS,AGENTS,IDENTITY}.md'
```

Compare to each repo file's md5 at the merged commit. SOUL/USER/TOOLS/AGENTS md5s must change from §4; IDENTITY must NOT change.

## §7. SKILL.md sync + session rotation (operator)

**§7a — SKILL.md is NOT agent-prompt-sync'd** (that pipeline handles only the 5 workspace files, `deploy_agent_prompts.py:61`). Verify how `~/.openclaw/skills/escalation/SKILL.md` on office2 is kept in sync and update it (manually if there is no automated skill sync). Confirm the deployed copy no longer references Goals(11).

**§7b — session rotation + gateway restart (C-007)**: if a session rotation is performed to pick up the new prompt, pair it with `openclaw gateway restart` (rotation can wedge the live WhatsApp DM lane — #583 gotcha #11). The restart flushes the in-memory queue, so re-run the smoke fresh afterward.

## §8. Deterministic behavior evidence + live smoke (operator) — NFR-004

**Deterministic (primary evidence):** the candidate set is computed by the helper, not the prompt — capture before/after and assert identical:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.escalation.enumerate_candidates' > after.json
# compare candidate task_ids + due_date formatting against a pre-merge capture
```

Expect identical candidate IDs (the Goals(11) exclusion was already a no-op post-#717; `vikunja_scope.py` already excludes only `[13]`).

**Live smoke:** trigger an escalation tick (or wait for the daily cron) and confirm the message shape (identity line `Sent by felix-admin-escalation:<model>`, or `[felix-admin-escalation]: IDLE` on a no-op tick) and that any reschedule write uses the ET offset (no `Z`).

## §9. Close out (operator)

- Merge message auto-closes #585 and #724 (full Goals(11) absorption).
- Confirm #732 remains open (deferred fleet path cleanup).
- Update the #167 active-threads memory: escalation done → next child is tasker #586.

## Rollback

If the deploy misbehaves: `git revert` the feat→main merge and push; agent-prompt-sync re-syncs the prior workspace files on the next tick. No manifest / rebaseline to unwind (rebaseline "not required"). If SKILL.md was hand-synced, revert that copy too.
