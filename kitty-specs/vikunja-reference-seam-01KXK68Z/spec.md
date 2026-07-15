# Feature Specification: Felix Vikunja reference seam + capture routing alignment

**Mission**: vikunja-reference-seam-01KXK68Z
**Branch**: feat/vikunja-reference-seam
**Status**: Draft (rescoped post-plan-review 2026-07-15)
**Issues**: kentonium3/kg-automation#748 + #745 (combined; epic #747)

## Overview

Felix resolves Vikunja projects and labels ad-hoc today — by title in some
places, by hardcoded id in others — with no single source of truth. That
fragility silently broke inbox routing when the #714 Vikunja reset deleted a
project: a by-title lookup for a now-deleted project failed, and captured items
were lost without a visible error (#743).

This mission does two things on one code surface (they cannot be cleanly split —
the same routing helper both resolves references and decides routing targets):

1. **#748 — the resolution seam.** Consolidate every *runtime* Felix
   project/label reference into one declared, validated registry that resolves
   against the locked post-reset names and **fails loud** when a reference cannot
   be resolved.
2. **#745 — capture routing alignment.** Retarget `felix-admin-capture`'s routing
   onto the post-reset Vikunja model: fall-through → **Inbox** (not a deleted
   "Someday" project); "someday" items → a task tagged `q:schedule` with **no due
   date** (the design's "important, not date-committed" state); apply Tier-1
   intake labels where determinable. This retires `route_someday`'s Someday-project
   lookup entirely.

Together they give Felix a stable reference foundation and correct post-reset
routing, so the downstream atomicity / intake-validation work (#746 / #749) can
build on it. **#746 (atomic finalize) and #749 (task-intake validation loop)
remain separate, sequenced fast-follows and are out of scope here.**

## User Scenarios & Testing

**Primary actor:** a Felix helper or agent that needs to act on a Vikunja
project or label (e.g. file a captured item into "Inbox", tag a task
`q:schedule`, scope a habits query).

- **Happy path (resolution):** the helper asks the registry for the identity of a
  logical name ("inbox"); the registry returns the correct owner-scoped identity;
  the helper proceeds. No live project/label listing is required on this path.
- **Happy path (routing, #745):** a captured block that is date-committable routes
  to its topic project; a "someday" block is created (in Inbox or the resolved
  topic project) with the `q:schedule` label and **no due date**; an
  unclassifiable block falls through to **Inbox**. Tier-1 labels (project / `f:`
  friction / `q:` quadrant) are applied where determinable; where not, the item is
  left in Inbox for the #749 intake-validation loop to prompt on.
- **Missing reference (exception):** the logical name is not declared, or its
  declared identity no longer exists in Vikunja. The helper receives a typed,
  descriptive failure and stops — it never silently writes to a wrong project or
  returns an empty result. (This is the #743 regression guard.)
- **Structure drift (exception):** a Vikunja reorg renames or deletes a
  referenced project/label. The next validation run reports the broken reference
  by name, loudly, so the operator updates the registry in one place.

## Requirements

### Functional — resolution seam (#748)

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | A single declared registry maps every logical Vikunja project and label name Felix uses at runtime to its Vikunja identity (id and/or selector). | Planned |
| FR-002 | All **runtime Felix consumer** code resolves Vikunja projects and labels exclusively through the registry; no runtime consumer resolves a project/label by ad-hoc title match or by a literal hardcoded id. (The `scripts/vikunja/` provisioning tools of the #714 config domain are exempt — see C-005.) | Planned |
| FR-003 | Resolving a logical name that is undeclared, or whose declared identity is absent in Vikunja, raises a typed descriptive error; the system never silently returns an empty result or acts on a wrong target. | Planned |
| FR-004 | A validation routine checks the declared registry against live Vikunja and reports, loudly, any declared name that is missing or whose recorded identity no longer matches (drift). When Vikunja is unreachable it exits non-zero as "could not validate" — a state distinct from "registry clean". | Planned |
| FR-005 | Every runtime resolution call site (full inventory below) is migrated onto the registry and its prior by-title / hardcoded-id lookup is removed, leaving no vestige. | Planned |
| FR-006 | Runtime label resolution accounts for per-user (per-token) label ownership so a label is resolved within the correct owning user's namespace (#715 two-token model). Scope for this mission: the one label with a live runtime consumer — `felix:ignore` (sync manual-override). The `f:/q:/t:/loe:` taxonomy labels have no runtime id-consumer yet; their per-token registry handling is **deferred to #749**. | Planned |
| FR-007 | The registry resolves against the locked post-#714-reset project and label names, and treats the felix-bot token's own native Inbox (id 14) as out of scope (never a resolution target). | Planned |
| FR-008 | The registry schema preserves the `{kind: project_id \| label, value}` selector shape for identities that will migrate representation (e.g. Habits moving from project-id 13 → `t:habit` label under #717). Identities are not pinned as bare integers where a future selector migration is anticipated. | Planned |
| FR-009 | The registry represents a declared-but-not-yet-provisioned reference (identity `null`, e.g. `Personal` before it exists live) as a distinct state; resolving it fails loud as "declared but unprovisioned", separate from both a clean resolution and an `id_drift`/`missing` validator finding. | Planned |

### Functional — capture routing alignment (#745)

| ID | Requirement | Status |
|----|-------------|--------|
| FR-010 | The capture fall-through / safe-fallback target is **Inbox** (id 1). Unclassifiable or no-project captures land in Inbox, not a "Someday" project. The capture AGENTS.md wording is corrected to match. | Planned |
| FR-011 | "Someday" captures are routed as a **task tagged `q:schedule` with no due date** (created in Inbox or the resolved topic project), representing the "important, not date-committed" state — not a lookup of a "someday" project. `route_someday`'s Someday-project-by-title lookup is retired. | Planned |
| FR-012 | Tier-1 intake labels (project assignment, `f:` friction, `q:` quadrant) are applied on routing where determinable; where not determinable, the item is left in Inbox for the #749 task-intake validation loop. | Planned |
| FR-013 | The existing routing-log / dedup substrate behavior is preserved (no regression to capture idempotency). | Planned |

### Non-Functional

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-001 | Resolution on the routing hot path performs zero per-call network requests to Vikunja (identities are available without a live fetch on each resolution). | Planned |
| NFR-002 | The validation routine completes within at most two Vikunja listing round trips (projects + labels) and is safe to run on demand. | Planned |
| NFR-003 | No new third-party dependencies are introduced; the standard library plus the existing Vikunja client only. | Planned |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | This feature changes only Felix-side resolution and routing code. It does not create, rename, or delete any Vikunja project, label, or filter — that is the domain of #714. | Active |
| C-002 | Resolution is owner-scoped to kent-owned projects; the felix-bot user's own native Inbox (id 14) is never a resolution target. | Active |
| C-003 | Proceed as if native is-null date filtering (#725) is unavailable indefinitely; nothing in this seam or the routing change depends on it. The `q:schedule`+no-due-date convention (FR-011) is independent of the #725 saved *filter*. | Active |
| C-004 | The locked post-reset names are those defined in `docs/design/vikunja-configuration-design.md`; the registry must not diverge from that document. The registry does **not** declare a "someday" project (it was deleted by design and reconceived as a label state). | Active |
| C-005 | The `scripts/vikunja/` provisioning tools of the #714 config-management domain — `setup_vikunja.py`, `provision_felix_bot.py`, `create_taxonomy_labels.py`, `migrate_tasks.py`, `reconcile_projects.py`, `create_saved_filters.py`, `validate_felix_bot.py` — legitimately resolve by title/id and are **exempt** from FR-002. `scripts/vikunja/create_task.py` (the `/create-vikunja-task` operator/agent slash-command helper) is also exempt as an operator-invoked tool that resolves a caller-supplied `--project` argument; it is not on a Felix autonomous routing path. See the Scope note for the (out-of-scope) optional hardening. | Active |

## Success Criteria

- **SC-001:** 100% of Felix's **runtime** Vikunja project/label resolutions go through the single registry — zero remaining by-title or hardcoded-id lookups in runtime consumer code. Enforced by an acceptance grep (below) over the migrated surface; the exempt `scripts/vikunja/` provisioning tools (C-005) are excluded from the gate.
- **SC-002:** A deleted or renamed referenced project/label produces a loud, actionable failure within one validation run, rather than a silent mis-route or empty result (regression guard for the #743 class).
- **SC-003:** Changing a project/label identity requires editing only the registry (a single location), with no other code changes.
- **SC-004:** No increase in the number of Vikunja API calls made on the routing hot path relative to today.
- **SC-005:** "Someday" captures produce a `q:schedule`-tagged, no-due-date task and unclassifiable captures land in Inbox — verified against the post-reset model, with no remaining reference to a "Someday" project in capture code or AGENTS.md (#745).

### SC-001 acceptance grep (gate)

The migration is not done until a grep over runtime consumer code (excluding the
C-005 exempt list) finds **zero** of:
- Vikunja title-equality resolution (`title == "<Project/Label>"`, `p.get("title") == …`) against a project/label name that Felix routes on;
- integer project-id / label-id literals used as resolution targets (e.g. `= 13`, `project_id: 13`, `PROJECT_ID = 1`);
- direct `/projects` or `/labels` list-and-filter calls made to *resolve a known logical reference* (as opposed to the validator's single live-list, or provisioning tools).

## Runtime resolution call-site inventory (FR-005)

The plan's original "4 sites" undercounted. The full runtime inventory to migrate:

| # | Site | Current resolution | Notes |
|---|------|--------------------|-------|
| 1 | `scripts/inbox/route_someday.py` | `find_someday_project` by-title `"Someday"` | **Retire** per FR-011 (not a mechanical swap — routing-target change). |
| 2 | `scripts/security/credential_health_check/vikunja_writer.py` | `lookup_inbox_project_id` by-title | Migrate to `project_id("inbox")`. |
| 3 | `scripts/common/vikunja_scope.py` | `HABIT_SELECTOR` / `ESCALATION_EXCLUDED_PROJECT_IDS = [13]` | Read the id through the registry; **preserve the selector shape** (FR-008); derive exclusion from `project_id("habits")` (see plan). |
| 4 | `scripts/sync/diff.py` | `PRIVATE_PROJECT_IDS = frozenset()` | Config-injected *set*, not a name→id. Derive from a registry `private` flag, or explicitly scope OUT (plan decides). |
| 5 | `scripts/habits/query_active_habits_v2.py:100` | `HABITS_PROJECT_ID = 13` (+ title const :104, used :237) | Migrate to registry. |
| 6 | `scripts/habits/reconcile_completions.py:71` | `HABITS_PROJECT_ID` (=2 on this branch; fixed to 13 on main `5e24ac4e`) | Migrate to registry (supersedes the raw-int fix). |
| 7 | `scripts/habits/backfill_jsonl_from_comments.py:63,172` | Habits by `title == "Habits"` | Migrate to registry. |
| 8 | `scripts/habits/query_active_habits_weekly.py:63,99` | Sources id from `vikunja_scope` (good) but keeps a module-level `HABITS_PROJECT_ID` mirror | Collapse the mirror onto the seam. |
| 9 | `scripts/sync/classify.py:47,88` | `felix:ignore` label by `title == MANUAL_OVERRIDE_LABEL` | Migrate to registry label resolution (the one live label consumer, FR-006). |

**Exempt (C-005), NOT migrated:** `scripts/vikunja/validate_felix_bot.py` (`DEFAULT_TARGET_PROJECT_ID = 13`), `scripts/vikunja/create_task.py` (`DEFAULT_PROJECT_ID = 1` + `resolve_project_id` by-name), and the other `scripts/vikunja/` provisioning tools.

## Key Entities

- **Project reference** — a logical project name (e.g. "inbox", "personal") bound to a Vikunja project identity, with an owner, an optional `private` flag, and a provisioned/unprovisioned state.
- **Label reference** — a logical label name (e.g. `felix:ignore`) bound to a label identity within an owning token's namespace.
- **Selector** — the `{kind, value}` identity form (`project_id` or `label`) that lets an identity's representation migrate without changing consumers (FR-008).
- **Registry** — the declared collection of project and label references (the single source of truth).
- **Validation report** — the set of missing / drifted / unreachable findings produced by checking the registry against live Vikunja.

## Assumptions

- **Representation (confirmed with operator 2026-07-15):** the registry is a committed machine-readable data file (source of truth) fronted by a thin typed accessor, matching the project's "machine-readable data authoritative, code is a view" convention.
- **Identity strategy (confirmed 2026-07-15):** project/label identities are committed into the registry for a network-free hot path, with a separate validation routine that asserts committed identity ↔ name still agree against live Vikunja and fails loud on drift.
- The locked names and structure are taken from `docs/design/vikunja-configuration-design.md` (Inbox, Felix / kg-automation, Clients › {PointerHealth, spec-kitty}, Personal, Metal Casework, CT-90day, Habits; labels `f:`, `q:`, `t:`, `loe:`, `felix:ignore`).
- Two Vikunja tokens exist (felix-bot and kent) per #715; label namespaces are per-token.
- **Live-probe (design-phase-research, before locking ids/label handling):** confirm live Habits project id = 13 at seed time; and confirm which token resolves `felix:ignore` and whether felix-bot can see it (finding #6). Document reality; do not speculatively encode taxonomy-label handling.

## Scope

**In scope:** a declared runtime project/label registry; migration of the full runtime resolution call-site inventory onto it; fail-loud resolution; a drift/missing/unreachable validation routine; the #745 capture routing alignment (fall-through→Inbox, someday→`q:schedule`+no-due-date, Tier-1 labels, retire `route_someday` project lookup); correcting capture AGENTS.md.

**Out of scope:** any change to Vikunja's own configuration (#714); routing atomicity (#746); the task-intake validation loop (#749); native is-null date filtering (#725); the `f:/q:/t:/loe:` taxonomy-label runtime registry (deferred to #749); migrating the exempt `scripts/vikunja/` provisioning tools (C-005). **Optional future hardening (not this mission):** making `create_task.py`'s by-name resolution registry-aware for declared logical names — noted so it is not forgotten, deliberately deferred to keep scope tight.

## Edge Cases

- **Duplicate project titles** (e.g. two "Inbox" projects across users): the registry pins the correct owner-scoped identity; the felix-bot token's own Inbox (id 14) is excluded.
- **Declared name absent in Vikunja:** fail loud (FR-003).
- **Declared but unprovisioned** (identity `null`, e.g. `Personal`): distinct fail-loud path (FR-009), not `id_drift`.
- **Identity drift** (name still present but id changed): flagged by validation (FR-004).
- **Vikunja unreachable at validation time:** non-zero "could not validate", distinct from "registry clean" (FR-004).
- **Label present under one token but not another:** resolved in the correct namespace, or fail loud (FR-006).
- **Sub-project hierarchy** (Clients › PointerHealth/spec-kitty): the flat registry does not model parent/child. Fine for id resolution; noted so no consumer expects hierarchy from the registry.

## Dependencies

- `docs/design/vikunja-configuration-design.md` — the locked post-reset names.
- Existing `scripts/common/vikunja_client.py` and `scripts/common/vikunja_config.py`.
- `scripts/common/vikunja_scope.py` — the existing selector layer this mission folds onto the registry (#723).
- Consumed by #746 / #749; relates to #714 (reset), #715 (per-user labels), #717 (habits project→label migration), #725 (is-null primitive).
