# Research: Backup Pointer Key Ledger

Phase 0 output, **v2** — revised after the post-plan review point-cut. Four v1 findings were
disproved by review and are corrected in place with the correction stated, not silently edited;
seven findings are new. Everything below was verified against the live system or actual source on
2026-08-30.

## R1 — CORRECTED. The prose is accurate and enforced; the gap is that seven keys have no rule at all

**v1 claimed**: the inventory's `health_check.expected` states the contract in "a medium with no
enforcement", and "two of the described rules were separately implemented … the rest were never wired
to anything."

**That was wrong on both halves.** `expected` states exactly three rules — `restic_exit_code ∈ {0,3}`,
`prune_exit_code = 0`, and a non-null *parseable* `snapshot_timestamp_utc` — and `probes.py` enforces
**all three**. Nothing described in `expected` is unenforced. The `note` field separately *enumerates*
schema fields including `integrity_check_run` and `integrity_check_passed`, but enumerating a field is
not stating a rule about it.

**Corrected finding**: the defect is not unenforced prose. It is that **three rules exist, hand-written
in one consumer, and seven emitted keys have no rule anywhere** — no prose, no code, nothing. The
ledger's initial content is therefore *not* a transcription of a known-correct source, as v1 assumed;
the three existing rules are transcribed, and everything else is a new adjudication requiring the same
scrutiny as any new design.

This matters beyond accuracy: v1's "transcription" framing is what let its ledger entries go
unexamined, which is how the precedence defect (R12) survived planning.

## R2 — UNCHANGED. The tri-state trap, and why the surrounding style is the wrong template

Good-set membership is tested by explicit containment including `None`; any value not in the declared
good-set is unhealthy. No `isinstance` pre-filter.

`integrity_check_passed` is genuinely tri-state: `true`, `false`, `null` (not checked — six days in
seven). Both obvious implementations fail. **Truthiness** makes it unhealthy six days a week, and a
signal that cries wolf gets muted, taking the real Sunday failure with it. **Type-guarded** — what the
existing code does (`if isinstance(code, int) and code not in _RESTIC_OK_EXIT_CODES`) — reads healthy
for any unexpected type. The producer writes this document by shell interpolation, so a change
emitting `"false"` would be skipped by the guard and read healthy: the exact bug, reintroduced by
copying the surrounding style.

The existing guards are load-bearing for a different reason — `127` was made an integer *because* the
guard skips non-integers — so they are not being removed. But they are fail-open and must not be the
template for new adjudication.

*(Reviewers verified this finding and had no changes. See R13 for the half of it v1 got wrong.)*

## R3 — CORRECTED. The ledger↔constant equality test would be actively harmful

**v1 proposed**: keep `_RESTIC_OK_EXIT_CODES` / `_PRUNE_OK_EXIT_CODES` "for the 15 components with no
ledger", and add a test asserting the declared good-sets equal those constants.

**Both halves were wrong.** The constants are consulted only when a pointer *contains those exact
fields*, and only `restic-backup` emits them — verified across every tracked file: the sole references
are the producer, `probes.py`, `snapshot.py`, their tests, and docs. No ledger-free component emits
them, so the constants protect nothing once restic declares a ledger.

**And the equality test would make things worse.** Once the ledger is authoritative,
`_PRUNE_OK_EXIT_CODES` no longer governs `restic-backup`. A developer narrowing that constant for some
future purpose would see the equality test go red pointing at `restic-backup` — a component the
constant no longer affects — and the natural fix is to edit the ledger to match, **silently changing
restic's live adjudication as a side effect of editing a dead constant.** A seam built to prevent
drift becomes a channel that propagates changes where they were never meant to reach.

**Corrected decision**: the ledger is the only home for a ledger-declared component's good-sets. Keep
the `#902` "do not tidy up this duplication" rationale as a comment on the ledger's two entries, where
it now belongs. Either remove the legacy branches once verified unreachable, or keep them and assert
the invariant actually wanted — *no ledger-declared component is ever routed through them*.

## R4 — CORRECTED. The reconciliation binds the repo copy, not the deployed producer

**v1 claimed**: the test "runs the real producer".

It runs `scripts/office2/restic-backup.sh` — the **repo copy**. The live producer is
`/data/services/backup/scripts/backup.sh`, `deployed_by: "manual"`, root-owned. These are independent
files. A whole component, `backup-script-drift`, exists *because they diverged* — its own record says
"#889 changed the repo copy with no manifest and the live file was installed by hand; they matched
only by luck, on the one script the Tier-2 change-control guarantee depends on." It is **observe-only
by design** and can never converge them.

**Corrected finding**: the mission's central guarantee is true of the live producer only transitively,
via a daily md5 comparison run by a different component surfacing under a different name. That
dependency was named nowhere in v1. It must be stated in the runbook: **the ledger's guarantee is void
while `backup-script-drift` reports drift.** Language throughout is corrected from "the real producer"
to "the repo copy of the producer".

## R5 — CORRECTED. Early-exit reconciliation is near-vacuous; the value is in the verdicts

**v1 claimed**: reconciliation must hold across early-exit branches, justified by #906 hiding there.

`write_state_pointer` writes a **static heredoc** — every key name is emitted unconditionally on every
path; only *values* vary. So reconciling the key set across early exits re-checks the same names and
**can never fail**. A safeguard that cannot fail is this mission's own defect class in test form.

**Corrected finding**: keep the early-exit executions, but assert the **evaluator's verdict** on each,
not the key set. That covers the real #906 shape (values: `PRUNE_RC` staying `127`,
`snapshot_count: null`) and is where R16's false-positive path lives. Had v1 specified it this way,
R16 would have surfaced in planning rather than review.

## R6 — UNCHANGED. Live pointer shape, used as the fixture source

Fixtures derive from the live document read 2026-08-30 02:51 UTC (Saturday's run): ten keys,
`restic_exit_code: 0`, `prune_exit_code: 0`, `snapshot_count: 14`, `script_finished_at_utc` present,
`integrity_check_run: false`, `integrity_check_passed: null`. That last pair is the six-days-in-seven
shape and must read **healthy**. `snapshot_count: 14` confirms the repository is established.

*(Independently re-fetched and confirmed byte-identical during review.)*

## R7 — SUPERSEDED BY SCOPE DECISION. The 25-hour window no longer governs

The original prioritisation rested on Sunday's verdict persisting from 04:00 UTC until Monday 04:00
UTC, giving ~25 h for a consumer to land and adjudicate this week's real result. That reasoning is
still factually correct.

It no longer applies: the decision to close all four catastrophic legs makes this a producer-changing
Tier-2 mission with a manual install, which will not land inside that window. **The window is
explicitly forgone in exchange for completeness** — recorded so nobody later reads the missed window
as a slip.

## R8 — REFINED. Two delivery paths, one of which needs the operator

The canary change rides the checkout pull with no manifest (#746 precedent) — unchanged.

The **producer** cannot ride anything. Verified live on office2:

```
/data/services/backup/scripts/   drwxr-xr-x root:root    ← not writable by claude
backup.sh                        -rwxr-xr-x root:root
claude sudo                      "a password is required"
```

felix-deployer runs as `claude` and therefore cannot install it. The install is a manual operator step
via `ssh office2-kgale` (C-002), and the mission is incomplete until `backup-script-drift` reports
convergence.

## R9 — UNCHANGED, RE-VERIFIED. Rebaseline does not apply

Re-checked after the scope change, against the authoritative consumer rather than path globs:
`check_audited_surface_drift.py` reports no audited-surface match for any touched file, **including
`scripts/office2/restic-backup.sh`**. Merge record: `Rebaseline: not required — no audited surface
touched`.

## R10 — UNCHANGED. CI runs an older Python than either host

`.github/workflows/test-ci.yml` pins `python-version: '3.11'`; office4's venv and office2 both run
3.12.3. A 3.12-only construct passes every local check and reddens CI after push.

## R11 — UNCHANGED. Adversarial evidence

No dependency added, upgraded, or removed, so the supply-chain pass has no security-impacting decision
to challenge. The design's contested points were surfaced by the post-plan point-cut instead. **No
contested finding was dropped silently** — the four disproved v1 findings are corrected above with
their disposition stated, and the accepted ones appear as R12–R18 and as spec requirements.

---

## New findings from the review

## R12 — The legacy chain is organised per rule-block, not per key

`_explicit_error` adjudicates **two** rules under **one** presence test:

```python
if "restic_exit_code" in pointer:
    ...good-set check...
    snapshot_ts = pointer.get("snapshot_timestamp_utc")
    if _parse_iso(snapshot_ts) is None:
        return "restic pointer has no usable snapshot_timestamp_utc"
```

v1's precedence rule ("legacy applies only to keys the ledger does not name") is expressed per *key*.
Suppressing that branch for `restic_exit_code` **deletes the snapshot-timestamp guard with it** —
reopening #902/FR-009 verbatim, in the mission whose thesis is that such couplings must not recur.

**And CI would not have caught it.** Every FR-009 regression test builds its `health_check` dict
without a `key_ledger`, so all of them exercise the legacy path and stay green forever while the one
component that carries a ledger regresses. NFR-003 as v1 wrote it would have been satisfied by a build
shipping the defect. Hence NFR-003's ledger-aware clause and SC-007.

**Resolution**: lift the timestamp rule into its own named predicate rather than suppressing branches,
so no rule survives only inside another key's block.

## R13 — The bool/number collision runs in both directions

v1's invariant covered a number against a boolean good-set. The host language collides both ways:

```
False in [0, 3]     -> True      # restic_exit_code: false would read HEALTHY
1     in [True, None] -> True    # a numeric 1 satisfies the integrity good-set
0     in [False]    -> True
```

Given R2's own observation that this producer builds JSON by shell interpolation, `false` reaching a
numeric good-set is a realistic drift. Matching must be **type-identity in both directions**, with all
four combinations tested.

## R14 — The freshness anchor is chosen by a module constant, not by the ledger

`_resolve_timestamp` walks the module-level `TIMESTAMP_KEYS` tuple in fixed order and takes the first
present, parseable key. **It takes no `health_check` argument and cannot see a ledger.** So a ledger
declaring "key X is the freshness anchor" is a claim the mechanism does not implement.

For restic today the declaration is honoured *by accident* — `snapshot_timestamp_utc` happens to
precede `script_finished_at_utc` in the tuple. The accident is the problem: office4's producer will
plausibly emit `completed_at_utc`, which sorts **first**, so its ledger would declare one anchor while
the probe judged another — a run producing no snapshot reading fresh, #902 reopened on the second host
by the contract meant to prevent it.

**Resolution**: when a ledger declares a `freshness` predicate, that key *is* the anchor;
`TIMESTAMP_KEYS` remains the fallback for ledger-free components only. At most one `freshness`
predicate per ledger (v1's contract permitted two with no resolution rule).

## R15 — Nothing binds a ledger to a reconciliation harness, and deleting a ledger is silent

v1's Obligation 2 — the mission's whole thesis — was enforced by **prose in a contract document**. The
validator checks ledger *shape* and cannot know whether a test exists. So:

- Declaring a ledger and writing no harness passes everything. #913 adding office4's ledger while
  deferring the harness would ship a hand-maintained list — exactly what plan.md says the mission
  prevents.
- **Deleting the ledger** passes everything too, since absence is legal (16 components have none), and
  silently returns the component to pre-mission behaviour.
- A reconciliation parametrised over "components with a ledger" yields a **green suite with zero
  assertions** if that list is ever empty — a shape with five documented instances in this repo in one
  day.

**Resolution**: `reconciliation_harness` becomes a required member of `key_ledger`, validated to exist
on disk; the reconciliation asserts its selection is non-empty and equals the set of ledger-declaring
components; one hardcoded pin asserts `restic-backup` has a ledger. That last is a hand-maintained
list — of *producers* (2, changing yearly), not of *keys* (14, changing per commit). Accepting one
while refusing the other is deliberate and stated.

## R16 — `snapshot_count` is unguarded and can be `null` on a *successful* run

Two problems in `write_state_pointer`, and the asymmetry is the tell:

```bash
repo_size_bytes=$(du -sb ... | awk '{print $1}')
[ -z "$repo_size_bytes" ] && repo_size_bytes="null"      # guarded — stays diagnostic
...
if all=$(restic snapshots --json 2>/dev/null) && [ -n "$all" ]; then
    snapshot_count_json=$(echo "$all" | jq 'length')      # UNGUARDED — becomes load-bearing
fi
```

- If `jq` emits nothing, the heredoc writes `"snapshot_count": ,` — **invalid JSON**. Today the field
  is unread so this is latent; this mission promotes it to deciding health.
- `snapshot_count` comes from a **second** `restic snapshots --json` call. If the full listing fails or
  times out while `--latest 1` succeeded, the count is `null` on a run that backed up fine. Under a
  bare `minimum: 2`, `null` is not numeric → **unhealthy**: a false alarm on a healthy backup.

**Resolution**: add the missing guard (now permitted — C-001 is lifted), and make an unmeasurable
count read **unknown**, not unhealthy (FR-016). "Could not count" is not "counted one" — the same
distinction the whole mission rests on, and it would have been got wrong in the very rule added to fix
it.

## R17 — A second consumer reads this document with its own duplicated rules

`scripts/deploy/lib/snapshot.py` — the Tier-2 deploy pre-flight gate — reads the same file directly,
with its own `_RESTIC_OK_EXIT_CODES = frozenset({0, 3})`, its own `_STATE_INSTANT_FIELD`, and its own
future-skew guard. The inventory documents the divergence as deliberate: a prune failure makes the
component unhealthy but does **not** gate deploys.

Two consequences. First, v1's "the state document is the only interface between the backup and
everything that judges it" is false; the ledger's scope is the **canary's** verdict, so
`diagnostic_only` means "does not decide canary health", never "unused" — otherwise the next reader
deletes a key the deploy gate depends on. Second, this is where R18 comes from.

## R18 — The future-skew guard already exists here, with a chosen value

```python
_FUTURE_SKEW_TOLERANCE = _dt.timedelta(minutes=5)
if instant > now + _FUTURE_SKEW_TOLERANCE:
    ... "error_code": "RESTIC_TIMESTAMP_IN_FUTURE"
```

`snapshot.py` already guards **this exact field on this exact document**. v1 specified FR-008's
tolerance as "a small margin" with no number anywhere — untestable as written, and two plausible
choices (0 s, 4 h) produce opposite failures.

**Resolution**: adopt **5 minutes, strict `>`**, because two consumers of one file must not disagree,
and the value is already justified in-repo. Independently sound: the tightest freshness budget in the
inventory is 600 s, so a tolerance at or above it would defeat the guard entirely for that component —
5 minutes stays safely below.

The recorded lesson from a prior mission applies exactly: *the correct idiom already existed in a
sibling.*

## R19 — Producer data sources (feasibility verified, restic 0.16.4)

| Key | Source | Cost |
|---|---|---|
| `files_processed` | `restic stats --mode files-by-contents latest --json` → `total_file_count` | One extra scan of a 3.6 GB repo. Chosen over `restic backup --json`, which would replace the human-readable `--verbose` log the runbook depends on. |
| `source_roots_present` | `restic snapshots --latest 1 --json` → `.paths[]` vs configured roots | None — that call already runs and already returns the field. |
| `repo_fs_free_bytes` | `df -B1 --output=avail` on the repository path | None. Measures the *filesystem*, which is what fills; `repo_size_bytes` measures the repository and stays diagnostic. |
| `last_integrity_check_utc` | Read prior document before overwrite; carry forward unless the check just ran | Must tolerate a missing or corrupt prior document without aborting the run. |

Capacity figures verified live: repository volume `/dev/sdd1`, 916 GiB total, **864 GiB free, 1%
used**, repository 3.6 GB. The 50 GiB floor is ~14× the current repository size.

## Open items carried into implementation

- office4's ledger placement (a component entry with `host: office4`, in an inventory holding zero
  office4 entries today) is confirmed by #913 (C-007).
- The 16 remaining pointer-emitting components are tracked as #937 (C-005, FR-011).
- The canary's own liveness remains self-observed and therefore unwatched (spec R-001). Not closed
  here; the fourth leg of the v0.2 catastrophe stays open and is recorded as a known false premise
  rather than an assumption.
