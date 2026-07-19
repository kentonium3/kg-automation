# Research: OpenClaw Skills Deploy/Sync

Phase 0 research for mission `openclaw-skills-sync-01KXW1DQ` (#775). Each decision was validated by
probing the real environment (DIR-015) — office2 filesystem, `openclaw.json`, the shared deploy
libs, and `health.record`.

---

## D-1 — Parallel module vs. extending `deploy_agent_prompts.py`

**Decision**: Build a **parallel module** `scripts/openclaw/deploy/deploy_agent_skills.py`.

**Rationale**:
- `deploy_agent_prompts.py` (~900 lines) is tightly coupled to the **agent-inventory scope model**:
  `iter_agents()` reads `service-inventory.json → services[openclaw].agents.*`, each agent carrying
  `source_in_repo` + `workspace`, and `is_in_scope()` allowlists a 5-file set
  (`AGENTS/IDENTITY/SOUL/TOOLS/USER.md`). Skills have a *different* scope model: one directory per
  skill under `scripts/openclaw/skills/`, a **single** `SKILL.md`, and a **different dest base**
  (`/home/claude/.openclaw/skills/`, not an agent `workspace`).
- Overloading the prompt helper with a second scope model would entangle a **load-bearing
  silent-failure guard** (the #563-class prompt sync) with unrelated logic — higher regression risk,
  violates DIRECTIVE_024 (locality of change).
- A parallel module keeps the prompt path untouched and gives the skills sync clean ownership,
  its own audit log, health watermark, freshness pointer, and systemd unit — operationally
  symmetric with prompt-sync.

**Reuse without duplication**:
- Import as-is from `scripts/deploy/lib/`: `gitsync.advance_checkout` (race-immune fast-forward),
  `deploylock.deploylock` (shared checkout lock — the skills tick MUST take it so it never races
  felix-deployer / prompt-sync on `/home/claude/kg-automation`), `health.record` (streak-dedup
  watermark).
- The two generic primitives currently defined *inside* the prompt module — `compute_md5` (chunked
  hashlib) and `atomic_copy` (temp-write + fsync + mode-preserve + `os.replace`) — are **duplicated
  locally** (~40 trivial stdlib lines). Two call sites is within the rule-of-three; extracting a
  shared `scripts/openclaw/deploy/_sync_common.py` is deferred until a third consumer appears, so we
  don't refactor the working prompt file for this mission.

**Alternatives considered**:
- *Extend the prompt module* — rejected: entangles the load-bearing guard, two scope models in one
  file.
- *Extract a shared sync framework now* — rejected: premature; only two consumers; refactoring the
  silently-failing-guard prompt path carries avoidable regression risk (revisit at consumer #3).

---

## D-2 — Deployed target path (DIR-008: read real paths, don't infer)

**Decision**: Sync to `/home/claude/.openclaw/skills/<skill>/SKILL.md` (filesystem convention).

**Evidence**:
- `find` on office2 located the six deployed skills at `/home/claude/.openclaw/skills/<skill>/SKILL.md`
  (post-#653 relocation into claude-user space). `vikunja-api` carries a leftover
  `SKILL.md.backup.2026-04-10` sidecar (evidence of the ad-hoc hand-edit workflow being replaced).
- **`openclaw.json`'s `skills` block is a *different* subsystem** — an npm-plugin skill registry
  (`skills.install.nodeManager: npm`, `skills.entries: {1password, slack, …}` all `enabled: false`).
  Our six custom `SKILL.md` skills are **not** in that map; they live on the filesystem and are read
  by agents at runtime (proven by #734: the deployed `vikunja-api` skill still presented the deleted
  Goals project). Do **not** conflate the two — the sync targets the filesystem skill dirs, not the
  openclaw.json plugin registry.
- There is no configurable skills-dir *path* key in `openclaw.json` to read; the path is the stable
  `~/.openclaw/skills/` convention, verified empirically. The helper takes it as a documented
  constant with an override for tests.

---

## D-3 — Failure alerting integration

**Decision**: Reuse `scripts/deploy/lib/health.record` for the streak-dedup watermark, with a
notifier seam that dispatches via **`scripts.common.alert_bus.emit(Alert(...))`** and returns
**`result.ok`**.

**Evidence / rationale**:
- `health.record(actor, result, *, state_path, notifier, confirmed_reasons=…, render=…)` calls
  `notifier(title, body) -> bool` and stamps `last_alert_ts` **only on delivered=True**, firing at
  most one alert per confirmed-failure streak (verified in `health.py`). A `None`/raising/False
  notifier never crashes the tick and leaves the crossing unstamped for retry.
- **Notifier contract (verified in `scripts/common/alert_bus/model.py`)**: `emit(Alert) ->
  AlertResult`, and `AlertResult` exposes **`.ok`** (+ `reason`, `topic_configured`) — there is **no
  `.delivered`** field. The notifier seam MUST `return emit(Alert(...)).ok`. Using `.delivered`
  would raise `AttributeError`, which `health.record` catches and treats as *undelivered* → the
  failure-streak crossing never stamps and **never alerts** (a silent-alert bug). *(Codex #1 HIGH-2.)*
- `Alert` requires `source, severity, title, description` (non-empty; `__post_init__` raises
  otherwise) + optional `action`, `details: dict[str,str]`. The two watermarks pass a
  skills-accurate `render` producing `(title, body)`; the notifier maps that to
  `Alert(source="agent-skill-sync", severity=Severity.<…>, title=title, description=body)`.
- `scripts.common.alert_bus` is the **canonical unified bus**. prompt-sync reaches it indirectly by
  `importlib`-loading felix-deployer's hyphenated-dir `notify.py` (a vestigial wrapper over the same
  bus). Calling `alert_bus.emit` directly is cleaner, avoids the importlib dance, and delivers to the
  same topic (`FELIX_ALERT_NTFY_TOPIC`).
- Two watermarks mirror prompt-sync's structure: a **git-advance** watermark (from
  `advance_checkout`'s reason) and a **copy-failure** watermark (`confirmed_reasons={"copy_failed"}`
  + a skills-accurate `render`), so a persistent copy failure — a deployed skill silently not
  updating, the #563 class — fires one alert.

---

## D-4 — Drift check design (INDEPENDENT, alert-only) — revised after Codex #1 HIGH-3

**Decision**: The drift check is a **standalone comparator**
`scripts/openclaw/enforcement/skills_drift_check.py`, independent of the sync's code path,
registered as a **canary probe** (`scripts/canary/registry.py`, the established independent-observer
surface, #327). It directly MD5-compares each checkout-repo `SKILL.md` against its deployed copy,
alert-only, ignoring `*.backup*` (FR-010), and reports **orphans** — deployed skills with no repo
counterpart (FR-014). The sync's `--dry-run` remains an operator convenience but is **not** the
FR-009 mechanism.

**Why the original (sync `--dry-run` = drift check) was wrong** *(Codex #1 HIGH-3)*:
- It shares the sync's code path, so a bug in the sync's comparison would hide in both — not an
  independent check.
- Because the sync overwrites office2 every tick, a dry-run using the same checkout/code could be
  masked by the next remediating tick; it doesn't independently prove the deployed surface.

**Revised rationale**:
- A separate comparator run by the **canary** is genuinely independent (a different observer process,
  its own cadence + alert-dedup) and can catch the case the sync itself can't see: *sync reports
  success but the deployed file still differs*, plus repo-removed **orphans** (FR-014, Codex
  MEDIUM-3) that copy-only intentionally leaves in place.
- The comparator runs **on office2** (where the canary runs), reading both the checkout-repo and the
  deployed file locally — no SSH round-trip. Exit non-zero on drift/orphan; the canary translates
  that into an alert with dedup.
- The existing `scripts/openclaw/enforcement/drift_check.py` + `detection.py` is an **agent
  baseline-manifest three-way diff** (`factory-baselines.json`/`baseline-manifest.json`, per-agent
  `tracked_files`). Skills have no baseline manifest and a single-file model — the standalone
  comparator is cleaner than force-fitting skills into that engine. It lives beside it in
  `scripts/openclaw/enforcement/` for discoverability.
- Complementary coverage: sync **not running** → freshness canary (`skills-last-tick.json` staleness)
  + health watermark; sync running but a file **persistently fails to copy** → copy-health watermark;
  deployed file **differs despite reported success** or **orphan** → this independent drift probe.

---

## D-5 — Deploy vehicle + the `systemctl --user` caveat

**Decision**: Deploy through a **`deploys/queued/skills-sync.yaml`** manifest (DIR-004, **tier: 3**)
whose entrypoint `scripts/deploy/deploy-skills-sync.sh` runs a **HARD verify-before-enable gate**
(mirroring `deploy-felix-canary.py` / `deploy-habits-weekly-driver.py`): (a) pre-flight, (b) confirm
the new helper + units are present in the shared checkout, (c) copy `.service`/`.timer` into
`~/.config/systemd/user/`, (d) `systemctl --user daemon-reload`, (e) **smoke** — `systemctl --user
start agent-skill-sync.service` once and assert it wrote `skills-last-tick.json`, (f) **only then**
`systemctl --user enable --now agent-skill-sync.timer`, (g) assert `is-enabled` + the timer appears
in `list-timers`. All `systemctl --user` calls export `XDG_RUNTIME_DIR=/run/user/$(id -u)`. A failed
smoke/enable **fails the deploy loudly** (felix-deployer marks it failed + alerts).

**Evidence / rationale** *(Codex #1 HIGH-1)*:
- **`systemctl --user` works from the deploy pipeline** — verified precedent:
  `scripts/deploy/deploy-felix-canary.py` (verify-before-enable gate: run the real unit once, assert
  its output, then `enable --now`) and `scripts/deploy/deploy-habits-weekly-driver.py`
  (`daemon-reload` → `enable --now` → `is-enabled` → `list-timers` assertions). So the enable is a
  **hard gate**, not best-effort: an installed-but-not-running timer is exactly the stranded-edit
  failure this mission exists to eliminate — silently "applying" it would defeat the mission.
- **`XDG_RUNTIME_DIR` caveat (probed)**: a non-login ssh session reports `systemctl --user
  is-system-running` = `degraded` and can't see the linger-run units; the deploy entrypoint therefore
  exports `XDG_RUNTIME_DIR=/run/user/$(id -u)` (as the precedent scripts do) so `--user` resolves.
- No chicken-and-egg: helper code + units + manifest + entrypoint land in the **same merge commit**;
  felix-deployer advances the checkout *then* scans `deploys/queued/`, so the entrypoint is present
  when applied (unlike prompt-sync #667, whose fix repaired the pull path and needed a manual
  bootstrap — 0012).
- **Audited-surface globs must be extended** (Codex #1 MEDIUM-1): `audited-surfaces.json`'s
  `systemd-user-units` currently matches `scripts/office2/*.{service,timer}` (not
  `scripts/openclaw/deploy/*`) and `deploy-pipeline` matches `scripts/deploy/lib/**` (not the new
  `deploy-skills-sync.sh`). The mission extends those globs so C-002's rebaseline claim actually
  holds; otherwise the new surfaces would be silently unmonitored.
- **Audited surface**: the manifest sets `audited_surface: true` (new systemd unit + deploy script).
  On the felix-deployer happy path the auto-rebaseline (#685 watermark) covers it; the merge commit
  records the rebaseline outcome per `security-baseline-ops.md`. Confirm the audited-surface globs in
  `audited-surfaces.json` already match `scripts/deploy/**` + the new unit (extend if not).

---

## D-6 — Sync surface + scope enumeration

**Decision**: Enumerate scope from the repo dir `scripts/openclaw/skills/*/SKILL.md` (FR-011); one
`(skill_name, repo_path, deployed_path)` unit per skill. Copy-only, never prune (FR-004); the drift
check and sync both ignore office2-side `*.backup*` sidecars (FR-010).

**Evidence**:
- Repo and office2 each hold exactly the same six skills (`doc-audit`, `escalation`, `skill-author`,
  `task-intelligence`, `vikunja-api`, `whisper`), each dir containing exactly one file, `SKILL.md`
  (verified). No orphan in either direction *today*. Deriving scope from the repo dir means a newly
  added skill dir is picked up with no code change; a skill removed from the repo stops being synced
  and its deployed copy is left in place per copy-only — but that residual is **not silent**: the
  independent drift check reports it as an **orphan** (FR-014, D-4). A future prune *policy* is out
  of scope.
- Current drift is real and months-deep (deployed mtimes: whisper 03-28, skill-author 04-01,
  vikunja-api 04-10, doc-audit 05-12, task-intelligence 05-23, escalation 07-14) — the first live
  sync will converge all drifted skills.

**Two guards folded from Codex #1**:
- **First-run dest-dir creation (FR-016, Codex MEDIUM-5)**: the sync creates `dest.parent`
  (`parents=True, exist_ok=True`) before the atomic copy — mirroring `deploy_agent_prompts.sync_agent`
  (`agent.workspace.mkdir(...)`) — so a missing `/home/claude/.openclaw/skills/<skill>/` on a new
  skill or repaired host doesn't fail every copy.
- **Multi-file guard (FR-015, Codex MEDIUM-4)**: A4 keeps the payload single-file (`SKILL.md`) for the
  current 6, but if a repo skill dir gains any other file the sync emits a **warning-audit** record
  so the (out-of-scope) multi-file expansion is surfaced, not silently dropped. A test asserts the
  warning fires.
- **`atomic_copy` note (Codex LOW-2)**: the duplicated `read_bytes()` whole-file copy is acceptable
  because `SKILL.md` files are small markdown; if skills later carry large assets, switch to a
  streaming temp write (revisit with the multi-file guard).

---

## Testing approach (DIRECTIVE_034, test-first)

- **Unit**: `compute_md5`, `atomic_copy` (mode-preserve, temp-cleanup on failure), scope enumerator
  (repo-dir derivation, empty/malformed dir), `is_in_scope`/backup-ignore, drift computation,
  exit-code mapping, audit-record shapes, health-watermark integration (mock notifier), `--dry-run`
  writes nothing.
- **Integration**: temp repo + temp "deployed" dir → induce drift → sync converges + audit records;
  idempotent no-op (0 writes/0 alerts); induced copy failure → exit 1 + copy-health streak alert
  (mock notifier delivered/undelivered); `*.backup*` ignored; `--dry-run` prints DRIFT and mutates
  nothing.
- Use a **normalizing** fixture for the deployed side (store bytes as they'd land) so an echo-only
  mock can't hide a divergence — mirrors the mock-vs-live lesson banked from #757.
- The lock/gitsync path is exercised with the shared-lib seams; the deploylock contention → clean
  defer (exit 0, no copy) case is covered.
