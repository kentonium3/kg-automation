# Quickstart / Verification: Retire _private folder guard apparatus

How to verify the mission's acceptance criteria. Run from repo root unless noted.

## Pre-flight (NFR-002, D6)

```bash
# Re-confirm the private folder is absent from office2's vault before removing guards.
ssh office2-claude 'ls -d /home/kgale/second-brain/notes/04-Growth/_private 2>&1'
# Expect: "No such file or directory"
```

## SC-001 — no residual folder-specific ENFORCEMENT remains

```bash
# Live surfaces only (exclude frozen archives, kitty-specs, .kittify, the migration allowlist).
grep -rn "04-Growth/_private" . \
  | grep -vE "\.git/|kitty-specs/|\.kittify/|docs/archive/|docs/research/|vault-path-registry-migration|observation/tests/fixtures"
# Expect: only intentional physical-exclusion NARRATIVE (if any), never an enforced red-line,
# validator constant, or "absolute rule". Zero enforcement occurrences.
```

## SC-002 — gates green without the privacy-boundary lint

```bash
# The validator is gone; nothing calls it.
test ! -f tooling/scripts/validate_privacy_boundary.py && echo "validator removed: OK"
grep -rn "validate_privacy_boundary" .githooks/ .github/workflows/ Makefile .agents/ && echo "STILL WIRED (bad)" || echo "no dangling callers: OK"

# Local pre-commit gate + full suite.
python3 -m pytest tests/ -q            # 0 failures
# (pre-commit runs automatically on the mission's own commits; confirm green.)
```

## SC-004 + NFR-003 — general hygiene retained + generalized

```bash
python3 -m pytest tests/escalation/test_hard_fail.py tests/inbox/test_mark_processed.py -q
# Expect pass; assertion count for leak/refusal >= pre-change count.
```

## SC-005 + FR-008 — unrelated feature untouched

```bash
git diff --name-only main...HEAD | grep -E "test_sync_cache|sync_cache" && echo "TOUCHED (investigate)" || echo "Vikunja is_private untouched: OK"
python3 -m pytest tests/common/test_sync_cache.py -q   # still green
```

## SC-006 — graph-ingest model reframed

```bash
# The design docs describe "verify not present", not "never ingest _private" enforcement.
grep -n "verify\|physical exclusion\|not present" docs/design/second-brain-graph-layer.md docs/design/executive-assistant-architecture.md
grep -n "never ingest\|absolute rule" docs/design/second-brain-graph-layer.md docs/design/executive-assistant-architecture.md \
  && echo "stale enforcement language remains (bad)" || echo "reframed: OK"
```

## SC-003 + NFR-004 — agents deploy + smoke (office2)

```bash
# Deploy cleaned prompts via the existing agent-prompt-sync path, then verify parity + smoke.
# (agent-prompt-sync is a pull-based systemd timer; force/verify per docs/runbooks/openclaw-agent-setup.md.)
# Parity: repo prompt files vs deployed under /data/services/openclaw/... (md5 match).
# Smoke: one message round-trip per affected agent; each responds normally with no _private reference required.
# Validator: workspace validator passes without the privacy invariants.
python3 -m pytest scripts/openclaw/agents/tests/test_validate_workspace.py -q
```

## C-003 — rebaseline disposition (confirm, don't assume)

```bash
# Prompt content is not hashed by audit.sh (#621) → expect "All clear" (no drift from prompt edits).
ssh office2-claude 'sg docker -c /data/services/security-monitor/scripts/audit.sh 2>&1 | tail -3'
# If All clear: record "Rebaseline: not required — agent prompts not content-hashed by audit.sh (#621)".
# If unexpected drift: investigate before recording.
```

## Done-when

All of SC-001..006 pass, both hygiene test files green with retained coverage, office2 agents
smoked, and the rebaseline disposition recorded on the merge.
