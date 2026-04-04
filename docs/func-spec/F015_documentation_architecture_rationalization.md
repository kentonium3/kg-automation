---
title: "F015: Documentation Architecture Rationalization"
doc_type: func-spec
status: draft
---

# F015: Documentation Architecture Rationalization

**Version**: 1.1
**Priority**: HIGH
**Type**: Documentation & Governance
**Recommended Mission Type**: `documentation` (gap-fill iteration mode)

---

## Executive Summary

The kg-automation repository has accumulated documentation across multiple directories
that grew organically without a unifying structure. Many documents are unreferenced from
CLAUDE.md or the Felix constitution, making them undiscoverable by agents and difficult
to maintain. The machine-readable artifact home is split and underdocumented. The
distinction between runbooks (prescriptive, action-oriented) and reference/explanation
docs is not enforced, making it unclear what an agent should execute vs. read for context.

Current gaps:
- ❌ No chain of reference from CLAUDE.md to most documents — many docs are invisible to agents
- ❌ Directory structure grew organically — unclear purpose boundaries across dirs
- ❌ `handbooks/` mixes runbooks, reference, and explanation content without type discipline
- ❌ Machine-readable artifact home undocumented — `systems/` partially redundant with `docs/design/architecture/data/`
- ❌ No Divio classification — docs cannot be validated for completeness or type correctness
- ❌ `docs/docs-readme.md` is stale (2025) and references non-existent diagram files
- ❌ F016 has unresolved path dependencies on governance/ and postmortems/ homes

This spec covers documentation quality work: Divio classification, gap analysis,
frontmatter correction, INDEX.md creation, and chain-of-reference repair.

**Prerequisites (Claude Code out-of-cycle task, completed before this spec runs):**
Physical directory restructuring — renaming `handbooks/` to `runbooks/`, moving
`research/` under `docs/design/`, creating `runbooks/governance/` and `postmortems/`,
archiving orphaned directories, migrating `workflows/` content, and deprecating `systems/`
— executed by Claude Code directly. This spec assumes that structure is already in place.

---

## Problem Statement

**Current State (INCOMPLETE):**
```
docs/
├─ ❌ docs-readme.md — stale index, references missing diagram files
├─ ✅ constitution/ — Felix constitution, agent registry — good, underlinked
├─ ✅ design/ — architecture, standards, vision — cleanest area
│   ├─ ✅ architecture/ — current-state docs + data/ JSON — authoritative
│   └─ ✅ standards/ — doc standards
├─ ✅ func-spec/ — spec-kitty specs — unchanged
├─ ⚠️  runbooks/ — content moved from handbooks/, not yet classified
├─ ✅ diagnostics/ — actively used — unchanged
└─ ❌ No master index — agents cannot discover most documentation

CLAUDE.md
└─ ❌ references runbooks/ but not constitution/, standards/, INDEX.md
```

**Target State (COMPLETE — this spec's deliverables):**
```
docs/
├─ INDEX.md — master map, referenced from CLAUDE.md
├─ constitution/ — linked from CLAUDE.md
├─ design/
│   ├─ architecture/ — unchanged
│   ├─ standards/ — unchanged
│   └─ research/ — moved pre-spec
├─ func-spec/ — unchanged
├─ runbooks/ — all files classified, correct doc_type frontmatter
│   ├─ governance/ — ready for F016 files
│   └─ [misclassified content moved to design/ or constitution/]
├─ postmortems/ — created pre-spec, ready for F016 first entry
└─ diagnostics/ — unchanged

CLAUDE.md — references INDEX.md and constitution/
docs/design/architecture/data/ — machine-readable home documented
```

---

## CRITICAL: Study These Files FIRST

**Before implementation, spec-kitty planning phase MUST read and understand:**

1. **Current CLAUDE.md**
   - Find `CLAUDE.md` in repo root
   - Note every document and directory currently referenced
   - All references must remain valid — no broken links

2. **Architecture README and change-control**
   - Find `docs/design/architecture/README.md`
   - Find `docs/design/architecture/change-control.md`
   - Note that `docs/design/architecture/data/` path must not change

3. **Felix Constitution**
   - Find `docs/constitution/FELIX-CONSTITUTION.md`
   - Understand existing governance principles
   - Note where documentation standards principle (from F016) belongs here

4. **All files in docs/runbooks/**
   - Classify each against Divio types: how-to guide, reference, explanation
   - This classification drives frontmatter corrections and any content moves

5. **docs/docs-readme.md**
   - Understand its intent — becomes the basis for `docs/INDEX.md`
   - Identify all stale references to be corrected

6. **Spec-kitty documentation mission**
   - Understand the gap-fill iteration mode
   - Understand how Divio types map to this system's internal audience

7. **F016 spec**
   - Find `docs/func-spec/F016_change_control_governance.md`
   - Note all path dependencies (governance/, postmortems/) — this feature resolves them

---

## Functional Requirements

### FR-1: Divio Classification of Existing Documentation

**What it must do:**
- Classify every active document in `docs/` against the Divio 4-type system
- For this system's internal audience, the four types map as follows:
  - **How-to guides**: Prescriptive step-by-step runbooks — executable by humans or agents
  - **Reference**: Describes the system machinery — architecture docs, service context, CLAUDE.md
  - **Explanation**: Why things work the way they do — constitution, design principles, ADRs
  - **Tutorials**: Guided learning — absent by design for a solo operator system
- Produce a gap analysis identifying: missing docs by type, misclassified docs, duplicate coverage

**Business rules:**
- A document that mixes types: dominant type wins, ambiguity noted in frontmatter
- `docs/diagnostics/` is actively used — exempt from any archival
- Classification results drive all subsequent FR decisions in this spec

**Success criteria:**
- [ ] Every active document classified by Divio type
- [ ] Gap analysis produced identifying missing coverage by type
- [ ] Misclassified or out-of-place documents identified

---

### FR-2: Machine-Readable Artifact Home Documented

**What it must do:**
- Establish `docs/design/architecture/data/` as the canonical home for all
  current-state operational JSON (service inventory, network topology, credentials, etc.)
- Document that schemas describing those files co-locate in the same directory
- Update the architecture README to state this explicitly
- Update CLAUDE.md to reference the machine-readable artifact home

**Business rules:**
- No files in `docs/design/architecture/data/` are moved — this is policy documentation only
- Future features creating new machine-readable artifacts must follow this convention

**Success criteria:**
- [ ] Architecture README states `docs/design/architecture/data/` as canonical home
- [ ] Schema files co-located with or clearly linked from the data they describe
- [ ] CLAUDE.md references the machine-readable artifact home
- [ ] Convention documented in `docs/INDEX.md`

---

### FR-3: Runbook vs. Reference Distinction Enforced

**What it must do:**
- Within `docs/runbooks/`, enforce the distinction between runbook content
  (how-to, prescriptive, action-oriented) and reference/explanation content
- Runbooks must be structured as step-by-step procedures executable by a human or agent
- Reference/explanation content belonging in `docs/design/architecture/` or the Felix
  constitution must be moved there
- Each runbook must declare its audience in frontmatter: human-only, agent-executable, or both
- The `doc_type` frontmatter value `handbook` replaced with `runbook`, `reference`,
  or `explanation` to match Divio classification

**Business rules:**
- Content is moved, never deleted
- Agent-executable runbooks flagged for future skill conversion (out of scope here)
- `vikunja-ops.md` title already says "Runbook" — its `doc_type` must be corrected to `runbook`

**Success criteria:**
- [ ] All files in `docs/runbooks/` have correct `doc_type` frontmatter
- [ ] All runbooks structured as executable step-by-step procedures
- [ ] Misclassified content moved to appropriate locations
- [ ] Agent-executable runbooks flagged in frontmatter

---

### FR-4: Master Index and Chain of Reference

**What it must do:**
- Create `docs/INDEX.md` as the master documentation map
- INDEX.md lists every active directory, its purpose, Divio types it contains,
  and key documents within it — both markdown and machine-readable files
- INDEX.md explicitly referenced from CLAUDE.md as the documentation map
- Felix constitution explicitly referenced from CLAUDE.md
- INDEX.md maintenance added to the change-control protocol

**Business rules:**
- INDEX.md replaces `docs/docs-readme.md` — old file archived
- INDEX.md references machine-readable data files alongside their markdown companions
- Adding a new document or directory without updating INDEX.md is a protocol violation

**Success criteria:**
- [ ] `docs/INDEX.md` created, covering all active directories and key documents
- [ ] CLAUDE.md updated to reference INDEX.md and `docs/constitution/`
- [ ] `docs/docs-readme.md` archived
- [ ] Change-control protocol updated to require INDEX.md updates on every feature
- [ ] Every active document reachable via chain starting from CLAUDE.md or Felix constitution

---

### FR-5: F016 Path Dependencies Resolved

**What it must do:**
- Confirm and document the resolved paths for all files F016 needs to create:
  - Governance files → `docs/runbooks/governance/`
  - Postmortems → `docs/postmortems/`
  - Change risk taxonomy → `docs/design/architecture/data/`
- Update F016 spec with resolved paths, removing all TBD notations

**Success criteria:**
- [ ] F016 spec updated with all resolved paths
- [ ] F016 ready to proceed to spec-kitty after F015 acceptance

---

## Architecture Documentation Updates

This feature does not change deployed services, credentials, or network topology.
Architecture JSON files are not modified.

### Markdown Updates Required

| File | Change |
|---|---|
| `CLAUDE.md` | Add references to `docs/INDEX.md` and `docs/constitution/`; update any `handbooks/` references to `runbooks/` |
| `docs/design/architecture/README.md` | Add machine-readable artifact home statement |
| `docs/design/architecture/change-control.md` | Add INDEX.md update to the protocol |
| All files with links to moved documents | Update references to new paths |

### New Files Required

| File | Purpose |
|---|---|
| `docs/INDEX.md` | Master documentation map — replaces stale docs-readme.md |

### No JSON Updates Required

No machine-readable data files are created or modified by this feature.

---

## Out of Scope

- ❌ Writing new documentation to fill Divio gaps — gap analysis identifies; filling is future work
- ❌ Converting runbooks to agent skills — flagging only
- ❌ F016 implementation — this feature unblocks F016's paths; F016 runs after F015 acceptance
- ❌ Automated doc validation or CI link checking — separate feature
- ❌ Any changes to `docs/design/architecture/data/` content

---

## Success Criteria

### Classification
- [ ] Every active document has correct `doc_type` frontmatter
- [ ] Gap analysis produced
- [ ] Agent-executable runbooks flagged

### Machine-Readable Home
- [ ] Architecture README and CLAUDE.md state canonical data home

### Chain of Reference
- [ ] `docs/INDEX.md` created and complete
- [ ] CLAUDE.md references INDEX.md and constitution/
- [ ] Change-control protocol updated
- [ ] No broken references in repo

### F016 Unblocked
- [ ] F016 spec updated with resolved paths

### Quality
- [ ] `docs/design/architecture/data/` path unchanged
- [ ] `docs/diagnostics/` unchanged
- [ ] All content moves accompanied by reference updates

---

## Architecture Principles

### Divio for Internal Documentation
- Tutorials absent by design for solo operator system
- How-to guides = runbooks (prescriptive, executable)
- Reference = architecture docs, CLAUDE.md, service inventory narrative views
- Explanation = constitution, design principles, ADRs, postmortems

### Runbooks as Proto-Skills
- A well-structured runbook can be converted to an agent skill
- Audience declaration (human-only vs agent-executable) creates the conversion pipeline

### Single Canonical Home Per Artifact Type
- All operational JSON → `docs/design/architecture/data/`
- All runbooks → `docs/runbooks/`
- All design/research → `docs/design/`
- All governance → `docs/runbooks/governance/`
- All postmortems → `docs/postmortems/`

---

## Constitutional Compliance

✅ **Document-first / GitOps pattern** — INDEX.md adds discoverability without changing version-control model

✅ **System documentation comprehensive and current** — comprehensive requires discoverability

✅ **Machine-readable as authoritative record** — FR-2 formalizes this existing principle

---

## Risk Considerations

**Risk: Reference breaks after handbooks/ rename**
- All inbound references to `docs/runbooks/` must be updated; planning phase audits first

**Risk: Divio classification is subjective on borderline docs**
- Use dominant type; note ambiguity in frontmatter; do not over-engineer

**Risk: INDEX.md becomes stale immediately**
- Mitigation: Change-control protocol update (FR-4) makes INDEX.md maintenance mandatory

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Audit all `docs/runbooks/` or `docs/runbooks/` references in CLAUDE.md, func-spec/, ai-agents/
- Study `docs/design/architecture/change-control.md` before modifying it
- Study Felix constitution for tone and structure before adding documentation standards principle

**Focus Areas:**
- INDEX.md quality is the primary deliverable — it determines whether chain-of-reference is solved
- FR-5 (F016 path resolution) is a hard dependency for the next feature in sequence

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-04 | Initial draft as F016 |
| 1.1 | 2026-04-04 | Renumbered F015; physical file moves split to Claude Code prereq task; FR sections cleaned up and renumbered |

---

**END OF SPECIFICATION**
