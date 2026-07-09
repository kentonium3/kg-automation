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

| Condition | Range base for `observe()` | Watermark after tick |
|---|---|---|
| `W` absent (first run) | `pre_pull_head` (legacy fallback, FR-002) | advance (C4) |
| `W` valid ancestor of `post_pull_head` | `W` | advance (C4) |
| `W` provably invalid / non-ancestor (`git cat-file -e W^{commit}` fails OR `merge-base --is-ancestor W post` non-zero) | self-heal: use `post_pull_head` as base (`observe` → `not_required`) | advance (C4) |
| `W` present but git/diff fails for **any other** reason (transient: lock, malformed output) | `observe` → `not_required` | **UNCHANGED — retry next tick** (FR-004) |

- **Post-condition**: `observe(base, post_pull_head)` is called with `base` per the table.
  When `base != post_pull_head` and an audited-surface commit is in the range, a pending
  token is armed **even if `pre_pull_head == post_pull_head`** (the #685 repro).
- **Never** advance the watermark past an unverified range on a transient failure (Codex HIGH-1).

## C4 — Watermark advance (`run_tick`, end of tick)

- **`_record_success` returns a structured result** (`commit_sha`, `pushed`,
  `applied_path`, `error`); `commit_sha` is captured immediately after `git commit`,
  **even if the push fails** (Codex MED-1).
- **Post-condition**: watermark = the deployer's **last own `deploy(applied)` commit that
  is a descendant of `post_pull_head`**, or `post_pull_head` if no own commit this tick.
  (Deterministic "last own commit" — not a vague max-along-history and not a blind
  `rev-parse HEAD`.)
- **Never** re-observes a `deploy(applied)` commit: on the *next* idle tick,
  `observe(watermark, post_pull_head)` yields an empty range → `not_required` (SC-004).
- Advance MUST be crash-safe: a write failure logs and continues; the tick still returns 0.

## C5 — `fold_manifest_baselines(declared, *, observed_head_sha, manifest_names, token_path=None) -> dict`

- **`declared` empty** → no-op; returns `{"outcome":"not_required"}`. Legacy manifests
  (FR-009) hit this path.
- **Token exists** → union `declared` into `expected_baselines`, persist, return
  `{"outcome":"merged", ...}`.
- **No token exists** → create one with observe-like fields: synthetic
  `surface_ids:["manifest-declared"]`, `expected_baselines: sorted(declared)`,
  `observed_head_sha` = the passed value, `pending_since_utc` = now, `matched_files: []`,
  `last_check_utc: null`, `alerts_emitted: []`. `manifest_names` are recorded for outcome
  correlation. Returns `{"outcome":"created", ...}`.
- MUST NOT raise; MUST NOT run any audit (pure token mutation).

## C6 — Manifest validation (`validate_manifest`)

- `expected_baselines` absent → unchanged (valid as today).
- `expected_baselines` present:
  - every element ∈ known-baseline set → else **invalid**, error names the offender(s).
  - `audited_surface != true` → **invalid**, error states the coupling requirement.
- The known-baseline set is read from the registry via a **non-exiting** helper; a
  missing/malformed registry yields an **invalid-manifest error**, never `SystemExit`
  (Codex MED-2). A guard test asserts the derived union equals the 14-baseline inventory
  (Codex LOW).

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

## C8 — Same-tick clear grace rule (`reconcile`, FR-010, Codex HIGH-2)

- **Pre-condition**: a token exists and the read-only audit returns `D=∅`.
- **If** the token was created or folded **this tick** (its `pending_since_utc` is this
  tick, or its age < one tick) → **do NOT** `cleared_clean`. Leave the token, return/log
  `pending_clean`. A later tick re-checks.
- **Else** (token older than the grace window) → `cleared_clean` as today.
- Rationale: a deploy whose audited effect materializes *after* the same-tick audit must
  not have its pending rebaseline erased before the drift is observable. Applies to all
  tokens, not only manifest-declared ones.

## Invariants across all paths

- The tick returns `0` under any injected exception in a new code path (NFR-001).
- `check_audited_surface_drift.py` (CI reminder) imports the same `audited_surfaces`
  module and is unaffected by the manifest-schema change (NFR-005, C-002).
- No new runtime dependency is introduced (NFR-004).
