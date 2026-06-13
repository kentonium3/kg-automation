---
work_package_id: WP03
title: Rotation-script integration + rollback
dependencies:
- WP01
- WP02
requirement_refs:
- FR-012
- FR-013
- FR-014
- NFR-006
tracker_refs:
- kentonium3/kg-automation#597
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
agent: claude
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/security/
execution_mode: code_change
mission_slug: openclaw-auth-verifier-01KV0Y9E
owned_files:
- scripts/security/anthropic-rotate.sh
- tests/security/test_anthropic_rotate_gate.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

Extend the existing `scripts/security/anthropic-rotate.sh` with two changes: (a) write a per-rotation manifest at rotation start, then invoke `anthropic-verify --check` as a fail-closed gate at rotation end — on verify failure, emit a copy-pasteable rollback command and exit non-zero (no auto-rollback); and (b) add a `--rollback <ts>` argparse branch that reads the manifest and restores the three rotation artifacts (plaintext file, `openclaw.json`, the SQLite-side `auth-profiles.json.sqlite-import.<ts>.bak`).

## Context

The existing `anthropic-rotate.sh` (shipped via `#591`) follows a five-step flow: paste new key → write plaintext → update SQLite via `openclaw models auth paste-api-key` → restart gateway → run `inbox-7am` liveness probe. It already creates a `.bak` for `openclaw.json` automatically (per the openclaw CLI behavior). It does NOT currently keep a manifest of all backups for a rotation, so there's no way for a separate `--rollback` command to find the right files later.

This WP adds:

- **Manifest write at rotation start** (FR-013 transitively): immediately after argument parsing, the script writes `~/.cache/anthropic-rotate/manifest.<unix-ts>.json` listing the paths of the three backups that will be created during this rotation. The unix-ts is the rotation timestamp; it's also written to a shell variable `ROTATION_TS` used in step 6.
- **Step 6 verify gate** (FR-012, FR-013, NFR-006): after Step 5 (liveness probe), invoke `anthropic-verify --check`. On non-zero exit, print the findings (captured from the verifier's stdout) and a one-line `--rollback ${ROTATION_TS}` command, then exit with the verifier's exit code. Add ≤ 5 seconds to a successful rotation (the verifier's own NFR-001 budget is 30 s; the extra overhead is just the subprocess spawn).
- **`--rollback <ts>` mode** (FR-014): a new argparse branch. Reads `~/.cache/anthropic-rotate/manifest.<ts>.json`, validates all three backup paths exist, restores them in order (openclaw.json → SQLite import bak → plaintext file), restarts the gateway, reports the result. If any backup is missing, refuses to roll back partially.

The existing rotate script's self-update-from-main re-exec pattern (`exec "${BASH_SOURCE[0]}" "$@"`) must be preserved.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Depends on WP01 + WP02 — the verifier's `--check` and `--repair` modes must be available before the rotation script can invoke them. Spec-kitty's `next` flow allocates the worktree based on the dependency chain.

## Subtask guidance

### T011 — Add manifest write + Step 6 verify gate to `anthropic-rotate.sh`

Insert the following changes in the existing script. The manifest write happens immediately after the argparse block (around line 50 of the current script):

```bash
# ---- step 0: manifest write ----------------------------------------------

ROTATION_TS=$(date +%s)
MANIFEST_DIR="${HOME}/.cache/anthropic-rotate"
MANIFEST_FILE="${MANIFEST_DIR}/manifest.${ROTATION_TS}.json"
mkdir -p "${MANIFEST_DIR}"

# Compute the three backup paths up front so the manifest is written before
# any artifact is mutated.
PLAINTEXT_BAK="${PLAINTEXT_FILE}.pre-rotate.${ROTATION_TS}.bak"
OPENCLAW_JSON="${HOME}/.openclaw/openclaw.json"
OPENCLAW_JSON_BAK="${OPENCLAW_JSON}.bak"   # written by openclaw models auth paste-api-key
SQLITE_IMPORT_BAK="${HOME}/.openclaw/agents/main/agent/auth-profiles.json.sqlite-import.${ROTATION_TS}.bak"

cat > "${MANIFEST_FILE}" <<MANIFEST
{
  "rotation_ts": ${ROTATION_TS},
  "started_at_iso": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backups": {
    "plaintext_file": "${PLAINTEXT_BAK}",
    "openclaw_json": "${OPENCLAW_JSON_BAK}",
    "sqlite_import_bak": "${SQLITE_IMPORT_BAK}"
  },
  "rotation_completed_at_iso": null,
  "verify_outcome": null
}
MANIFEST
chmod 600 "${MANIFEST_FILE}"
echo "==> manifest: ${MANIFEST_FILE}"
```

Also update Step 2 (write plaintext file) to copy the existing plaintext to `${PLAINTEXT_BAK}` before overwriting — currently the script just overwrites; this WP adds the backup.

Then add Step 6 immediately after the existing Step 5 (liveness probe), before the closing summary:

```bash
# ---- step 6: verify (fail-closed gate) -----------------------------------

echo "==> Step 6: anthropic-verify --check (fail-closed gate)..."
VERIFY_OUTPUT=$(/home/claude/kg-automation/scripts/security/anthropic-verify.sh --check 2>&1) || {
  VERIFY_EXIT=$?
  echo "$VERIFY_OUTPUT" >&2
  cat <<EOF >&2

==> ROTATION VERIFY FAILED (exit ${VERIFY_EXIT} after rotation).
==> Rotation artifacts ARE in place but verifier flagged a finding above.
==> Inspect the finding, then EITHER remediate forward (e.g., anthropic-verify --repair if shadow)
==> OR roll back this rotation:

    /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback ${ROTATION_TS}

==> The rollback restores the plaintext file, openclaw.json, and the SQLite import-bak
==> from the per-step backups recorded at rotation start.
EOF
  # Update manifest with failure outcome
  python3 -c "
import json, pathlib
p = pathlib.Path('${MANIFEST_FILE}')
d = json.loads(p.read_text())
d['verify_outcome'] = 'failed'
d['rotation_completed_at_iso'] = None
p.write_text(json.dumps(d, indent=2))
"
  exit ${VERIFY_EXIT}
}
echo "  verify: green"

# Update manifest with success outcome
python3 -c "
import json, pathlib
from datetime import datetime, timezone
p = pathlib.Path('${MANIFEST_FILE}')
d = json.loads(p.read_text())
d['verify_outcome'] = 'passed'
d['rotation_completed_at_iso'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
p.write_text(json.dumps(d, indent=2))
"
```

The python3 invocations are fine because the script already requires python3 (the liveness probe uses it).

### T012 — Add `--rollback <ts>` mode to `anthropic-rotate.sh`

In the argparse block at the top of the script (between `--skip-liveness` and `--help` cases), add:

```bash
--rollback)
  ROLLBACK_TS="$2"
  shift 2
  ;;
```

After the argparse loop, branch:

```bash
if [[ -n "${ROLLBACK_TS:-}" ]]; then
  MANIFEST_DIR="${HOME}/.cache/anthropic-rotate"
  MANIFEST_FILE="${MANIFEST_DIR}/manifest.${ROLLBACK_TS}.json"
  if [[ ! -f "${MANIFEST_FILE}" ]]; then
    echo "ERROR: manifest not found: ${MANIFEST_FILE}" >&2
    exit 1
  fi
  echo "==> anthropic-rotate --rollback ${ROLLBACK_TS}"
  echo "==> manifest: ${MANIFEST_FILE}"
  PLAINTEXT_BAK=$(python3 -c "import json,sys; print(json.load(open('${MANIFEST_FILE}'))['backups']['plaintext_file'])")
  OPENCLAW_JSON_BAK=$(python3 -c "import json,sys; print(json.load(open('${MANIFEST_FILE}'))['backups']['openclaw_json'])")
  SQLITE_IMPORT_BAK=$(python3 -c "import json,sys; print(json.load(open('${MANIFEST_FILE}'))['backups']['sqlite_import_bak'])")
  # Verify all three backups exist before mutating anything
  MISSING=()
  for path in "${PLAINTEXT_BAK}" "${OPENCLAW_JSON_BAK}" "${SQLITE_IMPORT_BAK}"; do
    [[ -f "$path" ]] || MISSING+=("$path")
  done
  if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "ERROR: backup(s) missing — refusing partial rollback:" >&2
    printf '  - %s\n' "${MISSING[@]}" >&2
    exit 1
  fi
  echo "==> restoring openclaw.json..."
  cp "${OPENCLAW_JSON_BAK}" "${HOME}/.openclaw/openclaw.json"
  chmod 600 "${HOME}/.openclaw/openclaw.json"
  echo "==> restoring SQLite import bak (triggers openclaw doctor --fix import)..."
  cp "${SQLITE_IMPORT_BAK}" "${HOME}/.openclaw/agents/main/agent/auth-profiles.json"
  openclaw doctor --fix --non-interactive >/dev/null
  echo "==> restoring plaintext file (atomic)..."
  cp "${PLAINTEXT_BAK}" "${PLAINTEXT_FILE}.tmp"
  chmod 600 "${PLAINTEXT_FILE}.tmp"
  mv "${PLAINTEXT_FILE}.tmp" "${PLAINTEXT_FILE}"
  echo "==> restarting openclaw-gateway.service..."
  systemctl --user restart openclaw-gateway.service
  echo "==> rollback complete. Run anthropic-verify --check to confirm."
  exit 0
fi
```

The `cp` of the SQLite import bak intentionally restores it under the canonical `auth-profiles.json` name (without the `.sqlite-import.<ts>.bak` suffix) so that `openclaw doctor --fix --non-interactive` finds it and re-imports it into the SQLite store. This is the original path the 2026.6 migration uses.

### T013 — Tests for the rotation-script gate and rollback

`tests/security/test_anthropic_rotate_gate.py`:

These tests exercise the bash script via `subprocess.run` against a temp-dir-built fixture office2 layout. The verifier itself is stubbed via a `PATH`-injected shell script that emits canned output and exits with a chosen code.

Test cases:

- **Manifest written at start**: invoke a no-op rotation (skip the interactive paste via a wrapper that supplies the key on stdin); assert `~/.cache/anthropic-rotate/manifest.<ts>.json` exists with the expected JSON shape.
- **Verify gate — green path**: stub `anthropic-verify.sh` to return exit 0; assert the rotation script's exit code is 0; assert the manifest's `verify_outcome` is `"passed"`.
- **Verify gate — shadow path (exit 2)**: stub `anthropic-verify.sh` to print a shadow finding and exit 2; assert the rotation script's exit code is 2; assert the rotation script's stderr contains the `--rollback ${ROTATION_TS}` command; assert the manifest's `verify_outcome` is `"failed"`.
- **Rollback — manifest missing**: invoke `--rollback 9999999999`; assert exit 1 with "manifest not found" message.
- **Rollback — backups present**: build a synthetic post-rotation state with all three backups in place; invoke `--rollback <ts>`; assert all three artifacts restored; assert post-rollback `--check` (real verifier this time) returns 0 against the restored state.
- **Rollback — backup missing**: synthesize a state where the plaintext bak is missing; invoke `--rollback <ts>`; assert exit 1 with "backup(s) missing" message; assert NO mutation occurred (other artifacts unchanged).
- **NFR-006 — overhead ≤ 5 s**: time the `--check` invocation within the rotation flow; assert duration < 5 s.

Use `subprocess.run(["bash", "-c", f"PATH={tmp_bin}:$PATH {script}"])` to inject the verifier stub. Use `tmp_path` for `${HOME}` so the manifest cache and openclaw paths don't pollute the developer's real environment.

### Files touched (final list)

- `scripts/security/anthropic-rotate.sh` (MODIFIED, ~+90 lines: manifest at start, Step 6 verify gate, `--rollback <ts>` branch)
- `tests/security/test_anthropic_rotate_gate.py` (NEW, ~280 lines)

## Test strategy

Test-first per DIRECTIVE_034. Author T013 against the spec contracts before T011/T012. Stub the verifier via `PATH` injection so the rotation-script tests don't depend on the verifier's full behavior. Use `tmp_path` aggressively to isolate from the developer's real `~/.cache/` and `~/.openclaw/`.

## Definition of Done

- All 3 subtasks completed; all tests pass; shellcheck clean on `anthropic-rotate.sh`.
- A real rotation against an office2 staging environment shows: manifest written at start, Step 6 verify reports green, rotation succeeds end-to-end.
- A deliberately-engineered post-rotation shadow (inject a row before Step 6) triggers the verify gate; the rotation script prints the rollback command and exits non-zero.
- `--rollback <ts>` against the staging environment restores the three artifacts and a subsequent `--check` reports green.

## Risks

- **Self-update re-exec interaction**: the existing script re-execs itself after pulling main; the new flags and manifest write must happen AFTER the re-exec. Place the manifest write after the `exec` line in the source. Verify by running the script twice (the second invocation should not re-pull or re-exec, per the `ANTHROPIC_ROTATE_REEXECED` guard).
- **Manifest path collision**: `manifest.<ts>.json` uses a unix timestamp; two rotations in the same second would collide. Unlikely in practice; if it ever happens, the second rotation overwrites the first manifest (acceptable failure mode).
- **`openclaw doctor --fix` re-import during rollback**: this triggers the same path that planted the original shadow in `#596`. The rollback is restoring the PRE-doctor state, so the re-import should reproduce the pre-rotation key value (not the planted-shadow value). Verify by sha8-comparing the post-rollback main SQLite to the pre-rotation backup.

## Reviewer guidance

- Verify the manifest is written BEFORE any rotation artifact is touched. Add a deliberate failure in Step 1 (the paste step); the manifest should still exist with `rotation_completed_at_iso: null` and the operator can use it to inspect what was planned.
- Verify the `--rollback <ts>` flow refuses partial rollback — manually delete one backup file, invoke `--rollback`, confirm exit 1 with the missing-paths list and NO mutation.
- Verify the verify gate's stderr emits the EXACT rollback command (the operator copy-pastes this; whitespace and quoting matter).
- Confirm shellcheck passes on the extended script.
- Verify the integration with the existing self-update re-exec doesn't break (manual run of the script twice).

## Commands

When `spec-kitty next` directs you here:

```bash
spec-kitty agent action implement WP03 --agent claude
```

When ready for review:

```bash
spec-kitty agent action review WP03 --agent claude
```
