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
| `snapshot` | Restic backup-recency verification (authoritative `last-backup.json` state file; daily-log parse as fallback) | `verify_restic_recent` |
| `verify` | File presence, stale-content, secret redaction | `verify_file_present`, `verify_no_stale_literal`, `redact_secrets` |
| `manifest` | Manifest load + Draft 2020-12 schema validation; applied-seq math. `validate_manifest` also enforces the optional `expected_baselines` field (declared by any deploy whose baseline drift has no signal in its own commit range: runtime CLI mutations, and reconcile deploys that install files changed earlier; names must be known security-monitor baselines and require `audited_surface: true`) via a non-exiting registry read — see `docs/runbooks/deploy/discipline.md`. | `load_manifest`, `validate_manifest`, `validate_manifest_file`, `next_applied_seq` |
| `applied` | Applied-entry writer for `deploys/applied/<NNNN>-<name>.yaml` | `write_applied` |
| `tier` | Tier-policy guard (CI + runtime modes) | `tier_guard` |
| `apply` | Canonical apply orchestrator (composes everything above) | `dry_run_then_apply_gate` |
| `userunits` | systemd **user**-unit install mechanism (#1066): preflight, plan, atomic install, one `daemon-reload` then an action per unit, loaded-config verification with a caller-supplied `expect`/`extra_check`, opt-in bounded next-elapse polling under a shared deadline, convergence. Policy (which properties must hold, restart vs enable-now vs none) stays with the caller; the module never prints. New unit-installing entrypoints must use it (`tests/deploy/test_unit_install_uses_userunits.py`). | `preflight_user`, `plan_install`, `install_units`, `daemon_reload`, `unit_action`, `apply_units`, `verify_unit`, `converged`, `parse_show`, `next_elapse_is_concrete` |
| `installed_report` | The installed-file report channel (#1072): an advisory producer that installers call for each file they wrote, and a fail-closed reader. See "The installed-file report" below. | `record_installed`, `read_report` |
| `timer_units` | Parse unit directives; the #1062 `Persistent=`-on-monotonic predicate | `directives`, `persistent_on_monotonic` |

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

## The installed-file report

How a deploy tells felix-deployer what it put on the host (#1072; contract
`kitty-specs/deploy-runtime-installed-report-01M4ZP8E/contracts/installed-report.md`).

- **Variable**: `FELIX_DEPLOY_INSTALLED_REPORT` names a file. The apply gate sets
  it to a fresh temporary path for `<entrypoint> --apply` only, and removes it
  from every other command's environment (pre/post verification, `--dry-run`).
- **Format**: JSON Lines, one `{"source": "<abs>", "dest": "<abs>"}` per changed
  file, appended after the file landed. `userunits.install_units` writes it;
  unchanged files are not reported.
- **Write failure**: the producer never fails an install. It prints one
  `FELIX_DEPLOY_INSTALLED_REPORT_WRITE_FAILED: ...` line to stderr, the only
  output the library produces.
- **Reader**: `read_report` never raises and rejects the whole report on any
  irregularity (symlink, FIFO, over 1 MiB, invalid UTF-8, a bad line, a relative
  path, NUL bytes, over 10,000 entries).
- **Result keys**: every result returned after `--apply` ran (success, apply
  failure, post-verification failure) carries `details["installed_report"]`
  (`entries`, `rejected`, `missing`, `warnings`) and
  `details["installed_report_write_failed"]`. Results returned before it never do.

felix-deployer maps the entries to baselines with
`rebaseline.baselines_for_installed_report`, which requires proof (source in
the repository, destination under the surface's `host_paths`). Entrypoints that
copy files themselves must import `userunits` or `installed_report`
(`tests/deploy/test_host_copies_report.py`). That guard is a tripwire, not a
proof: a copy in a helper module, `open(..., "w")`, `shutil.move`/`os.rename`,
a subprocess `cp`, or an import that is never called all escape it.

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

## Not everything on office2 ships through this pipeline

`scripts/office2/restic-backup.sh` is installed by hand with `sudo`, deliberately.
Its target directory holds a `NOPASSWD` sudo target, and making that directory
writable by the applier's `claude` account would make the grant equivalent to
`NOPASSWD: ALL` (#899). The `backup-script-drift` comparator (#903) reports when
the repo and deployed copies diverge, since automation is not available here.
See [`docs/runbooks/deploy/discipline.md`](<../../../docs/runbooks/deploy/discipline.md>).
