# Data Model: Robust Felix-Deployer Rebaseline Detection

Phase 1 output. Three data surfaces: one new (watermark), one extended (pending token),
one extended (manifest). All JSON except the manifest (YAML).

## Entity: Observe Watermark (NEW)

**File**: `/data/services/felix-deployer/state/rebaseline-observed-head.json`
(injectable via `watermark_path` for tests). Written atomically (`.tmp` + `os.replace`).

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | `1`. |
| `observed_head_sha` | str | The last HEAD felix-deployer fully processed for observe. Range base for the next tick. |
| `updated_at` | str | UTC ISO-8601 (`%Y-%m-%dT%H:%M:%SZ`), diagnostic only. |

**Invariants**:
- Absent file ⇒ no watermark yet ⇒ range base falls back to the tick's `pre_pull_head`
  (FR-002). Absent/corrupt is never an error (returns `None`, mirrors `read_token`).
- After a tick, `observed_head_sha` = `post_pull_head` extended only by the deployer's
  own `deploy(applied)` commit SHA(s) made that tick (R1) — never a blind `HEAD` resolve.
- `observed_head_sha` is only ever advanced forward along the ff-only history; on an
  unreachable SHA the range diff fails safe and the watermark advances to `post_pull_head`
  (FR-004).

**Lifecycle** (per tick):
1. `base = read_observed_head() or pre_pull_head`
2. `observe(base, post_pull_head)` → may arm/merge the pending token
3. `fold_manifest_baselines(declared)` → merges declared baselines into token
4. `reconcile()` → may rebaseline + clear token
5. `write_observed_head(post_pull_head, own_commits)` → advance watermark

## Entity: Pending Rebaseline Token (EXTENDED — no schema change)

**File**: `/data/services/felix-deployer/state/rebaseline-pending.json` (unchanged path
and `schema_version: 1`).

The only behavioral change: `expected_baselines` may now be populated from **two**
sources unioned together — (a) git-diff-matched audited surfaces (as today, via
`observe`) and (b) manifest declarations (via `fold_manifest_baselines`). No field is
added or removed; existing tokens remain valid (C-003).

When `fold_manifest_baselines` must create a token from scratch (no prior observe match
this tick), it uses:
- `surface_ids`: `["manifest-declared"]` (synthetic marker)
- `expected_baselines`: the declared set
- `matched_files`: `[]`
- other fields identical to `observe`'s create path (`pending_since_utc`,
  `observed_head_sha`, `last_check_utc: null`, `alerts_emitted: []`).

## Entity: Deploy Manifest (EXTENDED — schema change)

**File**: `deploys/queued/<name>.yaml` → `deploys/applied/NNNN-<name>.yaml`.
**Schema**: `deploys/schema/manifest-v1.schema.json` (`additionalProperties: false`).

New optional field:

| Field | Type | Notes |
|---|---|---|
| `expected_baselines` | array[str] | Baseline filenames this deploy is expected to drift (e.g. `["openclaw-cron.txt"]`). Each MUST be in the registry's known-baseline set (the 14-name union of `affected_baselines` ∪ `non_repo_baselines[].name`). |

**Validation rules** (`validate_manifest`):
- If present, every element MUST be a known baseline name → else validation error naming
  the offending value(s) (FR-007).
- If present, `audited_surface` MUST be `true` → else validation error (R2 coupling).
- Absent field ⇒ unchanged behavior (FR-009).

## Known-baseline set (validation source, derived — not stored)

Union computed at validation time from `docs/design/architecture/data/audited-surfaces.json`:

```
brew-packages.txt, brew-taps.txt, crontabs.txt, docker-images.txt,
enabled-services.txt, hosts-hash.txt, listening-ports.txt, openclaw-config.txt,
openclaw-cron.txt, pip-packages.txt, pth-files.txt, ssh-keys.txt,
systemd-user-dropins.txt, systemd-user-units.txt
```

(14 names; equals `expected_baseline_count`. Verified live 2026-07-09.)
