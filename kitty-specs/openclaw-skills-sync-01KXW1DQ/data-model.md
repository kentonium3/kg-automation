# Data Model: OpenClaw Skills Deploy/Sync

Mission `openclaw-skills-sync-01KXW1DQ` (#775). No database — the "model" is the in-memory sync
units and the on-disk record/state shapes. All records are stdlib-JSON (no schema library).

---

## Entities

### SkillSyncUnit (in-memory)

One unit of sync work, produced by the repo-dir enumerator (FR-011, D-6).

| Field | Type | Notes |
|-------|------|-------|
| `skill` | str | skill name = repo skill dir basename (e.g. `vikunja-api`) |
| `source` | Path | `<repo_root>/scripts/openclaw/skills/<skill>/SKILL.md` (source of truth) |
| `dest` | Path | `/home/claude/.openclaw/skills/<skill>/SKILL.md` (deployed) |

**Enumeration rule**: iterate `sorted(<repo_root>/scripts/openclaw/skills/*/)`; for each dir
containing a `SKILL.md`, emit one unit. A dir with no `SKILL.md` emits a `warning` audit record and
is skipped. A dir that contains files **other than** `SKILL.md` also emits a `warning` audit record
(multi-file guard, FR-015) — the payload stays `SKILL.md` only. `--skill <name>` restricts to one
unit; an unknown name is a validation error (exit 3).

**Drift predicate**: `drift = compute_md5(source) != md5(dest)` where a missing `dest` counts as
drift (dst treated as `absent`); on a real (non-dry-run) copy the sync creates `dest.parent`
(`parents=True, exist_ok=True`) first (FR-016). Backup sidecars (`*.backup*`) in the dest dir are
never a sync target and never a drift subject (FR-004, FR-010).

---

## Record & state shapes (on-disk, under `/data/services/openclaw/deploy/`)

### Audit log — `agent-skill-sync.jsonl` (append-only JSONL)

One JSON object per line. Common fields: `timestamp` (`YYYY-MM-DDTHH:MM:SSZ`), `tick_id` (uuid4),
`kind`.

| `kind` | Extra fields |
|--------|--------------|
| `copy` | `skill`, `filename` (`SKILL.md`), `src_md5`, `dst_md5_before`, `dst_path` |
| `skip` | `skill`, `filename`, `src_md5`, `dst_md5_before` (unchanged; non-dry-run) |
| `warning` | `skill`, `error` (source dir/file missing, OR multi-file skill dir — FR-015) |
| `error` | `skill`, `filename`, `error`, `error_class` (copy raised) |
| `git_pull_failed` | `stage`, `reason`, `local_head`, `origin_head`, `behind`, `ahead`, `error` |
| `git_pull_skipped` | `stage: lock`, `reason: lock_unavailable` (benign defer) |
| `health_record_error` / `copy_health_record_error` | `error`, `error_class` (escalation never fatal) |
| `tick_summary` | `skills_processed`, `files_copied`, `files_skipped`, `files_errored`, `git_head_after_pull`, `exit_code`, `duration_ms` |

### Freshness pointer — `skills-last-tick.json` (flat JSON, canary-readable)

```json
{ "status": "success|deferred|git_pull_failed|partial", "exit_code": 0, "completed_at_utc": "…Z" }
```
Written on **every** real (non-dry-run) tick, including a benign lock-defer — it signals *timer
liveness*, so `exit_code` is always `0` (failures escalate via the health watermark + audit log, not
this pointer). `completed_at_utc` is the canary-recognized key judged against `max_age_seconds`.

### Health watermarks (streak-dedup, `scripts/deploy/lib/health` format)

- `agent-skill-sync-git-health.json` — git-advance failures (from `advance_checkout` reason).
- `agent-skill-sync-copy-health.json` — copy failures (`confirmed_reasons={"copy_failed"}`, skills
  `render`). Each fires **at most one** alert per confirmed-failure streak via the alert-bus
  notifier; a clean tick resets the streak.

### Independent drift check — `scripts/openclaw/enforcement/skills_drift_check.py` (D-4)

A standalone comparator (NOT the sync's code path), registered as a canary probe. Reads both sides
locally on office2 (checkout-repo `SKILL.md` vs deployed `SKILL.md`).

- **Compares**: `md5(checkout-repo SKILL.md)` vs `md5(deployed SKILL.md)` per skill; ignores
  `*.backup*` (FR-010).
- **Orphan detection (FR-014)**: enumerate deployed skill dirs; a deployed skill with no repo
  counterpart is reported (alert-only; not deleted — copy-only preserved).
- **Exit contract**: `0` = all match, no orphans; **non-zero** = drift and/or orphan present (the
  canary translates non-zero into a deduped alert). `--json` prints per-skill `{skill, state:
  match|drift|orphan, repo_md5, deployed_md5}` for the probe.
- **Canary registration** (`scripts/canary/registry.py`): a `command`-style probe invoking the
  comparator, inheriting the canary's cadence + alert-dedup — genuinely independent of the sync.

### Freshness health_check (service-inventory.json, Codex LOW-1)

```json
{ "endpoint": "/data/services/openclaw/deploy/skills-last-tick.json",
  "method": "tick-signal-file", "max_age_seconds": 600 }
```

---

## Exit-code contract (mirrors `deploy_agent_prompts`, per FR/NFR + quickstart)

| Code | Meaning |
|------|---------|
| 0 | success (no drift OR all copies succeeded; also a benign lock defer; also `--dry-run`) |
| 1 | partial failure (advance ok, ≥1 per-file copy failed) |
| 2 | git advance failed (fetch/merge/diverged — no copies attempted) |
| 3 | validation error (missing `.git/`, missing skills dir, unknown `--skill`) |

## Invariants

- **INV-1** Repo `SKILL.md` is the sole source of truth; `dest` converges to it (never the reverse).
- **INV-2** Copy-only: the sync never deletes a dest-side file (FR-004).
- **INV-3** Atomicity: a dest file is either its prior content or the fully-copied new content —
  never partial (temp-write + fsync + `os.replace`, mode preserved).
- **INV-4** Determinism: no LLM/agent judgment in the runtime path (NFR-006).
- **INV-5** The checkout-touching critical section runs under the shared `deploylock`; on contention
  the tick defers cleanly (exit 0, no copy) — never races felix-deployer / prompt-sync.
- **INV-6** One alert per failure streak (NFR-004); freshness pointer stays `exit_code=0`.
- **INV-7** First-run safety: `dest.parent` is created (`parents=True, exist_ok=True`) before the
  atomic copy (FR-016) — a missing deployed skill dir never fails the copy.
- **INV-8** Multi-file surfacing: a repo skill dir with files beyond `SKILL.md` emits a warning-audit
  (FR-015); the payload stays single-file. The independent drift check reports repo-absent deployed
  skills as orphans (FR-014).
- **INV-9** The health-notifier seam returns `alert_bus.emit(Alert(...)).ok` (the `AlertResult`
  field is `.ok`, never `.delivered`).
