---
description: "Work packages for #849 live runtime: host-reachable endpoints (#1083)"
---

# Work Packages: #849 live runtime: host-reachable endpoints (#1083)

**Inputs**: Design documents from `kitty-specs/arms849-live-runtime-host-endpoints-01M7Q8F3/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md (no contracts/: `meta.json` records `"contracts": "none"`)

**Tests**: required. The spec makes tests part of the requirements (FR-006 is a red-first test; FR-002 is a ratchet with a positive control) and the plan's test plan (T-a to T-g, the live node, half-by-half) is binding.

**Organization**: Fine-grained subtasks (`Txxx`) roll up into three work packages. WP01 and WP03 own disjoint files and can run in parallel. WP02 needs WP01's `Endpoints` value and `live_runtime(endpoints=)` parameter.

**Prompt Files**: each work package has a prompt in `tasks/`. This file is the high-level map. The detail lives in the prompts.

**Implementer**: python-pedro (C-004). The orchestrating session does not write the code.

## Subtask Format: `[Txxx] [P?] Description`

- **[P]** marks a subtask that can proceed in parallel (different files or concerns).
- Subtasks are **reference rows**, not checkboxes. Record completion with `spec-kitty agent tasks mark-status <Txxx> --status done`.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `Endpoints` value object and `IN_NETWORK_ENDPOINTS` | WP01 | |
| T002 | `Resources.endpoints` and `_factory_g` passes host/port to `arm_g.make_bridge` | WP01 | |
| T003 | `Runtime.endpoints`; `live_runtime(..., *, endpoints=)` drives facade and health | WP01 | |
| T004 | `_props_n_ctx(base_url)`; `live_secondary_gate` default probe follows `runtime.endpoints` | WP01 | |
| T005 | T-a/T-b wiring tests and T-c fresh-process C-001 guard; adapt the resume test's `container_health` fake | WP01 | |
| T006 | `_host_endpoints_from_env()` override reader in the integration test module | WP02 | |
| T007 | T-d reader tests (defaults, partial override, non-integer port) | WP02 | [P] |
| T008 | Live node uses the host endpoints and exercises `runtime.health()` for real | WP02 | |
| T009 | T-e red-first: default runtime from the host fails on resolving `falkordb`, bounded by a subprocess timeout | WP02 | [P] |
| T010 | `HOST_LIVE_ENDPOINT_ENV` shared mapping from the substrate's published ports | WP03 | [P] |
| T011 | `live-required-nodes` passes the four overrides; `_step` evidence allowlist records them | WP03 | |
| T012 | `--verify` requires the four overrides and `ARMS849_LIVE=1` | WP03 | |
| T013 | T-f checker env test with an independent oracle; fake runner gates live passes on the overrides | WP03 | |
| T014 | T-g verifier tests: per-key absent and wrong value, legacy-shaped record | WP03 | |

---

## Work Package WP01: Runtime endpoint wiring (Priority: P1)

**Goal**: The live runtime's FalkorDB and llama targets become one value with in-network defaults, consumed by arm G's bridge, the serving facade, the health check and the secondary gate's `/props` probe.
**Independent Test**: T-a (default runtime targets `falkordb:6379` / `http://llama:8080` at all four consumers, through the real `_factory_g` and invoked callbacks), T-b (same fixture with a host pair; positive control), T-c (fresh process, overrides set before import, zero reads of the four keys).
**Prompt**: `tasks/WP01-runtime-endpoint-wiring.md`
**Requirement Refs**: FR-001, FR-002, C-001, C-002, C-004, NFR-001

### Included Subtasks

T001 `Endpoints` value object and `IN_NETWORK_ENDPOINTS` (WP01)
T002 `Resources.endpoints` and `_factory_g` passes host/port to `arm_g.make_bridge` (WP01)
T003 `Runtime.endpoints`; `live_runtime(..., *, endpoints=)` drives facade and health (WP01)
T004 `_props_n_ctx(base_url)`; `live_secondary_gate` default probe follows `runtime.endpoints` (WP01)
T005 T-a/T-b wiring tests and T-c fresh-process C-001 guard; adapt the resume test's `container_health` fake (WP01)

### Implementation Notes

- Plan D1, D1a, D2, D3, D7. `FALKORDB_ADDR`/`LLAMA_URL` stay as the source of the default.
- New tests go in a new module, `tests/research/test_arms849_endpoints.py`, so WP02 can own `test_arms849_integration.py` without overlap.
- `tests/research/test_arms849_resume.py` patches `container_health` with `lambda config: True`. After T003 the health callback passes three arguments, so that fake must accept them.

### Parallel Opportunities

- WP01 runs in parallel with WP03 (disjoint files).

### Dependencies

- None (starting package).

### Risks & Mitigations

- A consumer missed: half-by-half review (revert each of the four wirings alone; T-b must go red each time).
- `Resources`/`Runtime` constructed positionally by fakes: the new fields go last with defaults.

---

## Work Package WP02: Host overrides, live node and red-first proof (Priority: P1)

**Goal**: The required live node reads the host overrides and runs against the published ports, exercising FalkorDB and llama for real. A non-live red-first test proves that without the override the host run fails on name resolution.
**Independent Test**: T-d (reader defaults, partial override, non-integer port), T-e (red-first, runs in both office seed suites on office4), and the live node under `ARMS849_LIVE=1` with the stack up.
**Prompt**: `tasks/WP02-host-overrides-live-node.md`
**Requirement Refs**: FR-003, FR-006, C-001, C-003, SC-001

### Included Subtasks

T006 `_host_endpoints_from_env()` override reader in the integration test module (WP02)
T007 T-d reader tests (defaults, partial override, non-integer port) (WP02)
T008 Live node uses the host endpoints and exercises `runtime.health()` for real (WP02)
T009 T-e red-first: default runtime from the host fails on resolving `falkordb`, bounded by a subprocess timeout (WP02)

### Implementation Notes

- Plan D4, T-d, T-e, live-node row. The live node's node ID must not change: it is pinned in the checker's `REQUIRED_NODES` and `LIVE_NODES`.
- The reader lives in the test module (C-001: production reads no override).

### Parallel Opportunities

- T007 and T009 are independent of each other once T006 exists.

### Dependencies

- Depends on WP01 (`h.Endpoints`, `live_runtime(endpoints=)`, `Runtime.endpoints`).

### Risks & Mitigations

- T-e hanging on an unresolvable or unreachable host: it runs the attempt in a subprocess with a hard timeout. Production transport is not changed (P-6).
- T-e passing for the wrong reason: it asserts the error chain is a name-resolution failure naming `falkordb`.

---

## Work Package WP03: Checker records and verifier requires the host endpoints (Priority: P1)

**Goal**: The FR-015 checker drives the live nodes at the published ports, records the four overrides in the step evidence, and `--verify` refuses any record that lacks them or carries other values.
**Independent Test**: T-f (env passed to the runner and recorded environment both carry the overrides, against an independent oracle) and T-g (per-key absent and wrong value rejected; legacy-shaped record rejected; well-formed record accepted).
**Prompt**: `tasks/WP03-checker-verifier-host-endpoints.md`
**Requirement Refs**: FR-004, FR-005, NFR-002, SC-002, SC-003

### Included Subtasks

T010 `HOST_LIVE_ENDPOINT_ENV` shared mapping from the substrate's published ports (WP03)
T011 `live-required-nodes` passes the four overrides; `_step` evidence allowlist records them (WP03)
T012 `--verify` requires the four overrides and `ARMS849_LIVE=1` (WP03)
T013 T-f checker env test with an independent oracle; fake runner gates live passes on the overrides (WP03)
T014 T-g verifier tests: per-key absent and wrong value, legacy-shaped record (WP03)

### Implementation Notes

- Plan D5, D6, T-f, T-g. P-4 (contradictory-record hardening) is out of scope: kentonium3/kg-automation#1106.

### Parallel Opportunities

- WP03 runs in parallel with WP01 (disjoint files).

### Dependencies

- None for the unit tests. The end-to-end live proof (quickstart.md) needs WP01 and WP02 merged.

### Risks & Mitigations

- The evidence allowlist silently dropping the keys: T-f asserts on the recorded environment, not only on the env passed.
- Older records (run 3 at a5550894) stop verifying. That is intended, since records are commit-bound.

---

## Dependency & Execution Summary

- **Sequence**: WP01 and WP03 in parallel; WP02 after WP01.
- **MVP**: WP01 (the wiring everything else exercises).
- **After all three merge**: post-merge Codex review, then the quickstart.md checker run on office4 (SC-001 to SC-003).

## Requirements Coverage Summary

| Requirement ID | Covered By Work Package(s) |
|----------------|----------------------------|
| FR-001 | WP01 |
| FR-002 | WP01 |
| FR-003 | WP02 |
| FR-004 | WP03 |
| FR-005 | WP03 |
| FR-006 | WP02 |
| NFR-001 | WP01 |
| NFR-002 | WP03 |
| C-001 | WP01, WP02 |
| C-002 | WP01 |
| C-003 | WP02 |
| C-004 | WP01 |
| SC-001 | WP02 |
| SC-002 | WP03 |
| SC-003 | WP03 |

## Subtask Index (Reference)

| Subtask ID | Summary | Work Package | Priority | Parallel? |
|------------|---------|--------------|----------|-----------|
| T001 | Endpoints value object | WP01 | P1 | No |
| T002 | Resources.endpoints, _factory_g | WP01 | P1 | No |
| T003 | Runtime.endpoints, live_runtime(endpoints=) | WP01 | P1 | No |
| T004 | props probe follows the runtime | WP01 | P1 | No |
| T005 | T-a/T-b/T-c tests, resume fake | WP01 | P1 | No |
| T006 | override reader | WP02 | P1 | No |
| T007 | T-d reader tests | WP02 | P1 | Yes |
| T008 | live node extension | WP02 | P1 | No |
| T009 | T-e red-first | WP02 | P1 | Yes |
| T010 | HOST_LIVE_ENDPOINT_ENV | WP03 | P1 | Yes |
| T011 | checker env + evidence allowlist | WP03 | P1 | No |
| T012 | verifier requires overrides | WP03 | P1 | No |
| T013 | T-f checker env test | WP03 | P1 | No |
| T014 | T-g verifier tests | WP03 | P1 | No |
