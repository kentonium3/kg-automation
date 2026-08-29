# Tasks: Register office4 in the Architecture

**Mission**: `office4-architecture-registration-01M15RW2`
**Branch**: `feat/office4-architecture-registration` | **Merge target**: `feat/office4-architecture-registration`
**Date**: 2026-08-29

Derived from plan.md's implementation concerns IC-1…IC-7. Exact payloads live in
[contracts/architecture-data-payloads.md](contracts/architecture-data-payloads.md); record
shapes and invariants in [data-model.md](data-model.md); verified facts in
[research.md](research.md). WP prompts reference those rather than restating them, so there
is exactly one source of truth per value.

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Add office4 to `network.devices` in `network-topology.json` | WP01 | |
| T002 | Append office4 thin entry to `hosts` in `hardware-inventory.json` | WP01 | |
| T003 | Bump `last_updated` / `updated_by` on both JSON files | WP01 | |
| T004 | Assert `service-inventory.json` remains all-office2 | WP01 | |
| T005 | Run `validate_architecture_data.py --strict` | WP01 | |
| T006 | Create ADR 0008 file with sibling-matching frontmatter | WP02 | [P] |
| T007 | Write Context and Decision — the three-machine model | WP02 | [P] |
| T008 | Write the attended/unattended principle and placement test | WP02 | [P] |
| T009 | Write the five single-host citations | WP02 | [P] |
| T010 | Write the two office4 constraints (checkout, Unix users) | WP02 | [P] |
| T011 | Write Consequences incl. the Review-only affirmations subsection | WP02 | [P] |
| T012 | Add office4 to `physical-topology.md` | WP03 | |
| T013 | Correct three-device assumptions in `security-posture.md` | WP03 | |
| T014 | Confirm narrative matches the authoritative JSON | WP03 | |
| T015 | Add the 0008 row to the ADR index (`adr/README.md`) | WP04 | |
| T016 | Add 0008 to the ADR list in `docs/INDEX.md` | WP04 | |
| T017 | Add an ADR pointer to `DEVELOPER_PORTAL.md` outside the generated block | WP04 | |
| T018 | Add an ADR pointer to `docs/design/architecture/README.md` | WP04 | |
| T019 | Run the per-file registration loop and `validate_docs.py` | WP04 | |
| T020 | Update the `Tailscale` glossary entry to four devices | WP05 | |
| T021 | Add the four canonical terms to the glossary | WP05 | |
| T022 | Add an office4 row and ADR pointer to `CLAUDE.md` | WP05 | |
| T023 | Add `hardware-inventory.json` to `network-topology-changed` in the signal map | WP05 | |
| T024 | Verify the signal-map assertion and re-run the architecture validator | WP05 | |
| T025 | Comment on #909 correcting the premise and the non-failing verification | WP06 | |
| T026 | Run both validators at their real postures | WP06 | |
| T027 | Reconcile all four devices against the live tailnet | WP06 | |
| T028 | Assert zero office4 service records | WP06 | |
| T029 | Human review of relative links and heading hierarchy | WP06 | |
| T030 | Attest office4 `os` and `hardware` sources on the host | WP06 | |
| T031 | Write `verification-report.md` and hand off the `--no-ff` requirement | WP06 | |

Completion is event-sourced: record it with
`spec-kitty agent tasks mark-status T001 --status done`. The rows above are reference
rows, not checkboxes.

## Dependency graph

| WP | Depends on | Rationale |
|---|---|---|
| WP01 | — | Authoritative JSON lands first (charter: JSON authoritative, markdown follows) |
| WP02 | — | Independent prose; runs parallel to WP01 |
| WP03 | WP01 | Narrative views describe the JSON they follow |
| WP04 | WP02 | Registration needs the ADR's final filename to exist |
| WP05 | WP01, WP02 | Glossary and CLAUDE.md reference the ADR; the map edit is architecture data |
| WP06 | WP01–WP05 | Verification runs only once every deliverable exists; the #909 comment must match what was implemented |

**Parallelisation**: WP01 and WP02 start together. Once both land, WP03, WP04 and WP05 all
become available simultaneously — the widest point in the mission. WP06 closes it out.

---

## WP01 — Architecture data registration

**Goal**: office4 is present in both authoritative JSON records, at the right detail level,
without disturbing the service inventory.
**Priority**: P1 (everything narrative follows this)
**Requirements**: FR-006, FR-007, FR-008
**Independent test**: `network.devices` and `hosts` each contain four entries including
office4; `service-inventory.json` is byte-identical to its pre-mission state.
**Subtasks**: T001, T002, T003, T004, T005
**Estimated prompt size**: ~195 lines

**Implementation sketch**: apply contract C-1 to `network-topology.json`; apply contract C-2
to `hardware-inventory.json` by **appending** (a runbook reads `hosts[0].gpu`, so office2
must stay at index 0); bump metadata on both; run the positive service-inventory assertion;
run the architecture validator under `--strict`.

**Risks**: no validator catches a wrong *value* in a correctly-shaped field — the payloads
pass `--strict` whether `os` and `hardware` are right or wrong. Both values are fixed in
contract C-2 and must be copied exactly, not re-derived.

---

## WP02 — Author ADR 0008

**Goal**: a decision record that answers, without leaving the document, what the three
machines are, where a workload belongs, why office4 is not managed, what it must never
hold, and why it has no agent Unix users.
**Priority**: P1
**Requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-011
**Independent test**: a reader with no prior context answers contract C-5's five questions
from the ADR alone.
**Subtasks**: T006, T007, T008, T009, T010, T011
**Estimated prompt size**: ~215 lines

**Implementation sketch**: create `0008-three-machine-model.md` with frontmatter matching
ADR-0006/0007; write Context → Decision → governing principle → evidence → constraints →
Consequences; close with the Review-only affirmations subsection.

**Risks**: the ADR is read as settled truth for years, so an overstated citation is costlier
than a wrong line of code. Use the phrasings research.md R-3 settled.

---

## WP03 — Narrative views

**Goal**: the human-readable topology and security narratives describe four tailnet devices.
**Priority**: P2
**Requirements**: FR-009
**Independent test**: neither file asserts a three-device tailnet; both agree with
`network-topology.json`.
**Subtasks**: T012, T013, T014
**Dependencies**: WP01
**Estimated prompt size**: ~125 lines

**Risks**: `security-posture.md` may state the access model in prose that is true for three
devices and subtly wrong for four. Read it whole rather than grepping for "three".

---

## WP04 — ADR registration in the index surfaces

**Goal**: ADR 0008 is discoverable from every surface that indexes or points at ADRs.
**Priority**: P2
**Requirements**: FR-010
**Independent test**: the per-file loop in quickstart step 5 passes for all four files.
**Subtasks**: T015, T016, T017, T018, T019
**Dependencies**: WP02
**Estimated prompt size**: ~145 lines

**Risks**: `DEVELOPER_PORTAL.md` lines 138–210 are a **generated** block whose staleness
`validate_docs.py` checks. Editing inside it fails the commit gate. Two of the four files
have no ADR list at all — add a pointer, not an invented list.

---

## WP05 — Adjacent surfaces

**Goal**: no repo surface contradicts ADR 0008, and the signal-to-doc map stops reproducing
this mission's near-miss.
**Priority**: P2
**Requirements**: FR-013, FR-014, FR-015
**Independent test**: the glossary names four devices and defines all four canonical terms;
`CLAUDE.md` lists office4; the map's `network-topology-changed` entry names
`hardware-inventory.json`.
**Subtasks**: T020, T021, T022, T023, T024
**Dependencies**: WP01, WP02
**Estimated prompt size**: ~165 lines

**Risks**: `CLAUDE.md` is repo-root, not under `docs/` — do not add frontmatter it does not
already have. The map edit is itself architecture data, so re-run the validator after it.

---

## WP06 — Closeout: issue correction and verification

**Goal**: every acceptance check is executed and recorded, #909 no longer misleads, and the
one obligation the mission cannot satisfy itself is handed off explicitly.
**Priority**: P1 (nothing is done until this is)
**Requirements**: FR-012 (plus NFR-001…NFR-006 and C-004 verification)
**Independent test**: `verification-report.md` exists and records a concrete result — pass
or fail — for every quickstart step, with no step marked "not run".
**Subtasks**: T025, T026, T027, T028, T029, T030, T031
**Dependencies**: WP01, WP02, WP03, WP04, WP05
**Estimated prompt size**: ~185 lines

**Implementation sketch**: run quickstart steps 1–6 and record each outcome; comment on
#909; write the verification report; state in the handoff that C-004's `Rebaseline:` line
must ride a `git merge --no-ff` integration commit, which is outside this mission's gate.

**Risks**: this WP owns no repo source files by design — it performs an external action and
read-only verification, and writes only its own report into the mission directory. Do not
give it ownership of files other WPs edit.
