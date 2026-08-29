# Mission Specification: Register office4 in the Architecture

**Mission Branch**: `feat/office4-architecture-registration`
**Created**: 2026-08-29
**Status**: Draft
**Mission**: documentation
**Input**: GitHub issue [kentonium3/kg-automation#909](https://github.com/kentonium3/kg-automation/issues/909) — "Infra: office4 Phase 0 — ADR + architecture-data registration for the three-machine model"

## Documentation Scope

**Iteration Mode**: mission-specific
**Target Audience**: the maintainer (Kent) and future agent sessions reading the architecture store to decide where work belongs
**Selected Divio Types**: **explanation** (ADR 0008 — the decision and its reasoning) and **reference** (the architecture-data JSON and its narrative views)

This mission adds no documentation generator and configures no toolchain. The
deterministic verification it needs already exists as two blocking Docs-CI
validators; nothing new is introduced.

### The model being documented

```mermaid
flowchart TB
    subgraph tailnet["Tailnet — tail0f5f56.ts.net"]
        office2["office2<br/>MANAGED HOST<br/>unattended · runs all 47 services<br/>felix-deployer target"]
        office4["office4<br/>unmanaged peer<br/>attended · primary dev machine<br/>NOT a deploy target"]
        mac["kents-macbook-pro<br/>unmanaged peer<br/>attended"]
        phone["iphone-14-pro-max<br/>unmanaged peer<br/>capture + monitoring"]
    end

    place{"Where does a<br/>workload belong?"}
    place -->|"down 10 min unwatched<br/>= DATA LOSS"| office2
    place -->|"down 10 min unwatched<br/>= ANNOYANCE"| office4
```

The placement test is the load-bearing idea: office4 *is* always-on, so uptime
is not the axis that separates the machines. **Attendedness** is.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An agent session needs to know if office4 is a deploy target (Priority: P1)

A future Claude Code session picks up work that touches office4 and must
determine whether changes reach it through the `deploys/queued/` manifest
pipeline, or by some other means.

**Why this priority**: this is the question most likely to be answered wrongly
and most costly to get wrong. Felix's substrate is single-host *in code*, not
by convention — a session that assumes office4 is a managed host will write a
manifest that silently never applies, or worse, will try to make it apply.

**Independent Test**: a reader with no prior context can answer "is office4 a
felix-deployer target?" and cite the reason, using only the architecture store.

**Acceptance Scenarios**:

1. **Given** ADR 0008 is merged, **When** a session searches the architecture
   store for office4's deploy status, **Then** it finds an explicit statement
   that office4 is not a managed host, supported by named file-and-line
   evidence rather than assertion.
2. **Given** a session is about to place a `kg-automation` checkout on office4,
   **When** it consults ADR 0008, **Then** it finds the constraint that no
   checkout may live at a path felix-deployer would recognise, and why
   (`self-pull` makes "which checkout is the deploy" ambiguous).

---

### User Story 2 - Deciding where a new workload belongs (Priority: P2)

Kent or an agent is placing a new service, cron, or long-running process and
must choose between office2 and office4.

**Why this priority**: without a recorded rule, each placement is re-argued
from scratch and drifts toward whichever machine is convenient that day.

**Independent Test**: given a described workload, a reader applies the recorded
test and reaches the same placement Kent would, without asking him.

**Acceptance Scenarios**:

1. **Given** ADR 0008 is merged, **When** a reader applies the placement test
   to a workload whose ten-minute unattended outage would lose data, **Then**
   they place it on office2.
2. **Given** the same, **When** the outage would merely be an annoyance,
   **Then** they place it on office4.

---

### User Story 3 - Auditing the tailnet against the architecture store (Priority: P3)

Someone reconciles live tailnet devices against what the architecture store
records, looking for undocumented infrastructure.

**Why this priority**: this is the drift class that produced the undocumented
`codex` account (#917) — found live before it was found in documentation.

**Independent Test**: every device returned by `tailscale status` appears in
the architecture store, and the reconciliation finds no gaps.

**Acceptance Scenarios**:

1. **Given** the mission is merged, **When** the four live tailnet devices are
   compared against `network-topology.json`, **Then** all four are present with
   matching Tailscale IPs.
2. **Given** the mission is merged, **When** the same comparison is made against
   `hardware-inventory.json`, **Then** all four are present — office4 at the
   thin detail level used for the other unmanaged peers.

### Edge Cases

- **A checkout appears on office4 at a recognisable path.** ADR 0008 must state
  this constraint explicitly enough that a later session recognises the
  violation; the ADR is the only thing standing between the constraint and an
  accidental breach, since nothing enforces it mechanically.
- **office4's Tailscale IP changes.** The recorded IP becomes stale. The
  architecture store is the authority, so the fix is to update it — this
  mission records a point-in-time fact, verified live at authoring.
- **A future mission puts a service on office4.** That would contradict the
  `service-inventory.json` exclusion. The ADR must make clear that the exclusion
  is a *decision that can be revisited*, not an invariant of the schema — but
  revisiting it means **authoring a new ADR that supersedes the affected decision
  in ADR 0008**, not quietly adding a row and not editing 0008 in place.
  `docs/design/architecture/adr/README.md` states the rule: ADRs are immutable once
  approved; superseded decisions get a new ADR that references the prior one.
- **#909's own success criteria are internally inconsistent.** The issue asserts
  the Mac is absent from `hardware-inventory.json`; it is not. The spec resolves
  this in favour of verified reality (FR-007) and corrects the issue (FR-012).

## Requirements *(mandatory)*

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | ADR 0008 MUST exist at `docs/design/architecture/adr/0008-*.md` and record the three-machine model: office2 as the managed host; the MacBook Pro and office4 as unmanaged peers. | Ready |
| FR-002 | ADR 0008 MUST record the governing principle "office2 is unattended, office4 is attended", stating explicitly that uptime is not the distinguishing axis, and MUST give the placement test in a form a reader can apply to a concrete workload. | Ready |
| FR-003 | ADR 0008 MUST justify why office4 is deliberately not a managed host with five file-and-line citations, written as **repo-root-relative paths**, and MUST state that `manifest-v1.schema.json` sets `additionalProperties: false` — so a manifest naming a host is rejected, not merely unsupported. | Ready |
| FR-004 | ADR 0008 MUST record the constraint that office4 holds no `kg-automation` checkout at any path felix-deployer would recognise, and state the `self-pull` reasoning behind it. | Ready |
| FR-005 | ADR 0008 MUST record why office4 has no `claude`/`codex` Unix users — the office2 `claude` user exists because the agent is a remote actor on a host it does not live on; office4 inverts that. | Ready |
| FR-006 | `network-topology.json` MUST gain an office4 entry under `network.devices` with hostname `office4`, `tailscale_ip` `100.112.83.28`, and `os` `linux`. | Ready |
| FR-007 | `hardware-inventory.json` MUST gain an office4 entry under `hosts` at the *thin* detail level (hostname, role, hardware, os, network), with `os` `Linux Mint 22.3 (Ubuntu 24.04 noble base)` and `hardware` `Framework Desktop (AMD Ryzen AI Max 300 Series)`. | Ready |
| FR-008 | office4 MUST remain absent from `service-inventory.json`, and that absence MUST be verified as a positive outcome rather than assumed. | Ready |
| FR-009 | The narrative views MUST be brought into agreement with the authoritative JSON: `physical-topology.md` gains office4; `security-posture.md` is corrected wherever its text assumes three tailnet devices, **or** affirmed unchanged with recorded reasoning if a whole-file read finds no such assumption. | Ready |
| FR-010 | ADR 0008 MUST be added to the **ADR index** at `docs/design/architecture/adr/README.md` (required — it is the file that actually lists ADRs) and to the ADR list in `docs/INDEX.md`. `docs/DEVELOPER_PORTAL.md` and `docs/design/architecture/README.md` contain no ADR surface, so for those two "register" means adding a single pointer to the ADR index, not an ADR list they do not have. ⚠️ `DEVELOPER_PORTAL.md` lines 138–210 are a **generated** runbook-filter block (`<!-- begin:runbook-filter (generated; do not edit) -->`) whose staleness `validate_docs.py` checks — the pointer MUST go outside it. | Ready |
| FR-011 | Review-only targets (`adr/0004-tailscale-ssh-with-accept-acl.md`, `docs/runbooks/phone-termius-setup.md`) MUST be affirmed as changed or unchanged **in a named destination** — a "Review-only affirmations" subsection of ADR 0008's Consequences — so a reader can tell "read and unchanged" from "never opened". The ADR-0004 affirmation MUST cite the `tailscale debug prefs` → `"RunSSH": false` evidence. | Ready |
| FR-012 | Issue #909 MUST receive a comment correcting (a) the `hardware-inventory.json` premise and the success criterion built on it, and (b) its post-change verification step, which invokes `validate_architecture_data.py` without `--strict` and therefore cannot fail. | Ready |
| FR-013 | `docs/design/architecture/glossary.md` MUST be updated: its `Tailscale` entry MUST name four devices rather than "office2, Mac, and iPhone", and it MUST gain entries for the four canonical terms in Domain Language below. | Ready |
| FR-014 | `CLAUDE.md` MUST gain an office4 row in its Platform table and a pointer to ADR 0008, so the repo's highest-traffic file does not contradict the decision. | Ready |
| FR-015 | `signal-to-doc-map.json` MUST add `docs/design/architecture/data/hardware-inventory.json` to the `doc_targets` of `network-topology-changed`, so the next device addition does not repeat this mission's near-miss. | Ready |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | The architecture-data validator passes **under the posture the real gates use**. | `python3 tooling/scripts/validate_architecture_data.py --strict` exits 0. `--strict` is required: without it the validator is warn-only and exits 0 unconditionally, so the check could not fail. | Ready |
| NFR-002 | The docs validator passes. | `python3 tooling/scripts/validate_docs.py` exits 0 | Ready |
| NFR-003 | Every new or edited markdown file under `docs/` carries valid YAML frontmatter. | Enforced by `validate_docs.py`, which errors on a missing fence | Ready |
| NFR-004 | Relative links introduced or edited by this mission resolve. | **Human review item, not an automated one** — no tool in this repo checks links (`validate_docs.py` checks frontmatter and secrets only). The reviewer opens every relative link in the touched files and confirms it resolves; the count checked is recorded in the review. | Ready |
| NFR-005 | office4's recorded identity matches the live host, each field from its correct source. | `tailscale_ip` = `tailscale ip -4`; `os` from `/etc/os-release` (**not** `uname -a`, which reports the kernel build's Ubuntu provenance); `hardware` from `/sys/devices/virtual/dmi/id/{sys_vendor,product_name}` | Ready |
| NFR-006 | The ADR's file-and-line citations resolve to the content they claim. | 5 of 5 verified against the working tree, each written repo-root-relative | Ready |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Tier 4 (Auto-Commit). The mission changes documentation and architecture metadata only — no host, service, credential, port, or network change. office4 is already on the tailnet; this records that fact, it does not create it. | Ready |
| C-002 | No felix-deployer, manifest-schema, lock-namespacing, or baseline-registry change. Making office4 a managed host is a design change across five subsystems and is out of scope. | Ready |
| C-003 | JSON files are authoritative; markdown views follow. Where the two disagree, the JSON wins. | Ready |
| C-004 | No rebaseline is required — architecture-data JSON is not an audited surface per `audited-surfaces.json`. The line `Rebaseline: not required — documentation and architecture metadata only` MUST be recorded on the **`feat → main` integration commit**, which MUST be created with `git merge --no-ff` so that a commit exists to carry it. A fast-forward would produce no such commit, and `spec-kitty merge` exposes no commit-message option (amending its commit would be a prohibited manual git workaround). Verification checks both the message **and** that the commit has two parents, so an ordinary one-parent commit cannot satisfy it. This sits outside the mission's own gate by design. | Ready |
| C-005 | `kitty-specs/` and `.kittify/` are spec-kitty-owned and MUST NOT be hand-edited; all changes flow through spec-kitty commands. | Ready |
| C-006 | office4 MUST NOT be added to `service-inventory.json` in this mission. Adding it would imply managed-host status, which is precisely the decision being recorded against. | Ready |

## Domain Language

Terminology that must stay canonical, because the whole decision rests on it. FR-013
lands all four in `docs/design/architecture/glossary.md`, so they stay canonical beyond
this mission rather than only within it:

| Canonical term | Meaning | Avoid |
|---|---|---|
| **managed host** | A machine whose state Felix deploys to and audits — currently office2 alone. | "server", "the box", "production" |
| **unmanaged peer** | A tailnet device Felix does not deploy to: the MacBook Pro, the iPhone, and now office4. | "client", "workstation" used as if it implied a tier |
| **attended** / **unattended** | Whether a human is present to notice a failure. The axis that separates office4 from office2. | "always-on" as a synonym — office4 *is* always-on; that is the point |
| **thin entry** | The reduced `hardware-inventory.json` record used for unmanaged peers (hostname, role, hardware, os, network). | "stub", "placeholder" |

## Key Entities

- **ADR** — a numbered, immutable-once-merged decision record under
  `docs/design/architecture/adr/`. Records *why*, not just *what*.
- **Architecture data store** — the JSON under
  `docs/design/architecture/data/`, authoritative over its markdown views.
- **Signal-to-doc map** — `signal-to-doc-map.json`, which enumerates the doc
  targets a change class must address; the source of this mission's eight targets.
- **Device record vs service record** — `hardware-inventory.json` lists every
  tailnet device; `service-inventory.json` lists only what office2 runs. Neither
  file *defines* managed status: **ADR 0008 and the deploy/audit mechanisms do.**
  The all-office2 service inventory and the single rich hardware record are
  corroborating facts and mission postconditions, not semantic classifiers — a
  managed host could temporarily run zero services, and documenting a peer's
  hardware in detail would not make it managed. Treating inventory contents as the
  definition would let a later documentation edit appear to change architecture.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader who has never seen the migration can answer "is office4 a
  deploy target, and why not?" from the architecture store alone, in under two
  minutes, without consulting a GitHub issue or a local plan file.
- **SC-002**: A reader applying the recorded placement test to a described
  workload reaches the intended machine for both the data-loss and the
  annoyance case — 2 of 2.
- **SC-003**: All four live tailnet devices appear in both the device topology
  and the hardware inventory — 4 of 4 in each — and **all four** recorded IPs match
  `tailscale status`, not office4's alone.
- **SC-004**: office4 appears in zero service records, verified by an assertion that
  would fail if violated.
- **SC-005**: Every doc target is accounted for, none silently skipped:
  - **8 of 8** named by the signal-to-doc map — **6 updated**
    (`network-topology.json`, `physical-topology.md`, `security-posture.md`,
    `INDEX.md`, `DEVELOPER_PORTAL.md`, `architecture/README.md`) and **2 affirmed**
    (`adr/0004`, `phone-termius-setup.md`).
  - **5 more the map does not name** but which this mission requires:
    `adr/README.md` (the actual ADR index), `hardware-inventory.json`, `glossary.md`,
    `CLAUDE.md`, and `signal-to-doc-map.json` itself.
  - FR-015 closes that gap for one of the five, so the next device addition inherits
    `hardware-inventory.json` from the map instead of relying on a reviewer to notice.
- **SC-006**: Both validators pass **at commit time** — the `.githooks` pre-commit gate
  runs them on every commit. Docs CI does not fire on the mission merge (it triggers only
  on `main`), so "Docs CI green" is satisfied at Kent's `feat → main` push, not at
  mission close.
- **SC-007**: Issue #909's incorrect premise and its non-failing verification step are
  both corrected in the issue thread.
- **SC-008**: No repo surface contradicts ADR 0008 on merge — specifically `glossary.md`
  names four tailnet devices and defines the four canonical terms, and `CLAUDE.md`'s
  Platform table includes office4.

### Quality Gates

- No broken relative links in the touched files — **checked by the reviewer by hand**;
  nothing in this repo validates links
- Heading hierarchy is proper (H1 → H2 → H3, no skipped levels) — **also a human check**,
  for the same reason
- YAML frontmatter present on every touched markdown file under `docs/` — automated
- Every file-and-line citation in the ADR resolves to the claimed content
- office4's `os` and `hardware` values come from `/etc/os-release` and sysfs respectively,
  not from `uname -a`
- Kent's `feat → main` merge commit carries the `Rebaseline:` line required by C-004

## Assumptions

- **ASM-000**: office4 runs Linux Mint 22.3 (noble base), verified via `/etc/os-release`.
  An earlier draft recorded Ubuntu 24.04 by misreading `uname -a`'s kernel build string
  `#28~24.04.1-Ubuntu`; the correction is recorded in research.md R-4.
- **ASM-001**: office4's Tailscale IP `100.112.83.28` is stable for the
  foreseeable future. Verified live at authoring time via `tailscale ip -4`
  and `tailscale status`; the architecture store records point-in-time truth
  and is updated when the fact changes.
- **ASM-002**: The Tailscale device name `office4` (lowercase) is the correct
  identifier for both JSON records, following the `kents-macbook-pro`
  precedent of using the Tailscale device name rather than the system hostname
  (which is `Office4`, capitalised).
- **ASM-003**: ADR 0008 is the next free number; `adr/` currently ends at 0007.
  Verified by directory listing at authoring time.
- **ASM-004**: No concurrent mission is adding an ADR, so 0008 will not collide.

## Out of Scope

- Making office4 a managed host, or any felix-deployer, manifest-schema,
  lock-namespacing, or baseline-registry change to enable that
- Adding office4 to `service-inventory.json`, or registering any service,
  port, binding, credential, or data flow on office4
- Creating `claude` or `codex` Unix users on office4 — the ADR records why
  they are absent; it does not create them
- The remaining office4 migration issues under epic #908 — this is Phase 0 only
- Moving the spec-kitty-qa QA pipeline off office2 (#887 — targets exe.dev,
  not office4)
- Resolving the undocumented `codex` account (#917), which is cited only as
  precedent for the drift class this mission prevents
