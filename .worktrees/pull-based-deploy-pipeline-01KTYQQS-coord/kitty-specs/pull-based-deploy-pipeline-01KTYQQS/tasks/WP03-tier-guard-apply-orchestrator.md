---
work_package_id: WP03
title: Tier guard and apply orchestrator
dependencies:
- WP02
requirement_refs:
- FR-005
- FR-007
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
- T015
agent: "claude:sonnet:implementer-ivan:reviewer"
shell_pid: "28269"
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/lib/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- scripts/deploy/lib/tier.py
- scripts/deploy/lib/apply.py
- scripts/deploy/lib/README.md
- tests/deploy/test_tier.py
- tests/deploy/test_apply.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else.

## Objective

Implement the tier guard (CI + runtime modes) and the canonical apply orchestrator that the felix-deployer applier and bash wrappers consume. Document the full library API.

## Context

WP02 shipped the lower-level primitives (cron, snapshot, verify, manifest, applied). This WP composes them into:

1. `tier_guard` — the policy enforcement point for tier 0/1/2/3/4 classification.
2. `dry_run_then_apply_gate` — the canonical lifecycle from `data-model.md` (tier → snapshot → pre → dry-run → apply → post).
3. Module-as-CLI shims so bash callers can use the library via `python3 -m`.
4. A library-wide README anchored at `contracts/deploy-library-api.md`.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T011 — `lib/tier.py`

Implement `tier_guard(manifest: dict, mode: str) -> LibResult`. Two modes:

**`mode='ci'`** (used by `.github/workflows/deploy-manifest-validate.yml`):
- Reject if `manifest['tier'] == 0` → `LibResult(ok=False, summary='Tier 0 deploys must be manual via ssh office2-kgale', details={'error_code': 'TIER_0_REJECTED'})`
- Reject if `manifest['tier'] in {1, 2}` and `'verification' not in manifest` → `LibResult(ok=False, summary='Tier 1/2 requires verification block', details={'error_code': 'VERIFICATION_BLOCK_REQUIRED'})`
- Otherwise → `LibResult(ok=True, summary='Tier policy: pass')`

**`mode='runtime'`** (used by `lib.apply.dry_run_then_apply_gate`):
- Re-run all CI checks (defense in depth)
- Additionally: reject if `manifest['entrypoint']` does not exist on disk → `LibResult(ok=False, ..., details={'error_code': 'ENTRYPOINT_NOT_FOUND'})`

Tests cover every error_code path + the pass path × both modes.

### T012 — `lib/apply.py`

Implement `dry_run_then_apply_gate(manifest: dict, manifest_path: str) -> LibResult` per the state-transition diagram in `data-model.md`:

```python
def dry_run_then_apply_gate(manifest, manifest_path):
    # 1. tier_guard
    r = tier.tier_guard(manifest, mode='runtime')
    if not r.ok:
        return LibResult(ok=False, summary=r.summary,
                         details={**r.details, 'phase': 'tier_guard'})

    # 2. snapshot (Tier 2 only)
    if manifest['tier'] == 2:
        r = snapshot.verify_restic_recent()
        if not r.ok:
            return LibResult(ok=False, summary=r.summary,
                             details={**r.details, 'phase': 'snapshot'})

    # 3. verification.pre
    for cmd in manifest.get('verification', {}).get('pre', []):
        r = _run_shell(cmd)
        if not r.ok:
            return LibResult(ok=False, summary=f'pre failed: {cmd}',
                             details={**r.details, 'phase': 'verification_pre'})

    # 4. entrypoint --dry-run
    r = _run_shell([manifest['entrypoint'], '--dry-run'])
    if not r.ok:
        return LibResult(ok=False, summary='dry-run failed; not applying',
                         details={**r.details, 'phase': 'entrypoint_dry_run'})

    # 5. entrypoint --apply
    r = _run_shell([manifest['entrypoint'], '--apply'])
    if not r.ok:
        return LibResult(ok=False, summary='apply failed',
                         details={**r.details, 'phase': 'entrypoint_apply'})

    # 6. verification.post
    for cmd in manifest.get('verification', {}).get('post', []):
        r = _run_shell(cmd)
        if not r.ok:
            return LibResult(ok=False, summary=f'post failed: {cmd}',
                             details={**r.details, 'phase': 'verification_post'})

    return LibResult(ok=True, summary='applied', details={'phase': 'complete'})
```

`_run_shell(cmd)` is a private helper using `subprocess.run`; returns LibResult. Accepts string OR list.

Tests cover every `phase` exit point + the happy path. Use a fixture entrypoint script that the test creates with a mock filesystem.

### T013 — `lib/README.md`

Mirror `contracts/deploy-library-api.md` but trim to operational essentials. Audience: an engineer implementing a deploy script. Structure:

1. One-line purpose
2. The 5 modules and their public functions (one line each)
3. The `LibResult` return type
4. Module-as-CLI invocation pattern (`python3 -m scripts.deploy.lib.<module> <function> <args>`)
5. The hard rule: no `crontab` literal
6. Link to `kitty-specs/<slug>/contracts/deploy-library-api.md` for the full contract

Keep it under 150 lines.

### T014 — Module-as-CLI shims

Add `__main__.py` to each lib module that exposes a CLI surface. Pattern:

```python
# scripts/deploy/lib/cron/__main__.py  (or scripts/deploy/lib/cron_main.py imported by cron.py)
import sys, json
from . import openclaw_cron_disable, openclaw_cron_enable, openclaw_cron_edit, openclaw_cron_list

_FUNCS = {
    'openclaw_cron_disable': openclaw_cron_disable,
    'openclaw_cron_enable': openclaw_cron_enable,
    'openclaw_cron_edit': openclaw_cron_edit,
    'openclaw_cron_list': openclaw_cron_list,
}

def main():
    fn = _FUNCS[sys.argv[1]]
    result = fn(*sys.argv[2:])
    print(result.summary)
    if '--json' in sys.argv:
        sys.stdout.flush()
        # write JSON details to fd 3 if available; else stdout next line
        try:
            os.write(3, json.dumps(dict(result.details)).encode())
        except OSError:
            print(json.dumps(dict(result.details)))
    sys.exit(0 if result.ok else 1)

if __name__ == '__main__':
    main()
```

Apply the same pattern across modules. Bash callers use:

```bash
python3 -m scripts.deploy.lib.cron openclaw_cron_disable felix-vikunja-sync-driver
# Exit code: 0 on success, 1 on failure
```

### T015 — Round-trip integration test

`tests/deploy/test_apply.py` adds a top-of-file test that uses a real fixture manifest from `tests/deploy/fixtures/manifests/valid_tier3_minimal.yaml`. The entrypoint is a fixture shell script the test writes to a tmp dir: `#!/bin/bash\nexit 0`. Asserts `apply.dry_run_then_apply_gate(manifest, manifest_path).ok is True`. This is the smoke test that proves the whole composition works end-to-end without subprocess mocking the entrypoint.

## Test strategy

- `pytest tests/deploy/test_tier.py tests/deploy/test_apply.py -v` — green
- Round-trip test (T015) passes with a real subprocess-invoked entrypoint
- `python3 -m scripts.deploy.lib.cron openclaw_cron_list` returns deterministically when mocked

## Definition of Done

- All 5 owned files exist
- All tests pass
- Every `phase` exit in `apply.dry_run_then_apply_gate` has a corresponding test
- `tier_guard` rejects Tier 0 in both modes
- `tier_guard(mode='runtime')` rejects on missing entrypoint
- README accurately describes every exported function
- Module-as-CLI shim is testable end-to-end (subprocess invocation works in test)

## Risks

- **Shell escaping in verification commands**: manifests can contain arbitrary shell strings. The applier runs them in subshell; manifests are operator-authored and PR-reviewed, so this is acceptable risk, but document in README.
- **`_run_shell` quoting**: prefer `subprocess.run(cmd, shell=False)` when cmd is a list; only use `shell=True` when cmd is a string. Mixing causes silent failures.
- **Phase string drift**: the `phase` strings in LibResult.details MUST match those documented in `data-model.md` and `contracts/dm-payload-v1.md`. Hardcode them as module-level constants to prevent drift.

## Reviewer guidance

1. Cross-check every `phase` string against `contracts/dm-payload-v1.md`'s `phase` enum.
2. Verify `tier_guard(mode='runtime')` actually tests entrypoint existence (not just pattern match).
3. Run the round-trip test (T015) manually to confirm no mocks are involved.
4. Check that the module-as-CLI shim returns a non-zero exit code on `LibResult.ok=False`.

## Activity Log

- 2026-06-12T22:17:29Z – claude:sonnet:implementer-ivan:implementer – shell_pid=24966 – Assigned agent via action command
- 2026-06-12T22:27:06Z – claude:sonnet:implementer-ivan:implementer – shell_pid=24966 – Tier guard + apply orchestrator complete. README + CLI shims + round-trip test.
- 2026-06-12T22:27:36Z – claude:sonnet:implementer-ivan:reviewer – shell_pid=28269 – Started review via action command
- 2026-06-12T22:39:04Z – user – shell_pid=28269 – Review passed: tier_guard CI+runtime modes correct with all 3 error codes; dry_run_then_apply_gate runs canonical 6-phase sequence with module-level PHASE_* constants pinned by test; README 128 lines mirrors deploy-library-api.md; module-as-CLI shims work across all 6 modules via shared _cli.py helper; T015 round-trip uses real fixture manifest + real shell script with NO subprocess mocking; WP02-owned files (cron/snapshot/verify/manifest) only have minimal append-only __main__ shims extending the WP02 applied.py precedent; no crontab literal; all 117 tests pass.
