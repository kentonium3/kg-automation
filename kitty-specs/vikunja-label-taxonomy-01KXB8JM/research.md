# Research: Vikunja Label Taxonomy

Phase 0 output. Resolves the technical unknowns behind the reconcile helper.
All decisions are grounded in the live Vikunja instance and the proven
in-repo label scripts.

## R-01 — Vikunja label API surface

**Decision**: Use the existing REST endpoints via `VikunjaClient`:
- **List**: `GET /labels` — returns an array of `{id, title, hex_color, ...}`.
- **Create**: `PUT /labels` with body `{"title": <str>, "hex_color": <str>}` — Vikunja uses `PUT` (not `POST`) to create a label.
- **Delete**: `DELETE /labels/{id}`.

**Rationale**: `scripts/vikunja/setup_vikunja.py::create_labels` already creates
labels against this exact instance with `requests.put(f"{base_url}labels", json={"title", "hex_color"})`,
and a live `GET /labels` probe (2026-07-12) returned the array shape above.
`PUT`-to-create is Vikunja's documented convention.

**VikunjaClient specifics** (`scripts/common/vikunja_client.py`):
- Paths need a **leading slash** (`/labels`) — `base_url` already ends in `/api/v1` and `_compose_url` concatenates.
- `client.get("/labels", params={...})`, `client.put("/labels", json={...})`, `client.delete(f"/labels/{id}")`.
- Empty-body success (e.g. `DELETE`) parses to `{}`, not `None`.
- Typed exceptions (`VikunjaAuthError`, `VikunjaNotFoundError`, `VikunjaServerError`, `VikunjaTimeoutError`) — the helper surfaces failures rather than swallowing them (FR-007, NFR-001).

**Alternatives considered**: extending the older `requests`-based `setup_*.py`
scripts — rejected (introduces a second HTTP path; `VikunjaClient` is the
canonical stdlib boundary per DIRECTIVE_001 and Directive 6).

## R-02 — Pagination

**Decision**: Page `GET /labels` with `per_page=50`, incrementing `page` until a
batch returns fewer than 50 (or empty). Do not assume a single page.

**Rationale**: Vikunja caps `per_page` at 50 (established Felix gotcha; a
`len < 100` stop condition is wrong). Today only 3 labels exist, but after this
mission there are 12, and the helper must stay correct as the set grows.

## R-03 — Idempotency + matching key

**Decision**: Match existing labels to taxonomy entries by **exact `title`**.
Create only titles not already present. For deletion, match legacy labels by
**exact `title`** and delete by the resolved `id`. A label absent from the live
set is reported "already-absent" (delete) or created (taxonomy).

**Rationale**: Title is the stable human/machine key locked by the design doc
(C-001); ids are assigned by Vikunja and are not knowable in advance. Matching
by title makes the helper idempotent (NFR-002) and robust to differing ids
between environments. Mutation still uses `id` (FR-009) — title identifies,
id mutates.

## R-04 — Color format

**Decision**: Declare colors as bare 6-hex-digit strings (no leading `#`), e.g.
`f:1-flow → "4caf50"`. On create, send `hex_color` as the bare value. On
verification/comparison, **normalize both sides** by stripping any leading `#`
and lower-casing.

**Rationale**: The live `GET /labels` probe returns `hex_color` **without** a
leading `#` (`"2196f3"`). The legacy `setup_vikunja.py` sent values **with**
`#` and they were stored without it, so Vikunja tolerates both on input.
Normalizing on compare avoids a false color mismatch in the fidelity check
(C-001) regardless of which form the server echoes.

## R-05 — Destructive delete gating

**Decision**: The default run is **create-only**. Deletion of the three legacy
labels happens only when an explicit flag (e.g. `--delete-legacy`) is passed.
The operator confirms/triggers a recent Restic backup before invoking that flag.

**Rationale**: Deleting a Vikunja label cascades it off every task that carries
it — a Tier-2 application-state change (C-002). Separating the passes lets the
create pass (additive, safe) run and be verified first, and makes the
destructive action a deliberate, backup-gated second step (FR-006, SC-005).

## R-06 — Run location

**Decision**: Execute the live run on **office2** via `ssh office2-claude`,
where `VikunjaClient` resolves its defaults (token at
`/data/services/openclaw/secrets/vikunja-api`, base URL at
`/data/services/openclaw/config/vikunja-base-url.txt`). Invoke with the
`python3 -m scripts.vikunja.create_taxonomy_labels` module form from the repo
checkout so `scripts.common.*` imports resolve.

**Rationale**: The token and base-URL config live on office2; the Mac has
neither. Module-invocation (`-m`) form is required for `scripts.common.*`
imports (established Felix helper convention — script-path form fails
`ModuleNotFoundError`). office2 is `python3`-only (no `python`).

## R-07 — Test doubles

**Decision**: Unit tests inject a fake/mock `VikunjaClient` exposing `get`,
`put`, `delete` with the real method surface (leading-slash paths, list shape,
empty-dict delete result, typed exceptions for failure modes). No live network
calls in the test suite.

**Rationale**: Keeps tests deterministic and offline (NFR-001). The mock MUST
mirror the real client surface or tests pass while live behavior diverges — the
recurring mock-fidelity lesson from prior Felix deploys. A single fidelity test
also asserts the taxonomy constants exactly equal the design-doc set (guards
C-001 against silent drift).

## R-08 — Architecture-doc impact

**Decision**: No `docs/design/architecture/data/*.json` changes. This mission
adds no service, credential, port, or data flow — it creates labels in an
existing service via a new helper script. `scripts/vikunja/` is not an audited
surface (`audited-surfaces.json`), so **no security-baseline rebaseline** is
required. The design doc `docs/design/vikunja-configuration-design.md` **is**
edited (Tier-4 docs) to add the color column to its label tables — the colors
Kent chose 2026-07-12 — so the doc remains the single taxonomy authority
(post-plan finding #1). Titles/dimensions there are unchanged.

**Rationale**: Verified against the change-control taxonomy and the signal-to-doc
map change classes; none of `service-added-or-modified`,
`credential-added-or-modified`, `data-flow-added-or-modified`,
`network-topology-changed`, `systemd-unit-added-or-modified` apply.
