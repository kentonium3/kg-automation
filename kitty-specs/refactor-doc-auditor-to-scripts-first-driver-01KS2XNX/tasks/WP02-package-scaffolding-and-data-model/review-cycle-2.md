---
affected_files: []
cycle_number: 2
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T17:52:32Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1**: `TickSignal` does not match the E-009 contract schema.

`data-model.md` defines E-009 as the structured `last-tick.json` signal and explicitly points to `contracts/tick-signal.contract.md` for the full schema. The implemented `TickSignal` in `scripts/doc_audit/data_model.py` is a flattened shape with fields like `tick_id`, `started_utc`, `ended_utc`, `signals_seen`, `judgment_calls`, and `token_usage`. The contract requires fields such as `timestamp_utc`, `exit_code`, `duration_seconds`, `host`, nested `tick`, nested `judgment`, and `next_scheduled_tick_utc`.

How to fix:
- Update `TickSignal` to model the published contract shape for E-009.
- Use typed nested dataclasses for the contract's `tick` and `judgment` objects, or use clearly typed dict fields if the project wants to avoid extra exported entities.
- Update `tests/doc_audit/test_data_model.py` so the `TickSignal` tests cover empty, full, and partial contract-shaped outcomes, including `exit_code` and the nested `tick` / `judgment` payloads.

**Issue 2**: `mock_anthropic` does not patch `anthropic.Anthropic` as required by T009.

The WP prompt requires `mock_anthropic(monkeypatch)` to patch the `anthropic.Anthropic` client so downstream tests can use the fixture without setup boilerplate. The current fixture returns a fake client object, but it does not monkeypatch the SDK constructor. Downstream code that imports and instantiates `anthropic.Anthropic(...)` will still attempt to use the real client.

How to fix:
- Change the fixture signature to accept `monkeypatch`.
- Patch `anthropic.Anthropic` to return the fake client, while still returning that fake client from the fixture so tests can inspect calls and set `next_fixture`.
- If the real `anthropic` package is not installed in the test environment, patch a module/import target in a way that downstream WP code can rely on consistently, and document that target in the fixture docstring.

Downstream note: WP03, WP04, and WP05 depend on WP02. They should rebase after this package/data-model fix lands.
