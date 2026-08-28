# Research: Backup Integrity Observability

Every claim below was verified against the live host or the installed source on
2026-08-28.

## R-01 — The #899 boundary forbids automating the backup-script deploy

- **Decision**: `restic-backup.sh` stays hand-installed by the operator. #903
  resolves as detection plus a written decision.
- **Rationale**: The deploy applier runs as `claude`. Installing the script means
  writing `/data/services/backup/scripts/`, which holds the `NOPASSWD` sudo
  target `backup.sh`. Verified live, both halves of the #899 condition:

  ```
  $ ls -ld /data/services/backup/scripts
  drwxr-xr-x 2 root root ...
  $ touch /data/services/backup/scripts/.wtest
  Permission denied
  $ sudo -n -l | grep backup
      (root) NOPASSWD: /data/services/backup/scripts/backup.sh
  ```

  #899's root cause, in its own words: "A NOPASSWD grant names a path, not an
  inode… the leaf directory is `claude:claude 775`, so the grant is equivalent to
  `NOPASSWD: ALL`." Making that directory writable again to save a manual install
  would re-open a fixed privilege escalation.
- **Alternatives considered**: (a) relocate the script to a claude-owned path —
  rejected, the sudoers rule and root crontab both name the absolute path, and it
  is Tier 0; (b) a narrower sudoers rule permitting a specific install command —
  rejected, still Tier 0 and still widens a root-execution surface for
  convenience; (c) accept manual install, detect divergence — chosen.

## R-02 — A new pointer field is invisible unless the scan is taught to read it

- **Decision**: Add `prune_exit_code` and extend `_explicit_error` to check it.
- **Rationale**: `scripts/canary/probes.py:262-300` reads exactly seven keys:
  `restic_exit_code`, `exit_code`, `exit_status`, `status`, `errors`, `error`,
  `cycle_error`. A `prune_exit_code` field would be recorded faithfully and read
  by nothing — a pointer full of evidence beside a health check still reporting
  healthy. That is the #902 defect with extra steps.
- **Alternatives considered**: writing the failure into the existing `errors` key,
  which needs no canary change. Rejected: it conflates "the prune failed" with a
  generic error list and makes the pointer less self-describing, and the
  inventory `expected` prose could not state the rule precisely. The chosen
  option mirrors the existing `restic_exit_code` handling and only fires when the
  key is present, so no existing component changes behaviour.

## R-03 — `null` for "prune not attempted" reopens the hole

- **Decision**: `PRUNE_RC` initialises to `127`, matching the existing
  `BACKUP_RC=127  # "not run" sentinel` convention already in the script.
- **Rationale**: With `null`, a script killed between a successful backup and the
  prune writes `restic_exit_code: 0` and `prune_exit_code: null`. The scan
  guards with `isinstance(code, int)`, so `null` is skipped and the pointer reads
  **healthy** — precisely the silent-success path this mission exists to close.
  `127` reads unhealthy, which is true: retention did not run.
- **Trade-off accepted**: a failed backup exits before the prune, so it will also
  report `prune_exit_code: 127`. Double signalling on an already-unhealthy
  component, and arguably accurate.

## R-04 — Fixing the stale grep pattern would re-arm the trap

- **Decision**: Add `--emit-body` to `crontab_capture.py`, reusing
  `strip_header()`.
- **Rationale**: The #906 defect is not a wrong pattern, it is an unenforced
  coupling: header removal is implemented in code and re-implemented in prose,
  with nothing binding them. Verified live that the documented pattern now leaves
  two header lines behind, so the documented *verification* reports a false
  failure and the documented *recovery* installs a crontab that grows a stray
  comment pair on every recovery cycle. Correcting the pattern restores today's
  behaviour and leaves the next header change to break it again.
- **Alternatives considered**: a test asserting the prose pattern matches the
  header. Rejected — it binds the two but keeps two implementations; the emitter
  removes the second one entirely.

## R-05 — The comparator must fail closed

- **Decision**: An unreadable deployed copy reports `inconclusive`, never `match`.
- **Rationale**: The deployed copy is `root:root 755`, world-readable today, so
  the normal path works unprivileged. But a permission change, a missing file, or
  a mid-install partial write must not be reported as agreement. A comparator
  that fails open is the same defect class it exists to detect. This mirrors the
  `_unevaluable` / honest-unknown discipline already used by the canary probes.

## R-06 — The comparator's first act will be to report drift

Not a risk; a property worth stating. This mission changes
`scripts/office2/restic-backup.sh`, and the host will not have that change until
the operator installs it. So on first run the comparator will correctly report
divergence, and clear once the install happens. The tool's first real signal is
about its own mission.

## Adversarial evidence

No dependency is added, upgraded, or removed, so the supply-chain decision set is
empty.

## Post-plan review (Codex, read-only, 2026-08-28)

Two independent Codex runs on the same artifacts. Seven distinct findings, **all
accepted and folded in**; none deferred, none dropped. Both runs independently
raised the install-source gap and the prune good-set, which is the strongest
signal in the set.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | The privileged `sudo install` sourced from `/home/claude/kg-automation`, a claude-writable checkout, installing as root into the NOPASSWD target. Protects the destination, weakens the same boundary at the source. | **changed** — FR-010 added; quickstart now verifies the source against the reviewed commit, checks the working tree is clean, and confirms the installed hash afterwards. Raised independently by both runs. |
| 2 | HIGH | `_RESTIC_OK_EXIT_CODES` is `{0, 3}`; mirroring it for prune would accept exit 3, which for `forget` does not mean retention was applied. The backup script already treats only `0` as success. | **changed** — C-006 added pinning the prune good-set to `{0}`; plan corrected; tests must assert `3` is unhealthy. Raised independently by both runs. |
| 3 | HIGH | Pre-existing: restic freshness falls through `TIMESTAMP_KEYS` from `snapshot_timestamp_utc` to `script_finished_at_utc`, so a pointer with a null snapshot timestamp reads healthy — contradicting the inventory's own `expected` prose. Verified through the real probe: `ok=True, stale=False`. | **changed** — folded in as FR-009/SC-007 rather than deferred. Not caused by this mission, but the same defect class in the same component; shipping "backup integrity observability" around it would be hollow. |
| 4 | HIGH | `--emit-body` cannot fail closed by reusing today's `strip_header()`, which returns input unchanged both when no header matches and when the sentinel is missing — it cannot tell the caller whether a header was recognised. | **changed** — data-model now specifies refactoring to one shared parser returning body plus recognition, capture staying tolerant and the emitter failing closed. Run 2's framing was adopted over run 1's, because run 1's "add an emitter-level recogniser" would have created the second implementation this mission exists to remove. |
| 5 | MEDIUM | The comparator's health check must declare `success_status_values: ["success"]`; without an allow-list `probes.py` treats `status` as a deny-list and an unrecognised verdict word passes as healthy. | **changed** — required in the data model (#891 affirmative-health rule). |
| 6 | MEDIUM | Tier 3 manifests do not require a `verification` block, so a deploy that installs nothing can still pass. | **changed** — manifest declares `verification.post` regardless. |
| 7 | MEDIUM | The signal-to-doc-map lookup missed `deploy-manifest-added` and `office2-service-deployment`. | **changed** — verified both exist with targets not in the plan; added. Note run 2 judged the doc coverage complete and was wrong here; run 1 was right, which is why the map was re-queried rather than either verdict taken on trust. |

### Confirmed correct during review

- The `127` sentinel, with a full failure-path trace: mount-check failure,
  repo-inaccessible, backup failure, and killed-between-backup-and-prune all
  report `prune_exit_code: 127` and are correctly unhealthy; backup exit 3 with a
  clean prune stays healthy, consistent with existing semantics.
- Backward compatibility: `_explicit_error` ignores absent keys, and
  `snapshot.py`'s Tier-2 gate reads only `restic_exit_code` and timestamps, so
  the new field is inert there.
- The #899 argument against automating the deploy is correct, and the
  comparator's *reads* of that directory do not weaken the boundary provided it
  never writes there.
