---
work_package_id: WP07
title: Graph-ingest model reframe (#692/#696) to verify-not-present
dependencies: []
requirement_refs:
- FR-006
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-retire-private-folder-guards-01KY2MNK
base_commit: 812e4eb09436c2e1eb1a95bc5e0bc8e5f585fd55
created_at: '2026-07-21T16:27:09.719463+00:00'
subtasks:
- T023
- T024
agent: "claude:sonnet:architect-alphonso:implementer"
shell_pid: "24119"
shell_pid_created_at: "1784651349.979873"
history: []
agent_profile: architect-alphonso
authoritative_surface: docs/design/
create_intent: []
execution_mode: code_change
owned_files:
- docs/design/second-brain-graph-layer.md
- docs/design/executive-assistant-architecture.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load architect-alphonso` before anything else.

## Objective

Reframe the graph-ingest privacy model from "never ingest `_private`" *enforcement* to "verify the
private content is not present" *verification*, grounded in physical exclusion. Authoritative detail:
`data-model.md` IC-06 rows; FR-006/SC-006; and `research.md` D4. This is Kent's discovery decision
(full reframe, not just stripping language). **Design/model only — the runtime ingest-time check is
out of scope** (the pipeline is not built yet; #696 implements the check).

## Subtasks

- **T023** — `docs/design/second-brain-graph-layer.md`: in the privacy/ingest section, replace the
  "`_private` never ingested / privacy gate enforces exclusion" language with the physical-exclusion
  model: the private content lives only on devices Felix cannot reach, so it is never present to
  ingest; the #696 gate becomes a **verification that the excluded content is not present** in what
  gets ingested (not an in-repo enforcement rule). Keep the membrane/episode vocabulary consistent.
- **T024** — `docs/design/executive-assistant-architecture.md`: apply the same model reframe wherever
  it references the `_private` ingest gate (#696) — a verification, not an enforcement. Keep forward
  consistency with the §11a hexagonal-Lattice framing (the privacy boundary is a domain no port wires
  into — physical exclusion falls out of the architecture).

## Definition of Done

- Neither doc contains "never ingest `_private`" *enforcement* framing; both describe the
  physical-exclusion "verify not present" model.
- `grep -n "verify\|physical exclusion\|not present" docs/design/second-brain-graph-layer.md docs/design/executive-assistant-architecture.md` shows the new model.
- `python3 tooling/scripts/validate_docs.py` passes.

## Risks & reviewer guidance

- Keep the #696 gate forward-consistent (a verification the ingest pipeline will perform), not a
  vanished concept — the privacy requirement still exists, its *mechanism* changed.
- Reviewer: confirm the reframe reads as intentional design (not a half-deleted section) and stays
  consistent with the Life Lattice vocabulary.

## Activity Log

- 2026-07-21T16:29:28Z – claude:sonnet:architect-alphonso:implementer – shell_pid=24119 – Started implementation via action command
