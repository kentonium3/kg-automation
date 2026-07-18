# Quickstart: Task-Intake Validation Loop

How to exercise the loop end-to-end (mocked locally; live on office2).

## Local (mocked Vikunja)

```bash
# Scan: classify Inbox tasks and render the digest (no writes)
python3 -m scripts.intake.scan_inbox --dry-run --json --now-utc 2026-07-17T22:00:00Z

# Apply: feed a shorthand reply against a fixture correlation record (no writes)
printf '1 pointerhealth f3 schedule due:2026-07-22\n2 personal f1 do\n' \
  | python3 -m scripts.intake.apply_reply --reply - --state-dir tests/intake/fixtures --dry-run --json
```

Unit tests (deterministic, no live services — NFR-001):
```bash
pytest tests/intake -q
```
Coverage targets: Tier-1 classification (incl. `f:4` excluded), the full token
grammar + alias table resolving 100% of documented tokens without LLM (NFR-002),
read-modify-write non-clobber (NFR-003), echo-back on unresolved lines (FR-012),
and idempotent re-apply (FR-013).

## Live (office2)

```bash
# One inbox tick already runs the scan after route_and_finalize; to check state:
ssh office2-claude 'cat /data/services/openclaw/state/intake/intake-tick-$(TZ=America/New_York date +%F).json'

# Verify the seam declares the friction/quadrant labels (drift gate green):
python3 -m scripts.common.vikunja_refs_validate
```

Reply flow: the capture cron sends the numbered digest over WhatsApp; Kent
replies with the shorthand lines; the main agent correlates to the most-recent
digest and invokes `apply_reply`, then confirms what was applied (and echoes any
unparseable line).

## Definition of done signals
- SC-001..SC-009 in `spec.md` demonstrably pass (mocked corpus + one live tick).
- `vikunja_refs_validate.py` green with the new label declarations.
- #750 closed: no felix-bot label-attach path exists; all writes via the kent token.
