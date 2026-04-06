---
title: "F020: spec-kitty Charter Setup and Governance Migration"
doc_type: func-spec
status: draft
feature: F020
---

# F020: spec-kitty Charter Setup and Governance Migration

**Version**: 1.0
**Priority**: HIGH
**Type**: Infrastructure
**Recommended Mission Type**: `software-dev`
**Depends on**: None — can run in parallel with F019

---

## Executive Summary

spec-kitty's alpha release supersedes its "constitution" concept with a "charter"
concept. The charter is spec-kitty's workflow governance document — it captures
project-level policies (testing standards, quality gates, branching rules, deployment
constraints) and feeds them automatically into agent prompts at every workflow step.

**Critical distinction**: The spec-kitty charter and the Felix Constitution are
different governance artifacts serving different purposes:

| Artifact | Purpose | Location |
|----------|---------|----------|
| spec-kitty charter | Workflow governance for spec-kitty (testing, quality gates, branching) | `.kittify/charter/charter.md` |
| Felix Constitution | Felix agent governance (autonomy levels, privacy, directives) | `docs/constitution/FELIX-CONSTITUTION.md` |

These do not replace each other. This feature sets up the spec-kitty charter for
kg-automation and migrates any legacy 1.x constitution artifacts in `.kittify/`.
The Felix Constitution and all "Constitutional Compliance" sections in func-specs
are unaffected — they refer to Felix agent governance, not spec-kitty workflow governance.

Current gaps:
- ❌ No spec-kitty charter exists for kg-automation — workflow governance is undefined
- ❌ Any legacy 1.x spec-kitty constitution artifacts in `.kittify/` are stale
- ❌ spec-kitty agents receive no project governance context at workflow steps
- ❌ Quality gates, testing standards, and branching rules are not enforced by spec-kitty

This spec delivers a functioning spec-kitty charter for kg-automation via the
`spec-kitty charter interview` workflow, migrates any legacy artifacts, and confirms
the charter is active and injecting governance into spec-kitty workflow actions.

---

## Problem Statement

**Current State:**
```
.kittify/
├── config.yaml          ← project config (exists)
├── metadata.yaml        ← project metadata (exists)
└── [no charter/]        ← spec-kitty charter not set up

spec-kitty workflow actions (specify, plan, implement, review)
└── ❌ No governance context injected — quality gates and policies
       not enforced at workflow steps
```

**Target State:**
```
.kittify/
├── config.yaml                      ← unchanged
├── charter/
│   ├── charter.md                   ← authoritative policy document
│   ├── interview/answers.yaml       ← structured interview responses
│   ├── references.yaml              ← doctrine reference selections
│   └── library/*.md                 ← auto-generated guidance docs
└── [governance.yaml, directives.yaml auto-generated from charter]

spec-kitty workflow actions
└── ✅ Governance context injected at each step via `charter context --action`
```

---

## CRITICAL: Study These Files FIRST

Before implementation, the planning phase MUST read:

1. **spec-kitty charter documentation**
   - `https://docs.spec-kitty.ai/2x/doctrine-and-charter.html`
   - Understand the 3-layer model: charter.md → governance.yaml/directives.yaml
     → library/*.md
   - Understand the interview-generate-sync workflow
   - Note the five charter subcommands: interview, generate, context, status, sync

2. **spec-kitty charter how-to guide**
   - `https://docs.spec-kitty.ai/how-to/setup-governance.html`
   - Full walkthrough of interview, generate, and sync steps

3. **Current .kittify/ contents**
   - Inspect `.kittify/` in the repo root for any legacy 1.x constitution artifacts
   - Run `spec-kitty charter status` to understand current state
   - If a `constitution/` directory exists under `.kittify/`, that is the legacy
     artifact to be migrated

4. **CLAUDE.md — existing behavioral rules**
   - Any references to spec-kitty's governance model (not Felix governance) must
     be updated to reflect the charter concept
   - Felix Constitution references in CLAUDE.md are about Felix agent governance
     and must NOT be changed

5. **kg-automation project characteristics (for interview answers)**
   - Primary language: Python (scripts), Markdown (docs), JSON (data)
   - Testing: no formal test suite currently — lightweight validation via CI
   - Branching: push directly to main for routine changes; feature branches for
     complex work
   - Quality gates: spec-kitty review phase; no automated test suite gate currently
   - Deployment: office2 (Ubuntu 24.04 LTS); changes deployed via SSH + systemd
   - Paradigms: DOCS_ADJACENT (documentation lives alongside code) is relevant;
     LIBRARY_FIRST applies to Python scripts

---

## Functional Requirements

### FR-1: Audit .kittify/ for Legacy Constitution Artifacts

**What it must do:**
- Inspect `.kittify/` for any legacy 1.x spec-kitty constitution artifacts
  (e.g., a `constitution/` directory, a `constitution.md` file, or similar)
- Document what is found before making any changes
- If legacy artifacts exist, determine the migration path per spec-kitty's
  upgrade documentation before proceeding

**Success criteria:**
- [ ] `.kittify/` contents documented before any changes made
- [ ] Legacy constitution artifacts identified (or confirmed absent)
- [ ] Migration path determined if legacy artifacts exist

---

### FR-2: Run spec-kitty Charter Interview

**What it must do:**
- Run `spec-kitty charter interview` to capture kg-automation's project
  governance policies interactively
- Use the **comprehensive** profile (11 questions) — kg-automation has
  well-defined policies that warrant full capture
- Answer questions based on the project characteristics documented in the
  "Study These Files First" section above
- Produce `answers.yaml` and a draft `charter.md` in `.kittify/charter/`

**Key policy answers to encode:**
- **Testing**: lightweight CI validation; no formal test suite gate currently;
  doc validation (frontmatter) is the primary quality check
- **Branching**: push to main for routine changes; feature branches for
  complex multi-step work; conventional commits enforced
- **Quality gates**: spec-kitty review phase required; all WPs must be done
  before review; INDEX.md and architecture docs must be updated in same PR
- **Deployment**: office2 via SSH; Tier 0 changes (UFW, SSH) require Hard Lock
  per F016 change control governance — this is a critical constraint to encode
- **Paradigms**: DOCS_ADJACENT; LIBRARY_FIRST for Python scripts
- **Review policy**: Claude Code as implementer; Codex as reviewer (per
  `.kittify/config.yaml`)

**Business rules:**
- The charter is the authoritative policy document — answers must reflect
  actual kg-automation conventions, not generic defaults
- The Tier 0 Hard Lock rule from F016 is the most important deployment
  constraint to capture in the charter
- Do not use `--defaults` — the interview must be answered for this project

**Success criteria:**
- [ ] `spec-kitty charter interview` run with comprehensive profile
- [ ] `.kittify/charter/interview/answers.yaml` produced
- [ ] `.kittify/charter/charter.md` draft produced
- [ ] Charter accurately reflects kg-automation policies

---

### FR-3: Generate Charter Config

**What it must do:**
- Run `spec-kitty charter generate` to derive machine-readable config from
  the charter
- Confirm `governance.yaml`, `directives.yaml`, and `library/*.md` are
  produced in `.kittify/charter/`
- Run `spec-kitty charter status` to confirm no drift

**Business rules:**
- Auto-generated files (`governance.yaml`, `directives.yaml`, `library/*.md`)
  must never be manually edited — only `charter.md` is human-edited
- If generate produces warnings, resolve them before committing

**Success criteria:**
- [ ] `spec-kitty charter generate` runs without errors
- [ ] `governance.yaml` and `directives.yaml` produced
- [ ] `library/*.md` produced
- [ ] `spec-kitty charter status` shows no drift

---

### FR-4: Verify Governance Injection at Workflow Steps

**What it must do:**
- Run `spec-kitty charter context --action implement` and
  `spec-kitty charter context --action review` to confirm governance
  context is being injected at workflow steps
- Confirm the Tier 0 Hard Lock constraint appears in the governance output
- Confirm the docs-adjacent and library-first paradigms appear

**Success criteria:**
- [ ] `charter context --action implement` produces governance output
- [ ] `charter context --action review` produces governance output
- [ ] Tier 0 deployment constraint appears in governance context
- [ ] Paradigm selections reflected in context output

---

### FR-5: Migrate or Archive Legacy .kittify/ Artifacts

**What it must do:**
- If any legacy 1.x constitution artifacts were found in FR-1, migrate or
  archive them per spec-kitty's upgrade documentation
- If none were found, document that confirmation

**Success criteria:**
- [ ] Legacy artifacts migrated or confirmed absent
- [ ] `.kittify/` contains no stale 1.x constitution artifacts

---

### FR-6: Update CLAUDE.md spec-kitty Governance Reference

**What it must do:**
- Add a reference to the spec-kitty charter in CLAUDE.md so Claude Code
  is aware of project governance during spec-kitty workflow sessions
- This is a new addition — CLAUDE.md currently has no spec-kitty
  workflow governance reference
- This is distinct from the Felix Constitution reference, which stays unchanged

**What to add:**
A brief note under the Feature Development Workflow section indicating that
`spec-kitty charter context` injects governance at each step, and that the
charter at `.kittify/charter/charter.md` is the authoritative workflow
policy document.

**Business rules:**
- Felix Constitution references in CLAUDE.md are NOT changed — they are
  about Felix agent governance, not spec-kitty workflow governance
- The new reference is additive only

**Success criteria:**
- [ ] CLAUDE.md references `.kittify/charter/charter.md` as spec-kitty
  workflow governance
- [ ] Existing Felix Constitution references unchanged
- [ ] No behavioral rules removed or weakened

---

## Architecture Documentation Updates

This feature adds spec-kitty charter files to `.kittify/`. No deployed
services, credentials, ports, or data flows are changed.

No JSON architecture updates required.

The only file update beyond the FRs above:

| File | Change |
|------|--------|
| `docs/INDEX.md` | Note that `.kittify/charter/` exists and its purpose (brief, not a full section) |

---

## Out of Scope

- ❌ Renaming `docs/constitution/FELIX-CONSTITUTION.md` — Felix Constitution
  is Felix agent governance, not spec-kitty workflow governance; it is unchanged
- ❌ Renaming "Constitutional Compliance" sections in func-specs — these reference
  Felix governance; the name is appropriate and unchanged
- ❌ Adopting other spec-kitty 2.x alpha features beyond the charter — one change
  at a time
- ❌ Adding a formal test suite — the charter captures current lightweight
  validation; a test suite is a future feature decision
- ❌ Changes to agent AGENTS.md files — those reference Felix Constitution
  (Felix governance), which is unaffected by this feature

---

## Success Criteria

**Complete when:**

### Charter Setup
- [ ] `spec-kitty charter interview` complete with comprehensive profile
- [ ] `charter.md` accurately reflects kg-automation policies
- [ ] `governance.yaml`, `directives.yaml`, `library/*.md` generated
- [ ] `spec-kitty charter status` shows no drift

### Governance Verification
- [ ] `charter context` produces output for implement and review actions
- [ ] Tier 0 Hard Lock constraint present in governance context
- [ ] Paradigm selections reflected

### Migration
- [ ] Legacy 1.x constitution artifacts migrated or confirmed absent

### Documentation
- [ ] CLAUDE.md updated with spec-kitty charter reference (additive)
- [ ] INDEX.md notes `.kittify/charter/` purpose

---

## Architecture Principles

### Two Governance Models, One System

kg-automation operates with two distinct governance layers:

1. **spec-kitty workflow governance** — enforced by the charter at
   `.kittify/charter/charter.md`. Governs HOW features are built:
   testing standards, quality gates, branching, deployment constraints.
   Injected automatically into spec-kitty agent prompts.

2. **Felix agent governance** — enforced by the Felix Constitution at
   `docs/constitution/FELIX-CONSTITUTION.md`. Governs HOW Felix agents
   behave: autonomy levels, privacy rules, scope boundaries, logging.

These are complementary, not competing. A feature in kg-automation is subject
to both: spec-kitty workflow governance (FR-quality gates, testing, review)
and Felix agent governance (if the feature deploys or modifies agents).

### Charter Is Auto-Generated Below Layer 1

The interview-generate-sync model means the human-editable surface is minimal:
only `charter.md` is ever manually edited. Everything derived from it is
regenerated via `spec-kitty charter sync`. This is the same principle as
the machine-readable-as-authoritative-record pattern already established
in this project for architecture JSON files.

---

## Risk Considerations

**Risk: Charter interview answers don't accurately capture kg-automation policy**
- If the Tier 0 Hard Lock or other critical constraints are not captured,
  spec-kitty agents won't enforce them at workflow steps.
- Mitigation: FR-4 verification step confirms key constraints appear in
  governance context output before the feature is accepted.

**Risk: spec-kitty alpha charter behavior changes before F020 runs**
- The alpha release may update charter behavior.
- Mitigation: Planning phase reads the setup-governance how-to at
  runtime rather than relying on this spec's description of the workflow.
  Spec describes WHAT to achieve; planning phase discovers HOW.

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Read `https://docs.spec-kitty.ai/how-to/setup-governance.html` for the
  full step-by-step walkthrough before running any charter commands
- Run `spec-kitty charter status` first to understand current state
- Run `ls -la .kittify/` to see if any legacy constitution artifacts exist
- The project characteristics section above provides the answers for the
  interview — use them to answer questions accurately, not with generic defaults

**Key constraint to encode in charter:**
The F016 Tier 0 Hard Lock rule is the most important deployment constraint
for this project. The charter interview has a deployment constraints question —
ensure this is captured explicitly.

---

**END OF SPECIFICATION**
