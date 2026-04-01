---
work_package_id: WP03
title: Skill-Authoring Skill
lane: planned
dependencies: []
requirement_refs:
- FR-015
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning branch is main. Final merge target is main. Actual base_branch may differ for stacked WPs during implement.
subtasks: [T011, T012]
history:
- date: '2026-04-01T22:12:34Z'
  event: created
  agent: claude
priority: P1
---

# WP03: Skill-Authoring Skill

## Implementation Command

```bash
spec-kitty implement WP03
```

No dependencies — this WP is independent and can run in parallel with WP02 and WP04.

## Objective

Create the skill-authoring skill at `scripts/openclaw/skills/skill-author/SKILL.md` that teaches any agent how to write OpenClaw skills conforming to project standards. The skill must be self-contained — an agent reading only this skill can produce a compliant new skill without additional guidance (NFR-004).

## Context

- **Spec**: FR-015 (skill content requirements)
- **Plan**: Skill-Authoring Skill section
- **Research**: Skill-Authoring Skill Content section (conventions, best practices, review criteria)

**Key design decisions:**
- Bootstrapped from existing Whisper and Vikunja API skills
- Augmented with external best practices
- Includes community skill review criteria
- Living document — version-stamped, updated when conventions change

## Subtask T011: Study Existing Skills

**Purpose**: Read the two canonical skills to extract format patterns, conventions, and the elements that make them effective.

**Files to read:**

| File | What to extract |
|------|----------------|
| `scripts/openclaw/skills/whisper/SKILL.md` | Simplest skill — clean format reference. Note: frontmatter fields, section structure, how operations are documented, error handling format |
| `scripts/openclaw/skills/vikunja-api/SKILL.md` | Most complete skill — credential access pattern, pre-flight validation, structured error handling, identity labels, comprehensive operation docs |

**Elements to catalog for the skill-authoring skill:**

1. **Frontmatter structure**: required fields (name, description, version), description format (trigger phrases, scope boundaries, "does NOT handle" list)
2. **Document body structure**: title → prerequisites → operations → error handling → examples
3. **Credential pattern**: `$(cat /data/services/openclaw/secrets/<name>)` in curl commands
4. **ID resolution pattern**: "NEVER hardcode — resolve by name at runtime"
5. **Error handling pattern**: categorized errors (transient vs. permanent), specific agent behavior per error type
6. **Pre-flight validation pattern**: check inputs before making external calls
7. **Health check pattern**: verify service availability before operations
8. **Identity label pattern**: every task gets personal/intentional/metalcasework
9. **Idempotency pattern**: check for duplicates before creating
10. **Comment prefix pattern**: `[Felix]` on all agent-created content
11. **Logging pattern**: skills provide structured outputs, agents log them

## Subtask T012: Write skill-author/SKILL.md

**Purpose**: Create the complete skill-authoring skill.

**File**: `scripts/openclaw/skills/skill-author/SKILL.md`

**Create directory**: `scripts/openclaw/skills/skill-author/`

**Frontmatter:**

```yaml
---
name: skill-author
description: >-
  Teaches agents how to write OpenClaw skills that conform to kg-automation
  project standards. Use when creating a new skill, reviewing a skill for
  quality, or evaluating a community skill from ClawHub for installation.
  Does NOT handle: agent standing orders (AGENTS.md), agent identity
  (IDENTITY.md), or runtime agent configuration.
version: 1.0.0
---
```

**Document body — required sections:**

### Section 1: What This Skill Is

A skill-authoring meta-skill. It encodes the format, conventions, and quality standards for OpenClaw skills in this project. An agent reading this document should be able to write a new SKILL.md from scratch that passes review.

### Section 2: Skill File Structure

Every OpenClaw skill is a directory containing a `SKILL.md` file:

```
scripts/openclaw/skills/<skill-name>/
└── SKILL.md
```

On office2 after deployment: `~/.openclaw/skills/<skill-name>/SKILL.md`

### Section 3: Required Frontmatter

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Lowercase, hyphenated identifier (e.g., `vikunja-api`) |
| description | string | yes | Multi-line: what the skill does, when to use it, trigger phrases, and what it does NOT handle |
| version | semver | yes | Semantic version (e.g., `1.0.0`) |

**Description best practices:**
- Include trigger phrases: "Use when...", "Use for..."
- Include anti-triggers: "Does NOT handle: ..."
- Keep under 5 lines — agents use this to decide whether to load the skill
- Be specific about scope boundaries

### Section 4: Document Body Structure

```
1. Title and purpose statement (1-2 sentences)
2. Prerequisites (API base URL, health check, authentication)
3. Operations (step-by-step, one section per operation)
4. Error handling (categorized: transient vs. permanent)
5. Examples (concrete workflows showing full operation sequence)
6. References (optional — links to supporting files)
```

### Section 5: Project Conventions (MUST follow)

**5.1 Credentials:**
- Always read from `/data/services/openclaw/secrets/<name>`
- Use `$(cat /path/to/secret)` in curl commands
- NEVER embed credentials in skill text, output, or logs
- NEVER log or print credential values

**5.2 ID Resolution:**
- NEVER hardcode project IDs, label IDs, or entity IDs
- Always resolve by name at runtime
- Document the name → ID resolution procedure in the skill

**5.3 Error Handling:**
- Every operation must document success AND failure paths
- Categorize errors: transient (retry candidate) vs. permanent (surface immediately)
- For each HTTP error code: document specific agent behavior
- Pre-flight validation: reject bad inputs BEFORE making external calls
- NEVER fail silently — every failure produces observable output
- NEVER invent data — if required info is missing, halt and report
- Follow the halt-on-ambiguity pattern: if uncertain, stop and ask rather than guess

**5.4 Health Check:**
- Every skill that calls an external service must include a health check step
- Run health check before any operations
- If health check fails: report service down, do not attempt operations

**5.5 Identity Labels:**
- Every Vikunja task created by an agent MUST have an identity label
- Labels: `personal`, `intentional`, `metalcasework`
- Infer from context; if ambiguous, default to `personal`

**5.6 Logging:**
- Skills provide structured outputs that calling agents can log
- Every significant action should produce output the agent can include in its processing log
- Include enough detail for the centralized intelligence layer to categorize actions

**5.7 Idempotency:**
- Before creating an entity, check if it already exists
- Before adding a comment, check for an existing comment with the same prefix and date
- Document the idempotency check procedure in the skill

**5.8 Agent Comment Prefix:**
- All agent-created comments use the prefix `[Felix]`
- Format: `[Felix] YYYY-MM-DD | {state} | optional note`

### Section 6: Narrow Scope Guidance

- One skill = one responsibility
- A skill that transcribes audio should not also process the transcript
- A skill that manages tasks should not decide which tasks to create
- If a skill starts doing two things, split it into two skills
- State the scope boundary explicitly in the description frontmatter

### Section 7: Community Skill Review Criteria

When evaluating a community skill from ClawHub for installation:

**Security:**
- [ ] Does it read/write/transmit credentials? How?
- [ ] Does it execute arbitrary shell commands from external input?
- [ ] Does it access paths outside its stated scope?
- [ ] Does it communicate with external services? Which ones? Over what protocol?
- [ ] Does it respect the Tailscale-only constraint?

**Quality:**
- [ ] Valid frontmatter (name, description, version)?
- [ ] Description includes scope boundaries ("does NOT handle")?
- [ ] All error paths documented with specific agent behavior?
- [ ] Pre-flight input validation present?
- [ ] Health check before operations?
- [ ] Examples showing complete workflows?

**Compatibility:**
- [ ] Required binaries/services available on office2?
- [ ] Conflicts with existing skills (overlapping scope)?
- [ ] Uses credential store pattern?
- [ ] Compatible with identity label system?

**Scope:**
- [ ] One clear responsibility?
- [ ] Explicit "does not handle" list?
- [ ] Narrow enough for clear agent decision-making?

> **Constitutional requirement**: Community skills from ClawHub require Kent's explicit approval before installation. Present the full SKILL.md and all supporting files for review. Never self-approve a community skill installation regardless of autonomy level. This constraint does not expire.

### Section 8: Pattern References

Point the agent to the two canonical examples:

- **Format reference**: `scripts/openclaw/skills/whisper/SKILL.md` — simplest skill, clean structure. Good starting point for new skills.
- **Comprehensive reference**: `scripts/openclaw/skills/vikunja-api/SKILL.md` — most complete skill. Covers credential access, pre-flight validation, structured error handling, identity labels, and comprehensive operations documentation.

Include a note: "Read both reference skills before writing a new skill. The Whisper skill shows the minimum viable structure. The Vikunja API skill shows the full pattern."

### Section 9: Version and Maintenance

- This skill is version-stamped
- Updated when project conventions change
- Any feature that modifies project conventions must update this skill in the same commit
- If this skill's guidance conflicts with the constitution, the constitution wins

**Validation (NFR-004 self-containment test):**
- [ ] An agent reading ONLY this SKILL.md could write a valid new skill
- [ ] No external documents referenced as "required reading" (except the two pattern examples)
- [ ] All conventions explicitly stated (not implied)
- [ ] Review criteria are actionable checklists, not vague guidelines

## Definition of Done

- [ ] `scripts/openclaw/skills/skill-author/SKILL.md` exists with valid frontmatter
- [ ] All 9 sections present and complete
- [ ] Project conventions section covers all 8 conventions (credentials, IDs, errors, health check, labels, logging, idempotency, comment prefix)
- [ ] Community skill review criteria is an actionable checklist
- [ ] Pattern references point to correct existing skill paths
- [ ] ClawHub constraint exact wording included
- [ ] Self-containment test passes (NFR-004)
- [ ] File committed to target branch

## Risks

| Risk | Mitigation |
|------|-----------|
| Skill becomes stale as conventions evolve | Version-stamped. Constitution mandates updates with convention changes. |
| Too verbose for agent context | Keep under 300 lines. Concise but complete. |
| Pattern references point to moved/renamed skills | Verify paths exist before committing. |

## Reviewer Guidance

- **Self-containment test (NFR-004)**: Could an agent reading ONLY this SKILL.md write a compliant skill? If not, what's missing?
- Verify all 8 project conventions are explicitly stated with actionable guidance
- Verify review criteria checklists are yes/no checkable (not subjective)
- Verify ClawHub constraint wording matches the spec exactly
- Verify pattern reference paths are correct and files exist
- Check that the skill follows its own conventions (valid frontmatter, scope boundaries in description, version-stamped)
