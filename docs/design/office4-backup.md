---
id: office4-backup
title: "office4 — Backup Design (restic, user-level, unmanaged peer)"
doc_type: design
level: reference
status: draft
owners: [kent@intentional.biz]
last_validated: 2026-08-29
last_updated: "2026-08-29"
revision: v0.2
audience: agents_and_humans
---

# office4 — Backup Design

Design record for kg-automation#913 (office4 Phase 3a). office4 is the new primary
development workstation: Framework Desktop, Linux Mint 22.3, an **attended unmanaged
peer** under ADR-0008 — not a managed host.

> **v0.2 — revised after the post-plan review point-cut.** v0.1's health-signal section was
> a transcription of office2's *findings register*, not its *generative rule*. The review's
> verdict: a backup that captured an **empty snapshot**, onto a **98%-full disk**, into a
> **corrupting repository**, with a **dead alerter**, would have reported healthy on all six
> of v0.1's rules and passed all ten of its tests. §"Health signal contract" is rewritten
> around one structural rule. See §"What the review changed" for the full list.

## Symptom this addresses

office4 holds irreplaceable state — four agent config trees, memory and session stores,
credentials, and uncommitted work — with **no backup of any kind**. Repos survive via git;
nothing else does.

## Scope boundary, stated plainly

office4 has **exactly one disk** (`nvme0n1`, 1.8 TB, WD_BLACK SN850X), carrying `/boot/efi`
and `/`. A local-only repository therefore sits on the same physical device as the data it
protects.

> **This design delivers versioning and accidental-loss recovery. It does NOT deliver
> disaster recovery.** A disk failure loses the originals and the backup together — which is
> the exact symptom #913 names.

This is a deliberate first stage, chosen by the operator. Stage two is office2 as a remote
destination, and the design keeps that cheap: `RESTIC_REPOSITORY` is the single knob, and
office2 is reachable over the tailnet (verified 2026-08-29: SSH works, `/mnt/backups` has
865 G free, restic 0.16.4 both ends).

> ⚠ **Stage two is one knob, not zero work.** Switching to `sftp:` changes failure and timing
> characteristics that this design's health signal must already tolerate: network-dependent
> locking, far slower `prune`, `du -sb` on the repo path stops being meaningful for
> `repo_size_bytes`, and — critically — **the state pointer must not live inside the
> repository path** (see D9). v0.1 claimed "nothing else changes"; that was wrong.

> **Correction to decision D.** #908 and #913 both record a *6 TB* second drive. That figure
> is **wrong** (confirmed by the operator, 2026-08-29). The actual intent is a **4 TB SSD,
> purchase not imminent**. Those two issues still carry the erroneous number.

> `/data` **does** exist on office4 — born 2026-08-28 21:53, `kgale`-owned — but as a plain
> directory on the root filesystem, **not** a separate device, and it stays that way by
> operator decision. Do not read its presence as a second drive having landed. Verified:
> `lsblk` shows one disk; `df` puts `/data` on `nvme0n1p2`.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Repository at **`/srv/backup-office4`** | Outside `$HOME`, which is the backup source. See "The #888 lesson". |
| D2 | Password at **`/etc/restic/office4-password`**, root-owned `0640` group `kgale` | Outside the protected tree; readable by the unprivileged timer, **not writable** by it. |
| D3 | **Pin `--group-by host`** | The one place office4 must NOT copy office2. See "The `--group-by` scar". |
| D4 | Runs as **`kgale`, no sudo, no root** | ADR-0008: unmanaged peer, one Unix user, no service accounts. Also the only option — sudo is password-gated here. |
| D5 | **`systemd --user` timer**, not cron | House pattern since #327. Requires `loginctl enable-linger kgale` (done 2026-08-29). |
| D6 | Health emitted through **`scripts/common/alert_bus/`**, not a direct ntfy call | **Revised in v0.2.** The bus already fails safe, never raises, and ledgers alerts *even when delivery failed*. "Direct ntfy emit" was a regression against the #706 lesson, not a simplification of it. |
| D7 | **No drift comparator** (cf. #903) | It exists only because a deploy pipeline running as an unprivileged account shares office2. office4 has no pipeline. |
| D8 | Retention **7 daily / 4 weekly / 6 monthly / 1 yearly** | Unchanged from office2. A poisoned-dependency compromise may go undetected for weeks, so rollback points must span months. |
| D9 | State pointer at **`/srv/backup-office4-state/last-backup.json`** — *outside* the repo dir | **New in v0.2.** A pointer inside the repository path is a foreign file in a restic repo, and becomes unreachable the moment stage two moves the repo to `sftp:`. |
| D10 | Source set is **`/home/kgale` and `/data`** | **New in v0.2.** `/data` exists, holds real state, and v0.1 silently omitted it — with no rule that would ever have said so. D3 makes the set editable later without stranding snapshots. |

### The #888 lesson (why D1 and D2 look the way they do)

office2's restic password once lived at `/home/claude/.config/restic/password`. `/home/claude`
is one of office2's four backup **sources**. Deleting that home destroyed the only on-disk copy
of the key to every snapshot. Restic derives its master key from the password and has no
backdoor — the repository would have been permanently unreadable. Recovery on 2026-08-27
succeeded only because the password was independently recorded in a password manager.

Two consequences, both binding here:

1. Neither the repository nor the password may sit under any path in the source set.
2. The password **must** have an independent copy in a password manager. *(Satisfied
   2026-08-29: stored in 1Password before first use.)*

### The `--group-by` scar (why D3 exists)

`restic forget` defaults to `--group-by host,paths` and applies `--keep-*` **per group**.
office2 runs `forget` with no explicit `--group-by`, so its retention is keyed on its exact
four-path source set. Adding a fifth source path would place every future snapshot in a new
group; the old group would stop receiving snapshots and its kept snapshots would then never
age out, because nothing new arrives to push them past the keep-counts.

office2 is stuck with this. #895 worked around it by writing captured crontabs into an
already-covered path rather than adding `/var/spool/cron`. Retrofitting `--group-by` there was
explicitly rejected as "a far larger blast radius than the problem."

office4 is greenfield. **Pinning `--group-by host` before the first snapshot** makes the source
set editable forever, at zero cost. This is what makes D10 safe.

> #913's body states this constraint as *"a second **host** in the same repo would strand
> existing snapshots from pruning."* That mechanism is **wrong** — with the default
> `host,paths` grouping, a second host forms its own groups and prunes independently. The real
> hazard is adding a **path**. The separate-repository rule still stands, on other grounds:
> separate credentials, independent retention, no shared blast radius.

## Source set and exclusions

**Included:** `/home/kgale`, `/data`.

**Excluded:** rebuildable or machine-local bulk — `.venv`, `node_modules`, `__pycache__`,
`*.tmp`, `.cache`, `~/.cache/ms-playwright`, Go module cache, `.local/share/Trash`, Docker
state, browser caches. `/etc/restic` is excluded by construction (not under a source root) —
it holds the key to the repository and belongs in a password manager, not in the snapshots.

## Health signal contract

**v0.1 listed six inherited rules. That was a memorial, not a generator.** The review proved
it three ways, the sharpest being that **office2 still contains an unfixed instance of its own
defect class**: `restic-backup.sh` runs `restic check` weekly and writes
`integrity_check_passed`, and *nothing reads it*. A corrupt repository sets it `false` and
every health surface reports healthy. That is precisely the #902 shape, and the mission wrote
constraint C-003 forbidding unread fields — then did not apply it to the field already there.

### The structural rule (this replaces the table)

> **Every key emitted into the state pointer is either (a) listed in the adjudication table
> below with an explicit good-set, or (b) listed in `diagnostic_only`. A test enumerates the
> keys the producer actually emits and fails if any key is in neither list.**

One mechanism. It generates every rule v0.1 listed, it would have caught office2's
`integrity_check_passed`, and it catches the next unread field for free. It is the difference
between inheriting the rules and inheriting the symptoms.

State pointer: `/srv/backup-office4-state/last-backup.json` (D9), written **atomically**
(`.tmp` + `mv`) from a bash `EXIT` trap on **every** exit — so a stale pointer always means
"the job never fired", never "it fired and we lost the record".

### Adjudication table

| Key | Good-set | Unhealthy when | Why |
|---|---|---|---|
| `restic_exit_code` | `{0, 3}` | anything else, incl. `127` | 3 = warnings but a snapshot was produced. |
| `prune_exit_code` | `{0}` | anything else, incl. `3`, `127`, non-int | `forget` exiting 3 carries no snapshot guarantee. **Never merge this set with the one above** — the named future regression is "someone tidying two near-identical frozensets into one". |
| `snapshot_timestamp_utc` | parseable ISO, age within budget | absent, `null`, unparseable, or **future-dated beyond tolerance** | office2 shipped a hole where `exit 0` + null timestamp read fresh; a first fix guarding only absent/empty still let truthy `"not-a-date"` pass. Guard must be `_parse_iso(...) is not None`. **Future-dating is new in v0.2**: `age = now - ts` is never `> max_age` when negative, so a clock skew pins the component "fresh" indefinitely. office4 is a desktop in a non-UTC timezone; office2 is a UTC server. |
| `files_processed` | `> 0` | `0`, absent, non-int | **New in v0.2.** A source-path typo or over-broad exclude yields exit 0, a real snapshot, a fresh timestamp — and captures nothing. Nothing in v0.1 would have noticed. |
| `source_roots_present` | every configured root appears in the snapshot | any missing | **New in v0.2.** The companion to the above: a snapshot that is non-empty but missing a whole root. |
| `repo_fs_free_bytes` | above threshold | below | **New in v0.2, and office4-specific.** The repo shares `nvme0n1p2` with `/home/kgale`. The terminal state is not "backup fails" — it is "root filesystem full", which takes the machine down. A disk-full backup fails loudly; the slow approach to that cliff had **no signal at all** in v0.1. |
| `integrity_check_passed` | `true`, or `null` when not run | `false` | **New in v0.2.** Weekly `restic check`. v0.1 didn't run it, making office4 *strictly worse* than office2 on integrity. Reading it also repairs the office2 defect — see follow-ups. |
| `snapshot_count` | `> 1` after the first week | `1` on an established repo | **New in v0.2.** `restic init` against a wiped path yields one snapshot: fresh timestamp, exit 0, prune 0, all green, all history gone. |
| `probe_last_tick_utc` | within budget | stale | **New in v0.2.** See "What watches the watcher". |

`diagnostic_only`: `repo_size_bytes`, `script_finished_at_utc`, `snapshot_id`,
`integrity_check_run`.

Sentinels are the integer **`127`**, never `null` — a `null` is skipped by `isinstance` guards
and reads healthy.

Freshness budget: **100800 s (28 h)** — 24 h cadence plus 4 h slack.

### What watches the watcher

v0.1's alerting was emit-on-failure only. **Silence was indistinguishable from health**: a
disabled timer, revoked linger, missing topic env, or unreachable ntfy produced nothing, and
the operator reads nothing as "backups fine". That is the fail-open behaviour promoted to
system level — the very thing the design claims to guard against.

So: the probe writes its **own** tick pointer on every run, and `probe_last_tick_utc` is
adjudicated above. A probe that stops running goes stale and is caught by the next run or a
boot-time check. Alerts go through `scripts/common/alert_bus/` (D6), which ledgers even
undelivered alerts.

### Schema versioning

office4's pointer is **not** office2's. It omits some fields and adds six. Reusing
`schema_version: 1` would assert a compatibility that does not exist, so office4's pointer
carries a distinct `producer: "office4-restic-backup"` field.

**The validator must not be copy-pasted.** v0.1's test plan said tests must exercise "the real
probe" without naming which probe or where it lives — and the path of least resistance is to
copy `_explicit_error`'s logic into a new office4 script, creating a second unenforced coupling.
The contract's own meta-lesson is that all three of its defects were *unenforced couplings*.
Implementation must therefore either share a module with office2's probe or state explicitly
that it is a separate implementation with a separate schema identity.

## Success criteria (from #913)

- [ ] Backup target decided and recorded — this document
- [ ] restic on office4 with its **own** repository, separate from office2's
- [ ] Scheduled via systemd timer **and verified by a successful restore test**
- [ ] Repository password stored outside the tree it protects — ✅ done 2026-08-29, plus 1Password
- [ ] Freshness/health check with an alert path on failure

## Test plan

Per NFR-001, every health check must be demonstrated to report **unhealthy** for its failure
condition, exercised through the real probe rather than a reimplementation.

1. Fresh successful pointer → healthy.
2. `restic_exit_code: 3` → healthy.
3. `prune_exit_code: 3` → **unhealthy**. *The case a careless implementation gets wrong.*
4. `prune_exit_code: 127` → unhealthy.
5. `prune_exit_code: null` → unhealthy, not skipped.
6. Timestamp older than budget → unhealthy.
7. Timestamp `null` with `restic_exit_code: 0` → unhealthy.
8. Timestamp `"not-a-date"` → unhealthy.
9. Pointer absent → unhealthy, distinguishable from "read it and it was bad".
10. Pointer malformed JSON → unhealthy, reported inconclusive, never healthy.
11. **Timestamp future-dated beyond tolerance → unhealthy.**
12. **`files_processed: 0` → unhealthy.**
13. **A configured source root missing from the snapshot → unhealthy.**
14. **`repo_fs_free_bytes` below threshold → unhealthy.**
15. **`integrity_check_passed: false` → unhealthy; `null` → healthy.**
16. **`snapshot_count: 1` on an established repo → unhealthy.**
17. **`probe_last_tick_utc` stale → unhealthy.**
18. **Key-ledger test:** enumerate keys the producer emits; fail if any is neither adjudicated
    nor `diagnostic_only`. *This is the structural rule; it is the one test that generates the rest.*
19. **Repo unreachable** (password unreadable, repo path missing) → both exit codes stay `127`
    → unhealthy. Guards the pre-check office2 gets from `mountpoint -q`, which is meaningless
    here because there is no mount.

## What the review changed (v0.1 → v0.2)

| Finding | Change |
|---|---|
| Table was symptoms, not rules | Replaced with one structural rule + key ledger + test 18 |
| Alert path unmonitored; silence = health | `probe_last_tick_utc` adjudicated; alert_bus instead of direct ntfy (D6) |
| Backup could capture nothing | `files_processed`, `source_roots_present` (tests 12-13) |
| `/data` silently omitted from sources | D10 adds it |
| No capacity signal on a single disk | `repo_fs_free_bytes` (test 14) |
| No integrity check at all | Weekly `restic check`, `integrity_check_passed` **read** (test 15) |
| Future-dated timestamp never stale | Tolerance guard (test 11) |
| Repo re-init reads all-green | `snapshot_count` (test 16) |
| `schema_version: 1` was already lying | Distinct `producer` field |
| Pointer inside the repo dir | D9 moves it out; also unblocks stage two |
| "Stage two changes nothing else" | Corrected — locking, prune cost, `du -sb`, pointer location |

## Follow-ups this review generated

- **office2 defect:** `integrity_check_passed` is written and never read; a corrupt repository
  reports healthy. Violates the C-003 constraint its own mission authored. Needs its own issue.
- **#908 / #913** carry the erroneous 6 TB figure; should read 4 TB SSD, not imminent.

## What is explicitly NOT built

- Off-site replication (#919; stage two above is the cheap path)
- A drift comparator (D7)
- Registration into office2's `service-inventory.json` or felix-canary
- Any deploy-manifest integration — office4 is an unmanaged peer by ADR-0008
