# Quickstart: vikunja_refs

## Resolve a project (consumer)

```python
from scripts.common import vikunja_refs

pid = vikunja_refs.project_id("inbox")   # -> 1  (no network)
# undeclared name fails loud:
vikunja_refs.project_id("someday")       # -> raises VikunjaRefError (Someday is not a project post-#714)
```

## Resolve a label (per token)

```python
lid = vikunja_refs.label_id("q:schedule", owner_token="kent")
```

## Validate registry against live Vikunja (on demand)

```bash
cd /home/claude/kg-automation && python3 -m scripts.vikunja.validate_refs
# exit 0 + "registry OK" when reality == registry
# exit non-zero + per-reference findings when a name is missing or an id drifted
```

Run the validator after any Vikunja reorg; it is the reality-vs-registry check that keeps the seam honest (mirrors the approved-crons baseline discipline).
