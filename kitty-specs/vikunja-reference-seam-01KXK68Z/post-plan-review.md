# Post-plan review + rescope checklist — vikunja-reference-seam (#748 + #745)

**Status: plan committed; RESCOPE PENDING before `/spec-kitty.tasks`.** This file is the
authoritative resume record (conversation context was cleared). Read this, apply the rescope to
`spec.md` + `plan.md`, commit, then run `/spec-kitty.tasks` → **stop before `/implement`**.

## Mission facts
- Branch `feat/vikunja-reference-seam`, topology **single_branch** (no coord branch). Mission id
  `01KXK68Z…`, slug `vikunja-reference-seam-01KXK68Z`.
- Spec + plan already committed (`58c081f` spec, `6ee7601d` plan, `e1b6b33c` Phase 0/1 artifacts).
- Combination decision (recorded on #747/#745): **this mission = #748 + #745 combined** (seam +
  capture routing alignment; same code surface, route_someday can't be split). **#746 (atomic
  finalize) and #749 (intake validation loop) stay as separate sequenced fast-follows.**
- Post-plan review: Codex hung (self-inflicted, see memory [[feedback_never_hide_codex_activity]])
  → Opus reviewer-renata produced the findings below.
- Independent live bug already FIXED on main (`5e24ac4e`): reconcile_completions HABITS_PROJECT_ID
  2→13. (feat branch still shows =2 until this mission's migration rewrites it.)

## Reviewer findings (fold ALL into the rescoped spec/plan)

1. **CONFIRMED — call-site undercount: ~9 sites, not 4.** Plan listed route_someday,
   vikunja_writer, vikunja_scope, sync. Review found these ADDITIONAL runtime resolution sites:
   - `scripts/habits/query_active_habits_v2.py:100` — `HABITS_PROJECT_ID = 13` (+ title const :104, used :237)
   - `scripts/habits/reconcile_completions.py:71` — `HABITS_PROJECT_ID` (fixed to 13 on main; still migrate to seam)
   - `scripts/habits/backfill_jsonl_from_comments.py:63,172` — Habits by `title == "Habits"`
   - `scripts/vikunja/create_task.py:45` — `DEFAULT_PROJECT_ID = 1  # Inbox` + by-title `resolve_project_id()` (:73+) — **classify: runtime-Felix (migrate) vs operator tool (exempt)**
   - `scripts/vikunja/validate_felix_bot.py:69` — `DEFAULT_TARGET_PROJECT_ID = 13`
   - `scripts/sync/classify.py:47,88` — LABEL by `title == "felix:ignore"` (MANUAL_OVERRIDE_LABEL)
   - `scripts/habits/query_active_habits_weekly.py:63,99` — sources id from vikunja_scope (good) but keeps a module-level mirror to collapse
   → Add a WP acceptance grep (title-equality vs Vikunja titles; integer project-id literals; /projects & /labels calls) as the SC-001 gate.

2. **CONFIRMED (already handled) — Habits id 2-vs-13.** Fixed on main; the seam consolidates to one value (13, confirm live at seeding).

3. **CONFIRMED — route_someday targets the DELETED Someday project.** Not a mechanical swap — it's
   #745's routing-target decision. **Retarget** "someday" writes to `q:schedule` + no-due-date task
   in Inbox/Personal (per #745), NOT a "someday" project lookup. Do NOT declare "someday" as a
   registry project (would violate C-004 / the locked design).

4. **CONFIRMED — `PRIVATE_PROJECT_IDS`** (`scripts/sync/diff.py:55`, empty `frozenset()` default,
   threaded through diff/cycle/emit) is a config-injected *set*, not a name→id. Extend `ProjectRef`
   schema with a `private: bool` (or named group) and derive the set from it — OR explicitly scope
   the sync privacy set OUT. Data-model must change either way.

5. **CONFIRMED — boundary conflict with `vikunja_scope.py`** (already "the single source of
   selectors": `HABIT_SELECTOR {kind,value}` :59, `ESCALATION_EXCLUDED_PROJECT_IDS=[13]` :53).
   - Decide ownership: **fold vikunja_scope's constants into the registry and have vikunja_scope
     read from it** (preferred — one source), OR keep vikunja_scope as a selector layer over the
     registry. Don't create two competing single-sources.
   - `ESCALATION_EXCLUDED_PROJECT_IDS` must **derive** from `project_id("habits")`, not restate 13.
   - **PRESERVE the `{kind: project_id|label, value}` selector shape in the registry** — it exists
     because #717 will migrate Habits identity from project-id 13 → `t:habit` label. A flat
     name→int model throws that away. (Extend schema; don't pin `habits→13` as a bare int.)

6. **LOWER-CONFIDENCE — per-token labels (FR-006) unverified, no current consumer.** Only runtime
   label resolution today is `felix:ignore` by title (finding #1). The `f:/q:/t:/loe:` taxonomy
   labels have NO runtime id-consumer yet. **Scope #748 labels to `felix:ignore` (the one real
   consumer); DEFER the per-token taxonomy-label registry to #749.** Before locking a `label_id`
   signature, live-probe which token resolves labels + cross-token visibility (felix-bot writing
   kent-owned labels — can it even see them?). Document reality; don't speculatively encode.

7. **CONFIRMED — SC-001/FR-002 "anywhere in the codebase" contradicts C-001.** The
   `scripts/vikunja/{setup_vikunja,provision_felix_bot,create_taxonomy_labels,migrate_tasks,
   reconcile_projects,create_saved_filters}.py` provisioning tools legitimately resolve by title
   (they're the #714 config-management domain, out of scope). **Reword SC-001/FR-002 to "runtime
   resolution by Felix consumers"** and enumerate the exempt provisioning scripts. Classify
   `create_task.py` explicitly (finding #1).

8. **LOWER-CONFIDENCE — under-specified edges:**
   - **Null-id entries** (data-model shows `Personal`/labels with `vikunja_id: null` = not yet
     provisioned) vs accessor `project_id -> int`: define a distinct fail-loud path ("declared but
     unprovisioned"), distinct from `id_drift`. Interacts with finding #3.
   - **Validator when Vikunja unreachable:** must exit non-zero as "could not validate", distinct
     from "registry clean". Add to contract.
   - **Sub-project hierarchy** (Clients → PointerHealth/spec-kitty): flat registry can't model
     parent/child — fine for id resolution, but note so no consumer expects hierarchy.

Reviewer's overall verdict: the seam DESIGN (fail-loud D3, committed-ids+drift-validator D2/D5,
JSON-authoritative D1, NFR-001/002) is sound and consistent. The problem was surface area
(call sites, schema fields, label reality) being under-scoped — that's what the rescope fixes.

## Rescope action list (do these, then commit, then /spec-kitty.tasks)
- [ ] spec.md: broaden to **#748 + #745** (seam + capture routing alignment). Add routing FRs:
      fallback→Inbox; "someday"→`q:schedule` + no-due-date task; retire route_someday project
      lookup; apply Tier-1 labels where determinable.
- [ ] spec.md: reword FR-002 + SC-001 to **runtime resolution by Felix consumers**; add a
      Constraint enumerating the exempt `scripts/vikunja/` provisioning tools.
- [ ] spec.md: expand FR-005 to the full ~9-site inventory (finding #1); classify create_task.py.
- [ ] spec.md: scope labels to `felix:ignore`; note taxonomy labels deferred to #749 (finding #6).
- [ ] plan.md / data-model.md: extend `ProjectRef` schema — `private` flag (finding #4) + preserve
      `{kind,value}` selector (finding #5) + null-id "unprovisioned" state (finding #8).
- [ ] plan.md: vikunja_scope ownership decision (fold constants into registry, read-through;
      derive ESCALATION_EXCLUDED) (finding #5).
- [ ] plan.md/contract: validator-on-unreachable behavior; note sub-project hierarchy non-modeling.
- [ ] plan.md: route_someday = #745 retarget, NOT mechanical migration (finding #3).
- [ ] Add SC-001 acceptance grep as a gate.
- [ ] Optional live-probe (design-phase-research discipline): confirm live Habits=13 at seed, and
      the per-token label visibility question (finding #6) before locking label handling.
- [ ] Commit rescoped spec/plan; then `/spec-kitty.tasks` (read runbook fresh) → **STOP before /implement**.
