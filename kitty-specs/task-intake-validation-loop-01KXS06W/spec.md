# Feature Specification: Task-Intake Validation Loop

**Mission**: task-intake-validation-loop-01KXS06W
**Issue**: kentonium3/kg-automation#749 (P2-feature, area/felix-core); folds in #750 (P3-bug)
**Mission type**: software-dev

## Overview

The #714 Vikunja reset established a **Tier-1 task-intake standard**: every task
that leaves Inbox into a working project must carry a **working project (≠ Inbox)
+ a friction label (`f:`) + an Eisenhower quadrant (`q:`)**. Nothing enforces
this today, so the friction/Eisenhower taxonomy the reset created goes
unpopulated and Inbox becomes a permanent dumping ground — the strategic value of
surfacing `q:schedule` / `f:3-edge` work is lost.

This mission builds the validation loop the design deferred to this integration
epic (`docs/design/vikunja-configuration-design.md` §Required Fields, lines
215–233): *"Felix validates Tier 1 completeness and prompts via WhatsApp for any
missing fields. This validation loop is the mechanism that ensures the label
taxonomy stays populated rather than decaying into inconsistency."*

The loop **rides the existing inbox-processing crons**: after each inbox tick, a
deterministic helper scans the Vikunja **Inbox** (project id 1, resolved through
the #748 reference seam) for not-done, Tier-1-incomplete tasks and Felix sends a
**single batched WhatsApp digest** numbering them with their missing fields. Kent
replies in **compact shorthand** (e.g. `1 personal f2 schedule`); a deterministic
parser resolves the tokens to the canonical project + labels against the seam and
applies them **through the kent Vikunja token** (`vikunja-api-kent`) — which is
what closes #750 (felix-bot 403s on kent-owned label attach). The LLM is invoked
**only** for genuinely unresolvable tokens (Directive 6 two-layer split).
Applying a working project + `f:` + `q:` moves the task out of Inbox, which is how
it stops re-appearing — the loop **re-prompts until resolved** (no suppression
state).

## User Scenarios & Testing

**Primary actor:** Felix, on Kent's behalf, driven by the inbox-processing cron
and the WhatsApp DM lane.

**Trigger:** an inbox-processing tick completes; the intake scan runs and finds
one or more not-done tasks in the Vikunja Inbox that are Tier-1-incomplete.

**Happy path:** the deterministic scan enumerates Inbox tasks (read token),
classifies each as Tier-1-incomplete (in Inbox ⇒ no working project; and/or no
`f:`; and/or no `q:`), and Felix sends one batched WhatsApp digest: each task is
numbered with its title and the fields it's missing (plus an applicable Tier-2
prompt — a due date when the quadrant will be `q:do`/`q:schedule`). Kent replies
with one terse line per task keyed by its number. A deterministic parser maps the
tokens to the canonical project and labels, and applies them via the kent token
using read-modify-write. The reassigned task now has a working project + `f:` +
`q:`, leaves Inbox, and no longer appears in the next scan.

**Ambiguous token (LLM fallback):** a reply token cannot be resolved
deterministically against the taxonomy/aliases (e.g. an unrecognized project
fragment). Only then does Felix use LLM judgment to disambiguate; if it still
cannot resolve, the line is echoed back to Kent with what was understood and what
failed — never silently applied or dropped.

**Overload task:** Kent assigns `f:4-overload`. Overload is a **decomposition
trigger, not a schedulable state** — Felix flags the task for breaking down rather
than treating it as Tier-1-complete or routing it to a working queue.

**Applicable Tier-2:** the assignment is `q:schedule`, so the digest asked for a
due date. Kent's reply includes one; it is applied per the repository's ET
end-of-day date convention. A missing Tier-2 field never blocks Tier-1
completion.

**Persistently unlabeled task:** Kent doesn't answer for a task. Because the loop
rides ~4 inbox crons/day and re-prompts until resolved, that task re-appears in
subsequent digests (up to ~4/day) until it's labeled — an accepted trade-off
(IDLE-pings posture).

**No incomplete tasks:** the scan finds Inbox empty of incomplete tasks; no
digest is sent (silence, per Output Discipline).

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | A **deterministic** helper shall scan the Vikunja Inbox (project id resolved via the #748 `vikunja_refs` seam, not hardcoded) and enumerate **not-done** tasks, classifying each as Tier-1-complete or Tier-1-incomplete. No LLM is used in the scan. | Draft |
| FR-002 | **Tier-1 completeness** shall be defined as: a task has a project **≠ Inbox** AND at least one friction label in `f:1-flow`/`f:2-growth`/`f:3-edge` AND exactly one Eisenhower label in `q:do`/`q:schedule`/`q:delegate`/`q:eliminate`. A task in Inbox is Tier-1-incomplete by definition. `f:4-overload` does **not** satisfy the friction requirement (it is a decomposition trigger, per FR-009). | Draft |
| FR-003 | The intake scan shall **ride the existing inbox-processing crons** — it runs after each inbox tick — rather than on a separate schedule or on demand. | Draft |
| FR-004 | For a scan that finds ≥1 incomplete task, Felix shall send a **single batched WhatsApp digest** that numbers each incomplete task with its title and the specific Tier-1 fields it is missing, plus an applicable Tier-2 prompt (a due date when the task will be `q:do`/`q:schedule`). Never one message per task. | Draft |
| FR-005 | Kent shall supply missing fields in **compact shorthand**: one line per task keyed by the digest number, of the form `<n> <project> f<1-3> <quadrant>` plus optional Tier-2 tokens (a due date, `habit`, `loe:<s\|m\|l>`). A **deterministic parser** shall map the tokens to the canonical project and labels. | Draft |
| FR-006 | Token resolution shall be **deterministic against the #748 seam / design-doc taxonomy**, case-insensitive, and shall accept the documented shorthands/aliases (e.g. `f2`→`f:2-growth`, `schedule`→`q:schedule`, a project short-name→its canonical project). The **LLM shall be invoked only** for a token that cannot be resolved deterministically (genuine ambiguity). | Draft |
| FR-007 | Project reassignment and label attach shall be written through the **kent token** (`vikunja-api-kent`, the #715 two-token model); felix-bot shall be used **read-only** for intake and shall **never** attempt to attach a kent-owned label (it 403s). This closes #750. | Draft |
| FR-008 | Applying a working project (≠ Inbox) + `f:` + `q:` shall complete intake so the task **leaves Inbox** and no longer appears in subsequent scans — the resolution mechanism under the re-prompt-until-resolved policy (FR-011). | Draft |
| FR-009 | An `f:4-overload` assignment shall flag the task as **needing decomposition** and shall **not** treat it as Tier-1-complete nor route it to a working queue; Felix surfaces the decomposition need (per design-doc "Overload should never appear in an active work queue"). | Draft |
| FR-010 | **Applicable Tier-2** fields shall be prompted/accepted: a **due date** when the quadrant is `q:do`/`q:schedule`, `t:habit` when recurring, and `loe:` when supplied. Tier-2 fields are applied when given but **never block** Tier-1 completion. A due date shall be written per the repository's ET end-of-day convention (avoiding the `T00:00:00Z` off-by-one class). | Draft |
| FR-011 | The loop shall **re-prompt until resolved**: each scan re-lists every still-incomplete Inbox task with **no suppression state**. Repetition across the day's inbox ticks is accepted. | Draft |
| FR-012 | A reply line that cannot be deterministically parsed and is not LLM-resolvable shall be **echoed back to Kent** with what was understood and what failed — never silently applied or dropped. Well-formed lines in the same reply are still applied. | Draft |
| FR-013 | Reply application shall be **idempotent and non-clobbering**: labels/project are written **read-modify-write** so a task's pre-existing labels and unstated fields are preserved (Vikunja POST `/tasks/<id>` zeros unstated fields); re-applying the same reply, or acting on an already-completed task, is a no-op. | Draft |
| FR-014 | The scan and apply shall emit a **deterministic observability signal** (counts of tasks scanned / incomplete / prompted / applied / failed / ambiguous) per tick, sufficient for the health/doc-audit posture (observability-per-feature principle). | Draft |
| FR-015 | Documentation shall be synchronized: `docs/design/vikunja-configuration-design.md` (mark the validation loop implemented), `docs/design/architecture/data/` service-inventory + data-flow for the new intake scan + WhatsApp prompt flow (and md views), an intake-loop runbook, `docs/INDEX.md`/roadmap as applicable, and #750 closure notes. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The scan and the shorthand parse/resolution are deterministic and unit-testable without live Vikunja. | Vikunja reads/writes mockable; scan + parser have unit tests; **no LLM call** on the deterministic path. | Draft |
| NFR-002 | The deterministic grammar covers the full documented taxonomy so the LLM is a true fallback. | 100% of documented projects + `f:`/`q:`/`t:`/`loe:` tokens and their documented aliases resolve without LLM across the token test corpus. | Draft |
| NFR-003 | Reply application never loses unrelated task state. | 0 instances of a pre-existing label removed or an unstated field zeroed across the apply test corpus (read-modify-write proven). | Draft |
| NFR-004 | Prompt volume respects Felix Output Discipline. | At most **one** digest per inbox tick regardless of incomplete-task count; N incomplete tasks → 1 message. | Draft |
| NFR-005 | External calls are bounded within the cron turn. | Every Vikunja/WhatsApp call bounded by an explicit timeout; no unbounded hang within the cron turn. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | office2 is python3-only; helpers invoked as `python3 -m scripts.<domain>.<helper>`; bare `python` prohibited. | Draft |
| C-002 | Risk tier 3 (Python helpers + agent prompt). Deploy: helpers via office2 checkout self-pull; agent prompt(s) via `agent-prompt-sync`; a `deploys/queued/` manifest only if an office2 apply step beyond self-pull is needed. | Draft |
| C-003 | Two-token model (#715): **writes** (project/label attach) via `vikunja-api-kent`; **reads** may use felix-bot. Never attempt a kent-owned label attach with felix-bot. | Draft |
| C-004 | All Vikunja project/label resolution goes through the #748 `vikunja_refs` fail-loud seam; **no hardcoded ids**. If the seam does not yet declare a needed `f:`/`q:` label, it is extended there (with the drift/AST gate), not bypassed. | Draft |
| C-005 | Vikunja POST `/tasks/<id>` partial-replace zeros unstated fields → **always read-modify-write**; labels are attached per Vikunja's per-user ownership model. | Draft |
| C-006 | Directive 6 two-layer split: deterministic scan / parse / resolve / apply live in helpers; the LLM handles only genuine token ambiguity and the WhatsApp-exchange framing. | Draft |
| C-007 | The async WhatsApp reply arrives on the DM lane, disconnected from the inbox cron that sent the digest; the digest's stable task numbering (+ a short-lived correlation record) is what lets a later reply be applied deterministically. The exact agent wiring is a plan-phase decision. | Draft |

## Success Criteria

- **SC-001:** A not-done Inbox task lacking project/`f:`/`q:` is detected by the scan and appears in the digest with its specific missing fields listed.
- **SC-002:** A compact-shorthand reply for a task deterministically resolves to the correct project + `f:` + `q:` and is applied via the kent token, with **no LLM call** for documented tokens.
- **SC-003:** After a valid reply gives a task a working project + `f:` + `q:`, the task no longer appears in the next scan.
- **SC-004:** A reply assigning `f:4-overload` flags the task for decomposition and does **not** mark it schedulable or route it to a working queue.
- **SC-005:** Applying labels/project never removes a task's pre-existing labels or zeros its other fields (read-modify-write verified).
- **SC-006:** An unparseable/ambiguous reply line is echoed back to Kent with what was understood and what failed; other well-formed lines in the same reply are still applied.
- **SC-007:** A `q:do`/`q:schedule` assignment triggers a due-date prompt; a supplied due date is applied per the ET convention; Tier-2 absence never blocks Tier-1 completion.
- **SC-008:** felix-bot is never used to attach a kent-owned label (no 403 path exists); all intake writes go through the kent token — closing #750.
- **SC-009:** For any incomplete-task count N ≥ 1, the scan produces exactly one WhatsApp digest per inbox tick (Output Discipline); N = 0 produces no message.

## Key Entities

- **Inbox task** — a not-done Vikunja task in project id 1; has title, `project_id`, labels, `done`, `due_date`. The intake subject.
- **Tier-1 completeness** — the gate: project ≠ Inbox + a schedulable `f:` (1/2/3) + a `q:` quadrant.
- **Intake digest** — the single batched WhatsApp message per tick, numbering incomplete tasks and their missing fields (+ applicable Tier-2 prompts).
- **Compact-shorthand reply** — Kent's terse per-task assignment lines, keyed by digest number.
- **Shorthand grammar** — the deterministic token → (project, label, Tier-2) mapping, including documented aliases; the LLM-fallback boundary.
- **Correlation record** — the short-lived mapping of digest numbers → task ids that lets an async reply be applied deterministically.
- **Two-token pair** — `vikunja-api-kent` (writes/label-attach) and felix-bot (reads); the #715 split that FR-007 depends on.

## Assumptions

- The async WhatsApp reply is handled on the DM lane and correlated to the scan via the numbered tasks / a short-lived correlation record; the exact agent wiring (which handler parses the reply and invokes the apply helper) is designed in plan.
- The #748 `vikunja_refs` seam today declares `q:schedule` + the projects; plan may **extend** the registry to declare the full `f:`/`q:` label id set the loop attaches, governed by the existing drift/AST gate rather than hardcoding.
- Inbox crons run ~4×/day; riding them yields up to ~4 digests/day for a persistently-unlabeled task (accepted per Kent's re-prompt-until-resolved choice).
- Kent replies over WhatsApp; a multi-task reply is parsed line-by-line, each line independent.
- The design-doc taxonomy (`vikunja-configuration-design.md`) is the source of truth for the friction/Eisenhower/type/LOE label set and colors.

## Dependencies

- **#748 / #745** — CLOSED; the `vikunja_refs` reference seam and capture routing alignment are the resolution substrate this builds on.
- **#715** — provides the `vikunja-api-kent` write token and the friction/Eisenhower label taxonomy that FR-007/FR-002 depend on.
- **#714** — the intake standard and project restructure this loop enforces.
- **#750** — the felix-bot-can't-attach-kent-labels gap; folded in and closed by FR-007 / SC-008.
- **`docs/design/vikunja-configuration-design.md` §Required Fields** — the observer and source of truth for the standard.

## Documentation Synchronization

Per the architecture standing directive, the merge updates as applicable:
`docs/design/vikunja-configuration-design.md` (validation loop marked implemented),
`docs/design/architecture/data/` service-inventory + data-flow entries for the
intake scan and WhatsApp prompt flow (and their md views), a new intake-loop
runbook under `docs/runbooks/`, `docs/INDEX.md` / `docs/DEVELOPER_PORTAL.md` if a
doc surface is added, the capability roadmap status for the Felix↔Vikunja
integration thread, and the #750 closure note.
