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
empty. Post-plan review findings and dispositions are appended below.
