# Tasks: Vikunja image-archive staging and activation deploy route

**Mission**: vikunja-image-deploy-01M65D3V · **Branch**: `feat/vikunja-image-deploy` (planning, base and merge target) · **Issue**: #1087

Design authority: research.md (R-9 to R-24 take precedence over R-1 to R-8). The STAGE and ACTIVATE merges to `main` are Kent's (C-001).

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | see WP01 prompt | WP01 | |
| T002 | see WP01 prompt | WP01 | |
| T003 | see WP01 prompt | WP01 | |
| T004 | see WP01 prompt | WP01 | |
| T005 | see WP01 prompt | WP01 | |
| T006 | see WP01 prompt | WP01 | |
| T007 | see WP02 prompt | WP02 | |
| T008 | see WP02 prompt | WP02 | |
| T009 | see WP02 prompt | WP02 | |
| T010 | see WP02 prompt | WP02 | |
| T011 | see WP02 prompt | WP02 | |
| T012 | see WP03 prompt | WP03 | |
| T013 | see WP03 prompt | WP03 | |
| T014 | see WP03 prompt | WP03 | |
| T015 | see WP03 prompt | WP03 | |
| T016 | see WP03 prompt | WP03 | |
| T017 | see WP04 prompt | WP04 | |
| T018 | see WP04 prompt | WP04 | |
| T019 | see WP04 prompt | WP04 | |
| T020 | see WP04 prompt | WP04 | |
| T021 | see WP04 prompt | WP04 | |
| T022 | see WP04 prompt | WP04 | |
| T023 | see WP05 prompt | WP05 | |
| T024 | see WP05 prompt | WP05 | |
| T025 | see WP05 prompt | WP05 | |
| T026 | see WP06 prompt | WP06 | |
| T027 | see WP06 prompt | WP06 | |
| T028 | see WP06 prompt | WP06 | |
| T029 | see WP06 prompt | WP06 | |
| T030 | see WP07 prompt | WP07 | |
| T031 | see WP07 prompt | WP07 | |
| T032 | see WP07 prompt | WP07 | |
| T033 | see WP08 prompt | WP08 | |
| T034 | see WP08 prompt | WP08 | |
| T035 | see WP08 prompt | WP08 | |
| T036 | see WP08 prompt | WP08 | |
| T037 | see WP09 prompt | WP09 | |
| T038 | see WP09 prompt | WP09 | |
| T039 | see WP09 prompt | WP09 | |
| T040 | see WP09 prompt | WP09 | |

## WP01 — Release record and core primitives

- **Prompt**: [tasks/WP01-release-record-and-core-primitives.md](tasks/WP01-release-record-and-core-primitives.md)
- **Dependencies**: none
- **Requirements**: FR-002, FR-003, FR-006, FR-018, FR-019, C-006, C-007, NFR-002
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T001 (WP01)
T002 (WP01)
T003 (WP01)
T004 (WP01)
T005 (WP01)
T006 (WP01)

## WP02 — DB snapshot, rollback guard and readiness primitives

- **Prompt**: [tasks/WP02-db-snapshot-rollback-guard-and-readiness-primiti.md](tasks/WP02-db-snapshot-rollback-guard-and-readiness-primiti.md)
- **Dependencies**: WP01
- **Requirements**: FR-009, FR-010, FR-011, FR-014, FR-017, FR-018, FR-019
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T007 (WP02)
T008 (WP02)
T009 (WP02)
T010 (WP02)
T011 (WP02)

## WP03 — STAGE entrypoint and manifest

- **Prompt**: [tasks/WP03-stage-entrypoint-and-manifest.md](tasks/WP03-stage-entrypoint-and-manifest.md)
- **Dependencies**: WP01
- **Requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, NFR-002, NFR-003
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T012 (WP03)
T013 (WP03)
T014 (WP03)
T015 (WP03)
T016 (WP03)

## WP04 — ACTIVATE entrypoint

- **Prompt**: [tasks/WP04-activate-entrypoint.md](tasks/WP04-activate-entrypoint.md)
- **Dependencies**: WP01, WP02, WP05
- **Requirements**: FR-008, FR-009, FR-010, FR-011, FR-012, FR-017, FR-018, FR-020, NFR-001, NFR-002
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T017 (WP04)
T018 (WP04)
T019 (WP04)
T020 (WP04)
T021 (WP04)
T022 (WP04)

## WP05 — Compose fail-closed sandbox evidence on office2

- **Prompt**: [tasks/WP05-compose-fail-closed-sandbox-evidence-on-office2.md](tasks/WP05-compose-fail-closed-sandbox-evidence-on-office2.md)
- **Dependencies**: none
- **Requirements**: FR-017, C-002, C-003
- **Agent profile**: researcher-robbie · **Mode**: code_change

Subtasks:

T023 (WP05)
T024 (WP05)
T025 (WP05)

## WP06 — Rollback helper

- **Prompt**: [tasks/WP06-rollback-helper.md](tasks/WP06-rollback-helper.md)
- **Dependencies**: WP02
- **Requirements**: FR-013, FR-014, FR-015, FR-017, NFR-004
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T026 (WP06)
T027 (WP06)
T028 (WP06)
T029 (WP06)

## WP07 — Ingress helper

- **Prompt**: [tasks/WP07-ingress-helper.md](tasks/WP07-ingress-helper.md)
- **Dependencies**: WP01
- **Requirements**: FR-006, C-002
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T030 (WP07)
T031 (WP07)
T032 (WP07)

## WP08 — Cutover change set: Compose indirection, ACTIVATE manifest, inventory

- **Prompt**: [tasks/WP08-cutover-change-set-compose-indirection-activate.md](tasks/WP08-cutover-change-set-compose-indirection-activate.md)
- **Dependencies**: WP04
- **Requirements**: FR-007, FR-016, C-003, C-004
- **Agent profile**: python-pedro · **Mode**: code_change

Subtasks:

T033 (WP08)
T034 (WP08)
T035 (WP08)
T036 (WP08)

## WP09 — Runbooks and the go packet

- **Prompt**: [tasks/WP09-runbooks-and-the-go-packet.md](tasks/WP09-runbooks-and-the-go-packet.md)
- **Dependencies**: WP03, WP04, WP05, WP06, WP07, WP08
- **Requirements**: FR-015, FR-016, SC-004, NFR-004
- **Agent profile**: curator-carla · **Mode**: code_change

Subtasks:

T037 (WP09)
T038 (WP09)
T039 (WP09)
T040 (WP09)
