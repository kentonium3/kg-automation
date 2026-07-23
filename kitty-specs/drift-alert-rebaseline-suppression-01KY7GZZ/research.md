# Research: Suppress expected drift alerts during rebaseline

Phase 0 decisions. Each: Decision → Rationale → Alternatives considered.

## R1 — Invocation surface: one helper call at PUSH time (revised, Codex F1/F2)

- **Decision**: `audit.sh` calls the helper **once**, in the end-of-run summary block,
  **only when `ALERT=1`** (drift exists), with a `--list` mode that prints the fresh
  expected-baseline set. That set filters which `$ALERT_FILE` lines are pushed. The
  per-baseline drift path (`check_baseline`/`alert`) is untouched.
- **Rationale**: NFR-001 (≤100 ms per run) — in the common no-drift case the helper is
  never invoked. Reading at push time is the freshest possible read and eliminates the
  cache-at-start/decide-later stale-snapshot race (Codex F2). A per-baseline subprocess
  (~15 × Python startup) would add seconds and is unnecessary.
- **Alternatives**: (a) read once at the TOP and cache — rejected (stale-snapshot race,
  Codex F2). (b) per-baseline `is_expected` subprocess — rejected on latency. (c)
  audit.sh parsing the JSON in bash (`jq`/grep) — rejected: duplicates felix-deployer's
  schema/staleness in shell (violates C-002) and `jq` availability under `sg docker -c`
  is not guaranteed.

## R2 — Reuse felix-deployer's token reader; dedicated short window (revised, Codex F3)

- **Decision**: the helper imports `read_token` from
  `scripts/deploy/felix-deployer/rebaseline.py` (single source of truth for the token
  schema + absent/malformed→`None` semantics). "expected" = name ∈
  `token["expected_baselines"]`. "fresh" = `now − pending_since_utc ≤
  AUDIT_SUPPRESS_WINDOW_SECONDS`, a **dedicated ~900 s (15 min) constant in the helper**
  — explicitly NOT felix-deployer's 24 h `MAX_AGE_SECONDS`.
- **Rationale**: C-002 keeps the *token definition* single-sourced (reuse `read_token`),
  but the *suppression duration* is a security decision that must be short: a lingering
  or maliciously planted token must not mute the push for 24 h (Codex F3). ~15 min
  covers a slow reconcile (a few 5-min ticks) while hard-capping the mute.
- **Alternatives**: reuse `MAX_AGE_SECONDS` as the window (original plan) — rejected on
  the security-channel-mute concern. Define a parallel token *reader* — rejected
  (two sources of truth for what the token means).

## R3 — Suppress the push, retain the full local record (the issue's "suppress or downgrade" fork)

- **Decision**: for an expected drifted baseline, `audit.sh` still writes the audit
  log line and the `drift-events.jsonl` event (`emit_drift_event`) but does **not**
  call `alert()` — so no push fires for it. No separate "info" push is sent.
- **Rationale**: the drift is already durably recorded locally; the only noise the
  mission removes is the push. A low-priority confirmation push would re-introduce the
  per-deploy noise we are eliminating. FR-006 preserves the audit trail and the
  doc-audit signal untouched.
- **Alternatives**: downgrade to an info-severity ntfy — rejected as re-adding noise;
  full silence with no local record — rejected (FR-006 requires the record).
- **Operator note**: this is the one product choice worth a second look; it is flagged
  for Kent's review rather than silently assumed (spec Assumptions).

## R4 — Helper location: co-located with `rebaseline.py`

- **Decision**: `scripts/deploy/felix-deployer/expected_drift.py`, next to
  `rebaseline.py`.
- **Rationale**: it reads felix-deployer state and reuses `rebaseline`. Co-location
  lets it `import rebaseline` directly (script-dir on `sys.path[0]`) with no package
  gymnastics. Neither `rebaseline.py` nor this sibling matches an audited-surfaces
  pattern, so adding it triggers no rebaseline. It deploys to office2 via
  felix-deployer's own self-pull (checkout-resident) — no separate copy step.
- **Alternatives**: `scripts/security/…` — rejected (further from the module it
  reuses; would need path bootstrap to import `rebaseline`). `scripts/office2/security-monitor/`
  — rejected (that dir is the *consumer* side and is deployed as standalone copies).

## R5 — Fail-safe on every error path

- **Decision**: the helper wraps the `import rebaseline`, the token read, and the
  parse in try/except; ANY failure (import error, missing registry, OSError, malformed
  JSON, unparseable timestamp) prints nothing and exits 0. `audit.sh` uses
  `$(… 2>/dev/null || true)` so a non-zero exit or stderr also yields an empty set.
- **Rationale**: NFR-002/NFR-003 + guardrail preference — a security-detection surface
  must never lose a true positive because a coupling read failed. Ambiguity → alert.
- **Alternatives**: raise on error — rejected (could crash the audit or, worse, be
  caught in a way that masks a real alert).

## R6 — Push filter scoped to baseline-drift lines only (revised, Codex F1)

- **Decision**: the push filter drops only `$ALERT_FILE` lines matching
  `^\[ALERT\] <name> changed since baseline:` whose `<name>` is in the expected set.
  IOC alert lines (`[ALERT] IOC: …`, `[ALERT] /etc/hosts modified…`) do not match that
  pattern and are therefore always pushed.
- **Rationale**: FR-003 + NFR-003. Expected drift is defined only for *baselines* named
  in the token; IOC detections are categorically not "expected deploy drift." Filtering
  at the push step (rather than skipping `alert()`) is precisely what keeps the drift
  visible to felix-deployer (R8) while still scoping the mute to baseline drift.
- **Alternatives**: skip `alert()` for expected baselines (original plan) — rejected
  (Codex F1: breaks felix-deployer's rebaseline trigger, see R8).

## R7 — Exact membership in Python + `grep -Fxq` (revised, Codex F5)

- **Decision**: the helper does list membership in Python (exact string equality). The
  shell-side filter uses `grep -Fxq -- "$name"` against the newline-delimited expected
  set — fixed-string, whole-line, exact match.
- **Rationale**: baseline names share prefixes (`systemd-user-units.txt` vs
  `systemd-user-unit-contents.txt`), so substring matching could falsely suppress a
  sibling; and a `case`-glob would treat metacharacters in `$name` as shell patterns
  (Codex F5). `-Fx` is exact and metacharacter-safe.
- **Alternatives**: `case " $set " in *" $name "*)` — rejected (glob metacharacter
  hazard). Substring `[[ ... == *$name* ]]` — rejected (prefix false-matches).

## R8 — Decouple drift DETECTION from the push (Codex F1, HIGH)

- **Decision**: `audit.sh`'s detection path is unchanged — every drift still calls
  `alert()` (emits `[ALERT] <name>`, sets `ALERT=1`) and the run still exits `1`.
  felix-deployer's `reconcile` parses those exact stdout lines + exit code to detect
  the expected drift and stamp the new baseline. Suppression happens *after* detection,
  at the push emit.
- **Rationale**: the original "skip `alert()`" design would have made felix-deployer's
  read-only audit see exit 0 / "All clear," so it would never rebaseline — the drift
  would then persist and, once the token cleared, page anyway (worse than the bug).
  Gating only the push preserves felix-deployer's contract byte-for-byte (FR-008).
- **Alternatives**: add a new `[DRIFT]`/`[SUPPRESSED]` marker + teach `rebaseline.py`
  to parse it (Codex's suggested option) — rejected as unnecessarily invasive: leaving
  the `[ALERT]` line intact and filtering only the push achieves the same with **zero**
  change to felix-deployer.

## R9 — Threat model + short window (Codex F3, MED)

- **Decision**: bound suppression to `AUDIT_SUPPRESS_WINDOW_SECONDS` (~15 min); document
  that an actor with `claude` write access could already trigger felix-deployer
  auto-rebaseline of a planted change (pre-existing vector) — this mission's push
  suppression adds no new capability and the short window caps the mute.
- **Rationale**: the security push channel must stay credible; it must never be
  mutable for a day by a lingering/planted token.
- **Alternatives**: full token-provenance validation (verify against deployer-observed
  HEAD + registry) — deferred as disproportionate to the pre-existing exposure; noted
  as a possible follow-up if the threat model tightens.

## R10 — Test/verify token-path override (Codex F4, MED)

- **Decision**: the helper honors an `EXPECTED_DRIFT_TOKEN_PATH` env var (default =
  `rebaseline.DEFAULT_TOKEN_PATH`). Unit tests and office2 live-verify point it at a
  temp token so felix-deployer's real state is never written or raced.
- **Rationale**: writing a synthetic token into the live state dir would race the
  running deployer timer (Codex F4) — it could consume, clear, or rebaseline on it.
- **Alternatives**: stop/mask the felix-deployer timer during the test — heavier and
  riskier than a read-path env override.
