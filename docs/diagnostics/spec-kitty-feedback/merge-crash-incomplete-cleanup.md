# Issue Report: VS Code Crash During Merge Leaves Incomplete Cleanup

**Date:** 2026-03-30
**Version:** spec-kitty-cli 2.1.2
**Severity:** Medium - Recurring crash with no automated recovery path
**Reporter:** Claude Opus (via Kent Gale)
**Status:** OPEN - Multiple crash mechanisms; code signing theory disproved by incident 6 (updates disabled, no binary replacement)

## Summary

VS Code crashes during or immediately after the `spec-kitty merge` finalization
step, leaving post-merge cleanup incomplete. This has occurred five times across
five separate implementation cycles at the same point in the merge workflow.
After the crash, `spec-kitty merge` cannot re-run because its preconditions
(worktrees exist) are no longer met, requiring manual recovery.

**Root cause (confirmed incident 5):** macOS code signing enforcement kills all
VS Code child processes (SIGTERM, code 15) when it detects that the on-disk
binary has changed since the process was loaded. This happens when a VS Code
update replaces binaries during a long-running session. The merge workflow's
worktree removal triggers new Code Helper subprocess spawns, which hit the
signature mismatch and cascade into a full process kill.

## Symptoms

After the crash, the following state is observed:

| Post-merge step | State after crash |
| --- | --- |
| Git merge commits | Completed |
| Status lane transitions (WP → done) | Changes written but **not committed** |
| Merge state file (.kittify/merge-state.json) | Removed (cleanup completed) |
| Worktree removal | Completed |
| WP branch deletion | **Incomplete** (stale branches remain) |
| Push to origin | **Not performed** |

## Recovery Failure

Running `spec-kitty merge --feature <slug>` after the crash fails with:

```text
Error: No WP worktrees found for feature '006-goal-and-outcome-structure'.
Check the feature slug or create workspaces first.
```

Running `spec-kitty merge --feature <slug> --dry-run --json` returns an empty
effective branch set (correct — merges are done) but plans a legacy
single-branch merge against a branch that no longer exists.

The `--resume` flag is also unusable because `.kittify/merge-state.json` was
already removed before the crash.

## Observed Incidents

| # | Date | Feature | Last WP | Notes |
| --- | --- | --- | --- | --- |
| 1 | ~2026-03 | Unknown | Unknown | First observed occurrence |
| 2 | ~2026-03 | Unknown | Unknown | Same pattern, recovered with /spec-kitty.merge |
| 3 | 2026-03-30 | F006 (006-goal-and-outcome-structure) | WP03 | Detailed state captured |
| 4 | 2026-04-01 | F009 (009-daily-habit-checkin) | WP06 | GitLens NOT installed; 6 WPs |
| 5 | 2026-04-01 | F010 (010-obsidian-sync-office2) | WP04 | Root cause confirmed: errSecCSStaticCodeChanged + SIGTERM |
| 6 | 2026-04-01 | F011 (011-second-brain-vault-cleanup) | WP07 | Updates disabled, no binary replacement, FSEvents overflow |
| 7 | 2026-04-01 | F012 (012-constitution-agent-governance-setup) | WP05 | **NO CRASH** — manual step-by-step with 5s pauses between worktree removals |

Note: Incidents 1 and 2 were not fully documented. The pattern was recognized
on incident 3. Incident 4 disproved the GitLens-only hypothesis. Incident 5
identified code signing enforcement as *one* crash mechanism. Incident 6
disproved it as *the only* mechanism — crash occurred with updates disabled
and no binary replacement during the session.

## Root Cause (Confirmed — Incident 5)

**macOS code signing enforcement kills VS Code child processes after a
background update replaces binaries mid-session.** The worktree removal
and Git extension ENOENT errors are symptoms, not the cause.

### True crash mechanism

1. A VS Code update replaces on-disk binaries (`Code`, `Code Helper`, etc.)
   while VS Code is still running with the old binaries loaded in memory
2. VS Code continues working normally — the mismatch is dormant
3. When a new `Code Helper` subprocess spawns (triggered by worktree removal,
   file watcher activity, or extension host operations), macOS verifies the
   code signature of the on-disk binary
4. macOS detects `errSecCSStaticCodeChanged` (error -67062) — the binary's
   code signature has changed since the process was loaded
5. macOS sends **SIGTERM (signal 15)** to all VS Code child processes
6. Extension host, ptyHost, shared process, file watcher, and renderer all
   die simultaneously with exit code 15, reason: `killed`

### Crash sequence (from system logs, incident 5)

```
11:50:21.250  [Security] errSecCSStaticCodeChanged (error -67062) on PIDs 87910, 87911
11:50:21.258  [Security] "This method should not be called on the main thread"
                          ← 20+ Security framework faults in rapid succession
11:50:21.499  Both code-verification processes enter exit handler and die
11:51:00.670  [File Watcher] Watcher shutdown because watched path got deleted (×4)
11:51:02.030  [Git] ENOENT: .git/worktrees/.../HEAD (×3)
11:51:02.214  Extension host exited with code: 15, signal: unknown
11:51:02.215  [error] crashed with code 15 and reason 'killed'
11:51:02.221  [error] ptyHost terminated unexpectedly with code 15
11:51:02.227  [error] shared-process crashed with code 15 and reason 'killed'
11:51:02.234  [error] renderer process gone (reason: killed, code: 15)
11:51:02.675  [error] fileWatcher crashed with code 15 and reason 'killed'
```

### Binary timestamp evidence (incident 5)

The pre-crash session started at 00:31. The VS Code binaries were replaced
during the session:

| File | Modified | Session started |
| --- | --- | --- |
| `Info.plist` | 05:47:36 | 00:31:23 |
| `Code` (main binary) | 05:58:23 | 00:31:23 |
| `Code Helper` | 05:58:22 | 00:31:23 |
| `Code Helper (Plugin)` | 05:58:23 | 00:31:23 |

The VS Code auto-updater log showed `idle` for every hourly check during
this session — the binaries were replaced by an external mechanism (macOS
background app refresh or a prior session's staged update).

### Why it appeared to be worktree-related

Worktree removal triggers new Code Helper subprocess spawns (for file
watcher cleanup, Git extension re-scanning, etc.). These new subprocesses
are the first to hit the code signature mismatch because macOS verifies the
on-disk binary at process launch. The file watcher shutdowns and Git ENOENT
errors that follow are consequences of the SIGTERM, not the cause.

### Why it appeared to be kg-automation-specific

kg-automation sessions run for 11+ hours (overnight development cycles),
giving ample time for a VS Code update to land mid-session. Bake-tracker
and test repos use shorter sessions that are less likely to span an update
window.

### Why removing GitLens appeared to help

Coincidence — the next merge after removing GitLens (F007) happened not to
span an update window. The subsequent merge (F009, 6 WPs) crashed without
GitLens installed.

### Previous hypothesis (disproved)

The original hypothesis was that rapid worktree removal caused a cascade of
file watcher shutdowns and Git extension ENOENT errors that crashed VS Code.
Incident 5 proved this wrong: the exit code is 15 (SIGTERM from macOS), not
an internal crash, and the `errSecCSStaticCodeChanged` error precedes all
file watcher and Git extension errors by 40 seconds.

### Log sources (incident 5)

| Source | Key evidence |
| --- | --- |
| `/tmp/vscode-merge-diagnostics-20260401-114948/system-errors.log` | `errSecCSStaticCodeChanged`, Security framework faults |
| `/tmp/vscode-merge-diagnostics-20260401-114948/process-count.log` | 10 of 11 Code Helper processes died simultaneously |
| `~/Library/Application Support/Code/logs/20260401T003122/main.log` | Exit code 15, reason: `killed` on all child processes |
| `~/Library/Application Support/Code/logs/20260401T003122/window1/fileWatcher.log` | 4 watcher shutdowns at 11:51:00 |
| `~/Library/Application Support/Code/logs/20260401T003122/window1/exthost/vscode.git/Git.log` | 3 ENOENT warnings at 11:51:02 (last entries) |

### Log sources (incident 3, original analysis)

All logs from: `~/Library/Application Support/Code/logs/20260329T000641/window1/`

| Log file | Key evidence |
| --- | --- |
| `fileWatcher.log` | 6 watcher shutdowns at 11:07:23 |
| `exthost/vscode.git/Git.log` | 3 ENOENT errors at 11:07:24 (last entries) |
| `exthost/eamodio.gitlens/GitLens.log` | Abrupt end at 11:07:24 |

## Impact

- Manual recovery required after every merge (commit status files, delete
  stale branches, push)
- Risk of state inconsistency if recovery steps are missed
- `spec-kitty merge` has no idempotent recovery path for this failure mode
- Workflow trust is eroded — users learn to expect crashes at merge time

## Mitigations

### Fix (applied 2026-04-01)

Set `"update.mode": "manual"` in VS Code settings to prevent background
updates from replacing binaries while VS Code is running. Updates must be
applied manually by restarting VS Code when prompted.

This addresses the root cause directly: if binaries are never replaced
mid-session, macOS will never detect a code signature mismatch, and the
SIGTERM cascade cannot occur.

### Previous workarounds (no longer necessary)

These were based on the disproved worktree-removal hypothesis:

1. ~~Run merges from an external terminal~~
2. ~~Close Source Control panel before merging~~
3. ~~Disable GitLens temporarily before merge operations~~

### Still recommended (spec-kitty improvement)

These are good defensive improvements regardless of the crash root cause:

1. **Make merge idempotent** — detect already-integrated branches and skip to
   cleanup, so the command can be re-run after any interruption
2. **Commit status files before worktree removal** — the post-merge status
   transitions are the most important cleanup step; committing them before
   worktree removal reduces the recovery burden from any failure mode

## Step-by-Step Reproduction Protocol

When the next multi-WP feature is ready to merge in kg-automation, execute the
merge manually step by step instead of running `spec-kitty merge`. This isolates
which operation triggers the VS Code crash.

**Important:** Run this from the VS Code integrated terminal (where the crash
occurs), not from an external terminal.

### Prerequisites

- Feature must have all WPs in `approved` lane
- You must be in the main repository directory (not a worktree)

### Step 0: Capture the planned operations

```bash
spec-kitty merge --feature <slug> --dry-run --json | python3 -m json.tool
```

Save this output. It lists the exact branches, worktree paths, and operations.

### Step 1: Checkout and update main

```bash
git checkout main
git pull --ff-only
```

Pause — observe VS Code. Stable? Continue.

### Step 2: Merge each WP branch (one at a time)

```bash
git merge --no-ff <feature>-WP01 -m 'Merge WP01 from <feature>'
# PAUSE — observe VS Code for 5-10 seconds
git merge --no-ff <feature>-WP02 -m 'Merge WP02 from <feature>'
# PAUSE — observe VS Code for 5-10 seconds
git merge --no-ff <feature>-WP03 -m 'Merge WP03 from <feature>'
# PAUSE — observe VS Code for 5-10 seconds
```

If VS Code crashes here, record which merge triggered it.

### Step 3: Remove worktrees (one at a time) — PRIME SUSPECT

Worktree removal deletes an entire directory tree that VS Code's file watcher
may be tracking. This is the most likely crash trigger.

```bash
git worktree remove .worktrees/<feature>-WP01
# PAUSE — observe VS Code for 10-15 seconds
git worktree remove .worktrees/<feature>-WP02
# PAUSE — observe VS Code for 10-15 seconds
git worktree remove .worktrees/<feature>-WP03
# PAUSE — observe VS Code for 10-15 seconds
```

If VS Code crashes here, record which worktree removal triggered it. Note
whether the crash happens immediately or after a brief delay (suggesting a
file watcher event queue).

### Step 4: Delete branches (one at a time)

```bash
git branch -d <feature>-WP01
# PAUSE — observe VS Code for 5 seconds
git branch -d <feature>-WP02
# PAUSE — observe VS Code for 5 seconds
git branch -d <feature>-WP03
# PAUSE — observe VS Code for 5 seconds
```

### Step 5: Commit status files and push

```bash
git add kitty-specs/<feature>/status.events.jsonl \
       kitty-specs/<feature>/status.json \
       kitty-specs/<feature>/tasks.md \
       kitty-specs/<feature>/tasks/*.md
git commit -m "chore: post-merge status updates for <feature>"
git push
```

### Recording results

After completing (or encountering a crash), document:

1. **Which step crashed** — step number and exact command
2. **Timing** — did the crash happen during the command or seconds after?
3. **VS Code state** — any error dialogs, frozen UI, or extension host crashes
   vs full window crash?
4. **Partial completion** — if crash occurred, which operations had already
   completed? Check with `git worktree list`, `git branch`, `git status`
5. **VS Code logs** — check `~/Library/Logs/DiagReports/` and
   `~/Library/Application Support/Code/logs/` immediately after restart

### Findings from spec-kitty-crash-test repo (2026-03-30)

Ran the full workflow in a clean test repo (spec-kitty-crash-test) from Claude
Code terminal (outside VS Code):

- **1-WP feature (001-add-changelog):** Merge completed without crash
- **3-WP feature (002-project-docs):** Merge completed without crash
- Both runs confirmed that status files are left **uncommitted** after merge
  (this is by design, not a crash artifact)
- The workflow itself is sound — the crash is likely triggered by VS Code's
  reaction to the rapid filesystem/git state changes, not by spec-kitty logic

This supports the hypothesis that the crash is VS Code-specific (file watcher,
git extension, or GitLens reacting to worktree removal + branch deletion).

## Suggested spec-kitty Improvement

Regardless of root cause, `spec-kitty merge` should handle the case where
merges completed but cleanup didn't:

- Detect that all WP branches are already integrated into the target
- Skip the merge step and proceed directly to cleanup (status commits,
  branch deletion, push)
- Make the merge command idempotent for post-crash recovery

## Manual Recovery Performed (Incident 3)

```bash
# Commit the uncommitted status file updates
git add kitty-specs/006-goal-and-outcome-structure/status.events.jsonl \
       kitty-specs/006-goal-and-outcome-structure/status.json \
       kitty-specs/006-goal-and-outcome-structure/tasks.md \
       kitty-specs/006-goal-and-outcome-structure/tasks/WP03-documentation-updates.md
git commit -m "chore: commit F006 post-merge status updates after VS Code crash"

# Delete stale branch
git branch -d 006-goal-and-outcome-structure-WP03-merge-base

# Push to origin
git push
```

## Variable Changes Before Next Test Cycle

**2026-03-30**: GitLens (`eamodio.gitlens`) uninstalled from VS Code. This removes one of the two suspected crash contributors. The next spec-kitty merge should use the step-by-step protocol in this document to determine whether the built-in Git extension alone is sufficient to trigger the crash, or whether the crash is resolved.

Expected outcomes:
- **Crash resolved**: GitLens was the primary contributor. File a bug report against GitLens.
- **Crash persists**: Built-in Git extension is the culprit. Add `log stream --process "Code Helper"` instrumentation and test disabling the built-in Git extension (`"git.enabled": false` in VS Code settings).

## Prior Resolution Attempt (2026-03-30) — Disproved

**GitLens was removed, crash appeared resolved, but recurred on 2026-04-01.**

### Test: F007 merge (4 WPs, step-by-step from VS Code integrated terminal)

Executed the full merge protocol from the VS Code integrated terminal while
monitoring from an external terminal:

**Monitoring setup** (external terminal):
```bash
tail -f "<VS Code logs>/exthost/vscode.git/Git.log" &
log stream --predicate 'process == "Code Helper" OR process == "Electron"' --level error
```

**Merge steps executed** (VS Code integrated terminal):
1. `git checkout main && git pull --ff-only` — stable
2. `git merge --no-ff 007-vikunja-api-skill-WP04` — stable (single effective tip)
3. `git worktree remove .worktrees/007-vikunja-api-skill-WP01` — stable
4. `git worktree remove .worktrees/007-vikunja-api-skill-WP02` — stable
5. `git worktree remove .worktrees/007-vikunja-api-skill-WP03` — stable
6. `git worktree remove .worktrees/007-vikunja-api-skill-WP04` — stable
7. `git branch -d` (all 4 branches) — stable
8. Status transitions and push — stable

**Result**: All 4 worktree removals completed without a VS Code crash. The
built-in Git extension logged ENOENT warnings for the deleted worktree HEAD
files (as expected) but handled them gracefully — no window crash.

**Conclusion at the time**: GitLens was the primary contributor. This was
**disproved** by incident 4 (below).

---

## Incident 4: F009 Merge Crash (2026-04-01) — GitLens NOT Installed

### Timeline (from git reflog)

| Time | Event |
| --- | --- |
| 00:07:49 | `checkout: moving from main to main` (merge prep) |
| 00:07:50 | `merge 009-daily-habit-checkin-WP06: Merge made by 'ort' strategy` |
| 00:08–00:12 | **VS Code crash** — window dies, Claude Code session lost |
| 00:13:12 | Manual recovery: `commit F009 post-merge status updates after VS Code crash` |

### State after crash

Same pattern as all previous incidents:

| Post-merge step | State |
| --- | --- |
| Git merge commits | Completed (WP06 merge at 00:07:50) |
| Status file updates (JSONL, snapshot, frontmatter) | Written but **uncommitted** |
| Worktree removal | Completed (none remaining) |
| WP branch deletion | Completed (none remaining) |
| Push to origin | **Not performed** |

### Key differences from prior incidents

- **GitLens was NOT installed** — uninstalled 2026-03-30
- **6 WPs** — largest merge to date (F006 had 3, F007 had 4)
- Merge was run via `spec-kitty merge` (not step-by-step protocol)
- Pre-crash VS Code window logs were **not preserved** — log rotation
  removed the session before it could be captured

### Forensic analysis: spec-kitty merge execution order

Source analysis of `specify_cli/merge/executor.py` reveals the exact operation
sequence within `merge_workspace_per_wp()`:

1. **Merge WP branches** into target (lines 585–624)
   - After each merge: `_mark_wp_merged_done()` updates status files
   - Status JSONL, snapshot JSON, and frontmatter are written **but not committed**
2. **Push to remote** (lines 627–636) — if `--push` flag set
3. **Remove worktrees** (lines 639–659) — `git worktree remove --force`
4. **Delete branches** (lines 661–684) — `git branch -d`, falls back to `-D`
5. **Render completion message** (lines 686–694)
6. **Exit** — status files remain uncommitted by design

The crash consistently interrupts at step 3 or between steps 3–4. Status file
writes (step 1) have always completed before the crash point.

### Log evidence

Pre-crash VS Code session logs were lost to rotation. The post-restart session
(`20260401T001803`) shows a normal startup with no crash artifacts. The
`cli.log` at `20260401T000822` (00:08, immediately after crash) shows only
`code --list-extensions` — likely the previous Claude session's diagnostics.

No macOS crash reports were generated (`~/Library/Logs/DiagReports/` empty),
suggesting the Electron process exited uncleanly but did not segfault.

### Volume hypothesis

| Feature | WP count | GitLens | Crash? |
| --- | --- | --- | --- |
| F006 | 3 | Yes | Yes (incidents 1–3) |
| F007 | 4 | No | No |
| F009 | 6 | No | **Yes** (incident 4) |

GitLens lowers the crash threshold. Without GitLens, the built-in Git extension
alone may still crash when the worktree count is high enough. The threshold
appears to be somewhere between 4 and 6 worktrees.

**However**: bake-tracker has run spec-kitty merges with many more than 6 WPs
without crashing, also from the VS Code integrated terminal. This rules out
both WP count and terminal type as the sole factor. The crash is
**kg-automation-specific**. Possible differentiators:

- **VS Code window identity**: kg-automation and bake-tracker open in separate
  VS Code windows. The kg-automation window may carry more accumulated state
  (open editors, SCM panel state, longer uptime)
- **File watcher load**: kg-automation has ~400+ tracked files, heavily
  markdown-based; bake-tracker is smaller and Python-focused. More active
  file watchers = more concurrent reactions to worktree deletion
- **Workspace settings**: kg-automation has markdownlint, markdown word-wrap,
  and trimming enabled — extensions that register additional file watchers
  on the doc-heavy tree
- **Repo size/complexity**: kg-automation has more directories, kitty-specs
  artifacts, and nested status files — the Git extension's `status -z -uall`
  scan is heavier

The crash appears to require a threshold of concurrent file watcher + Git
extension activity during worktree removal that kg-automation exceeds but
bake-tracker does not. Next test: `"git.enabled": false` in kg-automation
workspace settings before merging.

## Recovery Script

A recovery script is available at `scripts/merge-crash-recovery.sh`. It detects
and completes the standard post-crash cleanup (commit status files, delete stale
branches, push).

## Next Steps

1. **Investigate FSEvents overflow** — Incident 6 shows the FSEvents client
   drops events during rapid worktree deletion, followed immediately by
   SIGTERM. This may be the primary crash mechanism, with code signing being
   a separate (but coincidental) trigger in incident 5.

2. **Test mitigation**: Run merges from an external terminal (outside VS Code)
   to confirm the crash is VS Code-specific. If merges succeed externally,
   the fix is to run `spec-kitty merge` from a standalone terminal.

3. **File VS Code bug**: The FSEvents overflow → SIGTERM cascade appears to
   be a VS Code/Electron bug where rapid directory deletion causes
   unrecoverable file watcher state.

---

## Environment

- OS: macOS Darwin x64 25.3.0
- Python: 3.13
- spec-kitty-cli: 2.1.2
- VS Code: 1.113.0 (Universal), commit cfbea10c5ffb233ea9177d34726e6056e89913dc
- Electron: 39.8.3
- Chromium: 142.0.7444.265
- Node.js: 22.22.1
- Feature (crash incidents 1-3): 006-goal-and-outcome-structure (3 WPs)
- Feature (resolution test): 007-vikunja-api-skill (4 WPs)
- Feature (incident 4): 009-daily-habit-checkin (6 WPs)
- Feature (incident 5, code signing confirmed): 010-obsidian-sync-office2 (4 WPs)
- Feature (incident 6, code signing disproved as sole cause): 011-second-brain-vault-cleanup (7 WPs, 1 worktree at merge time)
- Feature (incident 7, NO CRASH): 012-constitution-agent-governance-setup (5 WPs, 5 worktrees removed with 5s pauses)

## Incident 6: F011 Merge Crash (2026-04-01) — Updates Disabled, No Binary Replacement

### Summary

Crash occurred with `"update.mode": "manual"` applied, disproving the
code signing theory as the sole root cause. VS Code binaries were NOT
replaced during the session. The Electron binary was last modified at
11:52:27 — before the session started at 12:21:05.

### Timeline

| Time (local) | Event |
| --- | --- |
| 12:21:05 | Session start; log confirms "manual checks only; automatic updates are disabled" |
| 15:39:35 | Claude Code extension: "WebSocket is not open" error (early instability sign?) |
| 16:12:03.791 | Last normal Git extension command (`git status -z -uall`, 19ms) |
| 16:12:04.327 | First file watcher shutdown (watched path got deleted) |
| 16:12:04.939 | 7th file watcher shutdown |
| 16:12:05.052 | **FSEvents DROPPED EVENTS**: "Events were dropped by the FSEvents client. File system must be re-scanned." |
| 16:12:05.655 | Git ENOENT: worktree HEAD files (.git/worktrees/...-WP01/HEAD, WP02/HEAD) |
| 16:12:05.772 | shared-process crashed with code 15 and reason 'killed' |
| 16:12:05.775 | ptyHost terminated unexpectedly with code 15 |
| 16:12:05.783 | fileWatcher crashed with code 15 and reason 'killed' |
| 16:12:05.858 | extensionHost crashed with code 15 and reason 'killed' |
| 16:12:05.862 | renderer process gone (reason: killed, code: 15) |
| 16:12:06.228 | network process gone (exitCode: 15, crashed: true) |

### State after crash

| Post-merge step | State |
| --- | --- |
| Git merge commit | Completed (`a768b9b Merge WP07`) |
| Status lane transitions | Written but **uncommitted** |
| Worktree removal | Completed |
| WP branch deletion | **Incomplete** (merge-base branch remained) |
| Push to origin | **Not performed** |

### Key evidence

1. **Updates were disabled** — main.log line 2: "manual checks only;
   automatic updates are disabled by user preference"
2. **No binary replacement during session** — Electron modified at 11:52,
   session started at 12:21. Code Helper at 05:58, Info.plist at 05:47.
3. **No `errSecCSStaticCodeChanged`** in system logs (searched ±1 hour)
4. **No macOS crash reports** — `~/Library/Logs/DiagReports/` empty
5. **No jetsam/memory pressure** — no OOM kill evidence
6. **FSEvents overflow** — "Events were dropped by the FSEvents client"
   occurs 720ms before the SIGTERM cascade
7. **All processes killed with SIGTERM (code 15)** — same exit code as
   incident 5, but different trigger
8. **System logs empty** for crash timeframe — rotated before capture

### Analysis

The crash mechanism for incident 6 is NOT code signing enforcement. The
sequence is:

1. spec-kitty merge removes the WP07 worktree (rapid directory tree deletion)
2. VS Code's file watcher detects 7+ watched paths being deleted
3. The FSEvents client (macOS file system event API) is overwhelmed and
   **drops events**, logging the error
4. ~700ms later, all VS Code child processes receive SIGTERM (code 15)

The gap between FSEvents overflow (16:12:05.052) and the first SIGTERM
(16:12:05.772) is consistent with Electron's main process detecting an
unrecoverable state in its file watching infrastructure and terminating
all children, OR with macOS itself sending SIGTERM due to the FSEvents
error.

### Implications for root cause

There are likely **two distinct crash mechanisms**:

1. **Code signing enforcement** (incident 5) — confirmed by
   `errSecCSStaticCodeChanged` in system logs. Triggered when VS Code
   spawns new subprocesses after binaries are replaced mid-session.
   Fixed by `"update.mode": "manual"`.

2. **FSEvents overflow** (incident 6) — triggered by rapid directory
   deletion during worktree removal. The FSEvents client drops events,
   leading to SIGTERM cascade. NOT fixed by update mode setting.

Both produce identical symptoms (exit code 15 on all processes) but have
different triggers. The code signing fix addresses only mechanism 1.

### Recovery performed

```bash
git add kitty-specs/011-second-brain-vault-cleanup/status.events.jsonl \
       kitty-specs/011-second-brain-vault-cleanup/status.json \
       kitty-specs/011-second-brain-vault-cleanup/tasks.md \
       kitty-specs/011-second-brain-vault-cleanup/tasks/WP07-end-to-end-verification.md
git commit -m "chore: commit F011 post-merge status updates after VS Code crash"
git branch -d 011-second-brain-vault-cleanup-WP07-merge-base
git push
```

### Log sources

| Source | Key evidence |
| --- | --- |
| `~/Library/Application Support/Code/logs/20260401T122104/main.log` | Update mode confirmed manual; exit code 15 on all processes |
| `~/Library/Application Support/Code/logs/20260401T122104/window1/fileWatcher.log` | 7 watcher shutdowns + FSEvents dropped events |
| `~/Library/Application Support/Code/logs/20260401T122104/window1/exthost/vscode.git/Git.log` | Normal operation until ENOENT at crash time |
| `~/Library/Application Support/Code/logs/20260401T122104/window1/renderer.log` | File watcher shutdowns + FSEvents overflow visible here too |
| macOS system log | Empty for crash timeframe (rotated) |

---

## Incident 7: F012 Merge (2026-04-01) — NO CRASH — Manual Step-by-Step with Pauses

### Summary

No crash occurred. Merge cleanup was performed manually, one step at a time,
with 5-second pauses between each worktree removal. This is the first successful
multi-WP merge cleanup from the VS Code integrated terminal since incident 3.

### Context

- Feature: 012-constitution-agent-governance-setup (5 WPs)
- All 5 WP branches had already been merged to main during implementation
- Cleanup consisted only of worktree removal and branch deletion (no merge step)
- VS Code updates disabled (`"update.mode": "manual"`)
- Session duration: ~2 hours at time of cleanup
- Breadcrumb file written before each step: `docs/diagnostics/f012-merge-breadcrumbs.md`

### Procedure executed

All steps run from VS Code integrated terminal (Claude Code).

| Step | Command | Wait after | Result |
| --- | --- | --- | --- |
| 1 | `git checkout main && git pull --ff-only` | — | Stable |
| 3a | `git worktree remove .worktrees/...-WP01` | 5s | Stable |
| 3b | `git worktree remove .worktrees/...-WP02` | 5s | Stable |
| 3c | `git worktree remove .worktrees/...-WP03` | 5s | Stable |
| 3d | `git worktree remove .worktrees/...-WP04` | 5s | Stable |
| 3e | `git worktree remove .worktrees/...-WP05` | 5s | Stable |
| 4 | `git branch -d` (all 5 branches) | — | Stable |
| 5 | `git add`, `git commit`, `git push` | — | Stable |

Step 2 (merge WP branches) was skipped because all branches were already
integrated into main.

### Key difference from prior incidents

The only procedural difference from `spec-kitty merge` is **timing**:

- `spec-kitty merge`: removes all worktrees in rapid succession (no delay)
- This test: 5-second pause between each worktree removal

Prior incidents showed FSEvents overflow ("Events were dropped by the FSEvents
client") occurring when multiple worktrees were deleted rapidly. The 5-second
pause gives the FSEvents client time to drain its event queue between deletions.

### Implications

This result is consistent with the FSEvents overflow theory from incident 6:

1. Rapid worktree deletion saturates the FSEvents event queue
2. macOS drops events when the queue overflows
3. VS Code/Electron detects the unrecoverable file watcher state
4. SIGTERM cascade kills all child processes

Spacing out the deletions avoids step 1, preventing the entire cascade.

### Suggested spec-kitty fix

Add a configurable delay between worktree removals in `spec-kitty merge`.
A 5-second pause between each removal appears sufficient to prevent the
FSEvents overflow. This is a simple, low-risk mitigation:

```python
# In merge/executor.py, between worktree removals:
import time
time.sleep(5)  # Prevent FSEvents overflow on macOS
```

Alternatively, `spec-kitty merge` could accept a `--worktree-removal-delay`
flag (default 5s on macOS, 0s elsewhere).

### Caveats

- This is a single successful test (N=1). The crash is not 100% reproducible
  even without pauses (F007 had 4 WPs and no crash). The pauses may be
  sufficient but are not yet proven necessary.
- The session was shorter (~2 hours) than typical crash sessions (11+ hours).
  Session duration may still be a contributing factor.
- Further testing needed: run `spec-kitty merge` with the delay on a future
  multi-WP feature to confirm the fix works programmatically.
