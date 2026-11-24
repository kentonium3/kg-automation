---
affected_files: []
cycle_number: 1
mission_slug: crash-loop-unit-alerting-01M858E8
reproduction_command:
reviewed_at: '2026-11-24T00:30:07Z'
reviewer_agent: codex
wp_id: WP05
---

# WP05 review feedback, cycle 1

Reviewer: Codex CLI gpt-6.1-sol (read-only, 2026-11-23); implementer Claude Opus 5.5. Verdict: REJECT.

- **MAJOR — scripts/deploy/deploy-crash-loop-unit-alerting.py:242:** Crash-loop event ledger failures can produce a false success. The canary records failed appends as `ledger:crash-loop:<scope>:<unit>:...`, but this filter checks only `crash_loop...`. If healthy scope lines were written before an event append fails, `_check_events()` sees zero events and passes—even if that event’s delivery failed. A read-only injected reproduction returned all seven checks passing with this error present. **Fix:** reject `ledger:crash-loop:` errors as hard verification failures. Add a regression with fresh artifacts, healthy scopes, a missing event record, and that tick error; require failure after exactly one start.

- **MINOR — deploys/queued/0043-crash-loop-unit-alerting.yaml:1:** The numbered filename follows the WP example but conflicts with `docs/runbooks/deploy/discipline.md:154`, which explicitly assigns numbering to felix-deployer. **Fix:** rename it to `deploys/queued/crash-loop-unit-alerting.yaml`; require the exact slug filename while queued in the manifest test.

- **MINOR — tests/deploy/test_deploy_crash_loop_unit_alerting.py:231:** The “writes nothing” test observes only the temporary working directory. Writes to absolute production paths would escape detection. Checking that local variable names exclude `"write"` adds no behavioral protection. **Fix:** guard filesystem mutation operations during the dry run and fail on any attempted write; remove the variable-name assertion.

The other manifest deviations are justified: **(1)** dropping `mission_slug` satisfies the schema’s exclusive `oneOf`; **(2)** omitting `apply_mode` follows its applied-record-only contract; **(4)** `audited_surface: true` without `expected_baselines` matches R-11 and the deploy-pipeline surface’s empty baseline set.

Scope checks are independent, and the retry permits exactly one extra start. The entrypoint contains no SSH, sudo, shell execution, credential reads, journal reads, or deployment/install operations. Other changed files are workflow records. I did not run pytest; test results are those supplied by the orchestrator.

VERDICT: REJECT

Orchestrator: the rename to deploys/queued/crash-loop-unit-alerting.yaml is approved. It changes the owned path; record the out-of-map rationale (discipline.md: felix-deployer assigns the number).
