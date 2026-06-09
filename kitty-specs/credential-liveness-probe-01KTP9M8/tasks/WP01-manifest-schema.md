---
work_package_id: WP01
title: Manifest schema + Credential dataclass extension
dependencies: []
requirement_refs:
- FR-013
- FR-014
- NFR-006
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on the mission coordination branch per the rc41 #1777 workaround. During /spec-kitty.implement this WP gets its own lane worktree. Completed changes merge back into main as part of the mission's atomic merge.
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: "claude"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/security/credential_health_check/
execution_mode: code_change
mission_id: 01KTP9M86VF89TQM5SX7JVA83Z
mission_slug: credential-liveness-probe-01KTP9M8
owned_files:
- scripts/security/credential_health_check/manifest.py
- tests/security/credential_health_check/test_manifest.py
- docs/design/architecture/data/credential-manifest.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load python-pedro
```

Python implementer posture: stdlib-only, test-first, locality of change.

## Objective

Extend `scripts/security/credential_health_check/manifest.py` to parse a new optional `liveness_probe` block per credential, and update the `gog-credentials-keyring` record in `credential-manifest.json` to opt into liveness monitoring. Foundational for WP03's orchestrator integration. Strictly additive: credentials without the block parse unchanged.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Lane worktree: allocated per `lanes.json` after `finalize-tasks` runs. The lane base is computed from dependencies (none for this WP); expect a worktree branched from main or from the mission coordination branch.

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | FR-013 (manifest block schema), FR-014 (gog-credentials-keyring update), NFR-006 (backward compat) |
| [../plan.md](../plan.md) § IC-02 | Concern map for manifest changes |
| [../data-model.md](../data-model.md) § LivenessProbeConfig | Dataclass shape + invariants |
| [../contracts/manifest-liveness-probe-block.md](../contracts/manifest-liveness-probe-block.md) | JSON Schema + validation rules + initial value + 7 test cases |
| `scripts/security/credential_health_check/manifest.py` | Existing 191-line parser; extend at the Credential dataclass + load_manifest function |
| `tests/security/credential_health_check/test_manifest.py` | Existing tests (extend; don't replace) |
| `docs/design/architecture/data/credential-manifest.json` | Schema-versioned manifest; `gog-credentials-keyring` entry gets the new block |

## Subtask Guidance

### T001 — Add `LivenessProbeConfig` dataclass

**Probe first**:

```bash
grep -n "class Credential\|@dataclass\|ManifestQualityError" scripts/security/credential_health_check/manifest.py
```

**Steps**:

1. Open `scripts/security/credential_health_check/manifest.py`.
2. Locate the existing `Credential` dataclass (likely near the top, after imports).
3. Above it (so the type is available for the `Optional[LivenessProbeConfig]` field), add:

   ```python
   @dataclass(frozen=True)
   class LivenessProbeConfig:
       """Per-credential liveness probe configuration.

       When `enabled is True`, all of `gog_account`, `keyring_file`, and
       `recovery_command` MUST be set. See
       kitty-specs/credential-liveness-probe-01KTP9M8/contracts/manifest-liveness-probe-block.md.
       """
       enabled: bool
       gog_account: Optional[str] = None
       keyring_file: Optional[str] = None
       recovery_command: Optional[str] = None
   ```

4. Make sure `Optional` is imported from `typing` at module top.
5. `frozen=True` matches the immutability invariant from data-model.md.

**Files**:
- `scripts/security/credential_health_check/manifest.py` (+~12 lines)

**Validation**:
- `python3 -c "from credential_health_check.manifest import LivenessProbeConfig; c = LivenessProbeConfig(enabled=True, gog_account='x@y.com', keyring_file='/tmp/k', recovery_command='echo'); print(c)"` works.
- Existing tests pass: `pytest tests/security/credential_health_check/test_manifest.py -v`.

---

### T002 — Extend `Credential` dataclass

**Steps**:

1. In the existing `Credential` dataclass, add the field:

   ```python
   liveness_probe: Optional[LivenessProbeConfig] = None
   ```

2. Place it after the existing optional fields (preserving the existing field order; do not reorder existing fields).
3. Default `None` ensures backward-compat — credentials without the manifest block parse with `liveness_probe = None`.

**Files**:
- `scripts/security/credential_health_check/manifest.py` (+1 line)

**Validation**:
- Existing tests pass.
- A test (added in T005) parses an existing manifest entry without `liveness_probe` and confirms `cred.liveness_probe is None`.

---

### T003 — Update manifest parser: read the block, validate when enabled

**Steps**:

1. Locate `load_manifest()` / the parsing function that constructs `Credential` instances.
2. Inside the per-credential loop, after the existing field reads, add a block:

   ```python
   liveness_probe_raw = cred_dict.get("liveness_probe")
   if liveness_probe_raw is None:
       liveness_probe = None
   else:
       # Validate unknown subkeys.
       allowed_keys = {"enabled", "gog_account", "keyring_file", "recovery_command"}
       unknown = set(liveness_probe_raw.keys()) - allowed_keys
       if unknown:
           raise ManifestQualityError(
               f"credential {cred_dict.get('name')!r}: liveness_probe contains "
               f"unknown keys: {sorted(unknown)}"
           )
       enabled = liveness_probe_raw.get("enabled", False)
       if enabled:
           for required in ("gog_account", "keyring_file", "recovery_command"):
               if not liveness_probe_raw.get(required):
                   raise ManifestQualityError(
                       f"credential {cred_dict.get('name')!r}: liveness_probe.enabled "
                       f"is true but {required!r} is missing or empty"
                   )
       liveness_probe = LivenessProbeConfig(
           enabled=enabled,
           gog_account=liveness_probe_raw.get("gog_account"),
           keyring_file=liveness_probe_raw.get("keyring_file"),
           recovery_command=liveness_probe_raw.get("recovery_command"),
       )
   ```

3. Pass `liveness_probe=liveness_probe` to the `Credential(...)` constructor (alongside the existing kwargs).
4. `ManifestQualityError` is an existing exception in this module — DO NOT create a new one.

**Files**:
- `scripts/security/credential_health_check/manifest.py` (+~25 lines)

**Validation**:
- A manifest without the block parses cleanly.
- A manifest with `enabled: true` but missing `gog_account` raises `ManifestQualityError`.
- A manifest with `liveness_probe: {foo: "bar"}` raises `ManifestQualityError`.

---

### T004 — Update `credential-manifest.json` `gog-credentials-keyring`

**Probe first**:

```bash
grep -n '"gog-credentials-keyring"' docs/design/architecture/data/credential-manifest.json
```

**Steps**:

1. Open `docs/design/architecture/data/credential-manifest.json`.
2. Locate the entry where `"name": "gog-credentials-keyring"`.
3. Find the actual keyring file path on office2 by reading from spec.md FR-006 or data-model.md (initial value section). It is:
   `/home/claude/.config/gogcli/keyring/_gogcli_key_v1_dG9rZW46ZGVmYXVsdDprZW50Z2FsZUBnbWFpbC5jb20`
4. Add (just before the closing `}` of the `gog-credentials-keyring` object) the block:

   ```json
   ,
   "liveness_probe": {
     "enabled": true,
     "gog_account": "kentgale@gmail.com",
     "keyring_file": "/home/claude/.config/gogcli/keyring/_gogcli_key_v1_dG9rZW46ZGVmYXVsdDprZW50Z2FsZUBnbWFpbC5jb20",
     "recovery_command": "ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh"
   }
   ```

5. Preserve the existing fields and their order; only add the new key at the end.

**Files**:
- `docs/design/architecture/data/credential-manifest.json` (+~6 lines)

**Validation**:
- `python3 -c "import json; json.load(open('docs/design/architecture/data/credential-manifest.json'))"` exits 0.
- `jq '.credentials[] | select(.name == "gog-credentials-keyring") | .liveness_probe'` (if `jq` is available) returns the new block.
- The parser (post-T003) loads the manifest and `gog.liveness_probe.enabled is True`.

---

### T005 — Add tests in `test_manifest.py`

**Probe first**:

```bash
grep -n "def test_" tests/security/credential_health_check/test_manifest.py
```

**Steps**:

Add these test cases following the existing test-file conventions (likely `tmp_path` fixtures + JSON writes, then `load_manifest`):

1. `test_credential_parses_with_full_liveness_probe_block` — write a manifest with the full block (all 4 fields), parse, assert `cred.liveness_probe.enabled is True` + all fields populated.

2. `test_credential_parses_without_liveness_probe_block` — write a manifest WITHOUT the block, parse, assert `cred.liveness_probe is None`.

3. `test_credential_parses_with_disabled_liveness_probe` — write a manifest with `liveness_probe: {enabled: false}` (no other fields), parse, assert `cred.liveness_probe.enabled is False` and other fields are `None`.

4. `test_liveness_probe_enabled_without_gog_account_raises` — write a manifest with `enabled: true` but no `gog_account`, assert `load_manifest()` raises `ManifestQualityError`.

5. `test_liveness_probe_enabled_without_keyring_file_raises` — similar, missing `keyring_file`.

6. `test_liveness_probe_enabled_without_recovery_command_raises` — similar, missing `recovery_command`.

7. `test_liveness_probe_unknown_subkey_raises` — write a manifest with `liveness_probe: {foo: "bar"}`, assert `ManifestQualityError`.

Use the existing `ManifestQualityError` exception (imported from the module under test).

**Files**:
- `tests/security/credential_health_check/test_manifest.py` (+~80 lines, ~7 test functions)

**Validation**:
- `pytest tests/security/credential_health_check/test_manifest.py -v` — all 7 new tests pass + all existing tests still pass.
- No regression in `pytest tests/security/credential_health_check/ -v`.

---

## Test Strategy

All tests are in `test_manifest.py`. No new test files. Pattern:

```python
def test_credential_parses_with_full_liveness_probe_block(tmp_path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({
        "schema_version": 2,
        "last_updated": "2026-06-09",
        "credentials": [{
            "name": "test-cred",
            "type": "oauth2",
            "scope": "test",
            "storage": "/tmp/test",
            "host": "office2",
            "used_by": [],
            "deployed_by": "test",
            "status": "active",
            # ... other required fields ...
            "liveness_probe": {
                "enabled": True,
                "gog_account": "test@example.com",
                "keyring_file": "/tmp/key",
                "recovery_command": "echo test",
            },
        }],
    }))
    creds = load_manifest(str(manifest_file))
    cred = creds[0]
    assert cred.liveness_probe is not None
    assert cred.liveness_probe.enabled is True
    assert cred.liveness_probe.gog_account == "test@example.com"
```

Required fields for `Credential` construction may vary; copy a working credential fixture from the existing tests in `test_manifest.py` and add the `liveness_probe` block.

## Definition of Done

- [ ] `LivenessProbeConfig` dataclass exists in `manifest.py` with `frozen=True`.
- [ ] `Credential` dataclass has `liveness_probe: Optional[LivenessProbeConfig] = None`.
- [ ] Manifest parser handles all four states: absent, present-enabled-complete, present-enabled-missing-field, present-disabled.
- [ ] `ManifestQualityError` is raised (not silent skip) for `enabled: true` with missing required field.
- [ ] `ManifestQualityError` is raised for unknown subkeys in the block.
- [ ] `credential-manifest.json` `gog-credentials-keyring` entry has the new block populated correctly.
- [ ] JSON validity check passes.
- [ ] 7 new tests in `test_manifest.py` all pass.
- [ ] All existing tests in `tests/security/credential_health_check/` STAY passing (regression sanity).

## Risks

- **Field order in `Credential` dataclass**: appending a new optional field is safe; do NOT reorder existing fields (would break positional constructors anywhere they exist).
- **Re-using `ManifestQualityError`**: confirm via `grep -n "class ManifestQualityError" scripts/security/credential_health_check/manifest.py`.
- **JSON validity**: easy to drop a trailing comma. Run the json.load check before committing.
- **Manifest schema version**: do NOT increment `schema_version` — additive optional field doesn't warrant a version bump.

## Reviewer Guidance

A reviewer should be able to verify in <5 minutes:

1. The new dataclass is present and properly typed.
2. The parser correctly handles all four cases (absent / enabled-complete / enabled-incomplete / disabled).
3. Tests cover each parsing branch.
4. The `credential-manifest.json` edit is the smallest possible diff (only adds the new block).
5. No fields in `Credential` were renamed or reordered.
6. JSON validity holds.
