---
work_package_id: WP01
title: Task Intelligence Skill
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-007
- FR-008
- FR-009
- FR-021
- FR-022
- FR-026
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Planning branch: main. Merge target: main. No dependencies — branch from main.'
subtasks: [T001, T002, T003, T004, T005, T006]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/skills/task-intelligence/
execution_mode: code_change
owned_files: [scripts/openclaw/skills/task-intelligence/**]
---

# WP01: Task Intelligence Skill

## Objective

Create the self-contained task-intelligence SKILL.md at `scripts/openclaw/skills/task-intelligence/SKILL.md`. This skill document encodes all task structuring logic, inference rules, confidence thresholds, project placement mapping, goal relationship procedures, repeat interval patterns, and error handling. It is the knowledge base that felix-admin-tasker reads to structure any task without additional guidance.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent
- **Spec**: `kitty-specs/013-vikunja-task-intelligence-agent/spec.md`
- **Plan**: `kitty-specs/013-vikunja-task-intelligence-agent/plan.md`
- **Research**: `kitty-specs/013-vikunja-task-intelligence-agent/research.md`
- **Data model**: `kitty-specs/013-vikunja-task-intelligence-agent/data-model.md`
- **Vikunja API contract**: `kitty-specs/013-vikunja-task-intelligence-agent/contracts/vikunja-task-enrichment-contract.md`

### Reference skill

Read `scripts/openclaw/skills/vikunja-api/SKILL.md` for the established skill document format. The task-intelligence skill should follow the same structural conventions (sections, formatting, tone) while being self-contained.

### Implementation command

```bash
spec-kitty implement WP01
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: None — this is the first WP
- **Actual base branch**: May differ if stacked; follow `spec-kitty implement` output

---

## Subtask T001: Create SKILL.md Structure with Attribute Tables

**Purpose**: Establish the SKILL.md file with proper header, purpose statement, and the required/optional attribute tables that define what a fully structured task looks like.

**Steps**:
1. Create directory `scripts/openclaw/skills/task-intelligence/`
2. Create `SKILL.md` with header following vikunja-api skill format:
   - Skill name: `task-intelligence`
   - Purpose: "Encode the rules for transforming raw task descriptions into fully structured Vikunja tasks"
   - Scope: What this skill covers and does NOT cover
3. Add **Required Attributes** table:

   | Attribute | Question | Can Infer? | Fallback |
   |---|---|---|---|
   | Title | What is the task? | Yes — from raw description | Clarify if ambiguous |
   | Identity label | Which identity? (personal/intentional/metalcasework) | Usually yes | Ask if ambiguous |
   | Project | Where does this belong? | Often yes | Ask |
   | Due date | When must this be done? | Sometimes (explicit dates) | Ask |
   | Priority | How important/urgent? | Sometimes (signal words) | Default to medium (2) |

4. Add **Optional Attributes** table:

   | Attribute | Question | When to Include |
   |---|---|---|
   | Start date | When should work begin? | Only if lead time or dependencies |
   | Repeating interval | Does this recur? | Only if task sounds recurring |
   | Goal relationship | Does this serve a declared goal? | Check against active goals |
   | Subtask/parent | Is this part of a larger task? | If task sounds like a component |
   | Blocking/blocked | Does anything depend on this? | If clear dependencies exist |

**Validation**:
- [ ] SKILL.md created at correct path
- [ ] Both attribute tables present with all fields
- [ ] Header matches vikunja-api skill format conventions

---

## Subtask T002: Define Confidence Threshold Model and Inference Rules

**Purpose**: Encode the rules for when the agent infers an attribute vs. asks Kent. This is the core intelligence model.

**Steps**:
1. Add a **Confidence Threshold** section:
   - Default threshold: ≥90% confidence = infer and include in proposal
   - Below 90% = ask Kent via primary interaction channel
   - Threshold is configurable — state that changing the threshold value here changes agent behavior without code changes

2. Add **Inference Rules by Attribute**:
   - **Title**: Always infer from raw text. Clarify only if raw text is genuinely ambiguous (multiple possible tasks in one description).
   - **Due date**: High confidence if explicit date/time in text ("next Friday", "April 15th", "by end of month"). Low confidence if no date reference — must ask.
   - **Priority**: High confidence if signal words present ("urgent", "ASAP", "important", "low priority", "whenever"). Default to medium (2) if no signal. Only ask if conflicting signals.
   - **Identity label**: Follow identity label inference rules (T003). High confidence for clear business/consulting/metalcasework context. Default to personal.

3. Add **When to Ask vs. Infer** decision tree:
   ```
   For each attribute:
     1. Extract signals from raw text and context
     2. Apply inference rules
     3. If confidence ≥ threshold → include in proposal
     4. If confidence < threshold → add to clarification questions
     5. If all required attributes above threshold → single confirmation message
     6. If any below → ask clarification first, then propose
   ```

**Validation**:
- [ ] Confidence threshold clearly stated and marked as configurable
- [ ] Each attribute has explicit inference rules
- [ ] Decision tree is unambiguous

---

## Subtask T003: Define Project Placement Mapping and Identity Label Inference

**Purpose**: Encode the mapping from task content/identity to Vikunja projects, and the rules for inferring identity labels.

**Steps**:
1. Add **Project Placement Mapping** section:

   | Content Signal | Identity | Target Project |
   |---|---|---|
   | Consulting, client work, marketing, thought leadership, revenue | intentional | Intentional LLC |
   | Business acquisition, CT course | personal | Business Acquisition |
   | Health, fitness, PT, medical, physical therapy | personal | Health & Conditioning |
   | Personal growth, habits, mindset, learning | personal | Personal Growth |
   | Metal casework, fabrication, ecommerce research | metalcasework | Metal Casework |
   | Ambiguous / no clear signal | — | Ask Kent; default to Inbox |

   **Rule**: Always resolve project by name at runtime via `GET /projects`. Never hardcode project IDs.

2. Add **Identity Label Inference Rules**:

   | Signal Words | Label |
   |---|---|
   | business, consulting, client, Intentional LLC, marketing, thought leadership, revenue, sales, invoice | intentional |
   | metal casework, fabrication, ecommerce research, metalbox | metalcasework |
   | Everything else (default when ambiguous) | personal |

   **Rule**: Always resolve label by name at runtime via `GET /labels`. Never hardcode label IDs. Identity labels: personal (id resolved at runtime), intentional (id resolved at runtime), metalcasework (id resolved at runtime).

3. Add **Ambiguity Handling**:
   - If content maps to multiple projects: ask Kent
   - If identity label is ambiguous: ask Kent
   - If task spans multiple projects: place in primary, add comment referencing secondary

**Validation**:
- [ ] All current Vikunja projects have mapping entries
- [ ] Runtime resolution rule stated (never hardcode IDs)
- [ ] Ambiguity handling covers edge cases

---

## Subtask T004: Define Goal Relationship Check Procedure

**Purpose**: Encode the procedure for checking active goals and proposing task-goal relationships.

**Steps**:
1. Add **Goal Relationship Check** section:
   - Before structuring any task, query the Goals project (resolve by name, not hardcoded ID)
   - Fetch all non-done tasks in Goals project: `GET /projects/{GOALS_PROJECT_ID}/tasks?filter=done%20%3D%20false`
   - For each goal, compare task content against goal title and description
   - If plausible relationship: include in proposal with proposed relation kind

2. Define **Relation Kind Selection**:
   - Task clearly contributes to a goal → `related` (default, low-commitment)
   - Task is an explicit step toward a goal → `subtask` of the goal
   - Only propose `subtask` when relationship is strong and specific
   - Never propose `blocking` or `precedes` for goal relationships

3. Define **Goal Relationship Proposal Format**:
   ```
   Related goal: "Goal title here"
   Proposed link: related (this task supports the goal)
   ```

4. Define **When NOT to Propose**:
   - If no goal has clear relevance — omit silently (do not ask)
   - If relationship is tenuous — omit (avoid false positives)
   - Never propose more than one goal relationship per task

5. Add **API Pattern for Creating Goal Relations**:
   ```
   PUT /tasks/{NEW_TASK_ID}/relations
   {"other_task_id": <GOAL_TASK_ID>, "relation_kind": "related"}
   ```

**Validation**:
- [ ] Goal query procedure is explicit
- [ ] Relation kind selection rules are clear
- [ ] False-positive prevention rules documented
- [ ] API pattern correct per research.md findings

---

## Subtask T005: Define Repeat Interval Conversion Table and API Patterns

**Purpose**: Encode how to translate Kent's natural language repeat requests into Vikunja's seconds-based repeat_after field.

**Steps**:
1. Add **Repeat Interval** section with conversion table:

   | Human Expression | repeat_after (seconds) | repeat_mode |
   |---|---|---|
   | "daily", "every day" | 86400 | 0 |
   | "every other day", "every 2 days" | 172800 | 0 |
   | "weekly", "every week" | 604800 | 0 |
   | "bi-weekly", "every 2 weeks", "fortnightly" | 1209600 | 0 |
   | "monthly", "every month" | 0 | 1 |
   | "quarterly", "every 3 months" | 7776000 | 0 |
   | "every 6 months", "twice a year" | 15552000 | 0 |
   | "yearly", "annually", "every year" | 31536000 | 0 |
   | "every N days" | N × 86400 | 0 |
   | "N days after completion" | N × 86400 | 2 |

2. Add **repeat_mode explanation**:
   - `0` (Default): Adds interval to existing dates. Skips past missed intervals.
   - `1` (Month): Adds one calendar month. Ignores repeat_after value.
   - `2` (FromCurrentDate): Adds interval to current time, not old date.

3. Add **CRITICAL API CAVEAT** (from research.md):
   > When marking a repeating task as done via the API, always include `repeat_after` and `repeat_mode` in the payload. Go's zero-value semantics can clear these fields to 0 if omitted.

4. Add **Repeat Detection Rules**:
   - High confidence: explicit repeat language ("every", "recurring", "repeating", "weekly")
   - Low confidence: implied repetition ("oil change" might be recurring but not stated)
   - If unsure: ask Kent "Is this a repeating task?"

**Validation**:
- [ ] Conversion table covers common intervals
- [ ] repeat_mode values documented correctly
- [ ] API caveat prominently stated
- [ ] Detection rules distinguish explicit from implied

---

## Subtask T006: Define Error Handling and Vikunja Unavailability Procedures

**Purpose**: Encode what the agent does when things go wrong — API failures, timeouts, ambiguous input.

**Steps**:
1. Add **Error Handling** section with response code handling:

   | Situation | Action |
   |---|---|
   | Vikunja 401 (auth failure) | Log error, alert Kent via channel, halt all operations |
   | Vikunja 403 (permission denied) | Log error, alert Kent, halt current task |
   | Vikunja 404 (not found) | Log warning, skip this task, continue batch |
   | Vikunja 500 (server error) | Log error, retry with backoff (30s, 60s, 120s), alert after 3 failures |
   | Network error (unreachable) | Log error, alert Kent, halt batch, preserve task context for retry |
   | Ambiguous input | Ask clarification via channel — never guess |

2. Add **Never Fail Silently** rule (Felix Constitution Directive 4):
   - Every error produces an observable output (log + channel notification)
   - If logging fails, the action did not happen (Directive 3)
   - Alert message format: `"⚠️ Task enrichment error: {error}. Task: {title}. Action needed: {what Kent should do}"`

3. Add **Task Context Preservation**:
   - If enrichment fails mid-flow, preserve the raw task input and any partial proposal
   - On retry, resume from last known state rather than starting over
   - If Vikunja is down during a batch, pause batch and retry when service returns

**Validation**:
- [ ] All error codes from Vikunja API contract are covered
- [ ] Never-fail-silently rule explicitly stated
- [ ] Alert format defined
- [ ] Context preservation procedure clear

---

## Definition of Done

- [ ] `scripts/openclaw/skills/task-intelligence/SKILL.md` exists and is complete
- [ ] All six sections present: attributes, confidence model, project mapping, goal check, repeat intervals, error handling
- [ ] Skill is self-contained — no external references needed to structure a task
- [ ] Follows vikunja-api skill format conventions
- [ ] No hardcoded project IDs, label IDs, or API tokens
- [ ] Confidence threshold marked as configurable

## Risks

- **Confidence model too conservative**: May generate excessive clarification questions. Acceptable for initial deployment — tune after operational feedback.
- **Project mapping incomplete**: New Vikunja projects added later will need mapping entries. Document this in the skill as a maintenance note.

## Reviewer Guidance

- Verify all Vikunja API patterns match `research.md` and `contracts/vikunja-task-enrichment-contract.md`
- Confirm no hardcoded IDs anywhere
- Check that confidence threshold is explicitly configurable
- Ensure error handling covers all cases from the API contract
- Verify repeat interval conversion table is accurate (cross-reference research.md)
