**Issue 1**: `scripts/doc_audit/judgment/drift_interpretation.py` imports the shared helper with `from doc_audit.judgment._llm_response import _strip_code_fence`, but WP01 T003 explicitly requires `from scripts.doc_audit.judgment._llm_response import _strip_code_fence`. The current import path fails the WP's standalone validation command:

```bash
python -c "from scripts.doc_audit.judgment.drift_interpretation import _parse_verdict; print(_parse_verdict)"
```

Observed failure:

```text
ModuleNotFoundError: No module named 'doc_audit'
```

Please change the `drift_interpretation.py` import to the required `scripts.doc_audit.judgment._llm_response` path, then rerun:

```bash
python -c "from scripts.doc_audit.judgment.drift_interpretation import _parse_verdict; print(_parse_verdict)"
python -m pytest tests/doc_audit/judgment/test_llm_response.py tests/doc_audit/judgment/test_drift_interpretation.py -v
python -m pytest --cov=scripts.doc_audit.judgment._llm_response tests/doc_audit/judgment/test_llm_response.py
```

Note: the focused pytest checks currently pass and helper coverage is 100%; this rejection is for the unmet T003 import requirement and failed standalone import validation.

Downstream impact: WP02 depends on WP01 and should rebase after this fix lands.
