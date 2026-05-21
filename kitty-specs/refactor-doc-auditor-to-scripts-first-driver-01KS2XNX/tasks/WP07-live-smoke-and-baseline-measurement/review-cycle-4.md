---
affected_files: []
cycle_number: 4
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-21T13:38:28Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP07
---

**Issue 1**: `pytest tests/doc_audit/test_smoke_live.py` does not skip cleanly by default.

WP07 validation explicitly requires the no-marker invocation to skip by default. Current `pytest.ini` uses `addopts = -m "not live_smoke"`, so running the focused file deselects both tests and exits with pytest code 5:

```text
python3 -m pytest tests/doc_audit/test_smoke_live.py -q
2 deselected in 0.02s
```

Fix by making the default focused invocation collect the live-smoke tests and mark them skipped with exit code 0, while still allowing `pytest -m live_smoke tests/doc_audit/test_smoke_live.py` to opt in. For example, remove the global deselection from `pytest.ini` and implement collection-time skip logic that only skips `live_smoke` tests when `-m live_smoke` was not requested. Re-run both:

```bash
python3 -m pytest tests/doc_audit/test_smoke_live.py -q
python3 -m pytest -m live_smoke tests/doc_audit/test_smoke_live.py -q
```

**Issue 2**: The new baselines directory is not discoverable from `docs/INDEX.md`, and no docs-debt deferral was captured.

Reviewer guidance for WP07 says to verify `docs/design/architecture/baselines/` is referenced from `docs/INDEX.md` OR captured as docs-debt if the index update is deferred. I found the new README and baseline JSON, but `docs/INDEX.md` only references the existing docs-debt issue template and has no baselines entry. Add an index entry for `docs/design/architecture/baselines/README.md`, or file/capture an explicit docs-debt deferral and reference it in the WP evidence.

**Downstream note**: WP09 depends on WP07; downstream agents should rebase after this fix lands.
