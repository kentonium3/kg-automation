# Implementation Plan: Deploys report what they installed so the rebaseline expects it

**Branch**: `fix/deploy-runtime-installed-report` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/deploy-runtime-installed-report-01M4ZP8E/spec.md`

**Branch contract**: planning base = merge target = `fix/deploy-runtime-installed-report`, cut from `main` at `87805c32`. Single topology, no coordination branch. The branch is merged into `main` after the post-merge Codex review.

## Summary

*(Revised 2026-10-15 after the post-plan review: Codex REJECT, paula APPROVE-WITH-CHANGES, debbie CONFIRMED-WITH-GAPS. See research.md, "Post-plan review dispositions".)*

A new `scripts/deploy/lib/installed_report.py` owns the channel: the variable name `FELIX_DEPLOY_INSTALLED_REPORT`, the JSONL format, the producer `record_installed(source, dest)` (advisory; on a write failure it prints one fixed marker line to stderr), and the hardened, fail-closed reader `read_report(path)`. `userunits.install_units` calls `record_installed` after each successful `os.replace` of a changed file.

`apply.dry_run_then_apply_gate` gives every command an environment with the variable **removed**. Only `--apply` gets a fresh `mkdtemp` report path. The read result (`installed_report`) is merged into **every** return after `--apply` runs, including a failed apply and a failed post-verification.

`rebaseline.baselines_for_installed_report(entries, repo_root, home)` validates **wholesale**. Every source must be in the repository, and every destination must resolve inside a host location that the matching surface declares in the new `audited-surfaces.json` field `host_paths`. Otherwise the whole report contributes nothing. It maps sources with the same `match_surfaces` that `observe` uses.

`_tick` keeps two named sets: `declared_baselines` (manifest intent, apply success only) and `reported_baselines` (installation evidence, any apply outcome). It unions them only at the fold call, and passes contributor names separately from `applied_this_tick`.

`fold_manifest_baselines` stamps `last_fold_utc` on a merge and persists the union of `manifest_names`. `_within_grace` measures from the later of `pending_since_utc` and `last_fold_utc`, so newly added expectations get a fresh grace window. Stale alerts still use `pending_since_utc`.

A guard test stops new hand-rolled host copies in deploy scripts.

## Technical Context

**Language/Version**: Python 3.12 on office2 (system `python3`). Python 3.12 and 3.13 in CI.
**Primary Dependencies**: standard library only. In-repo: `tooling/scripts/audited_surfaces.py` (`match_surfaces`, `load_audited_surfaces_or_error`), `scripts/deploy/felix-deployer/rebaseline.py`, `scripts/deploy/lib/{apply,userunits}.py`. There is no new third-party dependency, so DIRECTIVE_051 does not apply.
**Storage**: the per-apply report is a JSONL file in a fresh `tempfile.mkdtemp()` directory owned by the deployer process, deleted after it is read. There is no persistent state change, and the token schema is unchanged: it already carries `expected_baselines`.
**Testing**: pytest, offline. The existing tick harness `tests/deploy/test_tick_rebaseline.py` (fake git, `_wp04_seams`, real `_tick`) gets a 0029-replay end-to-end test, with `dry_run_then_apply_gate` running a real throwaway entrypoint script that calls `userunits.install_units`. Unit tests cover the library report writer, the apply-side reader and the rebaseline mapper.
**Target Platform**: office2, felix-deployer (claude user), running from `/home/claude/kg-automation`.
**Project Type**: single repo, scripts layout.
**Performance Goals**: NFR-001, under 1 s per tick (a file read, then a glob match per path).
**Constraints**: C-001 one matcher; C-002 expectation grows only from evidence; Tier 3.
**Scale/Scope**: about 4 source files, about 4 test files, and docs.

## Charter Check

| Gate | Status |
|---|---|
| Testing Standards (pytest for non-trivial Python; real-shaped fixtures) | PASS (planned): the 0029 replay uses the real `felix-vikunja-sync` unit file paths and the real registry |
| No dead code | PASS (planned): the reader is called by `apply`, which `_tick` calls; the writer is called by `install_units`, used by the 0031 entrypoint |
| Integration verification (no-staging-aware) | PASS (planned): form (b), post-merge. The first deployer tick on office2 runs the new code (no `tick_error` in the log) and the merge's own deploy-pipeline token clears (`cleared_clean`) |
| Tier | 3. No host, audit or unit change |
| Rebaseline obligation | Touches `scripts/deploy/lib/**` (deploy-pipeline, `affected_baselines: []`), so the expected outcome is `pending_clean` then `cleared_clean` |
| Deploy discipline | No manifest. The deployer and library run from the checkout the deployer itself pulls, and nothing on the host changes. The live verification above is the proof |
| Architecture docs | `data-flows.json` and `data-flows.md` (felix-deployer flow: the report file), `docs/runbooks/deployment.md` § expected_baselines, `deploy/discipline.md`, `scripts/deploy/lib/README.md` |

No violations.

## Project Structure

```
scripts/deploy/lib/userunits.py              # MODIFIED: report writer (changed files only)
scripts/deploy/lib/apply.py                  # MODIFIED: fresh report per --apply; defensive reader
scripts/deploy/felix-deployer/rebaseline.py  # MODIFIED: baselines_for_installed_paths()
scripts/deploy/felix-deployer/_tick.py       # MODIFIED: union reported baselines; rebaseline_reported log
tests/deploy/test_userunits.py               # MODIFIED: report writer tests
tests/deploy/test_apply_installed_report.py  # NEW: per-apply location, reader faults
tests/deploy/test_rebaseline_reported.py     # NEW: mapper (one matcher, out-of-repo, unmatched)
tests/deploy/test_tick_rebaseline.py         # MODIFIED: 0029 replay end to end + failed-apply case
docs/... (see Charter Check)
```

## Implementation Concern Map

### IC-01 — The channel module (`lib/installed_report.py`)

- **Purpose**: own the variable name, the format `{"source": abs, "dest": abs}`, the producer and the reader. The producer is advisory: a write failure never fails an install and prints `FELIX_DEPLOY_INSTALLED_REPORT_WRITE_FAILED: <reason>` to stderr. The reader opens with `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`, `fstat` must be a regular file, it reads at most 1 MiB + 1 byte, decodes UTF-8 strictly, and parses every line. Any bad line, over 1 MiB, or over 10,000 entries rejects the **whole** report.
- **Relevant requirements**: FR-001, FR-004, FR-010, NFR-002
- **Affected surfaces**: `scripts/deploy/lib/installed_report.py` (new), `tests/deploy/test_installed_report.py` (new)
- **Sequencing/depends-on**: none

### IC-02 — The library reports (userunits)

- **Purpose**: `install_units` calls `record_installed(src.resolve(), dst.resolve())` after each successful replace of a changed file. Unchanged files and dry runs report nothing.
- **Relevant requirements**: FR-001
- **Affected surfaces**: `scripts/deploy/lib/userunits.py`, `tests/deploy/test_userunits.py`
- **Sequencing/depends-on**: IC-01

### IC-03 — Apply provides, isolates and reads

- **Purpose**: an `env` argument for `_run_shell`. All commands get `os.environ` minus the variable; `--apply` gets the variable set to a fresh `mkdtemp` path. After `--apply` returns, success or failure, read the report and check `--apply`'s stderr for the write-failure marker. Merge `details["installed_report"] = {"entries": [...], "rejected": bool, "warnings": [...]}` into every result returned after `--apply` (apply failure, post-verification failure, success). Clean up the directory; any setup, read or cleanup error becomes a warning, never an exception.
- **Relevant requirements**: FR-002, FR-004, FR-007, NFR-002
- **Affected surfaces**: `scripts/deploy/lib/apply.py`, `tests/deploy/test_apply_installed_report.py` (new)
- **Sequencing/depends-on**: IC-01

### IC-04 — Map with proof of installation (`rebaseline`)

- **Purpose**: `baselines_for_installed_report(report, repo_root, home, registry=None)`. If the report is rejected, return nothing. Otherwise, for each entry, the source must resolve inside `repo_root` and the destination must resolve inside a `host_paths` entry (expanded against `home`) of a surface whose patterns match the repo-relative source. Validation is wholesale: any entry failing either check rejects the whole report. Union the matched surfaces' `affected_baselines`. A surface without `host_paths` contributes nothing. An unreadable registry gives nothing plus a warning. Add `"host_paths": ["~/.config/systemd/user/"]` to the `systemd-user-units` surface.
- **Relevant requirements**: FR-003, FR-004, FR-009, C-001, C-002
- **Affected surfaces**: `scripts/deploy/felix-deployer/rebaseline.py`, `docs/design/architecture/data/audited-surfaces.json`, `tests/deploy/test_rebaseline_reported.py` (new)
- **Sequencing/depends-on**: IC-01 (entry shape)

### IC-05 — Tick: two gates, folding, grace freshness

- **Purpose**: in `_tick`, `reported_baselines` is gathered from every `dry_run_then_apply_gate` result that ran `--apply` (any outcome) and mapped through IC-04. `declared_baselines` is unchanged (success only). The two are unioned **only** at the fold call, with a one-line intent-versus-evidence rationale. `reported_contributors` is kept separate from `applied_this_tick`, so failed manifests are never stamped as applied. The tick logs `rebaseline_reported` per manifest: entries, baselines, rejected, warnings, `apply_ok`, and an absorbed-drift note. `fold_manifest_baselines` gets `last_fold_utc` and a persisted `manifest_names` union on merge; `_within_grace` uses the later of `pending_since_utc` and `last_fold_utc`, and `_maybe_stale` is unchanged.
- **Relevant requirements**: FR-003, FR-005, FR-006, FR-007
- **Affected surfaces**: `scripts/deploy/felix-deployer/_tick.py`, `scripts/deploy/felix-deployer/rebaseline.py`, `tests/deploy/test_tick_rebaseline.py`
- **Sequencing/depends-on**: IC-03, IC-04
- **Tests** (real reconcile with an injected audit runner, not the stubbed reconcile used by the existing declared-baseline test):
  - the 0029 replay ends `completed`;
  - a scratch destination gives `unexpected_drift`;
  - a failed apply plus a declared baseline folds nothing, while a failed apply plus a report folds;
  - post-verification failure still folds;
  - old token → fold → clean audit keeps the new expectation through grace.

### IC-06 — Recurrence guard and docs

- **Purpose**:
  - `tests/deploy/test_host_copies_report.py`: a non-allowlisted Python file under `scripts/deploy/` (outside `lib/`) that calls `shutil.copy*`, `shutil.copyfile`, `os.replace`, or `Path.write_*`/`write_bytes` must import a reporting installer (`userunits`) or `installed_report`. This reuses #1066's frozen, evidence-bound allowlist approach, extended with the entrypoints that copy without reloading.
  - Docs: the lib README contract section, `deployment.md` (automatic for library installs; `expected_baselines` still required for everything else, with the five historical episodes as examples), `discipline.md`, `CLAUDE.md`, and `data-flows.json`/`.md`.
- **Relevant requirements**: FR-008, FR-010
- **Affected surfaces**: `tests/deploy/test_host_copies_report.py` (new), docs listed above
- **Sequencing/depends-on**: IC-05
