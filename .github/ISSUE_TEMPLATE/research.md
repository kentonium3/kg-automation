---
name: Research
about: Investigation or evaluation that must be completed before a feature can be specced
title: "Research: "
labels: P3-candidate
assignees: ''
---

<!--
INSTRUCTIONS FOR AUTHOR
- Focus on WHAT to learn and WHY it matters — not HOW to gather
- HOW is determined by spec-kitty methodology phase
- Discovery pointers (where to look) are welcome; specific commands are not
- State what decision this research unblocks
- Delete all HTML comment blocks before submitting
-->

## Research Purpose

<!--
2–3 sentences: what gap in knowledge this research fills and what
decision it enables. Why is this research needed now?
-->

**Decision gate**: This research must be complete before [#NNN / decision]
can proceed. The current blocker is: [specific unknown].

---

## Research Questions

<!--
The questions the research must answer. Findings must address each one.
Aim for 3–6 questions. More than 6 suggests the scope is too broad.
Each question must be answerable in principle — not vague or open-ended.

Good: "Does gog support headless token refresh on Linux?"
Bad:  "What are gog's capabilities?"
-->

### RQ-1: [Primary question]

<!--
1-2 sentences expanding on what specifically needs to be understood.
-->

**Acceptable answer form**: [What a good answer looks like — e.g.,
"a yes/no determination with evidence" or "a ranked comparison table"]

---

### RQ-2: [Secondary question]

**Acceptable answer form**:

**Depends on**: [RQ-X, if this question builds on another's answer]

---

### RQ-3: [Question]

**Acceptable answer form**:

---

## Known Sources

<!--
Discovery pointers for the gathering phase. Internal sources first.
Point to WHERE evidence can be found — not HOW to interpret it.
-->

### Internal sources

- `[path or system component]` — [what it reveals about RQ-X]

### External sources

- [URL or reference] — [what it covers and which RQ it informs]

### Sources to approach with caution

<!--
Optional. Flag sources that may be biased, outdated, or incomplete.
-->

---

## Evaluation Criteria

<!--
Only include this section if the research is comparing options.
Remove entirely for yes/no or descriptive research.
-->

| Criterion | Weight | Description |
|-----------|--------|-------------|
| | High / Medium / Low | |
| | High / Medium / Low | |
| | High / Medium / Low | |

---

## Scope

### In scope

-
-

### Out of scope

- ❌ Implementation work — research missions produce findings, not code
- ❌
- ❌

---

## Expected Outputs

<!--
What findings.md must contain for the research to be accepted.
Map each output to the research question(s) it answers.
-->

| Output | Answers | Description |
|--------|---------|-------------|
| | RQ-1 | |
| | RQ-2, RQ-3 | |
| Recommendation | All | Synthesized recommendation with rationale |

**Downstream use**: The findings from this research will be consumed by:
- [#NNN] — [which outputs feed which sections]

---

## Constraints

<!--
Hard boundaries on how the research is conducted.
Not preferences — constraints. "Read-only on live system" is a constraint.
"Prefer official docs" is a preference (put it in Notes instead).
-->

-
-

---

## Success Criteria

### Evidence
- [ ] All research questions have findings with cited sources
- [ ] At least 3 independent sources consulted
- [ ] Conflicting evidence documented and reconciled

### Findings
- [ ] findings.md addresses every RQ with supported conclusions
- [ ] Gaps or unknowns explicitly called out rather than silently omitted

### Recommendation
- [ ] A clear recommendation is stated (not just a summary of evidence)
- [ ] Risks or caveats to the recommendation are documented

### Downstream readiness
- [ ] [#NNN] spec can be written without further unknowns

---

## Notes for Methodology Phase

<!--
Discovery pointers — WHERE to look, not HOW to interpret.
Help the gathering phase start efficiently.
-->

-
-

---

## Spec-ready criteria

<!--
Self-check before this research issue is ready for /spec-kitty.specify.
Phone-filed issues are not expected to meet this bar at capture time.
-->

This issue is ready for spec-kitty when:

- [ ] **Research Purpose** names the decision gate this research unblocks
- [ ] **Research Questions** lists 3–6 specific, answerable questions
- [ ] Each RQ has an **Acceptable answer form** specified
- [ ] **Known Sources** lists at least one starting point per RQ (internal or external)
- [ ] **Scope** has both In-scope and Out-of-scope items filled
- [ ] **Expected Outputs** maps outputs to RQs with a clear downstream consumer
- [ ] **Success Criteria** checkboxes are intact (template defaults are usually right)
- [ ] HTML comment guidance blocks have been removed
