# Research: Suppress expected drift alerts during rebaseline

Phase 0 decisions. Each: Decision → Rationale → Alternatives considered.

## R1 — Invocation surface: one helper call per audit run (not per baseline)

- **Decision**: `audit.sh` calls the helper **once** near the top of the run with a
  `--list` mode that prints the full set of fresh expected-baseline names; the result
  is cached in a shell variable and consulted by string membership inside
  `check_baseline()`.
- **Rationale**: NFR-001 (≤100 ms added per run). A per-baseline subprocess (~15
  baselines × Python startup + import) would add seconds. One call amortizes the
  Python + `import rebaseline` cost across the whole run and keeps the per-baseline
  check a pure in-shell string test.
- **Alternatives**: (a) per-baseline `is_expected <name>` subprocess — rejected on
  latency. (b) audit.sh parsing the JSON itself in bash (`jq`/grep) — rejected: would
  duplicate felix-deployer's schema + staleness logic in shell (violates C-002) and
  `jq` availability under the `sg docker -c` minimal environment is not guaranteed.

## R2 — Reuse felix-deployer's token reader + staleness (single source of truth)

- **Decision**: the helper imports `read_token` and `MAX_AGE_SECONDS` from
  `scripts/deploy/felix-deployer/rebaseline.py`; "fresh" = token present AND
  `now - pending_since_utc ≤ MAX_AGE_SECONDS`; "expected" = name ∈
  `token["expected_baselines"]`.
- **Rationale**: C-002. felix-deployer already defines the token schema, the atomic
  writer, the `read_token` (absent/malformed → `None`), and the 24 h staleness
  threshold. Reusing them guarantees the audit's notion of "expected"/"stale" can
  never drift from felix-deployer's.
- **Alternatives**: define a parallel reader/threshold in the helper — rejected
  (two sources of truth; the exact class of coupling bug the mission fixes).

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

## R6 — Suppression scoped to the baseline-drift path only

- **Decision**: only `check_baseline()` drift consults the expected set. The generic
  `alert()` calls for IOCs (`/tmp/pglog`, `sysmon.service`, suspicious containers,
  `/etc/hosts`) are never suppressed.
- **Rationale**: FR-003 + NFR-003. Expected drift is defined only for *baselines*
  named in the token; IOC detections are categorically not "expected deploy drift" and
  must always page.
- **Alternatives**: suppress at the final send step by filtering the alert file —
  rejected (couples IOC and baseline alerts; harder to scope; risk of muting an IOC).

## R7 — Word-boundary membership test

- **Decision**: membership uses a whitespace-delimited exact-token match (e.g. a
  `case " $EXPECTED_DRIFT " in *" $name "*)` guard), not a substring match.
- **Rationale**: baseline names share prefixes (`systemd-user-units.txt` vs
  `systemd-user-unit-contents.txt`); a substring test could falsely suppress a
  sibling. Exact-token matching prevents cross-baseline false suppression.
- **Alternatives**: substring `[[ $EXPECTED_DRIFT == *$name* ]]` — rejected (false
  matches between prefix-sharing names).
