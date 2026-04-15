---
affected_files: []
cycle_number: 1
mission_slug: 026-vault-path-registry-and-folder-renumber
reproduction_command:
reviewed_at: '2026-04-11T06:33:40Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

**Issue**: WP05 halted mid-risky-window after discovering a pre-existing silent failure in Obsidian Sync (office2 → cloud direction) that caused vault content divergence between Mac and office2 for ~4–5 days. Halting the mission is a Path A decision (operator authorized) because the sync divergence is a broader operational issue that deserves its own investigation, not a workaround inside an infrastructure refactor.

**Timeline of what happened in WP05**:

1. **T027 (Tier 2 pre-flight) — PASS.** Restic backup verified via file mtime (most recent snapshot `cb5ec0d1...` from 2026-04-11 04:00 UTC, ~14h old). Note: `restic snapshots` command cannot be run as the `claude` user because snapshot files are owned by `root:root` with mode 400. File mtime verification via directory listing was the workaround. Separate runbook improvement needed.

2. **T028 (Cron pause) — DONE then REVERSED.** All 4 `felix-admin-capture` cron jobs (`inbox-7am`, `inbox-noon`, `inbox-5pm`, `inbox-10pm`) were disabled via `openclaw cron disable`. Risky window opened at ~2026-04-11 05:51 UTC. Cron re-enabled at ~2026-04-11 06:38 UTC (Path A halt).

3. **T029 (02-Inbox-Processed folder creation) — DONE, state preserved for mission restart.** Folder created on the Mac (`~/second-brain/notes/02-Inbox-Processed/` with `.gitkeep` + `README.md` placeholder). Also created on office2 via `ssh office2-claude 'mkdir -p'` when Obsidian Sync failed to propagate the Mac state within ~30s. The office2 folder was chgrp'd to `secondbrain` and chmod'd to `2775` to match the 00-Inbox permission pattern. **These folders remain in place — future WP05 restart can use them as-is.**

4. **T030 (Obsidian UI folder renames on Mac) — DONE on Mac, partially reflected on office2.** Kent renamed all 8 folders via Obsidian UI in sequence, one at a time, with inter-rename wikilink verification. All 8 renames completed successfully on the Mac. Mac vault state at T030 completion: clean 10-folder 00–09 ordinal sequence. All real wikilinks auto-updated correctly. Only drift: 2 documentation references inside vault CLAUDE.md (inline code span + plain text references) and 1 frontmatter wikilink in `06-Business/daily-work-priorities.md:15`. These were tracked for end-of-WP05 cleanup.

5. **Sync failure discovery.** Office2 did NOT propagate any of the 8 renames. Diagnostic investigation revealed:
   - `ob sync --continuous` process running as `kgale` (PID 117496) since 2026-04-07 — authenticated OK per `ob login`
   - But the process was apparently stuck or its sync mechanism was broken — 4+ days of silent non-propagation
   - Restart attempt: killed PID 117496; an auto-restart supervisor immediately spawned PID 192643 with the same command line (indicating there IS a supervisor, not just a raw nohup process)
   - After restart, office2 pulled cloud state for 4 of 8 renames cleanly (`03-Constitution`, `04-Growth`, `06-Business`, `07-Finance`) but the other 4 folders had local content never pushed to cloud, causing a three-way merge that kept BOTH old and new folder names
   - Straggler files in old folders: `00-Inbox/` (3 files), `03-Health/` (1), `06-Journal/` (1), `07-Resources/` (1) — totaling 6 files
   - Diff analysis showed some stragglers are NEWER versions than the Mac/cloud state. For example:
     - `00-Inbox/Inbox 2026-04-09 1047.md`: office2 version has `status: processed` (newer), cloud version had `status: unprocessed` (stale)
     - `03-Health/Health-Fitness.md`: office2 version has `updated: 2026-04-09` and a walking activity entry, cloud version has `updated: 2026-04-08` and no walking entry
   - The cloud+Mac state was then updated with office2's local content, resulting in Mac vault now having BOTH old and new folder names for the 4 conflict pairs

6. **Root cause (suspected, not confirmed)**: Obsidian Sync's office2 → cloud direction appears to have been silently failing for 4+ days. Files modified on office2 (by the `claude` user via felix-admin-capture, and by direct kgale edits) were not pushed to cloud, even though:
   - The `ob sync --continuous` process was running
   - The account was authenticated (`ob login` confirmed)
   - The cloud → office2 direction appeared to work (process was alive)
   - No error logs, no alerts, no crash-loop

**Impact beyond mission 026**:
- Kent's Mac has been showing stale content for ~4–5 days for files that office2 updated
- felix-admin-capture has been processing inbox items on office2, writing results, and those results never reached the Mac
- Kent's vault on the Mac and phone is missing the newest state for these files
- This is a significant operational issue that requires its own P1-bug investigation

**State preserved for WP05 restart**:
- Mission branch + lane-a branch unchanged (all the WP01/WP02/WP03 code + Phase 1 reconciliation work is safe)
- `02-Inbox-Processed/` folder exists on both Mac and office2 (do not delete)
- `paths.json` in lane-a still has PRE-rename folder names (correct for pre-rename state)
- `CLAUDE.md.tmpl` `_private/` boundary still references `02-Growth/_private/` (pre-rename — correct)
- `deploy-f026.sh --apply --mode post-rename` was NOT executed
- felix-admin-capture cron is RE-ENABLED and back on schedule

**State that needs manual cleanup by Kent (before WP05 restart)**:
- Mac vault has BOTH old and new folder names for 4 folder pairs (`00-Inbox` + `01-Inbox`, `03-Health` + `05-Health`, `06-Journal` + `08-Journal`, `07-Resources` + `09-Resources`)
- Phone vault has the same conflicted state (likely)
- office2 vault has the same conflicted state
- Straggler files in old folders on all 3 devices need to be consolidated into the new folder locations (office2 versions are authoritative for the specific files where diffs exist)
- The root cause of office2 → cloud sync failure needs investigation and fix

**Open issues that need filing (after Path A halt is complete)**:
- P1-bug: Obsidian Sync silent failure — office2 → cloud direction broken since ~2026-04-06; vault divergence for 4–5 days with no detection
- Runbook improvement: `claude` user cannot verify Restic backups because snapshot files are `root:root` mode 400; documented verification method in `backup-and-recovery.md` doesn't work from claude account

**What WP05 restart will require when we resume**:
1. Obsidian Sync root cause understood and fixed
2. Vault state clean on Mac, phone, office2 — only the 10-folder 00–09 ordinal sequence, no old-named duplicates
3. Straggler content properly merged into new folders (not orphaned)
4. Restart from T027 (re-verify Tier 2 backup), T028 (re-pause cron), [T029 skipped — already done and preserved], T030 (NO renames needed, Mac already has new names), T031 (update paths.json + CLAUDE.md.tmpl), T032 (deploy + verify), T033 (cron resume + runlog)

**Decision to halt**: Operator (Kent) explicitly authorized Path A after reviewing the sync divergence findings. Rationale: "Mission 026 is an infrastructure refactor with no time pressure. The sync divergence is a broader operational issue that deserves full attention, not triage inside a risky window."
