**Issue 1: Enabled Moment 0 path constructs `JudgmentClient` with the wrong signature**

`scripts/doc_audit/signals/drift_event.py:176-178` calls `JudgmentClient(api_key_path=api_key_path)`, but the actual client constructor in `scripts/doc_audit/judgment/client.py:67` is `JudgmentClient(config: Config)`. This means the load-bearing enabled path fails before `route_drift_event(...)` can run, so FR-005/FR-009 and the enabled-success cursor/drain acceptance path are not satisfied in production. The new tests mock `doc_audit.signals.drift_event.JudgmentClient`, so they do not catch the real constructor mismatch.

Fix: update `_get_judgment_client()` to construct the real client with the adapter config, matching the existing helper path (`scripts/doc_audit/helpers/handle_drift_events.py` uses `JudgmentClient(config)`). Add or adjust a test so the enabled path would fail on the real constructor shape, for example by asserting the mocked constructor is called with `cfg` rather than an `api_key_path` keyword, or by exercising `_get_judgment_client()` with the Anthropic SDK/API-key reader patched at the lower level.

WP03 depends on WP02, so downstream agents should rebase after this WP is fixed.
