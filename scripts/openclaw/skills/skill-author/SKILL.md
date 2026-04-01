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

# Skill-Authoring Skill

This is a meta-skill. It encodes the format, conventions, and quality standards for OpenClaw skills in this project. An agent reading this document can write a new SKILL.md from scratch that passes review without additional guidance.

## 1. What This Skill Is

A skill-authoring reference that defines how to create OpenClaw skills conforming to kg-automation project standards. Use this skill when:

- Writing a new skill from scratch
- Reviewing an existing skill for compliance
- Evaluating a community skill from ClawHub before recommending installation

This skill does NOT cover agent standing orders, agent identity configuration, or runtime orchestration. Those are governed by AGENTS.md and IDENTITY.md respectively.

## 2. Skill File Structure

Every OpenClaw skill is a directory containing a `SKILL.md` file:

```
scripts/openclaw/skills/<skill-name>/
└── SKILL.md
```

On office2 after deployment: `~/.openclaw/skills/<skill-name>/SKILL.md`

The directory name must match the `name` field in the SKILL.md frontmatter. Use lowercase with hyphens as separators (e.g., `vikunja-api`, `whisper`, `skill-author`).

## 3. Required Frontmatter

Every SKILL.md begins with YAML frontmatter containing these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Lowercase, hyphenated identifier matching the directory name (e.g., `vikunja-api`) |
| description | string | yes | Multi-line: what the skill does, when to use it, trigger phrases, and what it does NOT handle |
| version | semver | yes | Semantic version (e.g., `1.0.0`) |

**Description best practices:**

- Include trigger phrases: "Use when...", "Use for..."
- Include anti-triggers: "Does NOT handle: ..."
- Keep under 5 lines — agents use this to decide whether to load the skill
- Be specific about scope boundaries so agents can make clear load/skip decisions

**Example frontmatter:**

```yaml
---
name: my-skill
description: >-
  Does X using Y service. Use when an agent needs to perform X.
  Use for Z-related operations. Does NOT handle: A, B, or C.
version: 1.0.0
---
```

## 4. Document Body Structure

After the frontmatter, the document body follows this structure:

```
1. Title and purpose statement (1-2 sentences)
2. Prerequisites (API base URL, health check, authentication)
3. Operations (step-by-step, one section per operation)
4. Error handling (categorized: transient vs. permanent)
5. Examples (concrete workflows showing full operation sequence)
6. References (optional — links to supporting files)
```

**Title**: Use a heading matching the skill name in human-readable form (e.g., "Vikunja API Skill", "Whisper Transcription Skill").

**Prerequisites**: Document everything an agent needs before calling the first operation — service URL, health check command, authentication mechanism. An agent should be able to verify the service is available before attempting any operation.

**Operations**: One section per operation. Each operation section includes the exact command (typically curl via the exec tool), the expected response format, and what to do with the response. Use concrete code blocks — not pseudocode.

**Error handling**: A dedicated section documenting every failure mode. See Section 5.3 for the required error handling conventions.

**Examples**: End-to-end workflows showing how operations chain together. At minimum, include one example that exercises the most common use case.

## 5. Project Conventions

Every skill in this project MUST follow these conventions. Violating any of them is a review failure.

### 5.1 Credentials

- Always read credentials from `/data/services/openclaw/secrets/<name>`
- Use `$(cat /data/services/openclaw/secrets/<name>)` inline in curl commands
- NEVER embed credentials in skill text, output, or logs
- NEVER log or print credential values
- If a credential read fails, report a credential error and halt — do not fall back to alternative authentication

### 5.2 ID Resolution

- NEVER hardcode project IDs, label IDs, or entity IDs
- Always resolve by name at runtime (e.g., list all projects, find the one where `title` matches)
- Document the name-to-ID resolution procedure in the skill
- IDs can change if services are re-provisioned — name resolution ensures the skill survives reprovisioning

### 5.3 Error Handling

- Every operation must document both success AND failure paths
- Categorize errors: **transient** (retry candidate — e.g., 500, network timeout) vs. **permanent** (surface immediately — e.g., 401, 404)
- For each HTTP error code the skill's service can return: document specific agent behavior
- **Pre-flight validation**: reject bad inputs BEFORE making external calls
- NEVER fail silently — every failure produces observable output to the caller
- NEVER invent data — if required information is missing, halt and report
- Follow the **halt-on-ambiguity** pattern: if the input is uncertain or incomplete, stop and ask the caller rather than guessing

### 5.4 Health Check

- Every skill that calls an external service must include a health check step
- Run the health check before any operations
- If the health check fails: report the service as down and do not attempt further operations
- Document the exact health check command and expected response

### 5.5 Identity Labels

- Every Vikunja task created by an agent MUST have an identity label
- Labels: `personal`, `intentional`, `metalcasework`
- Infer from context; if ambiguous, default to `personal`
- Skills that create Vikunja tasks must document the label assignment step

### 5.6 Logging

- Skills provide structured outputs that calling agents can log
- Every significant action should produce output the agent can include in its processing log
- Include enough detail for the centralized intelligence layer to categorize actions
- Format outputs consistently so downstream processing can parse them

### 5.7 Idempotency

- Before creating an entity, check if it already exists (e.g., search by title before creating a task)
- Before adding a comment, check for an existing comment with the same prefix and date
- Document the idempotency check procedure in the skill
- If a duplicate is found, return the existing entity instead of creating a new one

### 5.8 Agent Comment Prefix

- All agent-created comments use the prefix `[Felix]`
- Format: `[Felix] YYYY-MM-DD | {state} | optional note`
- This prefix distinguishes agent comments from human comments and enables filtering

## 6. Narrow Scope Guidance

- One skill = one responsibility
- A skill that transcribes audio should not also process the transcript
- A skill that manages tasks should not decide which tasks to create
- If a skill starts doing two things, split it into two skills
- State the scope boundary explicitly in the description frontmatter using the "Does NOT handle" pattern
- When in doubt, make the skill smaller rather than larger — agents can compose multiple skills

## 7. Community Skill Review Criteria

When evaluating a community skill from ClawHub for installation, use these checklists. Every item must be verified — do not skip items or assume compliance.

### Security

- [ ] Does it read/write/transmit credentials? How?
- [ ] Does it execute arbitrary shell commands from external input?
- [ ] Does it access paths outside its stated scope?
- [ ] Does it communicate with external services? Which ones? Over what protocol?
- [ ] Does it respect the Tailscale-only constraint?

### Quality

- [ ] Valid frontmatter (name, description, version)?
- [ ] Description includes scope boundaries ("does NOT handle")?
- [ ] All error paths documented with specific agent behavior?
- [ ] Pre-flight input validation present?
- [ ] Health check before operations?
- [ ] Examples showing complete workflows?

### Compatibility

- [ ] Required binaries/services available on office2?
- [ ] Conflicts with existing skills (overlapping scope)?
- [ ] Uses credential store pattern?
- [ ] Compatible with identity label system?

### Scope

- [ ] One clear responsibility?
- [ ] Explicit "does not handle" list?
- [ ] Narrow enough for clear agent decision-making?

> **Constitutional requirement**: Community skills from ClawHub require Kent's explicit approval before installation. Present the full SKILL.md and any supporting files for review. Never self-approve a community skill installation regardless of autonomy level. This constraint does not expire and applies even at Autonomous (Level 3).

## 8. Pattern References

Two canonical skills exist in this project. Read both before writing a new skill:

- **Format reference**: `scripts/openclaw/skills/whisper/SKILL.md` — the simplest skill with a clean structure. Good starting point for new skills. Shows the minimum viable skill: frontmatter, health check, operations, error handling, and examples.
- **Comprehensive reference**: `scripts/openclaw/skills/vikunja-api/SKILL.md` — the most complete skill. Covers credential access, pre-flight validation, structured error handling, identity labels, idempotency checks, and comprehensive operations documentation.

Read both reference skills before writing a new skill. The Whisper skill shows the minimum viable structure. The Vikunja API skill shows the full pattern.

## 9. Version and Maintenance

- This skill is version-stamped (see frontmatter)
- Updated when project conventions change
- Any feature that modifies project conventions must update this skill in the same commit
- If this skill's guidance conflicts with the constitution, the constitution wins
- Increment the patch version for convention clarifications, minor version for new conventions, major version for structural changes

**Self-containment validation (NFR-004):**

- [ ] An agent reading ONLY this SKILL.md could write a valid new skill
- [ ] No external documents referenced as "required reading" (except the two pattern examples in Section 8)
- [ ] All conventions explicitly stated (not implied)
- [ ] Review criteria are actionable checklists, not vague guidelines
