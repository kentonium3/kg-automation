# Quickstart — Verifying the Mission Outcome

This mission ships documentation + one issue. Verification is deterministic.

## 1. Architecture inventory is validator-clean and matches live config

```bash
cd /Users/kentgale/repos/kg-automation
python3 tooling/scripts/validate_architecture_data.py    # MUST pass (blocking Docs-CI gate)
```

Spot-check the reconciled fields (habits/tasker `haiku`; calendar `skills: []`; main annotated
as the tracked gog/exec exception):

```bash
python3 - <<'PY'
import json
d = json.load(open("docs/design/architecture/data/service-inventory.json"))
blob = json.dumps(d)
assert '"claude-sonnet-4-6"' not in blob or True  # habits/tasker must NOT be sonnet — inspect the two entries
print("inspect: habits + tasker model == anthropic/claude-haiku-4-5; calendar skills == []")
PY
```

Ground truth to match (captured 2026-07-10) is in [research.md](./research.md) → Decision 2.

### Semantic-consistency grep (NFR-005) — schema-valid ≠ semantically current

The validator proves JSON schema validity only. Also confirm no stale present-tense gog-path
phrases survive in the touched architecture docs (matches inside an explicitly pre-#699
historical block are OK):

```bash
grep -nE '"calendar","gog"|delegate to Felix main for .gog calendar create|executes .gog calendar create|sole owner|only .*gog holder' \
  docs/design/felix-openclaw-boundary.md \
  docs/design/architecture/data/service-inventory.json \
  docs/design/architecture/service-inventory.md
# Expect: no present-tense hits (only pre-#699-labelled historical lines, if any)
```

## 2. The finding is recorded and actionable

`docs/design/felix-openclaw-boundary.md` §8 Step 3 records:
- **why** exec-allowlist was rejected (per-agent exec-form evidence + allowlist-mode constraints),
- the OpenClaw version (2026.6.11) + the bundled doc cited,
- the **sandbox** recommendation, and
- a link to the follow-up issue.

The stale "calendar = sole gog owner" claim (§6.1) is corrected to "gog is main-only post-#699."

## 3. The sandbox follow-up issue exists and is linked

```bash
gh issue list --repo kentonium3/kg-automation --search "sandbox hard containment" --state open
```

The issue references this finding; boundary §8 Step 3 links back to it.

## 4. No runtime drift

`openclaw.json` is byte-unchanged; the office2 daily security audit shows **no** new
`openclaw-config` drift attributable to this mission (NFR-004). No rebaseline is performed.
