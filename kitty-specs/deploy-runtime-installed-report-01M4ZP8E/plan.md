# Implementation Plan: Deploys report what they installed so the rebaseline expects it

**Branch**: `fix/deploy-runtime-installed-report` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/deploy-runtime-installed-report-01M4ZP8E/spec.md`

**Branch contract**: planning base = merge target = `fix/deploy-runtime-installed-report`, cut from `main` at `87805c32`. Single topology, no coordination branch. The branch is merged into `main` after the post-merge Codex review.

## Summary

`scripts/deploy/lib/userunits.install_units` appends one JSON line per *changed* installed file to the file named by `FELIX_DEPLOY_INSTALLED_REPORT`, when that variable is set. `scripts/deploy/lib/apply.dry_run_then_apply_gate` creates a fresh empty report file for each manifest and passes it to `--apply` only. Afterwards it reads the report back defensively and returns the repo-relative installed paths in `LibResult.details["installed_paths"]`, on success and on apply failure alike. felix-deployer's `_tick` maps those paths through a new `rebaseline.baselines_for_installed_paths(paths)`. That helper uses the same `match_surfaces` and registry read as `observe`. The tick unions the result into `declared_baselines`, which `fold_manifest_baselines` already folds into the token before reconcile. Each step logs a `rebaseline_reported` event.

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

### IC-01 — Library writes the report

- **Purpose**: `install_units` appends `{"path": "<absolute resolved source path>"}` per changed file to `$FELIX_DEPLOY_INSTALLED_REPORT`, if set. Unchanged files and dry runs write nothing.
- **Relevant requirements**: FR-001, NFR-003
- **Affected surfaces**: `scripts/deploy/lib/userunits.py`, `tests/deploy/test_userunits.py`
- **Sequencing/depends-on**: none
- **Risks**: a write failure must not fail the install. The report is advisory; a lost report degrades to today's behavior and is logged by the reader. The write is appended *after* each successful `os.replace`, so a partially failed install reports exactly what landed.

### IC-02 — Apply provides and reads the report

- **Purpose**: `dry_run_then_apply_gate` creates a fresh report file and passes it via the environment to `--apply` only, never to `--dry-run` or verification. It reads the file back with a size cap (1 MiB), JSON-per-line parsing and per-line type checks, and returns `details["installed_paths"]` (absolute strings, unfiltered) plus `details["installed_report_warnings"]`. It cleans up the directory, and does all of this on apply success and failure.
- **Relevant requirements**: FR-002, FR-004, FR-007, NFR-002
- **Affected surfaces**: `scripts/deploy/lib/apply.py`, `tests/deploy/test_apply_installed_report.py`
- **Sequencing/depends-on**: IC-01 (contract only)
- **Risks**: `_run_shell` currently takes no environment. Add an `env` keyword argument used only for the `--apply` call. Every other caller is unchanged.

### IC-03 — Map reported paths to baselines

- **Purpose**: `rebaseline.baselines_for_installed_paths(paths, repo_root, registry=None)` resolves each path. It rejects anything outside `repo_root` and symlink escapes, makes the rest repo-relative, runs `match_surfaces` (the same function and the same non-exiting registry read as `observe`), and returns `{baselines, matched, rejected, unmatched, warnings}`.
- **Relevant requirements**: FR-003, FR-004, C-001, C-002
- **Affected surfaces**: `scripts/deploy/felix-deployer/rebaseline.py`, `tests/deploy/test_rebaseline_reported.py`
- **Sequencing/depends-on**: none
- **Risks**: an unreadable registry gives no baselines, plus a warning, mirroring `observe`.

### IC-04 — Tick folds and logs

- **Purpose**: after each `dry_run_then_apply_gate`, successful or failed, the tick maps `details["installed_paths"]` through IC-03 and unions the result into `declared_baselines`. The existing fold runs if `declared_baselines` is non-empty. The tick logs `rebaseline_reported` with manifest, paths, baselines, rejected, unmatched and warnings. Folding on a failed apply needs `fold_manifest_baselines` to receive the manifest name too; check `manifest_names` handling.
- **Relevant requirements**: FR-003, FR-005, FR-006, FR-007, SC-001, SC-003
- **Affected surfaces**: `scripts/deploy/felix-deployer/_tick.py`, `tests/deploy/test_tick_rebaseline.py`
- **Sequencing/depends-on**: IC-02, IC-03
- **Risks**: the existing comment says declared baselines fold on apply success only (Codex HIGH-1). Reported baselines deliberately fold on failure too (FR-007); keep the two gates separate and documented. Any exception in the reported path must be caught per manifest, so that one manifest's bad report cannot affect the rest of the tick (NFR-002).

### IC-05 — Docs and architecture data

- **Purpose**: describe the automatic path, and narrow the `expected_baselines` guidance to drift the library did not cause. Add the report file to the felix-deployer data flow.
- **Relevant requirements**: FR-008
- **Affected surfaces**: `docs/runbooks/deployment.md`, `docs/runbooks/deploy/discipline.md`, `scripts/deploy/lib/README.md`, `CLAUDE.md` (rebaseline caveat paragraph), `docs/design/architecture/data/data-flows.json`, `docs/design/architecture/data-flows.md`
- **Sequencing/depends-on**: IC-04
