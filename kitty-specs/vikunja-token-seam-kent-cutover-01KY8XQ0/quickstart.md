# Quickstart / Verification — Vikunja token seam + kent cutover (phase 2 of #860)

## Local verification (per-step gates)

**After centralize (IC-01..03, still felix-bot):**
```bash
# Behavior-preserving: full affected suite + architectural ratchets green
python3 -m pytest tests/ -q -k "vikunja or inbox or habits or escalation or enrichment or trust or sync"
python3 -m pytest tests/architectural/ -q
```

**After the flip (IC-04):**
```bash
# SC-002 — single-point flip proof (the new test): overriding the one point moves every consumer
python3 -m pytest tests/ -q -k "token_seam or single_point or get_vikunja_token_path"
```

**SC-001 architectural gate (final, post-flip):**
```bash
# Expect ZERO runtime-consumer matches; only admin/one-shot + docs may appear.
grep -rnE "secrets/vikunja-api([^-]|$)" scripts/
```

## Attended Tier-2 cutover (IC-07 — office2, operator present)

Pre-flight:
```bash
# Restic snapshot ≤24h (Tier-2 gate)
ssh office2-claude 'cat /data/services/backup/state/last-backup.json'   # snapshot_timestamp_utc within 24h
```

Before/after connectivity baseline (both must match expectation):
```bash
# BEFORE (still felix-bot on office2) and AFTER (kent), for each consumer + the inverse probe:
ssh office2-claude 'BASE="https://office2.tail0f5f56.ts.net/api/v1"
  curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api-kent)" "$BASE/projects" \
    | python3 -c "import sys,json;print(sorted(p[\"id\"] for p in json.load(sys.stdin)))"'
# Inverse probe: kent view MUST include 16,17,18,19,20 and Inbox 1 + Habits 13.
```

Cutover = merge `feat/vikunja-token-seam-kent-cutover` → `main`; felix-deployer self-pulls and the runtime
starts resolving the kent token. Then spot-verify each consumer runs correctly as kent (sync exit 0 /
`cycle_error` null / cache refresh; a habits write; the credential-health writer), and confirm the
inverse-probe projects are now in the runtime view.

## Rebaseline (SC-005)

The credential-manifest is an audited surface. Record on the merge commit:
`Rebaseline: completed at <ts>` (auto via felix-deployer deferred-confirm) **or**
`Rebaseline: not required — <reason>`.
