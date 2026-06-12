# Data Model: Pull-Based Deploy Pipeline

**Mission**: `pull-based-deploy-pipeline-01KTYQQS`
**Phase**: 1 (design; depends on research.md)

Entities, relationships, invariants, and state transitions for the deploy pipeline. Most surfaces are file-system based (no DB); models are described as the on-disk shapes the library and applier read and write.

---

## Entities

### Manifest

A YAML file declaring intent to deploy. Authored by an operator or coding agent; lives in `deploys/queued/<name>.yaml` before apply, `deploys/applied/<seq>-<name>.yaml` after success.

**Schema v1** (see `contracts/manifest-v1.schema.json` for the canonical shape):

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | `"v1"` (changes only on schema migrations) |
| `name` | string | yes | kebab-case identifier, e.g. `inbox-prescan-helper-2026-06-15` |
| `mission_slug` or `issue` | string | yes-one-of | Source mission slug OR `kentonium3/kg-automation#NNN` |
| `tier` | integer | yes | 0–4 per change-risk-taxonomy.json; 0 always rejected |
| `entrypoint` | string | yes | Repo-relative path to the deploy script the applier invokes (`scripts/deploy/...sh` or `scripts/deploy/...py`) |
| `audited_surface` | boolean | yes | True if the deploy touches a path in `audited-surfaces.json` |
| `verification` | object | conditional | Required when `tier` ∈ {1, 2}; describes pre/post verification steps |
| `verification.pre` | array<string> | conditional | Pre-flight verification commands (must succeed before apply) |
| `verification.post` | array<string> | conditional | Post-flight verification commands (must succeed for apply to be recorded as success) |
| `notes` | string | optional | Free-text context for the operator |
| `created_at` | string (ISO 8601) | yes | Authoring timestamp |
| `created_by` | string | yes | Author identifier (operator handle or `kg-felix-bot`) |

### Applied Manifest

A Manifest that has been successfully applied. Same schema with two additions:

| Field | Type | Required | Description |
|---|---|---|---|
| `apply_mode` | string | yes | `manifest` for normal; `bootstrap` for the canonical first entry written by the bootstrap wrapper |
| `applied_at` | string (ISO 8601) | yes | When the applier recorded success |

The filename gets a sequential prefix: `deploys/applied/<NNNN>-<name>.yaml` where `NNNN` is monotonic. The bootstrap entry is `0001-bootstrap-felix-deployer.yaml`.

### Failure Record

Written next to a manifest in `deploys/failed/<name>-<ts>.yaml` when an apply fails. The manifest itself stays in `deploys/queued/` — operator decides whether to fix and retry, or delete to cancel.

| Field | Type | Required | Description |
|---|---|---|---|
| `manifest_name` | string | yes | The `name` of the manifest that failed |
| `failed_at` | string (ISO 8601) | yes | When the applier detected failure |
| `phase` | string | yes | One of: `tier_guard`, `verification_pre`, `entrypoint`, `verification_post` |
| `exit_code` | integer | conditional | Subprocess exit code if applicable |
| `error_summary` | string | yes | Truncated stderr/error message (≤500 chars) |
| `tick_log_excerpt` | string | optional | Last N lines of the applier tick log for context |

### Tick Log Entry

One JSON-shaped line appended to `/data/services/felix-deployer/logs/<YYYY-MM-DD>.jsonl` per tick. Followed by one line per processed manifest within that tick.

| Field | Type | Description |
|---|---|---|
| `ts` | string (ISO 8601) | Tick wall-clock time |
| `event` | string | `tick_start`, `tick_skip` (e.g., git pull fail), `manifest_processed`, `tick_complete` |
| `head_sha` | string | post-pull HEAD SHA |
| `queue_count` | integer | manifests found in queue this tick |
| `manifest_name` | string | (for `manifest_processed`) which manifest |
| `outcome` | string | (for `manifest_processed`) `applied`, `failed_<phase>`, `tier_0_rejected` |

### Library Primitive Result

Each library primitive (`cron.openclaw_cron_disable`, `verify.verify_file_present`, etc.) returns a `LibResult` dataclass:

| Field | Type | Description |
|---|---|---|
| `ok` | boolean | Did the primitive succeed |
| `summary` | string | One-line outcome |
| `details` | dict | Optional structured detail (for failure debugging) |

See `contracts/deploy-library-api.md` for the full API.

---

## Invariants

These properties MUST hold across all valid system states.

1. **Tier 0 never executes**: a Tier 0 manifest is rejected by CI at PR time AND by the applier at execute time. If the applier ever sees a Tier 0 manifest in the queue, it writes a `tier_0_rejected` failure record and does NOT call the entrypoint.
2. **Tier 1/2 manifests carry verification**: schema requires `verification` object when `tier ∈ {1,2}`. CI rejects manifests violating this.
3. **Failure record exists iff queue entry persisted**: every manifest that the applier attempted but did not successfully apply produces exactly one failure record per attempt. The manifest stays in the queue; only successful applies move out.
4. **Applied manifests are append-only**: nothing rewrites or deletes `deploys/applied/<NNNN>-*.yaml` entries. They are the audit trail.
5. **No openclaw cron payloads write to system crontab**: enforced by `lib/cron.py` — every primitive uses `openclaw cron` subcommands. CI greps `scripts/deploy/lib/` for `crontab` literals as a static check (#162 prevention).
6. **The applier never opens a network listener**: it only initiates outbound (`git pull`, `openclaw cron run`). No serving surface.
7. **Doctrinal cross-link graph is closed**: every node referenced in the IC-06 graph (plan.md "Doctrinal cross-link graph") points at a node that exists and back-links where the graph specifies. CI walks this graph on every PR.

---

## State transitions

### Manifest lifecycle

```
        ┌─────────────────────────┐
        │  Author writes YAML     │
        │  → deploys/queued/      │
        └──────────┬──────────────┘
                   │ PR merged to main
                   ▼
        ┌─────────────────────────┐
        │  Applier tick discovers │
        │  manifest in queued/    │
        └──────────┬──────────────┘
                   │
                   ▼
        ┌─────────────────────────┐
        │  tier_guard()           │
        │  Tier 0? → fail         │
        └──────────┬──────────────┘
                   │ pass
                   ▼
        ┌─────────────────────────┐
        │  verification.pre[]     │
        │  Any fail? → fail       │
        └──────────┬──────────────┘
                   │ pass
                   ▼
        ┌─────────────────────────┐
        │  invoke entrypoint      │
        │  Exit != 0? → fail      │
        └──────────┬──────────────┘
                   │ pass
                   ▼
        ┌─────────────────────────┐
        │  verification.post[]    │
        │  Any fail? → fail       │
        └──────────┬──────────────┘
                   │ pass
                   ▼
        ┌─────────────────────────┐
        │  Write applied entry    │
        │  git mv queued/ → app./ │
        │  Commit + push          │
        └──────────┬──────────────┘
                   │
                   ▼ (success)
        ┌─────────────────────────┐
        │  Manifest is in         │
        │  deploys/applied/       │
        └─────────────────────────┘

  Any "fail" branch:
        ┌─────────────────────────┐
        │  Write failure record   │
        │  → deploys/failed/      │
        │  Manifest stays queued  │
        │  Dispatch WhatsApp DM   │
        │  No auto-retry          │
        └─────────────────────────┘
```

### Library primitive composition (apply)

The `apply.dry_run_then_apply_gate` orchestrator is the canonical sequence. Each step is a library call; each result is a `LibResult`.

```
1.  tier.tier_guard(manifest, mode='runtime') → LibResult
2.  if tier ∈ {2}: snapshot.verify_restic_recent(max_age_h=24) → LibResult
3.  for cmd in manifest.verification.pre: shell(cmd) → LibResult
4.  shell(manifest.entrypoint + ['--dry-run']) → LibResult   # mandatory dry-run first
5.  shell(manifest.entrypoint + ['--apply']) → LibResult     # only if dry-run succeeded
6.  for cmd in manifest.verification.post: shell(cmd) → LibResult
7.  if all ok: notify.success_record() and applied/ move
   else: notify.dispatch_failure_dm(payload) and failed/ write
```

---

## Externally visible events

- **PR merged with a new queued/ manifest** — triggers the applier's next tick (passive; applier just polls).
- **Applier success** — appends a `manifest_processed:applied` line to the tick log; commits the applied/ move and pushes; no DM.
- **Applier failure** — invokes `openclaw cron run felix-deployer-alert` with a synthesized payload containing manifest name, tier, failure phase, and error summary. openclaw delivers the WhatsApp DM via the existing felix-admin pathway.
- **Tier 0 PR open** — CI fails; no merge, no applier involvement.

No webhooks, no push notifications outside the already-existing felix-admin DM surface.
