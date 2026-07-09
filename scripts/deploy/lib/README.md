# `scripts/deploy/lib/` — Felix Deploy Library

Vetted primitives for the felix-deployer applier and one-shot bash
deploy wrappers. Every public function returns a `LibResult` so callers
branch on a single boolean (`result.ok`) and read structured failure
detail from `result.details`.

The full v1 API contract lives at
`kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/deploy-library-api.md`.
This README is the operational summary — read the contract for the
versioning policy and non-goals.

## Modules

| Module | Purpose | Public functions |
|---|---|---|
| `cron` | OpenClaw cron primitives — never touches the system cron table | `openclaw_cron_disable`, `openclaw_cron_enable`, `openclaw_cron_edit`, `openclaw_cron_list` |
| `snapshot` | Restic backup-recency verification (fallback via daily log file) | `verify_restic_recent` |
| `verify` | File presence, stale-content, secret redaction | `verify_file_present`, `verify_no_stale_literal`, `redact_secrets` |
| `manifest` | Manifest load + Draft 2020-12 schema validation; applied-seq math. `validate_manifest` also enforces the optional `expected_baselines` field (CLI-mutation deploys declare drifted baselines; names must be known security-monitor baselines and require `audited_surface: true`) via a non-exiting registry read — see `docs/runbooks/deploy/discipline.md`. | `load_manifest`, `validate_manifest`, `validate_manifest_file`, `next_applied_seq` |
| `applied` | Applied-entry writer for `deploys/applied/<NNNN>-<name>.yaml` | `write_applied` |
| `tier` | Tier-policy guard (CI + runtime modes) | `tier_guard` |
| `apply` | Canonical apply orchestrator (composes everything above) | `dry_run_then_apply_gate` |

## Return type: `LibResult`

```python
@dataclass(frozen=True)
class LibResult:
    ok: bool
    summary: str               # one-line, ≤120 chars, log-safe
    details: Mapping[str, Any] # structured detail (see below)
```

Well-known keys in `details`:

* `phase` — set by `apply.dry_run_then_apply_gate` to one of:
  `tier_guard`, `snapshot`, `verification_pre`, `entrypoint_dry_run`,
  `entrypoint_apply`, `verification_post`, `complete`.
* `error_code` — e.g. `TIER_0_REJECTED`, `VERIFICATION_BLOCK_REQUIRED`,
  `ENTRYPOINT_NOT_FOUND`, `RESTIC_TOO_OLD`, `SCHEMA_VIOLATION`.
* `stderr_excerpt` — bounded stderr from a failed subprocess
  (≤ 2000 chars; truncated with `...<truncated>` suffix).
* `head_sha` — post-pull HEAD SHA when relevant (set by the applier,
  not by library primitives).

## The apply orchestrator

`apply.dry_run_then_apply_gate(manifest, manifest_path)` is the single
composition point. Sequence (each step a library call):

1. `tier.tier_guard(manifest, mode='runtime')`
2. `snapshot.verify_restic_recent()` — Tier 2 only.
3. Each `manifest.verification.pre[*]` via shell.
4. `<entrypoint> --dry-run` — mandatory; on failure, apply is NOT invoked.
5. `<entrypoint> --apply`.
6. Each `manifest.verification.post[*]` via shell.

On full success: `LibResult(ok=True, summary='applied', details={'phase': 'complete', ...})`.
On any failure: `ok=False` with `details['phase']` set to the stopping phase.

## Calling the library

### From Python (the applier)

```python
from scripts.deploy.lib import apply, manifest as manifest_mod

mani = manifest_mod.load_manifest("deploys/queued/some-deploy.yaml")
res = apply.dry_run_then_apply_gate(mani, "deploys/queued/some-deploy.yaml")
if not res.ok:
    record_failure(res)  # res.details['phase'] tells you where it stopped
```

### From bash (one-shot wrappers)

Bash callers MUST use the module-as-CLI shim, never re-implement the
primitives. The `-m` invocation is required because the library lives in
the `scripts.*` Python package; running the file path directly fails with
`ModuleNotFoundError`.

```bash
python3 -m scripts.deploy.lib.cron openclaw_cron_disable felix-vikunja-sync-driver
# Exit 0 on LibResult.ok=True; exit 1 otherwise.
# Prints LibResult.summary to stdout.
# Pass --json to also emit LibResult.details as JSON.
```

Each module that exposes a CLI surface has a `__main__.py` that maps
`argv[1]` → function name and `argv[2:]` → positional args. The applied
module additionally accepts a small argparse-based surface (see
`applied.py::_main`) because the bootstrap wrapper needs named args.

## The hard rule: no system-cron-table literal

The library NEVER reads `/etc/cron-tab` (hyphen added so this README
does not itself violate the rule) or shells to the system cron-tab
command. Every cron operation routes through `openclaw cron <subcommand>`.
CI greps `scripts/deploy/lib/` for the literal word (without the hyphen);
any hit outside a comment explaining the prohibition fails the build.
Precedent: closed issue
[kentonium3/kg-automation#162](https://github.com/kentonium3/kg-automation/issues/162).

## Risks and acknowledged trade-offs

* **Shell escaping**: `manifest.verification.pre` / `.post` strings run
  in a subshell via `subprocess.run(..., shell=True)`. Manifests are
  operator-authored and PR-reviewed, so this risk is accepted.
* **String vs list for `_run_shell`**: pass a `str` to invoke under a
  shell; pass a `Sequence[str]` to invoke `subprocess.run(..., shell=False)`.
  The entrypoint is always invoked as a list to avoid quoting surprises.
* **Phase string drift**: phase strings in `apply.PHASES` are pinned to
  match `contracts/dm-payload-v1.md` and `data-model.md`. Tests assert the
  full enum; CI catches drift.

## Versioning

`v1` — additions are non-breaking; signature changes require a
deprecation cycle. See the contract for the full policy.

## See also

* `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/deploy-library-api.md`
  — full v1 API contract.
* `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/dm-payload-v1.md`
  — WhatsApp DM payload schema (phase enum source of truth).
* `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/data-model.md`
  — entity model and lifecycle diagrams.
