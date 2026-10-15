# Tasks: Deploys report what they installed so the rebaseline expects it
**Mission**: `deploy-runtime-installed-report-01M4ZP8E` · **Issue**: kentonium3/kg-automation#1072 · **Branch**: `fix/deploy-runtime-installed-report`
Inputs: [spec.md](spec.md) · [plan.md](plan.md) · [contracts/installed-report.md](contracts/installed-report.md) · [data-model.md](data-model.md) · [research.md](research.md)

## Subtask Index
| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Producer `record_installed(source, dest)` | WP01 | |
| T002 | Hardened reader `read_report(path)` | WP01 | |
| T003 | Tests (`tests/deploy/test_installed_report.py`) | WP01 | |
| T004 | Round trip | WP01 | |
| T005 | Wire the producer | WP02 | |
| T006 | Tests (append to `tests/deploy/test_userunits.py`) | WP02 | |
| T007 | `_run_shell(cmd, *, env=None)` | WP03 | |
| T008 | Environment isolation | WP03 | |
| T009 | Read and merge on every post-apply return | WP03 | |
| T010 | Tests (`tests/deploy/test_apply_installed_report.py`) | WP03 | |
| T011 | Registry | WP04 | |
| T012 | Mapper `baselines_for_installed_report(report, repo_root, home, registry=None)` | WP04 | |
| T013 | Fold freshness and names | WP04 | |
| T014 | Mapper tests (`tests/deploy/test_rebaseline_reported.py`) | WP04 | |
| T015 | Freshness tests | WP04 | |
| T016 | Two named gates | WP05 | |
| T017 | Observability | WP05 | |
| T018 | Tick tests (`tests/deploy/test_tick_rebaseline.py`) | WP05 | |
| T019 | Guard `tests/deploy/test_host_copies_report.py` | WP06 | |
| T020 | Docs | WP06 | |
| T021 | Validators | WP06 | |

## WP01 — The installed-report channel module

**Prompt**: [tasks/WP01-installed-report-channel.md](tasks/WP01-installed-report-channel.md) · **Depends on**: none

T001 (WP01)
T002 (WP01)
T003 (WP01)
T004 (WP01)

## WP02 — userunits reports what it installed

**Prompt**: [tasks/WP02-userunits-reports.md](tasks/WP02-userunits-reports.md) · **Depends on**: WP01

T005 (WP02)
T006 (WP02)

## WP03 — apply provides, isolates and reads the report

**Prompt**: [tasks/WP03-apply-isolates-and-reads.md](tasks/WP03-apply-isolates-and-reads.md) · **Depends on**: WP01

T007 (WP03)
T008 (WP03)
T009 (WP03)
T010 (WP03)

## WP04 — rebaseline maps reports with proof of installation; fold freshness

**Prompt**: [tasks/WP04-rebaseline-maps-with-proof.md](tasks/WP04-rebaseline-maps-with-proof.md) · **Depends on**: WP01

T011 (WP04)
T012 (WP04)
T013 (WP04)
T014 (WP04)
T015 (WP04)

## WP05 — Tick folds reported baselines with two named gates

**Prompt**: [tasks/WP05-tick-two-gates.md](tasks/WP05-tick-two-gates.md) · **Depends on**: WP03, WP04

T016 (WP05)
T017 (WP05)
T018 (WP05)

## WP06 — Recurrence guard and docs

**Prompt**: [tasks/WP06-guard-and-docs.md](tasks/WP06-guard-and-docs.md) · **Depends on**: WP05

T019 (WP06)
T020 (WP06)
T021 (WP06)

