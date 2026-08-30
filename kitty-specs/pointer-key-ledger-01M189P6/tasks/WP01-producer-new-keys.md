---
work_package_id: WP01
title: 'Producer: make the four conditions expressible'
dependencies: []
requirement_refs:
- C-008
- FR-012
- FR-013
- FR-014
- FR-015
planning_base_branch: feat/934-pointer-key-ledger
merge_target_branch: feat/934-pointer-key-ledger
branch_strategy: Planning artifacts for this mission were generated on feat/934-pointer-key-ledger. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/934-pointer-key-ledger unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-pointer-key-ledger-01M189P6
base_commit: 8001891dfec98027d15463b0e143da793a223300
created_at: '2026-08-30T04:12:37.471900+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
history:
- at: '2026-08-30T03:54:28Z'
  actor: tasks
  note: Generated from plan v2 IC-04 after the post-plan review widened scope to full parity.
agent_profile: python-pedro
authoritative_surface: scripts/office2/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/office2/restic-backup.sh
- tests/office2/restic_backup/test_pointer_emission.py
role: implementer
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this file, load your assigned agent profile:

```
/ad-hoc-profile-load python-pedro
```

This establishes your identity, boundaries, and governance scope. Do not begin work until it is
loaded.

## Objective

Add the four keys that make the backup's catastrophic failure modes **expressible at all**, fix an
unguarded output that can emit invalid JSON, and bump the schema version.

This is the foundation work package. Until it lands, three of the four total-loss conditions cannot
be closed by any amount of adjudication downstream — the state document simply does not carry the
facts. You are not making anything *decide* health here; you are making the facts *sayable*. The
deciding happens in WP03/WP04.

## Context you need

`scripts/office2/restic-backup.sh` is office2's nightly backup. On every exit it writes a small JSON
"state pointer" to `$STATE_DIR/last-backup.json` from a bash `EXIT` trap. Every health surface reads
that document.

Today it emits ten keys. Three of them decide health; seven are inert. Worse, the document cannot
express:

- whether the weekly `restic check` has run *at all recently* (only whether it ran *today*),
- whether the backup actually captured any files,
- whether every configured source root made it into the snapshot,
- how much room is left on the volume.

So a backup capturing an empty snapshot, onto a nearly-full disk, whose verification silently stopped
weeks ago, reports healthy on every existing rule.

### ⚠️ This is a live Tier-2 backup script

The highest-risk edit in this mission. Two rules:

1. **Never let health bookkeeping break the backup.** Every addition must fail soft. A backup that
   aborts because its *own* instrumentation failed would be a self-inflicted outage far worse than
   the bug being fixed. Follow the existing style: compute into a shell variable, guard it, default
   to the JSON literal `null`.
2. **The `EXIT` trap must keep firing.** It is installed at line ~121 and writes the document on
   every exit after that point. Do not move, wrap, or conditionalise it.

### Known defect you are fixing along the way

`repo_size_bytes` is guarded against an empty result; its sibling `snapshot_count` is **not**:

```bash
repo_size_bytes=$(du -sb "$RESTIC_REPOSITORY" 2>/dev/null | awk '{print $1}')
[ -z "$repo_size_bytes" ] && repo_size_bytes="null"      # guarded

if all=$(restic snapshots --json 2>/dev/null) && [ -n "$all" ]; then
    snapshot_count_json=$(echo "$all" | jq 'length')      # NOT guarded
fi
```

If `jq` yields nothing, the heredoc emits `"snapshot_count": ,` — **invalid JSON**. Today the field is
unread so it is latent; this mission makes it decide health, so it must be guarded now.

## Subtasks

### T001 — Extend the emission harness and pin the current baseline

**Purpose**: Establish a red-then-green baseline before changing behaviour, and give the new keys
somewhere to be asserted. Test-first is charter doctrine (DIRECTIVE_034) and it matters here
specifically: this script's historical defects hid in branches that reading missed.

**Steps**:
1. Open `tests/office2/restic_backup/test_pointer_emission.py`. It already runs the real script with
   `restic`, `mountpoint`, and `du` stubbed on `PATH` and the output directories redirected via
   `LOG_DIR` / `STATE_DIR` / `BACKUP_MOUNT` env overrides. Read the `env` fixture and the `restic`
   stub's `case "$1" in` dispatch before changing anything.
2. Extend the `restic` stub's dispatch with a `stats)` branch emitting a JSON object with a
   `total_file_count` field, controlled by an env var (e.g. `STUB_FILE_COUNT`, default something
   non-zero) and failable via `STUB_STATS_FAIL`.
3. Extend the `snapshots)` branch so the full-listing form can return a `paths` array, controlled by
   an env var (e.g. `STUB_SNAPSHOT_PATHS`).
4. Add a `df` stub emitting a plausible `avail` figure in bytes, controlled by `STUB_FS_AVAIL` and
   failable via `STUB_DF_FAIL`.
5. Add a test that runs the script on the happy path and asserts the emitted key set **exactly**
   equals the current ten keys. This will pass now and fail after T002–T006 — that is intended; you
   will update it to the final fourteen as the last step of T006.

**Validation**: The new test passes against the unmodified script. Existing tests in the file still
pass.

### T002 — Emit `last_integrity_check_utc`, carried forward

**Purpose**: Make "the verification stopped running" visible. This is the subtlest of the four and the
one a reviewer found; it is not the same as "the check did not run today".

**Why it is needed**: every backup failure path in the script `exit 1`s *before* the Sunday integrity
block. So a failed Sunday skips verification entirely, `integrity_check_passed` stays `null` for
another seven days, and every day of that reads healthy. Repeated bad Sundays leave the repository
unverified for months, green throughout.

**Steps**:
1. Near the other state defaults, initialise `LAST_INTEGRITY_CHECK_UTC=null`.
2. **Before** the document is overwritten, read the previous one and carry the value forward:
   read `$STATE_FILE` if it exists, extract `.last_integrity_check_utc` with `jq -r`, and keep it
   when it is a non-empty, non-`null` string.
3. **This read must fail soft.** A missing file, unreadable file, or malformed JSON must leave the
   default and must not abort the run. Redirect stderr, check the exit status, and validate the
   extracted value before using it — do not assume `jq` succeeded.
4. In the Sunday block, when `restic check` **passes**, set `LAST_INTEGRITY_CHECK_UTC` to the current
   UTC instant in the same format the script already uses for `script_finished_at_utc`
   (`date -u +%Y-%m-%dT%H:%M:%SZ`). Set it **only on pass** — the field means "last time the
   repository was verified *good*", not "last time we tried".
5. Emit it in the heredoc as a quoted string, or the bare literal `null` when unset.

**Files**: `scripts/office2/restic-backup.sh`

**Validation**:
- A run where the check does not execute preserves the prior value.
- A run with a passing check sets it to now.
- A run with a *failing* check leaves the prior value unchanged.
- A missing prior document yields `null` and the run still completes.
- A **corrupt** prior document yields `null` and the run still completes. Assert this explicitly — it
  is the failure mode that would take the backup down.

### T003 — Emit `files_processed` [P]

**Purpose**: Distinguish a real capture from an empty one. A source-path typo or over-broad exclude
yields exit 0, a real snapshot, and a fresh timestamp while capturing nothing.

**Steps**:
1. After a successful backup, obtain a file count with
   `restic stats --mode files-by-contents latest --json` and extract `.total_file_count` via `jq`.
2. Guard it exactly like `repo_size_bytes`: on any failure, empty output, or non-numeric result,
   default to the literal `null`.
3. Emit as `files_processed`.

**Why this source**: the alternative, `restic backup --json`, would replace the human-readable
`--verbose` log the runbook depends on. `stats` preserves the log at the cost of one extra scan over
a 3.6 GB repository. Do not switch the backup invocation to `--json`.

**Validation**: happy path emits the stub's count; `STUB_STATS_FAIL` yields `null` and the run still
succeeds.

### T004 — Emit `source_roots_present` [P]

**Purpose**: Catch a snapshot that is non-empty but missing an entire source root — a partial capture
mistaken for a complete one.

**Steps**:
1. The configured roots are the paths passed to `restic backup` (currently `/data/services`,
   `/data/transcripts`, `/home/claude`, `/home/kgale`). **Define them once** in a shell array near the
   top and use that array both for the `restic backup` invocation and for this check, so the two can
   never drift apart. This is the point of the subtask — a hardcoded second copy would be a new
   unenforced coupling.
2. From `restic snapshots --latest 1 --json`, read `.[0].paths[]`.
3. Emit `true` when every configured root appears, `false` when any is missing, `null` when the
   comparison could not be performed.
4. Emit as `source_roots_present` (a bare JSON boolean or `null`, never a quoted string).

**Validation**: all roots present → `true`; a root removed from the stub's `paths` → `false`;
snapshots query failing → `null`.

### T005 — Emit `repo_fs_free_bytes` [P]

**Purpose**: Make the approach to a full volume visible. The terminal state is not "backup fails" but
"filesystem full", which is a far bigger problem than a missed backup.

**Steps**:
1. `df -B1 --output=avail "$RESTIC_REPOSITORY"`, skip the header, take the number.
2. Guard as with `repo_size_bytes`: any failure or non-numeric result → `null`.
3. Emit as `repo_fs_free_bytes`.

**Note**: this measures the **filesystem**, not the repository. `repo_size_bytes` measures the
repository and stays diagnostic-only. They are different facts and both are kept.

**Validation**: emits the stub's figure; `STUB_DF_FAIL` yields `null` and the run still succeeds.

### T006 — Guard `snapshot_count`, bump the schema

**Purpose**: Close the invalid-JSON path on a field this mission is about to make load-bearing, and
record that the document's shape changed.

**Steps**:
1. After the `jq 'length'` assignment, add the same guard its sibling already has: if the result is
   empty or non-numeric, set it to `null`.
2. Change `"schema_version": 1` to `2` in the heredoc.
3. Update the T001 test to assert the final **fourteen**-key set exactly.
4. Update the block comment at the top of the script to describe the new keys, matching the existing
   comment style — including *why* `last_integrity_check_utc` is carried forward, because that is the
   non-obvious one.

**Validation**: a run where the count query yields nothing emits `"snapshot_count": null` and the
document still parses as JSON. Assert by `json.loads`, not by string matching.

## Branch Strategy

- **Planning branch**: `feat/934-pointer-key-ledger`
- **Final merge target**: `feat/934-pointer-key-ledger`
- **Topology**: `single_branch` — no coordination branch.
- Execution worktrees are allocated per computed lane from `lanes.json`. Work in the workspace the
  implement command gives you; do not create branches by hand.

## Test Strategy

Tests are **required** here (charter: any non-trivial helper ships with pytest coverage; and this
script's history is of defects that survived code review).

- Extend `tests/office2/restic_backup/test_pointer_emission.py` only. Do not create a second test
  module for this producer — WP05 adds reconciliation in its own file.
- Every test executes the **real script** under stubs. Do not assert against the heredoc's source
  text; that is a second model of the producer and it will drift.
- All tests must be offline and deterministic (NFR-002): no network, no real restic, no dependence on
  the actual date or day of week. Drive the Sunday branch by controlling the environment, never by
  waiting for a Sunday.
- Cover the **early-exit paths**, not just the happy path — mount failure and repo-inaccessible both
  still write a document via the `EXIT` trap, and their values matter downstream.

## Definition of Done

- [ ] The producer emits exactly fourteen keys on every path, asserted by executing it.
- [ ] `last_integrity_check_utc` carries forward across runs, sets only on a passing check, and
      survives a missing or corrupt prior document without aborting.
- [ ] `files_processed`, `source_roots_present`, `repo_fs_free_bytes` each emit a real value on the
      happy path and the literal `null` on their own failure, never an empty slot.
- [ ] `snapshot_count` is guarded; the document parses as JSON even when the count query fails.
- [ ] `schema_version` is `2`.
- [ ] Source roots are defined once and used for both the backup invocation and the presence check.
- [ ] `make test` passes with no reduction from the 6324-test baseline.
- [ ] The script's header comment explains the new keys.

## Risks and Review Guidance

**For the reviewer, in priority order:**

1. **Fail-soft, everywhere.** Trace each new key's failure path. Any addition that can abort the
   backup is a reject — this script running is more important than its instrumentation being complete.
2. **The carry-forward read.** Confirm it tolerates a missing *and* a corrupt prior document, and that
   the test proves both. This is the one place a naive `jq` call can take the backup down.
3. **Single definition of source roots.** If the roots are written twice, reject: that is a new
   unenforced coupling of exactly the kind this mission exists to retire.
4. **`null`, never empty.** Every guard must produce the JSON literal `null`. An empty shell variable
   produces invalid JSON, which downstream turns into `unknown` and — critically — a first-seen
   `unknown` does not alert. An unparseable document is a silent failure, not a loud one.
5. **Tests execute the script.** Reject any assertion made by reading the heredoc rather than running
   the producer.
