# Quickstart: Author felix-admin-tasker workspace

Operator runbook for the authoring edit, validation, merge, deploy, and verification. Steps 1–4 are the in-mission (WP) work; steps 5–9 are operator-owned post-merge acceptance (excluded from the acceptance matrix, C-006).

## 1. Author the three files (per data-model.md move-table)

Edit only:
- `scripts/openclaw/agents/felix-admin-tasker/SOUL.md` — reduce to `## Voice` + a one-line privacy stance.
- `scripts/openclaw/agents/felix-admin-tasker/USER.md` — remove `## Privacy boundary`; trim the role re-statement in `## Context`; trim the "concise/direct" line in `## Communication preferences`; keep person block + `## Identities` + genuine context/prefs.
- `scripts/openclaw/agents/felix-admin-tasker/TOOLS.md` — correct `## Action log` format (FR-008); remove the confirmation Restriction; keep privacy path + token rule.

Do **not** edit `AGENTS.md` or `IDENTITY.md`.

## 2. Validate the invariants (must stay green)

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```

Assert the `felix-admin-tasker` object has `ok: true` with all four checks (`privacy_boundary`, `privacy_path_canonical`, `output_discipline`, `runtime_env_assumptions`) `ok`. A tasker-scoped assertion (not the whole-fleet exit code — calendar/#635 fails Invariant B, out of scope).

## 3. Conservation + scope check

Run the conservation invariants from `data-model.md` §"Conservation invariants" as greps, e.g.:

```bash
cd scripts/openclaw/agents/felix-admin-tasker
# enforceable privacy present in AGENTS + TOOLS, absent from SOUL + USER:
grep -l "04-Growth/_private" AGENTS.md TOOLS.md   # expect both
grep -L "04-Growth/_private" SOUL.md USER.md      # expect both (absent)
# confirmation rule absent from SOUL + TOOLS (present in AGENTS):
grep -i "without.*confirmation\|confirmation.*required" AGENTS.md
# stale action-log format gone:
grep -r "task-intelligence-YYYY-MM-DD.md\|task-intelligence-\*.md" TOOLS.md   # expect no match
# scope: only the three files changed
git -C "$(git rev-parse --show-toplevel)" diff --name-only
# AGENTS.md and IDENTITY.md byte-identical:
git -C "$(git rev-parse --show-toplevel)" diff --quiet -- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md scripts/openclaw/agents/felix-admin-tasker/IDENTITY.md && echo "AGENTS/IDENTITY unchanged"
```

## 4. Commit on the feature branch

Scoped add of the three files; conventional commit referencing #586. WP work merges to `feat/author-tasker-workspace`.

## 5. Merge to main (the deploy trigger)

After the mission's `spec-kitty merge` lands the WP on `feat/author-tasker-workspace` and the **post-merge Codex review** passes, merge the feature branch to `main`:

```bash
git switch main && git merge --no-ff feat/author-tasker-workspace -m "feat(#586): author felix-admin-tasker workspace to #587 standard

Closes #586
Rebaseline: not required — agent prompt files are not hashed by audit.sh (#621)"
git push origin main
```

`Closes #586` (bare, same-repo) auto-closes the issue on push.

## 6. Deploy via agent-prompt-sync (no manifest)

Merge-to-main is the deploy trigger. Force a tick if you don't want to wait:

```bash
ssh office2-claude 'systemctl --user start agent-prompt-sync.service'
```

Then confirm the tick picked up the merge:

```bash
ssh office2-claude 'tail -3 /data/services/openclaw/deploy/agent-prompt-sync.jsonl'
```

Look for `git_head_after_pull` = the merge commit and `files_copied` including the tasker files.

## 7. Verify deploy dir + md5 parity

Deploy dir is `/data/services/openclaw/tasker-agent/` (slug ≠ dir). Re-verify before trusting parity:

```bash
ssh office2-claude 'find /data/services/openclaw -maxdepth 2 -name AGENTS.md | grep -i tasker'
```

Compare repo ↔ office2 md5 for the three edited files (SOUL/USER/TOOLS) — expect a match at the merged commit; the changed files' md5 must differ from their pre-merge values (proving the swap landed).

## 8. Live smoke (behavior preservation — the real gate)

Trigger a tasker turn (a task proposal / structuring path, e.g. via a capture delegation or a direct enrichment request) and confirm:
- The reply starts with the identity line (`Sent by felix-admin-tasker:<model>`), no preamble.
- No narration between tool calls; a no-op turn is exactly `[felix-admin-tasker]: IDLE`.
- Proposal/structure content is unchanged in shape (project, due, priority, label).

## 9. Rollback (if needed)

Revert the merge commit on main and let agent-prompt-sync re-pull the prior version; or `git revert` the feat→main merge and push. No state/schema to unwind (content-only change).

## Rebaseline

`Rebaseline: not required — agent prompt files are not hashed by audit.sh (#621).` Recorded in the feat→main merge commit (step 5).
