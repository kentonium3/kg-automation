# WP06 Review — Cycle 1 — REJECT

Reviewer: codex (advisory, read-only). Verdict recorded by the orchestrator, which independently
verified the finding and agrees it blocks.

**The runbook itself passed on every substantive check**, including the ones most likely to fail:

- **Guarantee correctly bounded** — silent inertness impossible; deliberate inertness still possible
  through reviewed `diagnostic_only` entries. This is the claim the *spec* had to be corrected for
  overstating, and the runbook gets it right.
- **Drift caveat prominent**, explains the repo/live split and the observe-only comparator, and
  carries the check command.
- **No stale enumeration** — documented schema matches the producer and the ledger: v2, 14 keys,
  10 adjudicated + 4 diagnostic. Cross-checked against both sources.
- **Operator handoff runnable.** Rejecting the orchestrator's suggested install path was correct —
  that path does not exist on office2 — and the substituted procedure (fetch the reviewed commit,
  verify the hash, install) is coherent. Manual-install rationale, ≤24 h snapshot pre-flight, drift
  convergence and next-run-14-keys verification are all present.
- **The sequencing warning is explicit** — that the live component reads unhealthy until the producer
  is installed. An unwarned operator would have thought the mission broke the backup.
- **`last_integrity_check_utc` vs `integrity_check_run`** explained unusually well.
- **"What this does not cover"** names both R-001 and #937.
- `docs/INDEX.md` now makes a previously undiscoverable runbook navigable; `DEVELOPER_PORTAL.md`
  already linked it, so no change was needed there.

Your deferral of `service-inventory.md` and `service-dependencies.view.md` was also **correct** — I
verified independently that neither enumerates pointer fields, and no service identity, schedule, or
dependency edge changed. They are not made false by this mission.

One blocking gap.

---

## `docs/design/felix-capability-roadmap.md` is now overstating a shipped capability

Line 260 carries the row:

> **Backup integrity observability** | ✅ Shipped (2026-08-28) | #902, #903, #906 | *"Three defects
> sharing one shape — a mechanism meant to make failure visible did not."*

That row is now wrong in a way this mission specifically cares about. There was a **fourth** instance
of that same shape, and it was left behind **by that very mission**: `#902` added `prune_exit_code`,
wrote constraint C-003 forbidding unread pointer fields, applied it to the field it was adding — and
did not sweep `integrity_check_passed`, which was already sitting there unread. A repository that
`restic check` had *proven* corrupt reported healthy on every surface.

So the roadmap tells a reader that capability is closed when the class was still open. **That is the
roadmap overstating completion, which is this mission's own subject matter** — leaving it would be
self-refuting in exactly the way the stale field enumeration would have been.

I have extended WP06's `owned_files` to include the roadmap, so this is now in scope for you. No other
work package owns that file.

**Required:** update the roadmap so it is true after this mission. At minimum:

1. Amend or annotate the #902/#903/#906 row so it no longer reads as closing the class — it closed
   three instances and left a fourth. State that plainly; the roadmap's value is that it is honest
   about what shipped.
2. Add a row for this mission (#934) describing what actually changed: the pointer-key ledger — every
   emitted key is either adjudicated with an explicit good-set or declared `diagnostic_only` with a
   written reason, enforced by a test that executes the producer and reconciles both directions.
   Note the producer gained four keys (`last_integrity_check_utc`, `files_processed`,
   `source_roots_present`, `repo_fs_free_bytes`) at `schema_version: 2`, closing three of the four
   catastrophic conditions the office4 v0.2 review identified.
3. State the **stated limits** honestly, in the style the existing rows use:
   - the unwatched alerter (spec R-001) remains open — the canary's liveness is self-observed, so a
     stopped runner cannot report itself
   - the other 16 pointer-emitting components have no ledger (#937)
   - the producer install remains a manual privileged step **by decision** (the existing row already
     makes this point for #902; keep it consistent rather than repeating it as if new)
4. Follow the file's existing row format and voice. Read neighbouring rows first — they are dense,
   specific, and state limits explicitly. Match that.

**Do not** claim this mission closes the class entirely. It makes *silent* inertness impossible;
deliberate inertness remains available through a reviewed `diagnostic_only` entry. The runbook already
states this correctly — keep the roadmap consistent with it.

---

## Note

The reviewer could not run `validate_docs.py` (no venv in its sandbox, system Python without PyYAML).
You ran it with OK. Re-run after this change — the roadmap is a docs-CI-gated file.
