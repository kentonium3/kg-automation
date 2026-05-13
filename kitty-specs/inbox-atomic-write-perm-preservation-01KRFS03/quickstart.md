# Quickstart: Inbox atomic-write permission preservation

**Mission**: `inbox-atomic-write-perm-preservation-01KRFS03`

This guide walks the implementer through verifying the fix end-to-end after the work packages have run.

---

## 1. Local verification (Mac)

```bash
cd /Users/kentgale/repos/kg-automation
python3 -m pytest tests/inbox/ -v
```

**Expect**: 85 existing tests pass + new `test_atomic_write_perms.py` tests pass (at least 5 cases per helper × 2 helpers = 10+ new tests).

## 2. Deploy to office2

```bash
bash scripts/deploy/deploy-149.sh --apply --backup-confirmed
```

**Expect**: `/home/claude/kg-automation/scripts/inbox/inject_parse_error_marker.py` and `strip_parse_error_marker.py` updated on office2 with executable bits intact.

## 3. Smoke test — `inject_parse_error_marker.py` with mode preservation

On office2, as kgale, prepare a test file at a known mode:

```bash
echo -e "---\ntitle: smoke test\nstatus: unprocessed\n---\n\nBody." > /tmp/smoke.md
chmod 0664 /tmp/smoke.md
ls -la /tmp/smoke.md
```

**Expect**: `-rw-rw-r-- 1 kgale ... /tmp/smoke.md`.

Then as claude, run the marker injector:

```bash
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/inbox/inject_parse_error_marker.py /tmp/smoke.md 999 --date 2026-05-13 2>&1'
ssh office2-claude 'ls -la /tmp/smoke.md'
```

**Expect**:
- stderr contains `INFO: atomic_write /tmp/smoke.md mode=0o664 (preserved)`.
- `ls -la` shows mode `-rw-rw-r--` (still `0o664`, not `0o600`).
- File ownership becomes `claude:...` (UID preservation is out of scope; this is expected).

## 4. Smoke test — `strip_parse_error_marker.py` with mode preservation

Continuing on office2 as claude:

```bash
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/inbox/strip_parse_error_marker.py /tmp/smoke.md 2>&1'
ssh office2-claude 'ls -la /tmp/smoke.md'
```

**Expect**: same as step 3 — mode remains `0o664`, stderr log line emitted.

## 5. End-to-end canary (SC-002)

This is the load-bearing verification per the spec.

1. **Drop fresh canary on Mac**:
   ```bash
   cat > "/Users/kentgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 canary.md" <<'EOF'
   ---
   title: SC-002 canary
   status: "unterminated string
   created: 2026-05-13
   ---

   Body.
   EOF
   ```

2. **Wait for sync**: confirm office2 has it:
   ```bash
   ssh office2-claude 'head -5 "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 canary.md"'
   ```

3. **Trigger prescan + agent**:
   ```bash
   ssh office2-claude 'openclaw cron run 7fa9b299-f8fc-44c2-b37d-de4163c80cdf'
   ```

4. **Verify marker injected with correct mode**:
   ```bash
   ssh office2-claude 'ls -la "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 canary.md"; tail -5 "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 canary.md"'
   ```
   **Expect**: mode `0o664` (group-readable), marker present at end of file.

5. **Fix YAML on Mac**:
   Open `Inbox 2026-05-13 canary.md` in Obsidian and replace `status: "unterminated string` with `status: unprocessed`. Save.

6. **Verify Mac→office2 sync within 5 min**:
   ```bash
   ssh office2-claude 'head -5 "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 canary.md"'
   ```
   **Expect**: `status: unprocessed`. This is SC-002 verification — no manual chmod or rm required.

7. **Cleanup**: delete the canary from Mac inbox; sync propagates the deletion.

## 6. Rollback (if needed)

```bash
git revert <merge-commit-hash>
bash scripts/deploy/deploy-149.sh --apply --backup-confirmed
```

The deploy script's `--backup-confirmed` flag uses the most recent Restic snapshot. Re-running after a revert restores the prior helper code on office2.
