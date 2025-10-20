.PHONY: docs-check diagrams-sync

PY ?= python

docs-check:
	$(PY) tooling/scripts/validate_docs.py

diagrams-sync:
	$(PY) tooling/scripts/sync_mermaid_views.py --write
	$(PY) tooling/scripts/validate_docs.py
