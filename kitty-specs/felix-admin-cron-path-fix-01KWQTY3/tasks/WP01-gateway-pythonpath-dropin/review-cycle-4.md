---
affected_files: []
cycle_number: 4
mission_slug: felix-admin-cron-path-fix-01KWQTY3
reproduction_command:
reviewed_at: '2026-07-05T03:44:15Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

**Issue 1**: SC-10 is still not verified on the required acceptance surface.

The deploy entrypoint and manifest now verify `PYTHONPATH` with `systemctl --user show -p Environment` plus `/proc/<MainPID>/environ` for the live gateway process. That proves the gateway process has the environment value, but it does not exercise a real OpenClaw agent/cron subprocess payload from a non-repo cwd.

This contradicts the locked requirement in the WP prompt and mission artifacts:

- `contracts/path-resolution-and-migration.md` C1 says authoritative acceptance is `PYTHONPATH` confirmed inside a **real OpenClaw agent/cron subprocess** where the payload prints `os.environ["PYTHONPATH"]` from a non-repo cwd; proxy surfaces are not acceptable.
- `spec.md` SC-10 says the guardrail is verified present in a real OpenClaw-launched agent/cron subprocess.
- `plan.md` IC-01 says to run an agent/cron payload that prints `os.environ["PYTHONPATH"]` from a non-repo cwd before relying on the guardrail.
- The WP T002 guidance requires the deploy entrypoint to exercise that real agent/cron payload and stop if it fails.

The current implementation also documents the real-agent check as an operator post-deploy "belt" outside the automated gate, which inverts the requirement: the real agent/cron subprocess check is the hard SC-10 gate for this WP, not a later optional confirmation.

Fix: update `scripts/deploy/install-gateway-pythonpath-dropin.py` and `deploys/queued/0006-gateway-pythonpath-dropin.yaml` so the post-restart verification actually runs the required OpenClaw agent/cron subprocess payload from a non-repo cwd and asserts it prints exactly `/home/claude/kg-automation`. Keep the `systemctl show` check if useful, but do not substitute gateway `/proc/<MainPID>/environ` for the real subprocess acceptance gate. Add tests/assertions that would fail if the entrypoint no longer includes the real agent/cron SC-10 gate.

Anti-pattern checklist:

- Dead code: PASS. The new deploy entrypoint is referenced by the deploy manifest.
- Synthetic-fixture test: FAIL. Tests assert dry-run output for the `/proc/<MainPID>/environ` proxy path, not the required FR-001/FR-002 real agent/cron subprocess behavior. Deleting the real SC-10 implementation remains possible because it is absent.
- Silent empty return: PASS. No undocumented empty returns or pass statements found in the new production code.
- FR coverage: FAIL. FR-001/FR-002 acceptance depends on the real subprocess gate; current tests and manifest cover only drop-in declaration/gateway process state.
- Frozen surface: PASS. `scripts/openclaw/openclaw-gateway.service` was not modified.
- Locked decision: FAIL. The implementation contradicts the MUST-level SC-10 language in `spec.md`, `plan.md`, `contracts/path-resolution-and-migration.md`, and the WP prompt.
- Shared-file ownership: PASS. Lane metadata shows WP01 owns the changed implementation surfaces; unrelated mission status/task churn was ignored per WP isolation rules.
- Production fragility: PASS. No new production `raise` paths found.

Verification notes:

- `python -m py_compile scripts/deploy/install-gateway-pythonpath-dropin.py tests/deploy/test_install_gateway_pythonpath_dropin.py` passed.
- `pytest -q tests/deploy/test_install_gateway_pythonpath_dropin.py` could not run because `pytest` is not installed in this environment.
- `uv run pytest -q tests/deploy/test_install_gateway_pythonpath_dropin.py` also failed because `uv` could not spawn `pytest`.
