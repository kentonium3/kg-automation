.PHONY: docs-check diagrams-sync test

PY ?= python

# Full doc validation — mirrors the Docs CI workflow
# (.github/workflows/docs-ci.yml). Run before pushing, or let the
# .githooks/pre-commit gate invoke the cost-scoped subset (see #678).
docs-check:
	$(PY) tooling/scripts/validate_docs.py
	$(PY) tooling/scripts/validate_privacy_boundary.py
	$(PY) tooling/scripts/validate_architecture_data.py --strict

diagrams-sync:
	$(PY) tooling/scripts/sync_mermaid_views.py --write
	$(PY) tooling/scripts/validate_docs.py

# Run the non-live pytest suite. `live_smoke`-marked tests skip cleanly
# unless LIVE_SMOKE_ENABLED=1; the global urlopen guard in tests/conftest.py
# blocks accidental HTTP, so this is safe to run on CI without secrets.
# docs/archive/ is excluded — its archived tests reference removed modules
# and only break collection.
test:
	$(PY) -m pytest -q --ignore=docs/archive
