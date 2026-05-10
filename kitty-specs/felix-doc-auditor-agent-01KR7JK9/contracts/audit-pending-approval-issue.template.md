# Contract: Audit Pending-Approval Issue (Level 1 only)

**Filed by**: `felix-doc-auditor` at the end of an audit run when one or
more high-confidence edits are proposed at Assisted (Level 1) autonomy.
**Replaces**: the WhatsApp summary + reply contracts (deprecated v1.2.0,
issue #207).
**Purpose**: surface the proposed file mutations to Kent on a real
review surface (GitHub) so he can see the diff before authorizing the
commit.

## Issue title

```
Audit #<originating-audit-number>: pending approval — <N> proposed edit(s)
```

Examples:
- `Audit #186: pending approval — 1 proposed edit(s)`
- `Audit #168: pending approval — 0 proposed edit(s)` ← shouldn't happen; if no edits, no pending-approval issue is filed at all

## Labels (apply at creation)

- `audit-pending-approval` — primary marker; the cron-tick scanner
  filters by this
- One or more `area/*` labels — copied from the originating audit
- (Do NOT apply `P2-debt` to this issue; this is not a tracked-work
  artifact, it's an active gate.)

## Body template

```markdown
## Audit pending approval

**Originating audit**: #<N>
**Triggering commit**: `<sha>` (or `weekly` for weekly audits)
**Scope**: <area/*> (or `full-scope`)
**Docs reviewed**: <count>

## Proposed edits

Each numbered item is a high-confidence edit per the doc-audit skill's
Section 4.1 confidence rules. Apply ALL of them on `audit-approve`.

### 1. `<repo-relative-doc-path>`

**Change type**: <frontmatter_date | version_bump | path_rename | dead_ref_removal | registry_entry_add | registry_autonomy_update>

**Evidence**: <one-sentence pointer to the system-state source that justifies the edit, including the triggering commit SHA where applicable>

**Diff**:
```diff
- <line being removed>
+ <line being added>
```

### 2. `<next-doc-path>`

(repeat per edit)

---

## Already filed (autonomously, not part of this gate)

These were filed in the same audit run without requiring approval —
they're tracked-work artifacts that can be reviewed and closed
individually post-hoc.

**Docs-debt issues filed**: #<N>, #<M>, ...

**Missing-artifact issues filed**: #<N>, ...

**Items requiring human review** (could not classify): <list, or `(none)`>

---

## Decision

Apply ONE label to record your decision:

- **`audit-approve`** — Apply all proposed edits, commit atomically with the audit-issue reference, post the audit summary on #<N>, close both this issue and #<N>.
- **`audit-reject`** — Do NOT commit. Each proposed edit becomes its own `docs-debt` issue (with the proposed before/after preserved as evidence). Close both this issue and #<N>.
- **`audit-skip`** — Close both this issue and #<N> with a skip note. No commit, no demotion, no further debt issues.

The agent picks up the decision on its next cron tick (every 60 minutes).
No timeout — this issue stays open until you decide.

---

*Filed by `felix-doc-auditor:sonnet` (skill v1.2.0+).*
```

## Rules

- Always include the **`Diff`** code block per edit using `diff` syntax — Kent should see exactly what changes without leaving GitHub.
- Always include the **Evidence** line — every high-confidence edit must cite its source. If you can't write a one-sentence evidence line, the edit doesn't pass the confidence threshold; demote to debt instead.
- Always include the **Decision** instructions block — Kent shouldn't have to remember the label vocabulary.
- Cross-reference (not duplicate) the debt + missing-artifact issues already filed.
- Identity footer: `Filed by felix-doc-auditor:sonnet (skill v<version>)`.

## Lifecycle

1. **Created** by the agent at the end of an audit run (when one or more high-confidence edits exist). The originating audit issue's `status:in-progress` lock remains in place.
2. **Decision applied** by Kent (one of three labels).
3. **Picked up by the next cron tick** of `felix-doc-auditor`. The agent applies the decision per the table in SKILL.md Section 8.5.
4. **Closed by the agent** alongside the originating audit; the lock is released.

## Promotion behavior

After Level 1 → Level 2 promotion, this contract is **no longer used** —
the agent commits high-confidence edits directly without filing a
pending-approval issue. The originating audit is closed in the same
run.
