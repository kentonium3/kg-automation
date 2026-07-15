# Research: Felix Vikunja reference seam + capture routing alignment

Phase 0 decisions. All `[NEEDS CLARIFICATION]` items resolved; no markers carried forward.

## D1 — Registry representation

- **Decision:** committed JSON data file (source of truth) fronted by a thin typed Python accessor in `scripts/common/`.
- **Rationale:** matches the repo's governing convention — "machine-readable JSON is authoritative; code is a view" — and the existing `vikunja_config.py` seam pattern. JSON is human-eyeball-able and editable without a code change (SC-003); the accessor adds type safety and fail-loud semantics.
- **Alternatives considered:** (a) pure Python constants/enums — type-safe but requires a code edit to change identities, and buries the source of truth in code; (b) pure JSON with ad-hoc `json.load` at each call site — no fail-loud contract, invites drift. Rejected in favor of the hybrid.

## D2 — Identity strategy (committed ids vs live resolve)

- **Decision:** commit the Vikunja ids into the registry for a network-free hot path; a separate validator asserts committed id ↔ name still agree against live Vikunja and fails loud on drift.
- **Rationale:** satisfies NFR-001 (zero hot-path network calls) while still detecting structure changes (FR-004). Live-resolve-by-name on every call would add a `/projects` round trip per operation and is itself fragile against duplicate titles (the two-"Inbox" case).
- **Alternatives considered:** (a) live-resolve every call — fails NFR-001, fragile on duplicate titles; (b) committed ids with no validator — fast but re-introduces silent drift (the #743 failure mode). Rejected.

## D3 — Fail-loud contract

- **Decision:** an undeclared logical name, or a declared identity absent from live Vikunja (at validation time), raises a typed `VikunjaRefError`; resolution never returns `None`/empty as a "not found" signal.
- **Rationale:** the entire mission exists because a silent empty result (by-title lookup of a deleted project) caused #743. Fail-loud is the regression guard (SC-002). Aligns with the fail-loud / single-point-of-failure directive.
- **Alternatives considered:** returning `None` and letting callers decide — rejected; that is exactly today's failure mode.

## D4 — Label ownership (per-token)

- **Decision:** the registry records the owning token for each label; the accessor resolves a label within that token's namespace.
- **Rationale:** #715 established a two-token model (felix-bot + kent) and labels/filters are per-user. A label id is only meaningful within its owner's namespace, so the registry must carry ownership to resolve correctly for #749's future consumers.
- **Alternatives considered:** a single global label map — rejected; it would silently resolve to the wrong user's label or miss it.

## D5 — Drift validation scope & cost

- **Decision:** the validator performs at most two live listings (projects, then labels per relevant token) and reports every missing/drifted reference in one pass; it is an on-demand routine (importable + CLI), not on the hot path.
- **Rationale:** NFR-002; keeps the hot path network-free (D2) while giving an explicit, cheap way to confirm reality == registry (mirrors the `approved-crons.json` baseline-vs-live discipline already used elsewhere in the repo).
- **Alternatives considered:** per-call validation — rejected (violates NFR-001).

## D6 — Rescope decisions (post-plan review 2026-07-15)

- **Scope combines #748 + #745.** They share one code surface (the same routing
  helper both resolves references and picks routing targets) and cannot be cleanly
  split. #746 (atomic finalize) and #749 (intake validation loop) stay separate
  fast-follows.
- **Runtime call-site inventory is 9, not 4** (full list in spec.md FR-005): the
  four originally listed plus four habits sites, `sync/classify.py` (`felix:ignore`),
  and the `query_active_habits_weekly` mirror. The SC-001 grep gate enforces zero
  remaining runtime by-title/hardcoded-id lookups.
- **FR-002 / SC-001 mean "runtime resolution by Felix consumers"**, not "anywhere
  in the codebase" — the `scripts/vikunja/` provisioning tools (#714 domain) and
  the operator-invoked `create_task.py` legitimately resolve by title/id and are
  exempt (C-005). This resolves the earlier contradiction with C-001.
- **vikunja_scope ownership:** the registry owns the identity value;
  `vikunja_scope.py` stays the selector layer and reads through the registry
  (`HABIT_SELECTOR` ← `selector("habits")`; `ESCALATION_EXCLUDED` derives from
  `project_id("habits")`). One source, and the `{kind, value}` selector shape is
  preserved for the #717 Habits project-id → `t:habit` label migration.
- **Private-project set:** `sync/diff.py`'s `PRIVATE_PROJECT_IDS` (a config set,
  not a name→id) moves into the registry as `private_projects` names resolved to an
  id set — one declared home (empty today until a private project exists).
- **Labels scoped to `felix:ignore`** (the only live runtime label consumer);
  taxonomy `f:/q:/t:/loe:` per-token registry handling deferred to #749. Live-probe
  the resolving token + felix-bot visibility before locking label handling.
- **Unprovisioned + unreachable are explicit states.** A declared `null`-id ref
  fails loud as "unprovisioned" (not `id_drift`); a validator that can't reach
  Vikunja exits non-zero as "could not validate" (not "registry clean").
- **route_someday is a behavior change, not a mechanical swap:** it retargets
  someday → `q:schedule`+no-due-date and fall-through → Inbox (#745), and no
  "someday" project is ever declared (C-004).

## Non-goals confirmed
No Vikunja config change (C-001); no dependence on is-null date filtering #725
(C-003); no atomicity (#746) or task-intake validation loop (#749); no taxonomy
`f:/q:/t:/loe:` runtime registry (deferred to #749); the exempt `scripts/vikunja/`
provisioning tools + `create_task.py` are not migrated (C-005). **#745 capture
routing IS now in scope** (superseding the earlier draft's non-goal line).
