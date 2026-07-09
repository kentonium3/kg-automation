# Contract: Rebaseline Range & Manifest-Declared Baselines (v1)

Behavioral contract for the felix-deployer rebaseline engine after #685. Expressed as
observable pre/post-conditions per function, so tests can assert them directly using the
existing injection seams.

## C1 — `read_observed_head(watermark_path=None) -> str | None`

- **Absent file** → returns `None`. MUST NOT raise.
- **Corrupt/unreadable JSON** → returns `None`, logs WARNING. MUST NOT raise.
- **Valid** → returns `observed_head_sha`.

## C2 — `write_observed_head(sha, watermark_path=None) -> None`

- Writes `{schema_version:1, observed_head_sha:sha, updated_at:<utc>}` atomically
  (`.tmp` + `os.replace`), creating the parent dir if needed.
- On `OSError` → logs ERROR and returns (swallowed). MUST NOT raise (NFR-001/003).

## C3 — Tick observe-range selection (`run_tick`)

Given `pre_pull_head`, `post_pull_head`, and watermark `W`:

| Condition | Range base used for `observe()` |
|---|---|
| `W` present and reachable | `W` |
| `W` absent (first run) | `pre_pull_head` (legacy fallback, FR-002) |
| `W` present but unreachable (diff fails) | `observe` returns `not_required`; watermark advances anyway (FR-004) |

- **Post-condition**: `observe(base, post_pull_head)` is called with `base` per the table.
  When `base != post_pull_head` and an audited-surface commit is in the range, a pending
  token is armed **even if `pre_pull_head == post_pull_head`** (the #685 repro).

## C4 — Watermark advance (`run_tick`, end of tick)

- **Post-condition**: watermark = `post_pull_head` unioned (max along history) with the
  SHA(s) of `deploy(applied)` commits this tick captured from `_record_success`.
- **Never** re-observes a `deploy(applied)` commit: on the *next* idle tick,
  `observe(watermark, post_pull_head)` yields an empty range → `not_required` (SC-004).
- Advance MUST be crash-safe: a write failure logs and continues; the tick still returns 0.

## C5 — `fold_manifest_baselines(declared: set[str], token_path=None) -> dict`

- **`declared` empty** → no-op; returns `{"outcome":"not_required"}`. Legacy manifests
  (FR-009) hit this path.
- **Token exists** → union `declared` into `expected_baselines`, persist, return
  `{"outcome":"merged", ...}`.
- **No token exists** → create one (synthetic `surface_ids:["manifest-declared"]`,
  `expected_baselines: sorted(declared)`), persist, return `{"outcome":"created", ...}`.
- MUST NOT raise; MUST NOT run any audit (pure token mutation).

## C6 — Manifest validation (`validate_manifest`)

- `expected_baselines` absent → unchanged (valid as today).
- `expected_baselines` present:
  - every element ∈ known-baseline set → else **invalid**, error names the offender(s).
  - `audited_surface != true` → **invalid**, error states the coupling requirement.

## C7 — End-to-end reconcile classification (integration)

- **Out-of-band repro (Scenario 1)**: `pre==post` at the tick, but `W < post`, range
  contains a `scripts/office2/*.service` add → token armed with the systemd baselines →
  after the unit is deployed, reconcile sees `D = {enabled-services.txt,
  systemd-user-units.txt} ⊆ E` → `completed`.
- **CLI-mutation (Scenario 2)**: manifest declares `openclaw-cron.txt`; applied →
  `fold_manifest_baselines` puts it in `E` → reconcile sees `D ⊇ {openclaw-cron.txt},
  D ⊆ E` → `completed`, **not** `unexpected_drift`.
- **Self-commit (Scenario 3)**: idle ticks after a `deploy(applied)` commit →
  `observe` range empty → `not_required`; no spurious token.

## Invariants across all paths

- The tick returns `0` under any injected exception in a new code path (NFR-001).
- `check_audited_surface_drift.py` (CI reminder) imports the same `audited_surfaces`
  module and is unaffected by the manifest-schema change (NFR-005, C-002).
- No new runtime dependency is introduced (NFR-004).
