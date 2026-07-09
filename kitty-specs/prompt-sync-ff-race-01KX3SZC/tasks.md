# Tasks — Prompt-sync FETCH_HEAD race fix

**Mission**: `prompt-sync-ff-race-01KX3SZC` | **Branch**: `fix/prompt-sync-ff-race` → merges to `fix/prompt-sync-ff-race`
**Issue**: kentonium3/kg-automation#667

Tests ARE requested (NFR-001 concurrency proof is central). Design detail lives in
[plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md),
[contracts/lib-api.md](./contracts/lib-api.md) — WP prompts reference them.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `AdvanceResult` dataclass | WP01 | | [D] |
| T002 | `advance_checkout()` — fetch + ref-merge + divergence + `assume_locked` | WP01 | | [D] |
| T003 | gitsync unit tests (ff / no-op / ahead-only / diverged / never-FETCH_HEAD) | WP01 | [D] |
| T004 | gitsync primitive concurrency test | WP01 | [D] |
| T005 | `deploylock` context manager (flock, bounded retry, path resolution) | WP02 | | [D] |
| T006 | deploylock tests (exclusion, timeout→LockUnavailable, release) | WP02 | [D] |
| T007 | health watermark schema + atomic read/write | WP03 | | [D] |
| T008 | `health.record()` — streak logic (confirmed-only, defer-benign, throttle) | WP03 | | [D] |
| T009 | generic `dispatch_health_notification()` in notify.py | WP03 | | [D] |
| T010 | health/notifier tests | WP03 | [D] |
| T011 | felix-deployer: wrap whole tick critical section in `deploylock` | WP04 | | [D] |
| T012 | felix-deployer: bare pull → `advance_checkout(assume_locked=True)`; preserve pre/post head | WP04 | | [D] |
| T013 | felix-deployer: wire `health.record` + fail-loud ref-state logging | WP04 | | [D] |
| T014 | felix-deployer tests (rebaseline range preserved + ff-race behaviors) | WP04 | | [D] |
| T015 | prompt-sync: wrap fetch/merge+copy in `deploylock` | WP05 | | [D] |
| T016 | prompt-sync: `git_pull` internals → `advance_checkout`; preserve GitPullResult + enrich audit | WP05 | | [D] |
| T017 | prompt-sync: wire health + `dispatch_health_notification` + topic env in service unit | WP05 | | [D] |
| T018 | prompt-sync tests (audit contract intact + advance integration) | WP05 | | [D] |
| T019 | actor-level concurrency integration harness (both ticks, one lock, ≥100 pairs) | WP06 | | [D] |
| T020 | `deploys/applied/0012-prompt-sync-ff-race.yaml` bootstrap record | WP06 | [D] |
| T021 | docs: deployment.md bootstrap + security-baseline-ops.md manual-rebaseline note | WP06 | [D] |

## Work Packages

### WP01 — gitsync primitive (race-immune advance)
- **Goal**: `advance_checkout()` + `AdvanceResult` — the ref-merge fix. Foundation.
- **Priority**: P1 (MVP core). **Independent test**: unit + primitive concurrency.
- **Subtasks**: T001, T002, T003, T004
- **Dependencies**: none. **Prompt**: [tasks/WP01-gitsync-primitive.md](./tasks/WP01-gitsync-primitive.md) (~200 lines)

### WP02 — deploylock primitive
- **Goal**: standalone advisory flock context manager (actor-level scope). Foundation.
- **Priority**: P1. **Independent test**: exclusion + timeout.
- **Subtasks**: T005, T006
- **Dependencies**: none [P with WP01]. **Prompt**: [tasks/WP02-deploylock-primitive.md](./tasks/WP02-deploylock-primitive.md) (~150 lines)

### WP03 — health signal + generic notifier
- **Goal**: `health.record()` watermark + `dispatch_health_notification()`.
- **Priority**: P1. **Independent test**: streak/throttle/defer-benign.
- **Subtasks**: T007, T008, T009, T010
- **Dependencies**: WP01 (uses `AdvanceResult`). **Prompt**: [tasks/WP03-health-notifier.md](./tasks/WP03-health-notifier.md) (~220 lines)

### WP04 — felix-deployer integration
- **Goal**: wrap the whole tick in the lock; replace bare pull with `advance_checkout`; preserve #685 rebaseline range; wire health.
- **Priority**: P1. **Independent test**: rebaseline-range preserved + ff-race behaviors.
- **Subtasks**: T011, T012, T013, T014
- **Dependencies**: WP01, WP02, WP03. **Prompt**: [tasks/WP04-felix-deployer-integration.md](./tasks/WP04-felix-deployer-integration.md) (~260 lines)

### WP05 — prompt-sync integration
- **Goal**: wrap fetch/merge+copy in the lock; replace `git_pull` internals; preserve GitPullResult + audit; wire health + ntfy topic.
- **Priority**: P1. **Independent test**: audit contract intact + advance integration.
- **Subtasks**: T015, T016, T017, T018
- **Dependencies**: WP01, WP02, WP03. **Prompt**: [tasks/WP05-prompt-sync-integration.md](./tasks/WP05-prompt-sync-integration.md) (~260 lines)

### WP06 — actor-level concurrency harness + bootstrap deploy + docs
- **Goal**: the load-bearing NFR-001 proof (both ticks, one lock, one checkout) + bootstrap applied record + runbook docs.
- **Priority**: P1 (gate for deploy). **Independent test**: the harness itself.
- **Subtasks**: T019, T020, T021
- **Dependencies**: WP04, WP05. **Prompt**: [tasks/WP06-actor-concurrency-deploy.md](./tasks/WP06-actor-concurrency-deploy.md) (~220 lines)

## Dependencies & lanes
```
WP01 ─┐
WP02 ─┼─▶ WP04 ─┐
WP03 ─┘        ├─▶ WP06
       └────▶ WP05 ─┘
```
WP01/WP02 parallel (lane a/b); WP03 after WP01; WP04/WP05 after WP01-03 (parallel); WP06 after WP04+WP05.

## MVP scope
WP01 + WP02 + WP04/WP05 deliver the race fix; WP03 adds observability; WP06 proves + deploys.
