# Data Model: Cross-Repo Standing Rules Sweep

This mission has no runtime data model. The relevant model is a lightweight
review model for candidate rules.

## Entity: Candidate Rule

| Field | Type | Notes |
| --- | --- | --- |
| `source_path` | string | Repo-relative source file containing the candidate. |
| `source_lines` | string | Line or small range used as evidence. |
| `candidate_text` | string | Short paraphrase of the rule. |
| `classification` | enum | `promote`, `link-only`, `already-represented`, `repo-specific`, `agent-specific`, or `unclear`. |
| `rationale` | string | Why the candidate was or was not promoted. |
| `standing_rules_change` | string | Summary of the resulting edit, if any. |

## Invariants

- A rule cannot be promoted without source evidence.
- A rule cannot be promoted if it applies only to kg-automation infrastructure,
  office2 operations, or a single deployed agent.
- A procedural rule longer than a short bullet is linked, not duplicated.
- Existing protections for public-copy approval, local tracking records, and
  sibling-tool bug reporting must remain present after edits.

## State Transitions

```text
discovered -> classified -> applied | left-linked | left-local | needs-judgment
```

`needs-judgment` candidates are not blockers for implementation; they are
reported for follow-up rather than silently promoted.
