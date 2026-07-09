---
work_package_id: WP01
title: Watermark range, fold & grace (rebaseline engine + tick)
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-006
- FR-008
- FR-009
- FR-010
- NFR-001
- NFR-002
- NFR-003
tracker_refs: []
planning_base_branch: fix/felix-deployer-rebaseline-detection
merge_target_branch: fix/felix-deployer-rebaseline-detection
branch_strategy: Planning artifacts for this mission were generated on fix/felix-deployer-rebaseline-detection. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-deployer-rebaseline-detection unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
- T008
agent: "claude:opus:python-pedro:implementer"
history: []
agent_profile: python-pedro
authoritative_surface: scripts/deploy/felix-deployer/rebaseline.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/deploy/felix-deployer/rebaseline.py
- scripts/deploy/felix-deployer/_tick.py
- tests/deploy/test_rebaseline.py
- tests/deploy/test_tick_rebaseline.py
role: implementer
tags: []
shell_pid: "10163"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries,
and TDD discipline for this WP.

## Objective

Fix the primary #685 defect and its two folded-in Codex findings inside the felix-deployer
rebaseline engine and tick. Make the observe range **watermark-based** so it is complete
regardless of which actor advanced the checkout HEAD; capture the deployer's own commit
SHA so we never re-observe our bookkeeping commits; add a **same-tick clear grace rule**;
and add **`fold_manifest_baselines`** so manifest-declared baselines enter the pending
token. All changes are stdlib-only and fully unit-tested via the existing injection seams.

Read before coding: `../spec.md`, `../plan.md` (IC-01, IC-03), `../research.md` (R1, R4,
R7), `../data-model.md`, `../contracts/rebaseline-range-and-baselines-v1.md` (C1–C8).

## Context

- `scripts/deploy/felix-deployer/rebaseline.py` — the deferred-confirm engine.
  `observe(pre, post)` returns `not_required` when heads are equal (line ~212);
  `reconcile()` clears the token on `D=∅` (`cleared_clean`, ~574). Token store =
  `read_token`/`write_token`/`clear_token` (atomic tmp+os.replace). Paths are module
  constants and injectable via params.
- `scripts/deploy/felix-deployer/_tick.py` — `run_tick()` captures `pre_pull_head`
  before `git pull --ff-only` and `post_pull_head` after, then calls
  `observe(pre_pull_head, post_pull_head)` AFTER the queue loop. `_record_success()`
  returns `(bool, str)` and treats "commit ok, push failed" as failure.
- **Root cause**: an out-of-band `git pull origin main` advances HEAD before the tick, so
  the tick's own pull is a no-op, `pre==post`, and observe is skipped entirely.

### Reused signatures (do not guess — these exist in `rebaseline.py`)

```python
def read_token(token_path=None) -> dict | None            # absent/corrupt -> None, never raises
def write_token(token, token_path=None) -> None           # atomic; OSError swallowed+logged
def clear_token(token_path=None) -> None
def observe(pre_pull_head, post_pull_head, *, token_path=None, git_runner=None, registry=None) -> dict
def reconcile(*, token_path=None, audit_runner=None, registry=None, max_age_seconds=MAX_AGE_SECONDS, baselines_dir=None) -> dict
DEFAULT_STATE_DIR = pathlib.Path("/data/services/felix-deployer/state")
OUTCOME_* constants; token fields: schema_version, pending_since_utc, observed_head_sha,
  surface_ids, expected_baselines, matched_files, last_check_utc, alerts_emitted
```

Follow the same style: injectable path params defaulting to module constants, atomic
writes, `_log` at WARNING/ERROR, never raise out of engine functions.

---

### T001 — Watermark read/write

**Purpose**: Persist the last-observed head so the range survives out-of-band pulls.

**Steps** (`rebaseline.py`):
1. Add `DEFAULT_OBSERVED_HEAD_PATH = DEFAULT_STATE_DIR / "rebaseline-observed-head.json"`.
2. `read_observed_head(watermark_path=None) -> str | None` — return `observed_head_sha`
   from the JSON; absent file → `None`; corrupt JSON / OSError → `None` + WARNING log
   (mirror `read_token`). Never raise.
3. `write_observed_head(sha, watermark_path=None) -> None` — atomically write
   `{"schema_version": 1, "observed_head_sha": sha, "updated_at": <utc iso>}` via
   tmp + `os.replace`, creating parent dir; OSError → ERROR log + swallow. Never raise.
4. Export both in `__all__`.

**Validation**: absent → None; round-trip; corrupt file → None; unwritable dir → no raise.

### T002 — Watermark validity classification + range-base selection

**Purpose**: Only self-heal when the watermark is *provably* invalid; never advance past
an unverified range on a transient failure (Codex HIGH-1, FR-004, contract C3).

**Steps**: Add a helper (in `rebaseline.py`, injectable `git_runner`) that, given the
watermark `W` and `post_pull_head` and a git runner, returns a classification:
- `W` is `None` → `("fallback", None)` — caller uses `pre_pull_head`.
- `git cat-file -e "<W>^{commit}"` non-zero **or** `git merge-base --is-ancestor <W> <post>`
  non-zero → `("self_heal", post)` — use `post` as base (empty range → `not_required`),
  advance watermark.
- Both succeed → `("valid", W)` — use `W` as base.
- Any git invocation error that is *neither* of the above deterministic checks (e.g. the
  runner raises / returns an unexpected non-zero for cat-file due to a lock) → treat as
  `("transient", None)` — caller leaves the watermark UNCHANGED and skips advance this tick.

Keep this classification a pure function of the injected runner's results so tests can
drive every branch. Do NOT modify `observe()`'s signature.

**Validation**: each branch (`fallback`/`self_heal`/`valid`/`transient`) selectable via a
fake git runner.

### T003 — Structured `_record_success` + wire observe range base

**Purpose**: Capture the deployer's own commit SHA even when push fails (Codex MED-1), and
feed the watermark-based range into observe.

**Steps** (`_tick.py`):
1. Change `_record_success(...)` to return a small structured result — a dataclass or
   dict with `ok: bool`, `commit_sha: str | None`, `pushed: bool`, `applied_path: str|None`,
   `error: str|None`. Capture `commit_sha` immediately after a successful `git commit`
   (resolve HEAD), **before** attempting push; set `pushed` from the push result. A failed
   push still returns `ok=False` for queue purposes but MUST carry the captured
   `commit_sha`. Update the single call site in `run_tick`.
2. In `run_tick`, before calling observe: read watermark `W = read_observed_head()`;
   classify via T002; select the range base per the table (fallback → `pre_pull_head`).
   Call `observe(base, post_pull_head)`. Preserve the existing tick-log
   `rebaseline_observe` entry (add the resolved `base` and a `range_source` field:
   `watermark|fallback|self_heal`).

**Validation**: push-fail path still returns the captured `commit_sha`; observe called
with the classified base.

### T004 — Watermark advance (crash-safe)

**Purpose**: Advance the watermark past our own bookkeeping commit without a mid-tick race
(FR-003, contract C4).

**Steps** (`_tick.py`, end of the rebaseline block): collect the `commit_sha`s captured
from `_record_success` this tick. Set the new watermark to the **last** such SHA that is a
descendant of `post_pull_head` (verify with `git merge-base --is-ancestor post <sha>`), or
`post_pull_head` if none. Skip the advance entirely when T002 returned `transient`. Wrap
in try/except → log + continue (never crash). Emit a `rebaseline_watermark` tick-log entry
with the new value.

**Validation**: idle tick after a `deploy(applied)` commit → next tick observes an empty
range → `not_required` (SC-004); transient classification → watermark unchanged.

### T005 — Same-tick clear grace rule

**Purpose**: Don't erase a token whose drift hasn't had a chance to appear (Codex HIGH-2,
FR-010, contract C8).

**Steps** (`rebaseline.py`, in `reconcile()` where `drifted == set()` → `cleared_clean`):
before clearing, compute the token age from `pending_since_utc` vs now. If age is within
one tick (use a `grace_seconds` param defaulting to a single tick, e.g. 330s — one 5-min
tick plus slack), do NOT clear: return a new `OUTCOME_PENDING_CLEAN = "pending_clean"`,
persist `last_check_utc`, leave the token. Otherwise clear as today. Add the constant to
`__all__` and handle it in `_tick.py`'s reconcile-outcome logging (treat like a benign
outcome — no alert).

**Validation**: fresh token + `D=∅` → `pending_clean`, token retained; aged token + `D=∅`
→ `cleared_clean`.

### T006 — `fold_manifest_baselines` + tick collection

**Purpose**: Enter manifest-declared baselines into the token so CLI-mutation drift is
expected (FR-005/006, R4, contract C5).

**Steps**:
1. `rebaseline.py`: `fold_manifest_baselines(declared, *, observed_head_sha, manifest_names, token_path=None) -> dict`.
   - `declared` empty → `{"outcome": OUTCOME_NOT_REQUIRED}`.
   - token exists → union `declared` into `expected_baselines`; persist; `{"outcome":"merged", ...}`.
   - no token → create one with `surface_ids=["manifest-declared"]`,
     `expected_baselines=sorted(declared)`, `observed_head_sha=observed_head_sha`,
     `pending_since_utc=now`, `matched_files=[]`, `last_check_utc=None`,
     `alerts_emitted=[]`; persist; `{"outcome":"created", ...}`. Record `manifest_names`
     for correlation. Never raise; never run an audit.
2. `_tick.py`: during the queue loop, when a manifest is applied successfully, collect the
   union of `manifest_data.get("expected_baselines", [])` and remember the manifest name.
   After `observe()` and BEFORE `reconcile()`, if the collected set is non-empty call
   `fold_manifest_baselines(collected, observed_head_sha=post_pull_head, manifest_names=[...])`.

**Validation**: fold-create when no token; fold-merge when observe already armed one;
end-to-end declared `openclaw-cron.txt` → reconcile `completed` not `unexpected_drift`.

### T007 — Unit tests (`tests/deploy/test_rebaseline.py`)

Cover: watermark read/write/absent/corrupt (T001); validity classification all four
branches with a fake git runner (T002); grace rule fresh vs aged (T005); fold create /
merge / empty (T006). Use the existing fixture/injection style in the file.

### T008 — Tick tests (`tests/deploy/test_tick_rebaseline.py`)

Cover the integration behaviors with injected git/audit runners:
- **Out-of-band repro**: `pre_pull_head == post_pull_head` but watermark older and range
  contains a `scripts/office2/*.service` add → token armed, reconcile reaches `completed`
  (SC-001). This is the headline test — assert a token IS written where today it is not.
- **Self-commit skip**: after a `deploy(applied)` commit, an idle next tick observes an
  empty range → `not_required`, no spurious token (SC-004).
- **Push-fail SHA capture**: `_record_success` push fails → `commit_sha` still captured →
  watermark advances correctly.
- **Declared-baseline fold** end-to-end via the tick (SC-002).
- **No-crash regressions**: inject exceptions in watermark read/write and fold → `run_tick`
  returns 0 (NFR-001).
- **Backward compat**: a manifest without `expected_baselines` behaves exactly as before.

## Branch Strategy

Planning base and final merge target are both `fix/felix-deployer-rebaseline-detection`.
Execution worktrees are allocated per computed lane from `lanes.json`; land changes back on
the mission branch unless a human redirects.

## Definition of Done

- All 8 subtasks complete; `pytest tests/deploy/test_rebaseline.py tests/deploy/test_tick_rebaseline.py`
  green; `--cov-branch` gate met for the changed lines.
- `observe()` public signature unchanged; engine functions never raise.
- The out-of-band repro test fails on the pre-fix code and passes on the fixed code.
- `run_tick` returns 0 under every injected exception in the new paths.

## Risks & Reviewer Guidance

- Reviewer: confirm the watermark advance uses the deployer's **own captured commit SHA**,
  not a blind `rev-parse HEAD` (mid-tick race); confirm transient git failures leave the
  watermark UNCHANGED (no advance); confirm the grace rule defers but does not permanently
  withhold a clear; confirm no new non-stdlib import.

## Activity Log

- 2026-07-09T01:48:58Z – claude:opus:python-pedro:implementer – shell_pid=10163 – Assigned agent via action command
