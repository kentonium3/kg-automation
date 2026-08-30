---
id: restic-backup-ops
doc_type: runbook
title: Restic Backup Operations
status: approved
level: 2
owners: [kent]
audience: agents_and_humans
last_validated: '2026-08-30'
updated_by: 'pointer-key-ledger-01M189P6 (#934) + #511'
---

# Restic Backup Operations

The nightly backup for office2. Runs as a plain cron job under the `claude`
user with `NOPASSWD sudo` for one specific script — there is no systemd
unit or timer, so `systemctl status` will not find it.

> ⚠️ **Operator action pending (mission `pointer-key-ledger-01M189P6`, #934).**
> The repo producer (`scripts/office2/restic-backup.sh`) now writes **schema
> v2, fourteen keys**. The copy actually running on office2 still writes
> **schema v1, ten keys**, until an operator installs the update by hand —
> see [Operator handoff: installing the schema v2 producer](#operator-handoff-installing-the-schema-v2-producer)
> below. **Until that install happens, the live `restic-backup` canary
> component will read unhealthy** on the four adjudicated keys it cannot yet
> see. That is the ledger working as designed, not the mission having broken
> the backup — see the sequencing warning in that section before reacting to
> the alert.

## Where things live

| Resource | Path / Value |
|---|---|
| Script (canonical source) | [`scripts/office2/restic-backup.sh`](../../scripts/office2/restic-backup.sh) |
| Script (deployed) | `/data/services/backup/scripts/backup.sh` on office2 |
| Restic repo | `/mnt/backups/restic-repo` on office2 (2.7 TB drive at `/mnt/backups`) |
| Password file | `/etc/restic/password` (root-owned 0600; moved out of `/home/claude/.config/restic/` by #888 because the key lived inside the tree it protects) |
| Daily logs | `/data/services/backup/logs/backup-YYYY-MM-DD.log` |
| Health pointer | `/data/services/backup/state/last-backup.json` |
| Cron entry | `claude`'s crontab on office2, `0 4 * * *` (04:00 UTC daily) via `sudo /data/services/backup/scripts/backup.sh` |
| Sudoers grant | `claude ALL=(root) NOPASSWD: /data/services/backup/scripts/backup.sh` |

## Verifying backup currency (the load-bearing check)

The pre-flight check that Tier 2 changes depend on. Fast (sub-second),
no restic creds needed at check time, no read load on the repo:

```bash
ssh office2-claude 'jq -er '"'"'
  if .snapshot_timestamp_utc == null then "FAIL: no snapshot recorded" else
    (now - (.snapshot_timestamp_utc | fromdateiso8601)) as $age_sec |
    if ($age_sec > 100800) then "FAIL: stale (\($age_sec / 3600 | floor) hours old)"
    elif (.restic_exit_code != 0 and .restic_exit_code != 3) then "FAIL: restic exit \(.restic_exit_code)"
    elif (has("prune_exit_code") and .prune_exit_code != 0) then "FAIL: prune exit \(.prune_exit_code)"
    else "OK (\($age_sec / 3600 | floor) hours since snapshot)"
    end
  end'"'"' /data/services/backup/state/last-backup.json'
```

Returns one line on stdout and exit 0 (`OK …`) or exit 1 (`FAIL: …`).

The `prune_exit_code` clause is guarded with `has(...)` so a pointer written
before #902 — which carries no such field — still evaluates. Note the good-set
is `0` alone, deliberately narrower than the backup's `{0, 3}`: a `restic backup`
exiting 3 completed with warnings but still produced a snapshot, whereas
`restic forget` exiting 3 means snapshots could not be removed, which is not a
successful retention pass. `127` is the script's "never attempted" sentinel.

Freshness budget: 28 hours = 24 h cadence + 4 h slack for a slow run.
Restic exit codes 0 (success) and 3 (success with permission-denied
warnings) both pass.

## Health-pointer schema (#511, schema v2 as of pointer-key-ledger-01M189P6/#934)

The pointer at `/data/services/backup/state/last-backup.json` is written
atomically (`.tmp` + `mv`) by `backup.sh` on every exit — success OR
failure — so a stale pointer always means the cron has not fired.

**Fourteen keys, `schema_version: 2`.** The four rows marked **new** below
were added by mission `pointer-key-ledger-01M189P6` (#934). Which keys
*decide health* and which are recorded for diagnosis only is no longer
prose here — it is the machine-readable declaration at
`health_check.key_ledger` on the `restic-backup` entry in
`docs/design/architecture/data/service-inventory.json`, described in full in
[Key ledger: what decides health](#key-ledger-what-decides-health) below.
This table is the schema/source reference; treat the ledger as authoritative
for adjudication.

| Field | Source | Notes |
|---|---|---|
| `schema_version` | constant `2` | Adjudicated (`good_values: [2]`, C-008). A future bump forces a deliberate ledger review instead of passing silently. |
| `snapshot_timestamp_utc` | `restic snapshots --latest 1 --json` after the run | Authoritative. `null` when the snapshot query failed (repo broken). This is the ledger's freshness **anchor** — the key that decides component staleness. |
| `snapshot_id` | same query | `null` on failure. Diagnostic only — identifier for investigation, carries no health meaning. |
| `restic_exit_code` | the `restic backup` step's `$?` | NOT the script's overall exit. `127` = "never reached the backup step" (pre-check failed). Good set `{0, 3}`. |
| `prune_exit_code` | the `restic forget --prune` step's `$?` (#902) | Good set `{0}` ONLY. `127` = "never reached the prune step". Before #902 this was logged as a WARNING and discarded, so a stale lock blocked retention for ten hours while every health surface correctly reported the *backup* healthy. |
| `script_finished_at_utc` | `date -u` at script-end | Diagnostic only. Separate cron-finished witness so "did the cron fire" stays distinct from "did restic succeed" — deliberately **not** a freshness fallback: it was one, and a run producing no snapshot once read fresh through it (#902/FR-009). |
| `repo_size_bytes` | `du -sb /mnt/backups/restic-repo` | Diagnostic only. Trend data with the daily logs — measures the repository, not the filesystem that fills; `repo_fs_free_bytes` below is the capacity signal. |
| `snapshot_count` | `restic snapshots --json` length | After prune. Minimum 2 (a single snapshot means a wiped-and-recreated repository, US6). `null` (query failed) reads **unknown**, not unhealthy — `unmeasured_is_unknown`. |
| `integrity_check_run` | bool — true on Sundays | Diagnostic only. Whether the weekly check *executed today* — recency is adjudicated via `last_integrity_check_utc`, not this field; see below. |
| `integrity_check_passed` | bool or `null` | `null` on non-Sunday runs (good) or a run that never reaches the check. `false` (a real corrupt-repository verdict) is unhealthy — FR-001. |
| `last_integrity_check_utc` **(new)** | UTC instant of the last **passing** weekly `restic check`, carried forward from the prior pointer when today's run doesn't reach or doesn't pass the Sunday check | Adjudicated, freshness, bound 777600 s (9 days: tolerates one late/skipped Sunday, not two). See [why this key exists](#last_integrity_check_utc-vs-integrity_check_run) below — it is easy to mistake for redundant with `integrity_check_run` and it is not. |
| `files_processed` **(new)** | `.total_file_count` from `restic stats --mode files-by-contents latest --json` | Adjudicated, minimum 1. Distinguishes a real capture from an empty one — a source-path typo or an over-broad exclude can exit 0 with a fresh snapshot and capture nothing (US4). |
| `source_roots_present` **(new)** | whether every path in `SOURCE_ROOTS` appears in the latest snapshot's `paths` | Adjudicated, `good_values: [true]`. A partial capture — one configured root silently missing — is not mistaken for a complete one. `good_values` carries no `unmeasured_is_unknown` modifier (only `minimum` predicates may), so a producer-emitted `null` here (evaluation genuinely could not run) is **unhealthy**, not unknown — a narrower guarantee than `snapshot_count`'s, worth knowing before assuming the two behave alike. |
| `repo_fs_free_bytes` **(new)** | `df -B1 --output=avail` on the filesystem backing `RESTIC_REPOSITORY` | Adjudicated, minimum 53687091200 (50 GiB). The approach to a full volume is visible before the backup starts failing outright (US5). |

## Key ledger: what decides health

`restic-backup` is the first (and, until #913/office4 adopts its own, only)
producer whose emitted keys are governed by a **key ledger** — a
per-component declaration, at
`health_check.key_ledger` on the `restic-backup` entry in
`docs/design/architecture/data/service-inventory.json`, of what every
emitted key means for health. Full predicate semantics are the contract:
[`kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`](../../kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md).

The ledger has two categories, and every key the producer emits is in
exactly one:

- **`adjudicated`** — a key with an explicit predicate (`good_values`,
  `minimum`, or `freshness`, plus optional modifiers). A value outside the
  predicate makes the component unhealthy; a key **absent** from the
  document is unhealthy too, regardless of predicate — the producer that
  stops emitting a health-bearing key cannot pass unnoticed (FR-007).
- **`diagnostic_only`** — a key deliberately excluded from deciding
  *canary* health, with a written, non-empty reason. "Diagnostic" does not
  mean "unused by anything": a second reader, the Tier-2 deploy pre-flight
  gate (`scripts/deploy/lib/snapshot.py`), reads the same document with its
  own independent rules, and a key marked diagnostic here may still be
  load-bearing there.

**How a key gets placed.** The generative rule this mechanism enforces:
*every key the producer actually emits is either adjudicated with a stated
good-set, or declared diagnostic-only with a stated reason — a test executes
the producer, enumerates the keys it actually wrote, and fails, naming the
key, if any key is in neither list.* That test is
`tests/office2/restic_backup/test_ledger_reconciliation.py` (the
`reconciliation_harness` the ledger itself names); it also fails if the
ledger is deleted wholesale, or if the reconciled component selection is
empty. So a new key added to the producer without a corresponding ledger
entry is not a documentation debt — it is a red test.

**What this buys, and what it does not.** It makes *silent* inertness
impossible: a new key cannot be ignored by default, because the suite goes
red until someone places it. It does **not** remove the reviewer from the
loop — `diagnostic_only` remains a legitimate escape hatch, and a good-set
spanning the whole value domain adjudicates nothing. What changes is that an
inert key stops being the default and becomes a line in a diff, with a
written reason attached. Read this runbook's earlier schema table, or any
future one, with that distinction in mind: **the ledger cannot make a
reviewer's oversight impossible, only silence.**

### `last_integrity_check_utc` vs `integrity_check_run`

The least obvious of the four new keys, and the one most likely to be
mistaken for redundant with the pre-existing `integrity_check_run`:

- `integrity_check_run` (diagnostic only) answers **"did the weekly check
  execute today?"** — true only on the Sundays it ran, false every other
  day by design. A truthiness read on this field alone would cry wolf six
  days in seven.
- `last_integrity_check_utc` (adjudicated, freshness, 9-day bound) answers a
  different question: **"how long has it been since the check last
  *passed*?"** It is carried forward from the previous pointer whenever
  today's run doesn't reach or doesn't pass the Sunday check — because every
  backup failure path in the producer exits *before* the weekly check runs,
  a run of bad Sundays would otherwise reset a same-shaped field to `null`
  every week instead of accumulating the gap. That accumulation is exactly
  what closes US2/FR-012: a verification that has **silently stopped
  running** (not "didn't run today", but "hasn't passed in weeks") is
  invisible to `integrity_check_run` and visible to this key alone.

### The ledger binds the repo copy, not the deployed producer

**This is the caveat that bounds the whole mechanism's guarantee, and it is
stated here prominently on purpose.**

The key ledger, its reconciliation test, and the evaluator that adjudicates
health are all enforced against the **repository's** copy of
`scripts/office2/restic-backup.sh`. The **live** producer executing nightly
on office2 is a separate, independently-installed file:
`/data/services/backup/scripts/backup.sh`, `deployed_by: manual`, owned
`root:root`. These two files are reconciled by exactly one thing: a daily,
**observe-only** comparator, `backup-script-drift` (#903) — and observe-only
is deliberate, not a gap to be closed later: automating the install would
make `/data/services/backup/scripts/` writable by the `claude` deploy
account, which reopens the #899 privilege escalation this component exists
to avoid. `backup-script-drift` can report divergence; it can never
converge the two files.

**So: everything the ledger guarantees about live backup health is void
while `backup-script-drift` reports the two copies have diverged.** A
reader who does not know this will over-trust the mechanism — the ledger
adjudicates a document schema, not the process that writes it on office2
tonight. Check the current verdict before relying on the ledger for
anything live:

```bash
ssh office2-claude 'cat /data/services/backup/drift/script-drift-last-tick.json'
```

| `verdict` | meaning |
|---|---|
| `match` | the deployed script is the repo script — the ledger's guarantee holds for the live producer too |
| `drift` | they differ — the ledger's guarantee is **void** for whatever is actually running until this is resolved |
| `inconclusive` | the comparator could not read one side — treat identically to `drift`, never as agreement |

### What this does not cover

- **The canary's own liveness is self-observed.** `felix-canary`'s
  `tick-signal-file` health check is probed only by the canary process
  itself, so a stopped runner does not run, therefore does not probe,
  therefore never reports itself stale. This mission does not fix that; it
  is recorded as an open risk (spec R-001), not closed here.
- **Sixteen other pointer-emitting components have no ledger.** This
  mechanism covers `restic-backup` (and its sibling retention keys) only.
  The adoption path for the rest is tracked as
  [#937](https://github.com/kentonium3/kg-automation/issues/937); absence
  of a ledger on a component means "not yet adopted," never "no keys."

## Operational tasks

### Trigger a backup manually

```bash
ssh office2-claude 'sudo /data/services/backup/scripts/backup.sh'
```

The NOPASSWD sudoers entry allows this without a password prompt. The
run writes to today's log file at `/data/services/backup/logs/` and
refreshes the pointer.

### Inspect the most recent run

```bash
ssh office2-claude 'cat /data/services/backup/state/last-backup.json | jq .'
ssh office2-claude 'tail -20 /data/services/backup/logs/backup-$(date -u +%Y-%m-%d).log'
```

### List snapshots (requires sudo via kgale)

The repo files are `root:root` mode 400, so `claude` cannot run
`restic snapshots` directly. From your laptop:

```bash
ssh office2-kgale 'sudo RESTIC_REPOSITORY=/mnt/backups/restic-repo \
  RESTIC_PASSWORD_FILE=/etc/restic/password \
  restic snapshots --latest 5'
```

### Restore from a snapshot

The standard restic workflow. Identify the snapshot id from the listing
above, then:

```bash
ssh office2-kgale 'sudo RESTIC_REPOSITORY=/mnt/backups/restic-repo \
  RESTIC_PASSWORD_FILE=/etc/restic/password \
  restic restore <snapshot-id> --target /tmp/restore-<date>'
```

Inspect `/tmp/restore-<date>/`; copy paths back into place as needed.

### Verify a stale pointer fails the freshness check

Used to confirm the pre-flight check is actually load-bearing:

```bash
# Save the current pointer
ssh office2-claude 'cp /data/services/backup/state/last-backup.json /tmp/last-backup.json.bak'

# Inject a stale timestamp
ssh office2-claude 'jq ".snapshot_timestamp_utc = \"2026-05-25T04:00:00Z\"" \
  /tmp/last-backup.json.bak > /tmp/last-backup.json.stale'

# Run the freshness check against the stale copy — must FAIL
ssh office2-claude 'jq -er '"'"'<the check from above>'"'"' /tmp/last-backup.json.stale'
echo $?  # should be 1
```

The real pointer file is owned `root:root`, so this manual test is
sandboxed in `/tmp` and does not perturb production state.

## Operator handoff: installing the schema v2 producer

`scripts/office2/restic-backup.sh` is the repo source of truth. The deployed copy
is `/data/services/backup/scripts/backup.sh`, owned `root:root` in a `root:root`
directory.

**It is installed by hand, on purpose, and that will not change.** The deploy
pipeline runs as `claude`, so automating this install would mean making
`/data/services/backup/scripts/` claude-writable. That directory holds the
`NOPASSWD` sudo target `backup.sh`, and a writable directory on a NOPASSWD path
makes the grant equivalent to `NOPASSWD: ALL` — which is #899, a real privilege
escalation fixed on 2026-08-27. Automating the deploy would reopen it to save one
command. So the pipeline is not used here; instead `backup-script-drift` (#903)
reports when the two copies diverge.

**Why the deploy agent (`claude`) cannot do this itself**, spelled out because
without the reason someone will later try to automate it and be puzzled when it
fails: `/data/services/backup/scripts/` is `root:root drwxr-xr-x`; felix-deployer
runs as `claude`; and `claude` has no passwordless sudo. There is no credential
or grant this install could use that the pipeline itself has access to — the
repo change genuinely cannot install itself (spec C-002).

### ⚠️ pointer-key-ledger-01M189P6 (#934): this install is currently outstanding

As of this mission's merge, `scripts/office2/restic-backup.sh` writes
`schema_version: 2` (fourteen keys — four new, see
[Health-pointer schema](#health-pointer-schema-511-schema-v2-as-of-pointer-key-ledger-01m189p6934)
above). **The mission is not complete until an operator runs the install below
and the drift comparator reports converged** (spec C-002) — follow the steps
in [Installing an updated script](#installing-an-updated-script) using the
mission's merge commit as `<commit-sha>`.

**Tier-2 pre-flight, before installing (C-006):** this is a live-host script
replacement on the Tier-2 backup producer, so confirm a Restic snapshot no
older than 24 hours exists before proceeding:

```bash
ssh office2-claude 'jq -r ".snapshot_timestamp_utc" /data/services/backup/state/last-backup.json'
```

If the timestamp is more than 24 hours old, trigger a backup first (see
[Trigger a backup manually](#trigger-a-backup-manually)) and re-check before
installing.

**Sequencing consequence — read before you install, and before you react to
an alert.** Until this install lands, the deployed producer keeps emitting
ten keys while the ledger declares fourteen. The four keys the old producer
never wrote are absent-adjudicated keys, and absence is unconditionally
unhealthy (contract "Absence (unconditional)") — so the **live**
`restic-backup` canary component reads unhealthy from the moment this
mission's `service-inventory.json` change reaches the canary (existing
checkout pull, no deploy manifest) until the producer install below actually
happens. That gap is expected and correct — it is the mechanism proving it
notices an unmet contract, not a sign the backup itself broke. Close the gap
promptly by completing the install rather than investigating the alert as a
regression.

### Installing an updated script

**Install from GitHub, not from the office2 checkout.** `/home/claude/kg-automation`
is writable by the unprivileged `claude` account; installing from there as root
would let that account influence root-executed content. Fetching the reviewed
commit from GitHub removes it from the trust path entirely.

Two earlier versions of this procedure were wrong and are worth recording so they
are not reintroduced:

- Sourcing the install from `/home/claude/kg-automation/...` — protects the
  destination while leaving the source unverified.
- Verifying with `git -C /home/claude/kg-automation diff --quiet …` — `/home/claude`
  is mode `0750`, so `kgale` cannot traverse it. The command exits non-zero for
  *permission denied* and, wrapped in `&& … || …`, reports that as "working tree
  differs". A check that cannot distinguish "verified false" from "could not
  check" is the defect class this whole runbook exists to fix.

```bash
ssh office2-kgale
```

Fetch the exact reviewed commit into your own home (not `/tmp`, which is
world-writable and invites a swap between fetch and install):

```bash
curl -fsSL -o ~/restic-backup.sh https://raw.githubusercontent.com/kentonium3/kg-automation/<commit-sha>/scripts/office2/restic-backup.sh
```

Confirm the content hash matches the commit you reviewed:

```bash
md5sum ~/restic-backup.sh
```

Only then install, from the file you just verified:

```bash
sudo install -o root -g root -m 755 ~/restic-backup.sh /data/services/backup/scripts/backup.sh
```

Confirm what actually landed:

```bash
sudo md5sum /data/services/backup/scripts/backup.sh
```

It must equal the hash from the fetch. `backup-script-drift` then performs that
comparison daily without being asked, and will flip from `drift` to `match`.

### Verifying the install (pointer-key-ledger-01M189P6)

Two independent things must both be true before the mission is actually
complete — neither alone is sufficient:

1. **The drift comparator reports converged.** Check the next day's tick (or
   trigger one — `backup-script-drift` is a systemd user timer, not
   something the install itself re-runs):

   ```bash
   ssh office2-claude 'cat /data/services/backup/drift/script-drift-last-tick.json'
   ```

   `verdict` must read `match`. See [Reading the drift signal](#reading-the-drift-signal)
   below for what the other two values mean.

2. **The next real backup run emits all fourteen keys.** After the following
   night's cron fire (or a manual trigger, see
   [Trigger a backup manually](#trigger-a-backup-manually)):

   ```bash
   ssh office2-claude 'jq "keys | length" /data/services/backup/state/last-backup.json'
   ```

   Must read `14`, and `schema_version` must read `2`. Until both of these
   verifications pass, treat the live `restic-backup` component's unhealthy
   reads on the four new keys as the expected, correct state described in
   the sequencing warning above — not a new incident.

### Reading the drift signal

```bash
ssh office2-claude 'cat /data/services/backup/drift/script-drift-last-tick.json'
```

| `verdict` | meaning |
|---|---|
| `match` | the deployed script is the repo script |
| `drift` | they differ — reinstall, or find out who changed the host copy |
| `inconclusive` | the comparator could not read one side: missing, unreadable, a symlink, or not a regular file. **Never treated as agreement.** A symlinked deployed copy is especially significant: it would mean the NOPASSWD sudo target points somewhere else. |

## Retention policy

GFS, applied at the end of each run via `restic forget --prune`:

- 7 daily
- 4 weekly
- 6 monthly
- 1 yearly

A weekly `restic check` runs on Sundays. Result is captured into
`integrity_check_passed` in the pointer.

## What is NOT yet automated

**Superseded by pointer-key-ledger-01M189P6 (#934):** an earlier version of
this section said the pointer was consumed by Tier-2 pre-flight alone with
"no signal-extraction-style alarm" on it. That is no longer true and would
itself be exactly the kind of stale claim this mission exists to catch:
`felix-canary` reads `health_check.key_ledger` on every 15-minute tick and
reports `restic-backup` unhealthy through the `#701` felix-alert bus when an
adjudicated key fails — see
[Key ledger: what decides health](#key-ledger-what-decides-health) above.

What genuinely remains not-yet-automated:

- The cron has not been migrated to a systemd timer. Discoverability is
  via this runbook plus `service-inventory.json`; `systemctl` queries
  will return nothing for the backup itself.
- **The canary's own liveness is self-observed** (spec R-001) and
  **sixteen other pointer-emitting components have no key ledger** (#937) —
  see [What this does not cover](#what-this-does-not-cover) above. These
  remain true independent of everything else in this runbook.

## Cross-references

- **Service entry**: `docs/design/architecture/data/service-inventory.json` → `restic-backup` (updated_by `#511 + #159 + #208 + pointer-key-ledger-01M189P6/#934`).
- **Key ledger contract**: [`kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`](../../kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md) — the authoritative predicate semantics behind `health_check.key_ledger`.
- **Pre-flight checklist**: [`docs/runbooks/governance/pre-flight-checklist.md`](<./governance/pre-flight-checklist.md>) Tier 2 § "Confirm recent backup exists".
- **Backup architecture overview**: [`docs/design/architecture/backup-and-recovery.md`](<../design/architecture/backup-and-recovery.md>).
- **Canary Registry Operations**: [`docs/runbooks/canary-registry-ops.md`](<./canary-registry-ops.md>) — how `felix-canary` evaluates `health_check` (including `key_ledger`) and alerts.
- **Issues**: [#511](https://github.com/kentonium3/kg-automation/issues/511), [#934](https://github.com/kentonium3/kg-automation/issues/934) (this mission), [#937](https://github.com/kentonium3/kg-automation/issues/937) (adoption path for the other 16 components), [#913](https://github.com/kentonium3/kg-automation/issues/913) (office4's own ledger, reusing this mechanism).
