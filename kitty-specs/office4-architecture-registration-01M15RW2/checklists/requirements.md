# Specification Quality Checklist: Register office4 in the Architecture

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-29
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Requirement types are separated (Functional / Non-Functional / Constraints)
- [x] IDs are unique across FR-###, NFR-###, and C-### entries
- [x] All requirement rows include a non-empty Status value
- [x] Non-functional requirements include measurable thresholds
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

Validation ran in a single pass; no iteration was required. Counts: 12 FR, 6 NFR,
6 C, 3 user stories, 4 edge cases, 7 success criteria, 4 assumptions, 6 out-of-scope
items. IDs are contiguous and unique within each class.

Two items pass with a recorded deviation rather than silently:

1. **"No implementation details" / "technology-agnostic success criteria."** This is a
   *documentation* mission whose deliverables are specific files, so naming
   `hardware-inventory.json`, `network-topology.json`, and ADR 0008 is the requirement
   itself, not leakage — an ADR that did not say which file it is would be untestable.
   Likewise NFR-001/002 and SC-006 name the two validator commands. The charter makes
   CI doc validation a mandatory quality gate, which makes "the validators pass" a
   stakeholder-visible outcome here rather than an internal detail. Recorded so a
   reviewer can disagree on the record.

2. **"Written for non-technical stakeholders."** The subject matter is the boundary
   between two machines, so the spec cannot be made non-technical without losing its
   meaning. The mitigation is the Domain Language section and the Mermaid model, which
   let a reader who is not deep in Felix's internals follow the decision and apply the
   placement test.

### Upstream correction folded into this spec

Issue #909 asserts that `hardware-inventory.json` is a managed-host record from which
the MacBook Pro is absent, and sets a success criterion requiring office4 to be absent
from it too. That premise was verified false during discovery: the file's `hosts` array
already carries `kents-macbook-pro` and `iphone-14-pro-max` at a reduced detail level.
Following #909 literally would have made office4 the only tailnet device missing from
the device record — the exact drift the issue exists to prevent. Kent confirmed the
correction during discovery. FR-007 registers office4 at the thin detail level, and
FR-012 requires the issue thread to be corrected so the next reader is not misled.

The other half of #909's claim was verified true and is preserved: all 47 entries in
`service-inventory.json` are on office2, and C-006 keeps it that way.

All five file-and-line citations #909 offers as evidence for the single-host substrate
were verified against the working tree before being made a requirement (FR-003):
`manifest-v1.schema.json` has no `host` field; `scripts/deploy/lib/deploylock.py:41`
names `office2-checkout.lock`; `scripts/deploy/felix-deployer/_tick.py:59` defaults
`DEFAULT_REPO_ROOT` to office2's path; `scripts/deploy/felix-deployer/rebaseline.py:49`
documents stripping the `ssh office2-claude` wrapper because felix-deployer runs *on*
office2; and `scripts/deploy/lib/tier.py:73` embeds `ssh office2-kgale`.

### Workflow note

Decision Moments were not opened for the pre-`create` discovery questions. `decision
open` requires `--mission`, which cannot exist before `mission create`, and the
Discovery Gate runs before it — see kg-automation#922 and upstream #3434 / #3619. The
pre-known workaround from #3434 was applied (interview without pre-create records;
nothing gates on them). Any post-`create` clarification still uses the full protocol.

- Items marked incomplete require spec updates before `/spec-kitty.plan`
