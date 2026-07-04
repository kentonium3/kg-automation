# Quickstart: Author felix-admin-capture Workspace

The author → validate → merge → deploy-verify → smoke runbook for this mission. All repo
work happens on `feat/author-capture-workspace`; office2 steps are read-only verification
(no direct edits — merge to main is the deploy trigger).

## 1. Author the three files (+ AGENTS.md receiver)

Apply the move-table (research.md, Decision 1) to:

```
scripts/openclaw/agents/felix-admin-capture/SOUL.md   # voice/stance only
scripts/openclaw/agents/felix-admin-capture/USER.md   # filtered view, no date-handling, no ADD
scripts/openclaw/agents/felix-admin-capture/TOOLS.md  # tool surface + date-handling; label pointer only
scripts/openclaw/agents/felix-admin-capture/AGENTS.md # + Available Labels beside Step 3 (receiver only)
```

Pure relocation — do not reword content in a way that changes behavior.

## 2. Validate the shared invariants (#587 gate)

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```

Expected: `felix-admin-capture` reports `ok: true` (both invariants PASS). If privacy fails
with "only in SOUL.md", the enforceable rule was stripped — restore it to AGENTS.md/TOOLS.md
(FR-007).

## 3. Content-conservation check (no duplication, no loss)

Confirm each relocated block landed in exactly one place:

```bash
cd scripts/openclaw/agents/felix-admin-capture
grep -l "Date handling" USER.md TOOLS.md          # expect: TOOLS.md only
grep -c "Available Labels" AGENTS.md TOOLS.md      # expect: AGENTS.md 1, TOOLS.md 0 (pointer text differs)
grep -c "ADD" SOUL.md USER.md                      # expect: 0 0
grep -l "04-Growth/_private" AGENTS.md TOOLS.md    # expect: both (enforceable rule retained)
```

## 4. Capture the pre-deploy smoke baseline (NFR-001)

Before merge, record capture's current routing behavior on a known input set so post-deploy
can be compared. Read-only on office2:

```bash
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.inbox.prescan --json' > /tmp/capture-baseline-prescan.json
# (and note current classify/route decisions on any fixtures used for the smoke comparison)
```

## 5. Merge to main → automatic deploy

Land the mission via the normal spec-kitty merge (feature branch → the PR to main). Once the
change is on `origin/main`, the agent-prompt-sync timer picks it up within 5 minutes.

First, confirm the timer is live (read-only):

```bash
ssh office2-claude 'systemctl --user list-timers | grep agent-prompt-sync'
```

## 6. Verify the deploy (FR-009, FR-010 / parity)

```bash
# Sync recorded the copy of each changed file:
ssh office2-claude 'tail -20 /data/services/openclaw/deploy/agent-prompt-sync.jsonl'

# Byte-for-byte parity repo↔office2:
for f in SOUL.md USER.md TOOLS.md AGENTS.md; do
  ssh office2-claude "md5sum /data/services/openclaw/inbox-agent/$f"
  md5sum "scripts/openclaw/agents/felix-admin-capture/$f"
done
# expect matching hashes per file
```

## 7. Post-deploy smoke test (FR-011 / NFR-001)

Re-run the capture flow against the same inputs as step 4 and confirm identical routing
decisions (same classifications, same destinations, same clarification behavior). Any
divergence is a regression → roll back (step 8).

## 8. Rollback (SC-005)

```bash
git revert <merge-commit>        # restore prior SOUL/USER/TOOLS/AGENTS
# merge the revert to main; agent-prompt-sync re-copies the prior version within 5 min
```

## 9. Rebaseline (C-005 / #621)

Expected outcome: **not required** — agent-prompt files are not hashed by `audit.sh` (#621
gap), so no security baseline covers them. Record this on the merge commit
("Rebaseline: not required — agent prompt files not hashed by the monitor (#621 gap)").
