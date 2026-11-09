# Quickstart: Repeat cutover to v2.8.0-rrule.2

The runbook `docs/runbooks/vikunja-release-cutover.md` is authoritative. This is the order of operations. Any failed check stops the sequence, with no bypass or blind retry.

1. Merge PR1 once review and CI pass. Private values stay out of git.
2. Copy the candidate and ingress the published archive, checking exact bytes and hash. Let the STAGE manifest apply, then confirm the new image identity and that the previous image is retained. The service keeps running.
3. Check the notification disposition. If the backfill can reach only Kent, or mail is off and nothing reacts, record acceptance and proceed. If it could notify anyone else, or trigger an automation that cannot be paused, ask Kent first.
4. Confirm a Restic backup at most 24 hours old (tier 2).
5. Pause the Felix crons and `felix-vikunja-sync.timer`.
6. Run `preflight_release_baseline.py`. Require `PREFLIGHT_OK`, which includes the 90-second budget.
7. Send the lead a one-line note, then merge PR2. ACTIVATE stops the service, snapshots, runs the gate, selects the image, starts it and verifies it.
8. With writes closed, run A1–A3, B3 and B4 from the runbook, then `verify_release_upgrade.py` for migration IDs, integrity and subscription aggregates. Report to Kent.
9. Keep automations paused until Kent records ACCEPT. Kent does browser acceptance and decides ACCEPT or ROLLBACK.

## On failure

- Failure or crash before `snapshotted` is recorded: use `--recover-pre-snapshot`, which decides from the marker, including an unfinished one.
- Failure at the gate or later: stop, keep service state and evidence, and bring Kent the exact rollback steps with the write-loss count. Kent performs the privileged restore and acknowledgement. Never start the previous image on the upgraded database.

## Local verification

```sh
python3 -m pytest -q --ignore=docs/archive
python3 tooling/scripts/validate_docs.py
```
