# felix-health-check coverage fixtures (#1063)

- `last-tick.2026-10-14.json`: verbatim copy of office2
  `/data/services/felix-canary/state/last-tick.json`, captured 2026-10-14 ~18:45Z.
- `last-backup.2026-10-14.json`: verbatim copy of office2
  `/data/services/backup/state/last-backup.json`, captured the same day. It holds the manual
  15:30:30Z snapshot taken after the backup drive was re-seated (#1064).
  **It is genuinely unhealthy by the `restic-backup` key ledger**, because the weekly integrity
  check runs only on Sundays from `backup.sh`. The outage skipped 2026-10-04 and 2026-10-11, so
  `last_integrity_check_utc` (2026-09-27) is past its 9-day bound. Tests use it as a real failing
  case.

Derived shapes are built in the tests from these files and documented where they are built:
- the healthy-backup control, the real pointer with `last_integrity_check_utc` set to the
  2026-10-11 Sunday run that would have happened;
- the incident pointer, derived from `scripts/office2/restic-backup.sh`'s not-mounted path;
- the dead tick, last real tick 2026-09-27T15:52Z, replayed at 2026-09-28T11:00:03Z.
