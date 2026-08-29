# Implementation Plan: Register office4 in the Architecture

**Branch**: `feat/office4-architecture-registration` | **Date**: 2026-08-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/office4-architecture-registration-01M15RW2/spec.md`

## Summary

Write the office4 migration's architecture decisions into the durable architecture
store. Two Divio types are in play and no others: **explanation** (ADR 0008 — the
three-machine model and its reasoning) and **reference** (the architecture-data JSON
and its narrative views).

This is a documentation mission with **no documentation-site build**. There is no
framework, no generator, no theme, and no hosting target — the "documentation system"
here is the existing `docs/` tree plus two blocking CI validators. The scaffolded
template's Sphinx/JSDoc/rustdoc/Read-the-Docs machinery is struck out below as not
applicable rather than left as aspirational placeholder text.

## Technical Context

**Language/Version**: Python 3.12.3 (repo `.venv`; validators only — this mission ships no application code)
**Primary Dependencies**: PyYAML 6.0.3 and jsonschema (already in `requirements.txt`); no new dependency is added
**Storage**: Flat files in the repo — Markdown under `docs/`, JSON under `docs/design/architecture/data/`
**Testing**: `tooling/scripts/validate_architecture_data.py --strict` and `tooling/scripts/validate_docs.py`, run by the `.githooks` pre-commit gate and by Docs CI
**Target Platform**: The repository itself. Nothing deploys; office4 is not a deploy target, which is the substance of the decision being recorded
**Project Type**: Documentation / architecture metadata
**Performance Goals**: Not applicable — no runtime component. The relevant budget is the pre-commit gate, ~4s for both validators
**Constraints**: Tier 4 (Auto-Commit); JSON authoritative over Markdown; no rebaseline required; `kitty-specs/` and `.kittify/` never hand-edited
**Scale/Scope**: 1 new ADR, 2 JSON files edited, 3 index docs updated, 2 narrative views updated, 2 review-only affirmations, 1 issue comment

**Documentation Framework**: None. `docs/` is plain Markdown with YAML frontmatter, validated by repo scripts.
**Output Format**: Markdown + JSON, consumed in-repo and via Obsidian sync.
**Hosting Platform**: Not applicable — no published documentation site.
**Generator Tools**: Not applicable. `setup-plan` auto-detected `jsdoc` and `sphinx`; both are **false positives** from generic language sniffing. This repo has no JavaScript documentation surface and no Sphinx configuration, and this mission introduces neither.
**Accessibility Requirements**: Proper heading hierarchy and descriptive link text in all authored Markdown. No images are added, so alt text does not arise.

## Project Structure

### Mission artifacts

```
kitty-specs/office4-architecture-registration-01M15RW2/
├── spec.md                 # Committed (80429f5)
├── plan.md                 # This file
├── research.md             # Phase 0 — verification findings
├── data-model.md           # Phase 1 — record shapes for the two JSON files
├── contracts/
│   └── architecture-data-payloads.md   # Exact JSON to be added, and the invariants
├── quickstart.md           # Phase 1 — how to verify this mission landed correctly
└── tasks/                  # Phase 2 output (/spec-kitty.tasks)
```

### Repository files this mission touches

```
docs/
├── INDEX.md                                   # register ADR 0008
├── DEVELOPER_PORTAL.md                        # register ADR 0008
├── design/architecture/
│   ├── README.md                              # register ADR 0008
│   ├── physical-topology.md                   # narrative — add office4
│   ├── security-posture.md                    # narrative — re-read for 4 devices
│   ├── adr/
│   │   ├── 0004-tailscale-ssh-with-accept-acl.md   # REVIEW ONLY
│   │   └── 0008-three-machine-model.md             # NEW
│   └── data/
│       ├── network-topology.json              # add network.devices[] entry
│       └── hardware-inventory.json            # add hosts[] thin entry
└── runbooks/phone-termius-setup.md            # REVIEW ONLY
```

`service-inventory.json` appears in no list above. That absence is deliberate and is
itself a deliverable (C-006, SC-004).

## Phase 0: Research

### Objective

Verify every load-bearing factual claim *before* it becomes an ADR assertion. An ADR is
read as settled truth for years, so a wrong citation in it is more costly than a wrong
line of code — code fails loudly, a bad ADR quietly misinforms.

### Research tasks

1. **Verify the #909 premises against the working tree.** Both inventory claims, the
   device counts, and the next free ADR number. *(Complete — one premise was false; see
   research.md.)*
2. **Verify the five single-host citations.** Each must resolve to the content #909
   claims, at the line it claims. *(Complete — 5 of 5 confirmed.)*
3. **Verify office4's live identity.** Tailscale device name, IP, and OS, taken from the
   host rather than from the plan document. *(Complete.)*
4. **Establish the thin-entry precedent.** Determine the exact field set used for
   unmanaged peers in `hardware-inventory.json` so office4 matches it rather than
   inventing a shape. *(Complete.)*
5. **Confirm the rebaseline obligation.** Check `audited-surfaces.json` directly rather
   than trusting the issue's assertion. *(Complete — architecture-data JSON is not an
   audited surface.)*

### Research output

See [research.md](research.md).

## Phase 1: Design

### Objective

Fix the exact content shapes before authoring, so the ADR and the two JSON edits are
mechanical to write and mechanical to check.

### Design decisions

**D-1 — office4 is registered in `hardware-inventory.json`, contrary to #909.**
The issue's premise was verified false. office4 gets a *thin* entry matching the
`kents-macbook-pro` / `iphone-14-pro-max` shape. Approved by Kent during discovery.

**D-2 — the managed/unmanaged boundary is carried by `service-inventory.json` and the
ADR, not by presence in the device record.** This is what makes D-1 safe: registering
office4 as a device does not imply managed-host status, exactly as it does not for the Mac.

**D-3 — identifiers come from Tailscale, not from the OS.** The device is recorded as
`office4` (Tailscale device name), not `Office4` (the system hostname). This follows the
`kents-macbook-pro` precedent.

**D-4 — the ADR argues from evidence, not assertion.** Every claim that Felix's
substrate is single-host cites a file and line verified in Phase 0.

**D-5 — "review only" targets get a written affirmation.** A reviewer must be able to
tell "read and unchanged" from "never opened" (FR-011).

### Structure of ADR 0008

Following the shape of the existing ADRs 0001–0007 (status / context / decision /
consequences), with frontmatter matching repo convention:

1. **Context** — office4 arrives as primary dev machine; the substrate is single-host in
   code; nothing recorded the boundary.
2. **Decision** — three-machine model; office2 managed, Mac and office4 unmanaged peers.
3. **The governing principle** — office2 unattended, office4 attended; uptime is *not*
   the axis; the placement test in applicable form.
4. **Why office4 is not a managed host** — the five citations.
5. **Constraints that follow** — no recognisable checkout on office4; no `claude`/`codex`
   Unix users, with the remote-actor reasoning.
6. **Consequences** — what becomes easy, what becomes harder, what would have to change
   to revisit this.

### Success criteria validation

| Spec criterion | How this plan satisfies it |
|---|---|
| SC-001 findability | ADR registered in three index surfaces (FR-010), so it is reachable from the documentation map, the portal, and the architecture README |
| SC-002 placement test | ADR section 3 states the test in applicable form, with both worked cases |
| SC-003 four devices in both records | FR-006 and FR-007; verified by quickstart step 2 |
| SC-004 zero service records | C-006; verified by quickstart step 3 as a positive check |
| SC-005 eight doc targets | FR-009, FR-010, FR-011 — five updated, two affirmed, plus the ADR itself |
| SC-006 validators + CI | Pre-commit gate runs both; Docs CI re-runs on push |
| SC-007 issue corrected | FR-012 |

## Charter Check

*GATE: evaluated against `.kittify/charter/charter.md`.*

| Charter policy | Status |
|---|---|
| YAML frontmatter required on all markdown | **Must comply** — ADR 0008 needs frontmatter matching sibling ADRs; enforced by `validate_docs.py` |
| Architecture decisions live in `docs/design/` | **Complies** — ADR under `docs/design/architecture/adr/` |
| JSON authoritative, markdown views follow | **Complies** — JSON edited first, narrative views updated to match (D-2) |
| Conventional commits | **Must comply** — `docs:` prefix |
| Update docs when behaviour changes | **Complies** — this mission *is* that update |
| doc validation via validators in CI (mandatory) | **Complies** — both validators are pre-commit and CI gates |
| pytest for non-trivial Python helpers | **Not applicable** — no Python helper is added |
| Integration verification before `for_review` (mandatory) | **Satisfied by** the quickstart verification steps; there is no deployed service to integrate against |
| Deployment constraints (office2-only, deploy script required) | **Not applicable** — nothing deploys. Recording that office4 is not a deploy target is the mission |
| Review Policy: solo maintainer, no PR requirement | Mission merges to `feat/office4-architecture-registration`; Kent takes `feat → main` |

**No charter conflicts identified.**

## Supply-Chain Security

**No dependency is added, upgraded, or removed** in any ecosystem. No brew tap, pip
index, npm registry, or MCP plugin is introduced. PyYAML and jsonschema are already
pinned in `requirements.txt` and are used only by the pre-existing validators.

Stating this explicitly because silence is not compliance: the
`051-supply-chain-install-safety` directive is examined and found to have no surface to
act on in this mission. No adversarial-squad challenge pass is required, because no
security-impacting dependency decision is made.

## Implementation Concerns

Concerns for `/spec-kitty.tasks` to translate into work packages. They are ordered by
dependency: the JSON edits are authoritative and should land before the narrative views
that describe them (charter: JSON authoritative, markdown follows).

**IC-1 — Architecture data registration.** Add office4 to `network.devices` in
`network-topology.json` and a thin entry to `hosts` in `hardware-inventory.json`. Bump
`last_updated` / `updated_by` on both, matching the existing convention. Verify
`service-inventory.json` remains untouched. *(FR-006, FR-007, FR-008; C-003, C-006)*

**IC-2 — Author ADR 0008.** The decision record itself, with verified citations and
frontmatter matching sibling ADRs. Largest single unit of judgement in the mission.
*(FR-001 … FR-005; NFR-003, NFR-006)*

**IC-3 — Narrative views.** Update `physical-topology.md` for four devices; re-read
`security-posture.md` and correct any text that assumes three. *(FR-009)*

**IC-4 — Registration and affirmation.** Register ADR 0008 in `docs/INDEX.md`,
`docs/DEVELOPER_PORTAL.md`, and `docs/design/architecture/README.md`. Record explicit
review-only affirmations for ADR-0004 and `phone-termius-setup.md`. *(FR-010, FR-011)*

**IC-5 — Issue correction.** Comment on #909 correcting the `hardware-inventory.json`
premise and the success criterion built on it. *(FR-012, SC-007)*

**IC-6 — Verification.** Run both validators, confirm the four-device and zero-service
checks, and confirm the merge commit carries the `Rebaseline: not required` line.
*(NFR-001, NFR-002, NFR-004, NFR-005; C-004)*

## Risks & Dependencies

**R-1 — The ADR outlives its evidence.** Line numbers drift as code changes, so the
citations decay. *Mitigation*: cite the file and the behaviour together, so a moved line
still leaves a findable claim; never cite a bare line number alone.

**R-2 — The `hardware-inventory.json` correction is mistaken for scope creep.** A
reviewer reading only #909 will see a success criterion being violated. *Mitigation*:
FR-012 corrects the issue, and research.md records the evidence and Kent's approval.

**R-3 — A future session adds a service on office4.** Nothing mechanically prevents it.
*Mitigation*: the ADR frames the exclusion as a revisitable decision requiring an ADR
amendment, not a silent row addition.

**R-4 — Nothing enforces the no-recognisable-checkout constraint.** It is documentation
only. *Accepted*: mechanical enforcement would require the felix-deployer changes this
mission explicitly excludes (C-002). Recorded in the ADR's consequences.

**Dependencies**: none external. All edits are local files; both validators are already
installed in the repo `.venv` (verified during specify, after the office4 setup fix in
kg-automation#923).
