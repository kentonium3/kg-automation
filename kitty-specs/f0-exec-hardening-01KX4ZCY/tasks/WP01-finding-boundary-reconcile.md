---
work_package_id: WP01
title: Finding + full boundary-doc reconcile
dependencies: []
requirement_refs:
- FR-001
- FR-004
- FR-005
- FR-006
- FR-007
- NFR-002
- NFR-003
tracker_refs:
- kentonium3/kg-automation#675
planning_base_branch: feat/f0-exec-hardening
merge_target_branch: feat/f0-exec-hardening
branch_strategy: Planning artifacts for this mission were generated on feat/f0-exec-hardening. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/f0-exec-hardening unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: claude
history:
- at: '2026-07-10T03:00:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: architect-alphonso
authoritative_surface: docs/design/felix-openclaw-boundary.md
create_intent: []
execution_mode: code_change
owned_files:
- docs/design/felix-openclaw-boundary.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via
`/ad-hoc-profile-load architect-alphonso` (or the equivalent profile loader in your harness).
The profile carries the identity, governance scope, and boundaries you operate under during
this WP. Treat the profile as authoritative for tone, escalation rules, and Op lifecycle.

## Objective

Update **`docs/design/felix-openclaw-boundary.md`** to (a) record the Foundation-0 Step-3
finding — that OpenClaw's per-agent exec allowlist **cannot** hard-contain `gog` on the worker
agents without breaking their real behavior, because exec approvals are best-effort operator
guardrails, not strong isolation — (b) reconcile the doc's now-stale post-#699 `gog`-ownership
across the **whole document**, and (c) draft the sandbox follow-up issue + the #675 tracker
disposition. **This WP edits one markdown file only.** It makes **no** `openclaw.json` or
runtime change.

## Context

Foundation-0 Steps 1 (memory-core kill) and 2 (skill-scoping / soft containment) are deployed.
The intended Step 3 was hard containment via a per-agent exec allowlist. Design-phase research
(see `research.md`, Decision 1) proved this is not achievable with the allowlist alone. Also,
**#699 migrated `felix-admin-calendar` off `gog`** onto the Felix calendar helper, so several
"calendar is the gog owner" claims in this doc are now historical.

**Read before starting (authoritative sources — do not re-derive):**
- `kitty-specs/f0-exec-hardening-01KX4ZCY/spec.md` (FR-001, FR-004, FR-005, FR-006, FR-007; NFR-002/003/005)
- `kitty-specs/f0-exec-hardening-01KX4ZCY/research.md` — **Decision 1** (the finding + evidence + narrower-knob disposition), **Decision 2** (post-#699 gog is main-only), the sandbox 3-part proof, and the #675 disposition section. Quote its evidence; do not invent new claims.
- `kitty-specs/f0-exec-hardening-01KX4ZCY/plan.md` (IC-01)
- `docs/design/felix-openclaw-boundary.md` — the file you edit; note existing §§1–10.

**Discipline (important):** this doc is the boundary **design-of-record**. Do **not** delete
its historical design narrative. Reconcile by (i) adding a dated **status banner** near the top
and the finding at §8 Step 3, and (ii) annotating now-stale lines inline as
`*(pre-#699 historical — see 2026-07-10 status update)*` rather than rewriting history.

## Subtasks

### T001 — Record the finding at §8 Step 3 (FR-001, NFR-002, NFR-003)

Rewrite/extend §8 Step 3 (currently "Exec-hardening — hard containment") into a **FINDING**:
- State the honest conclusion: exec approvals are **best-effort operator guardrails, not
  strong isolation**; no per-agent allowlist that is simultaneously (a) tight enough to deny
  `gog`, (b) non-breaking for the workers' real behavior, and (c) free of human-in-the-loop
  approvals exists for this fleet today.
- Cite the OpenClaw version validated against — **2026.6.11 (e085fa1)** — and the bundled doc
  `~/.local/lib/node_modules/openclaw/docs/tools/exec-approvals-advanced.md`.
- Keep it falsifiable (NFR-003): name the specific mechanics — redirection unsupported;
  `$()`/backticks rejected; inline eval requires approval under `strictInlineEval`; `python3
  -m` interpreter-binding uncertainty.

### T002 — Evidence table + explicit disposition of the narrower knobs (FR-001, NFR-002)

Add, under the finding:
- The **per-agent exec-form evidence** table from `research.md` Decision 1a (capture/habits/
  calendar/tasker/escalation: clean `python3 -m` vs inline eval / heredoc / redirection / curl
  / scratch scripts).
- An **explicit disposition of each narrower knob** (from research Decision 1): `argPattern`,
  `strictInlineEval`, `safeBins`/`safeBinProfiles`, `ask=on-miss` — one line each on why it is
  rejected (do not leave the reader thinking an obvious config was missed).

### T003 — Whole-doc gog-ownership sweep (FR-004)

Add a dated status banner immediately after the title/intro:
> **STATUS UPDATE 2026-07-10 (post-#699 + Step-3 finding):** `gog` is now used by **`main`
> only** (gmail/drive/etc.). `felix-admin-calendar` is a **former** gog owner — #699 migrated
> it onto the Felix calendar helper; it is now `gog`-free. Sections below describing calendar
> as a gog owner are **pre-#699 historical**. Hard containment via exec-allowlist was found
> infeasible (see §8 Step 3); the real lever is sandbox (follow-up issue in §8).

Then annotate the stale present-tense claims in **§2** (current-state table), **§4**
(capability map — calendar→gog row), **§6** (design intent: "gog scoped to calendar", the
example `skills: ["calendar","gog"]`, "main becomes pure router"), **§6.1** (pre-flight table
"felix-admin-calendar … sole owner"), and **§8** Steps 2–3 ("calendar the only non-main gog
holder") with the inline `*(pre-#699 historical — see 2026-07-10 status update)*` marker, or a
one-clause correction. Goal: the NFR-005 semantic grep finds no *un-annotated* present-tense
"calendar owns/holds gog."

### T004 — Sandbox recommendation + 3-part proof + follow-up draft + §8 pointer (FR-005)

- In the finding, add the **sandbox recommendation**: `agents.defaults.sandbox.mode: "non-main"`
  (Docker backend) is the correct hard-containment lever; note **network:none ≠ no network**.
- Add an **appendix** titled `## Appendix A — Sandbox hard-containment follow-up (issue draft)`
  containing a ready-to-file issue body (infra template style: Symptom / Observer /
  Cost-of-doing-nothing, then scope). The scope MUST require proving **three properties
  separately**: (i) `gog` binary absent/unreachable in the worker sandbox; (ii) Google egress
  blocked; (iii) Vikunja API + kg-automation checkout/venv/state paths still work so each
  worker's real cron job runs — plus **fold in Step 4 (`skills.allowBundled`)** as a named
  sub-item. (The orchestrator files this at merge; leave a `#TBD` placeholder for the number.)
- Add a §8 Step-3 pointer: "continuation tracked in the sandbox follow-up issue (#TBD — see
  Appendix A; filed at mission merge)."

### T005 — #675 disposition recommendation (FR-007)

Add a short subsection (in §8 or the appendix) recommending the **#675 tracker disposition**:
close #675 as **rescoped** — "allowlist hard-containment found infeasible; finding + doc
reconcile landed; remaining hard boundary superseded by the sandbox follow-up #TBD" — with the
operator confirming the close-vs-keep-open call at merge. Make explicit that "docs + issue"
does **not** equal hard-containment *completion*.

## Definition of Done

- [ ] §8 Step 3 records the finding with the version + bundled-doc citation and falsifiable mechanics (T001).
- [ ] Evidence table + explicit disposition of `argPattern`/`strictInlineEval`/`safeBins`/`ask=on-miss` present (T002).
- [ ] Dated status banner added; §2/§4/§6/§6.1/§8 stale gog-ownership annotated as pre-#699 historical or corrected (T003).
- [ ] Sandbox recommendation + Appendix A issue draft (3-part proof + Step 4) + §8 pointer present (T004).
- [ ] #675 disposition recommendation present (T005).
- [ ] **No file other than `docs/design/felix-openclaw-boundary.md` is modified.** No `openclaw.json`/runtime change (FR-006).
- [ ] `grep -nE '"calendar","gog"|sole owner|only .*gog holder|executes .gog calendar create' docs/design/felix-openclaw-boundary.md` returns only lines inside the labelled pre-#699 historical context.

## Branch Strategy

Planning base: `feat/f0-exec-hardening`. Final merge target: `feat/f0-exec-hardening`.
Execution worktrees are allocated per computed lane from `lanes.json` during
`/spec-kitty.implement`. Completed changes merge back into `feat/f0-exec-hardening`.

## Reviewer Guidance

Verify the finding matches `research.md` Decision 1 (no overstated "no narrower config exists"
— it must be the guardrails-not-isolation framing with each knob disposed of). Confirm history
is preserved (annotations, not deletions) and that the appendix issue draft demands the three
separately-proven sandbox properties. Confirm nothing outside the boundary doc changed.
