---
work_package_id: WP05
title: Adjacent surfaces — glossary, CLAUDE.md, signal-to-doc map
dependencies:
- WP01
- WP02
requirement_refs:
- FR-013
- FR-014
- FR-015
planning_base_branch: feat/office4-architecture-registration
merge_target_branch: feat/office4-architecture-registration
branch_strategy: Planning artifacts for this mission were generated on feat/office4-architecture-registration. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/office4-architecture-registration unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
- T023
- T024
phase: Phase 2 - Consistency
history:
- at: '2026-08-29T04:12:53Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/glossary.md
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- docs/design/architecture/glossary.md
- CLAUDE.md
- docs/design/architecture/data/signal-to-doc-map.json
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP05 – Adjacent surfaces

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objectives & Success Criteria

Two of these files are made **wrong** by this mission; the third is the mechanism that
caused the mission to nearly miss a target. Fixing all three is what makes this mission
address the cause rather than the symptom.

Done when: the glossary names four tailnet devices and defines all four canonical terms;
`CLAUDE.md`'s Platform table includes office4; and the signal map's
`network-topology-changed` entry names `hardware-inventory.json`.

## Context & Constraints

- Approved scope addition — decision `01M15TBPHB2JRXFD5ZZCQC0PHN`. See
  [research.md](../research.md) R-8 and [contracts](../contracts/architecture-data-payloads.md) C-7.
- **Depends on WP01 and WP02** — the glossary and CLAUDE.md reference the ADR.
- Tier 4 throughout.

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: `feat/office4-architecture-registration`
- **Merge target branch**: `feat/office4-architecture-registration`

## Subtasks & Detailed Guidance

### Subtask T020 – Update the `Tailscale` glossary entry

- **File**: `docs/design/architecture/glossary.md`
- **Current text (line ~15)**: "Mesh VPN providing encrypted connectivity between **office2,
  Mac, and iPhone**." — three devices, stale the moment ADR 0008 merges.
- **Steps**: change it to name four devices including office4. Keep the rest of the entry
  (Tailscale-only access, Serve HTTPS termination) intact.
- **Also review the `office2` entry** ("Always-on hub for all services"). Consider whether
  it now needs the managed-host framing so it does not read as "the only machine". Affirm
  your conclusion either way in the Activity Log.

### Subtask T021 – Add the four canonical terms

- **Purpose**: spec.md's Domain Language section declares four terms canonical "because the
  whole decision rests on" them. Declaring them in a mission spec without landing them in
  the repo glossary makes them canonical for the mission's duration and no longer.
- **Steps**: add entries in the file's existing `| **Term** | definition |` shape:
  - **managed host** — a machine whose state Felix deploys to and audits; office2 alone.
  - **unmanaged peer** — a tailnet device Felix does not deploy to: the MacBook Pro, the
    iPhone, and office4.
  - **attended / unattended** — whether a human is present to notice a failure. The axis
    separating office4 from office2. Note that "always-on" is *not* a synonym — office4 is
    always-on; that is the point.
  - **thin entry** — the reduced `hardware-inventory.json` record used for unmanaged peers
    (hostname, role, hardware, os, network).
- Cross-reference ADR 0008 so a reader can reach the reasoning.

### Subtask T022 – Add office4 to `CLAUDE.md`

- **File**: `CLAUDE.md` (repo root)
- **Current**: the Platform table (~line 39) lists `| MacBook Pro | Primary authoring and
  interaction |` and has no office4 row. Its only machine-access section is "Server Access
  (office2)".
- **Why this matters most**: every session loads `CLAUDE.md` at startup; almost none opens
  an ADR unprompted. Leaving the highest-traffic file asserting the opposite of ADR 0008
  defeats the mission's stated purpose.
- **Steps**: add a Platform row for office4 — attended primary development machine, **not** a
  managed host and **not** a deploy target. office2 keeps "Always-on hub". Add a one-line
  pointer to ADR 0008 near the table.
- ⚠️ `CLAUDE.md` is repo-root, **not** under `docs/` — do **not** add YAML frontmatter it
  does not already have.

### Subtask T023 – Fix the signal-to-doc map

- **File**: `docs/design/architecture/data/signal-to-doc-map.json`
- **Purpose**: no change class currently lists `hardware-inventory.json` in `doc_targets`,
  yet `change-control.md:20` says new hardware or host → `hardware-inventory.json`. The
  narrative doc knows and the machine-readable map does not — and repo doctrine makes the
  JSON authoritative, so today the authoritative file is the wrong one. CLAUDE.md tells every
  spec/plan agent to derive doc targets from this map, so the omission reproduces this
  mission's own near-miss on the next device addition.
- **Steps**: find the entry with `match.source == "mission-architecture-impact"` and
  `match.change_class == "network-topology-changed"`, and add
  `docs/design/architecture/data/hardware-inventory.json` to its `doc_targets` array.
- Do **not** add it to a different change class. Do **not** restructure the file.

### Subtask T024 – Verify

- **Steps**: run the precise assertion from [quickstart.md](../quickstart.md) step 5b — it
  selects the specific `network-topology-changed` entry, asserts exactly one exists, and
  checks the exact path is in its `doc_targets`. A looser "is the string anywhere in the
  file" check would pass even if you added the path to the wrong change class.
- Then `python3 tooling/scripts/validate_architecture_data.py --strict` — the signal map is
  itself architecture data — and `python3 tooling/scripts/validate_docs.py`.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Adding the path to the wrong change class | T024's assertion targets the specific entry |
| Adding frontmatter to `CLAUDE.md` | Explicitly called out in T022 |
| Describing office4 as a host/server in the glossary or CLAUDE.md | Both subtasks state the framing required |
| Glossary terms drifting from spec.md's Domain Language | Copy the definitions from that table |

## Review Guidance

- Confirm the glossary's `Tailscale` entry names four devices, office4 among them.
- Confirm all four canonical terms exist and that "attended" explicitly rejects "always-on"
  as a synonym.
- Confirm `CLAUDE.md` gained a row and a pointer, gained **no** frontmatter, and does not
  call office4 a host or deploy target.
- Confirm the map edit landed in `network-topology-changed` specifically, and both
  validators are clean.

## Activity Log

- 2026-08-29T04:12:53Z – system – Prompt created.
