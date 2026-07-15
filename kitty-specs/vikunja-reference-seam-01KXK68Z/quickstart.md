# Quickstart: vikunja_refs + capture routing

## Resolve a project (consumer)

```python
from scripts.common import vikunja_refs

pid = vikunja_refs.project_id("inbox")   # -> 1  (no network)
# undeclared name fails loud:
vikunja_refs.project_id("someday")       # -> raises VikunjaRefError (Someday is not a project post-#714)
# declared but unprovisioned fails loud (not 0/None):
vikunja_refs.project_id("personal")      # -> raises VikunjaRefError ("declared but unprovisioned") until seeded
```

## Resolve a label (per token)

```python
# felix:ignore is the one live runtime label consumer this mission migrates.
# (f:/q:/t:/loe: taxonomy labels are deferred to #749.)
lid = vikunja_refs.label_id("felix:ignore", owner_token="kent")
```

## Read the raw selector (selector layer, e.g. vikunja_scope)

```python
sel = vikunja_refs.selector("habits")    # -> {"kind": "project_id", "value": 13}
# lets Habits later migrate to {"kind": "label", "value": "t:habit"} (#717) without touching consumers
```

## Validate registry against live Vikunja (on demand)

```bash
cd /home/claude/kg-automation && python3 -m scripts.vikunja.validate_refs
# exit 0 + "registry OK" when reality == registry
# exit non-zero + per-reference findings when a name is missing / drifted / unprovisioned
# exit non-zero + a single "unreachable" finding when Vikunja can't be listed
#   (distinct from "registry clean" — you have NOT confirmed the seam is honest)
```

Run the validator after any Vikunja reorg; it is the reality-vs-registry check that keeps the seam honest (mirrors the approved-crons baseline discipline).

## Capture routing (#745) — post-reset model

```
someday-classified block  -> task in Inbox/topic project, label q:schedule, NO due date
unclassifiable block      -> Inbox (id 1)   # fall-through, NOT a "Someday" project
determinable Tier-1 tags  -> apply project / f: / q: labels on the way in
                             (undeterminable -> left in Inbox for the #749 intake loop)
```

`route_someday`'s old `find_someday_project` by-title lookup is retired — there is no "Someday" project post-#714.
