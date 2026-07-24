# Research — Vikunja token seam + kent cutover (phase 2 of #860)

## R1 — Live premise verification (design-phase probe, 2026-07-23)

**Decision**: Proceed with the felix-bot → kent flip; the premise is confirmed live.

**Evidence** (office2, `GET /projects` under each token):
- **felix-bot (`vikunja-api`)** sees: `1 Inbox, 6 Business Acquisition, 8 Health & Conditioning,
  9 Intentional LLC, 10 Metal Casework, 13 Habits, 14 Inbox(felix-bot's own)`. **Blind to 16–20.**
- **kent (`vikunja-api-kent`)** sees: `1, 6, 8, 9, 10, 13, 16 Felix/kg-automation, 17 Clients,
  18 PointerHealth, 19 spec-kitty, 20 Personal` + saved filters (negative ids). Does **not** see 14.

**Rationale**: This is the exact visibility gap #860 describes. The flip *gains* projects 16–20 and
loses nothing runtime-critical — the runtime targets Inbox=**1** and Habits=**13** (`vikunja_refs.json`),
both visible to kent. Project **14** (felix-bot's private Inbox) is not referenced by any runtime consumer
(runtime inbox = project 1), so leaving felix-bot dormant owning 14 (C-002) is safe — no runtime path
loses a target.

**Alternatives considered**: (a) share projects 16–20 to felix-bot instead of flipping — rejected by
Kent (#860 decision): keeps the two-token tax and per-user scoping fragility. (b) content-swap the
`vikunja-api` file to the kent token value on office2, leaving the misleading filename — rejected: the
issue wants the credential retired and the path honest.

## R2 — Runtime consumer inventory (grep-confirmed at HEAD `93834f4e`)

Token-resolution patterns after Phase 1 (**corrected after the post-plan Codex review**, which caught
that the first inventory omitted escalation + enrichment and misclassified `apply_reply`):
- **Group A — already centralized** (bare `VikunjaClient()`): `inbox/route_and_finalize`,
  `inbox/route_someday`, `vikunja/create_task`, `trust/assertion_verifier`, `habits/weekly_report_driver`,
  `habits/query_active_habits_weekly`. Inherit the flip automatically once the client default routes
  through `get_vikunja_token_path()`.
- **Group B — self-load a felix-bot `DEFAULT_TOKEN_PATH` literal** (13 modules): `habits/{sweeper,
  record_completion, exclude_completed, set_due_dates, identify_workout_task, migrate_schedule}`,
  **`escalation/{record_completion, reconcile_completions}`**, **`enrichment/{record_completion,
  reconcile_completions}`**, `security/credential_health_check/vikunja_writer`, and
  `sync/{cycle,fetch}` (literal `config.secrets_dir / "vikunja-api"`). All confirmed at
  `escalation/record_completion.py:111`, `escalation/reconcile_completions.py:136`,
  `enrichment/record_completion.py:118`, `enrichment/reconcile_completions.py` (imports the constant).
- **Kent-pinned exception — NOT a flip participant**: `intake/apply_reply.py` explicitly loads the
  **kent** token (`DEFAULT_KENT_TOKEN_FILE`) and **refuses** the felix-bot path (`apply_reply.py:1001-1013`,
  #750/#715). Already at the target identity; retains its refusal guard; documented in SC-002, not re-pointed.

**Decision**: IC-01 adds the single point; IC-02 routes the client default (covers Group A);
IC-03 routes all 13 Group-B modules. Non-runtime literals stay as-is and are the *only* permitted
SC-001 matches, in two classes: (a) felix-bot-targeting admin/one-shot — `provision_felix_bot`,
`validate_felix_bot`, `swap_vikunja_secrets`; (b) kent-only admin tools whose felix literal is a
**refusal/guard** — `migrate_tasks` (`:78-82`), `create_saved_filters` (`:80-82`),
`reconcile_projects` (`:63-67`), plus `apply_reply`'s guard.

**Deployment fact (verified)**: the deployed drivers invoke Group B/C with **no** token args
(`ExecStart=/usr/bin/python3 -m scripts.habits.sweeper`; `… weekly_report_driver`); `--token-path` is a
local-testing surface only. So centralization is a pure code change with **zero deployment-argument
impact** — no manifest/systemd/cron edit needed for the token path.

## R3 — Resolution-helper design (mirror `get_vikunja_base_url`)

**Decision**: `get_vikunja_token_path() -> Path` in `scripts/common/vikunja_config.py`. Resolution order:
1. `VIKUNJA_TOKEN_PATH` env var (if set, non-empty) — the testing/override seam and the SC-002 lever.
2. Module default constant — the single place the runtime identity lives (felix-bot at IC-01, kent at IC-04).

Fail-loud: a missing/unreadable resolved file raises a single typed error from the helper/`VikunjaClient`
(NFR-002). `VikunjaClient._load_default_token()` calls the helper at call time (not import time, so tests
and env overrides work). `--token-path` CLI args keep working but default to `get_vikunja_token_path()`.

**Rationale**: exactly parallels the accepted `get_vikunja_base_url()` seam (#520) — same file, same
override-then-default shape, same test approach. Lowest-surprise, no new dependency.

**Alternatives**: a full config object / dataclass — rejected as over-engineering for a single path
(C-001, no abstract port); the base-URL helper set the house pattern and this matches it.

## R4 — SC-001 grep semantics (avoid the `-kent` false match)

**Decision**: the gate is a **tracked-text** ratchet `git grep -nE "secrets/vikunja-api([^-]|$)" -- scripts
':!**/__pycache__/**'` (not raw `grep -rnE`, which traverses `__pycache__` binaries — a Codex catch).
After IC-04 the single default is `…/vikunja-api-kent`; `([^-]|$)` deliberately excludes the `-kent` suffix
so the kent path is **not** a match. Only felix-bot literals (`…/vikunja-api` followed by non-`-`/EOL) match
— which post-flip must exist **only** in the enumerated non-runtime files of R2's two allowlist classes
(felix-targeting admin + kent-only refusal guards) and docs describing the dormant credential.

## R8 — Sync identity-expansion cutover gate (Codex MED)

**Decision**: Before the live cutover, run a **dry-run sync cycle under the kent token** and capture the
first-observation delta. Under kent, `sync/fetch.py:137-183` (`fetch_full_poll`) enumerates every visible
project and pages each project's tasks; kent newly sees projects 16–20 (R1), so the first live cycle
post-flip will observe a burst of new tasks + emit the corresponding events/cache writes. Gate the live
run on that delta being expected and bounded — do not let the first kent cycle be an unmeasured surprise.
IC-07 owns this; SC-004 records it.

## R9 — Sync failure-classification preservation (Codex MED)

**Decision**: `sync/cycle.py:141-157` currently catches only `OSError` in the preamble and records
`phase="preamble"`, `exit_code=1`. The new typed fail-loud helper (R3) can raise a non-`OSError`. IC-03
must adapt the helper's token-resolution/read failure into sync's existing preamble path so the
`cycle_error` token, phase, and exit code are unchanged — with a parity test. Otherwise a token failure
post-refactor would be classified differently than at HEAD (a silent behavior change NFR-001 forbids).

## R5 — Doc targets (signal-to-doc-map, confirmed)

- `mission-credential-added-or-modified` → `data/credential-manifest.json`, `credentials-and-secrets.md`,
  `identity-model.md`.
- `mission-architecture-doc-added` → `docs/INDEX.md`, `docs/DEVELOPER_PORTAL.md`,
  `docs/design/architecture/README.md` (ADR README/index) — for the new **ADR-0007**.
- Additional in-scope agent surface (not in the map; #831): `skills/vikunja-api/SKILL.md`,
  `skills/escalation/SKILL.md`, `agents/felix-admin-tasker/{TOOLS,AGENTS}.md`.
- `data-flows.(md|json)`: review — the flow shape is unchanged (poll Vikunja), only the caller identity;
  update only the token/identity annotation if present.

## R6 — ADR decision record

**Decision**: author **ADR-0007** "Retire Vikunja felix-bot; single kent-token runtime identity",
superseding ADR-0002's write-attribution rationale. ADR-0002 stays as the historical record, marked
`Superseded by ADR-0007`. Context: per-user object scoping (#715/#717) made agent-vs-human attribution
expensive and actively caused incomplete reads (#860). Consequence: runtime attributes to kent; felix-bot
Vikunja user dormant (attribution history preserved on existing tasks); GitHub `kg-felix-bot` unaffected.

## R7 — Validator convergence (#748, FR-005)

**Decision**: `scripts/vikunja/validate_refs.py` already defaults to the kent token; post-flip the runtime
*and* the validator use the same (kent) view, so the structural blindness that hid #860 (validator on kent,
runtime on felix-bot) is closed by construction. Confirm the validator's default token now equals
`get_vikunja_token_path()` (single source) rather than an independent literal, so they cannot re-diverge.
