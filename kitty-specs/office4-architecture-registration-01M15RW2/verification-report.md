# Verification Report — Register office4 in the Architecture

**Mission**: `office4-architecture-registration-01M15RW2`
**Date**: 2026-08-29
**Produced by**: WP06 (closeout)

Every quickstart step has a concrete result below. Where a step could not be run, it is
recorded as **NOT RUN with the reason** — never as passing. That distinction is the point:
a check that cannot tell "verified false" from "couldn't check" is the defect class this
repo keeps hitting, and this report exists partly to avoid adding to it.

## A note on what "verified" means here

The mission merges five lane branches; **at the time of writing, none are merged**, so no
single tree contains the complete output. Each fact below was therefore verified against the
lane that *owns* it, plus a read-only merge-safety analysis. The whole-tree checks are marked
**deferred to post-merge** with the exact command to run. This is a consequence of putting
verification in a work package, which necessarily runs before merge — a plan-level design
choice worth revisiting next time, not a tool fault.

## Quickstart results

| Step | Check | Result | Evidence |
|---|---|---|---|
| 1 | `validate_architecture_data.py --strict` | **PASS** | `OK (0 findings)`, exit 0, run per lane |
| 1 | `validate_docs.py` | **PASS** | `validate_docs: OK`, exit 0, run per lane. Must use `.venv/bin/python`; `~/.local/bin/python3` (first on PATH) lacks pyyaml and exits 1 |
| 2 | 4 devices / 4 hosts / office2 rich + `hosts[0]` | **PASS** | `['office2','kents-macbook-pro','iphone-14-pro-max','office4']` in both records; office2 the only entry with `disks`/`bios` |
| 3 | Zero office4 service records | **PASS** | All **47** services `host: office2`. Positive assertion, would fail if violated |
| 4 | All four IPs match the live tailnet | **PASS** | `tailscale status` reconciled against `network-topology.json` — all four match, not office4 alone |
| 4b | `os` / `hardware` provenance | **PASS** | `/etc/os-release` → `NAME="Linux Mint"`, `VERSION="22.3 (Zena)"`, **`UBUNTU_CODENAME=noble`** (that third line is what sources the recorded parenthetical); sysfs → `Framework` + `Desktop (AMD Ryzen AI Max 300 Series)`. Both match. `uname -a` deliberately not used |
| 5 | ADR registered in all four surfaces | **PASS** | Per-file loop on `0008-three-machine-model` passed for `adr/README.md`, `INDEX.md`, `DEVELOPER_PORTAL.md`, `architecture/README.md` |
| 5b | Adjacent surfaces | **PASS** (but incomplete — see PM-2) | glossary names four devices + all four canonical terms; `CLAUDE.md` has the office4 row; signal map's `network-topology-changed` entry names `hardware-inventory.json` — verified with the precise selector **and its inverse** (path appears in no other entry) |
| 5c | Review-only affirmations | **PASS** | ADR 0008 `### Review-only affirmations` covers `adr/0004` (citing `RunSSH: false`) and `phone-termius-setup.md` |
| 6 | ADR answers its five questions | **FAILED when finally run → since fixed** | This row first read PASS on the evidence "verified across four independent review cycles" — a citation of other work, not an execution of the step. Nobody had run it. When this report's reviewer did, **Q4 was not answerable**. See F1 |
| 7 | `Rebaseline:` line on the integration commit | **NOT RUN — deferred by design** | Requires a `feat → main` merge that does not exist yet. See Handoff below |
| — | Diff scope (C-001 Tier 4, C-002) | **PASS** | All five lanes confined to `docs/`, `CLAUDE.md`, `kitty-specs/`. Nothing under `scripts/deploy/**` or `deploys/**` |
| — | Links introduced by this mission resolve | **PASS** | 285 relative links swept across the 12 changed files; **282 resolve**. The 3 that fail are pre-existing (base lines 36-38 of `architecture/README.md`), not introduced here — filed as **#927** |
| — | Heading hierarchy | **PASS** | No skipped levels in any of the 9 changed markdown files |
| — | Lane merge safety | **PASS** | See below |

## Merge-safety analysis (read-only)

lane-c branched from lane-a *before* WP01's correction, so it still carries the superseded
`updated_by` containing the false "exposes no port" phrase. This looked like a hazard —
merging could have silently reintroduced a corrected falsehood into the **authoritative** JSON.

Verified it is safe, by computing the merge rather than reasoning about it:

- The three-way merge base for that file is `390bc686` (lane-a's original WP01 commit), which
  lane-c inherited **unchanged**.
- Git therefore sees only lane-a as having modified the line, and lane-a's fix wins.
- Computed merge of lane-a + lane-c: `exposes no port` → **0 occurrences**;
  `It does run standard sshd` → **1**. Correct text survives.

All five lanes also merge cleanly against the mission branch individually. **No rebase was
performed** — it would have been unnecessary churn on approved work.

## SC-005 accounting — every doc target

**8 named by the signal-to-doc map:** 6 updated (`network-topology.json`,
`physical-topology.md`, `security-posture.md`, `INDEX.md`, `DEVELOPER_PORTAL.md`,
`architecture/README.md`) + 2 affirmed review-only (`adr/0004`, `phone-termius-setup.md`).

**5 the map does not name, but which the mission required:** `adr/README.md` (the actual ADR
index), `hardware-inventory.json`, `glossary.md`, `CLAUDE.md`, `signal-to-doc-map.json`.

FR-015 closes that gap for `hardware-inventory.json`, so the next device addition inherits it
from the map rather than depending on a reviewer noticing. **13 of 13 accounted for, none
silently skipped.**

## Issue correction (FR-012)

Posted: <https://github.com/kentonium3/kg-automation/issues/909#issuecomment-5460474191>

Covers both required corrections — the false `hardware-inventory.json` premise, and the
post-change verification step that invoked the validator without `--strict` and therefore
could not fail.

## ⚠️ Handoff — the one obligation this mission cannot satisfy itself

**C-004 requires the `feat → main` integration commit to carry:**

```
Rebaseline: not required — documentation and architecture metadata only
```

**It must be created with `git merge --no-ff`.** A fast-forward produces no commit to carry
the line, and `spec-kitty merge` exposes no commit-message option (16 flags; none of them
sets a message — every one was checked). Amending
spec-kitty's merge commit would be a prohibited manual git workaround.

Verify after that merge, on `main` — **both** checks, because the message grep alone would
pass on an ordinary one-parent commit:

```bash
git log -1 --format=%B | grep -i "^Rebaseline:"
```

```bash
test "$(git rev-list --parents -n1 HEAD | wc -w)" -eq 3 && echo "OK: two-parent merge commit"
```

**Docs CI has the same shape**: `.github/workflows/docs-ci.yml` triggers only on `main`, so it
does not fire on the mission merge. SC-006 is satisfied at commit time by the `.githooks` gate
and at Kent's push by CI.

## Findings raised during closeout

| # | Issue | Note |
|---|---|---|
| **#927** | 3 pre-existing broken links in `architecture/README.md` — and nothing in the repo checks links | Found by the sweep above; not introduced here |
| **#926** | office4 sshd accepted password auth over the tailnet | **Remediated and closed by Kent during the mission**; re-probed and confirmed `publickey` only |
| **#925** | `felix-vikunja-sync.timer` documents catch-up that `Persistent=` cannot provide without `OnCalendar=` | Found while the ADR was about to cite it as an example |
| **#922 / #924 / #3795** | spec-kitty defects (specify Decision-Moment ordering; stale documentation-mission WP template) | #3795 filed upstream with approved copy |


## Post-merge Codex review — FAIL, then fixed

The mandatory post-merge review ran against the complete merged diff before the feature branch
reached `main`, and returned **FAIL** with three blocking findings. All three were cross-WP or
whole-diff problems that no per-work-package review could have seen. All were verified and
fixed in a follow-up commit on the feature branch.

**PM-1 — the ADR's placement test routed a real managed workload to office4.** The test asked
only "annoyance or data loss?". Applied to `felix-deployer` — a five-minute systemd timer whose
queue is durable under `deploys/queued/` — ten unwatched minutes lose nothing and cost only
delay. "Recoverable" ⇒ **office4**, contradicting the same ADR's statement that office2 is the
sole deployer target.

The defect was structural: a binary recoverable/unrecoverable test silently assumes every
candidate *may* be attended. The test is now two ordered questions — **(1) must this run when
nobody is watching?** (if yes, office2, regardless of cost) then **(2) is ten unwatched minutes
recoverable?** — and a third worked case (`felix-deployer`) was added showing why the ordering
is load-bearing. This is the ADR's central contribution, and it was wrong.

**PM-2 — three surviving three-device claims, and the mechanism fix did not cover them.**
`docs/design/README.md:115` ("syncs across all devices"), `:208` ("connecting all three"), and
`docs/design/architecture/service-inventory.md:214` ("across all three devices") all became
false when office4 was registered — **the same defect class the mission had already fixed
twice** (in `CLAUDE.md` and the glossary), in files nobody had looked at. `docs/design/README.md`
also still listed three devices and opened "Felix runs in three places".

Worse, `signal-to-doc-map.json`'s `network-topology-changed` entry routed neither file, so the
next device addition would have repeated it exactly. Both files are now targets, and the
rationale explicitly tells the next author to sweep for device counts and "all devices" / "all
three" phrasing, which no validator checks.

**This invalidated SC-008** ("no repo surface contradicts ADR 0008"), which was recorded as PASS
above on the strength of checking only the surfaces the mission had touched. SC-008 is true
again now — but it was false at the moment this report first claimed it, and the check that
would have caught it was a repo-wide sweep the report never ran.

**PM-3 — the issue-matrix `#909` row was still `in-mission`**, a non-terminal verdict the
mission-review gate rejects. Flipped to `fixed` through the CLI seam with merged-tree evidence.

**PM-4 (advisory, accepted)** — the three hard-named ADR-0008 pointers sit outside the ADR
index's supersession convention. Already recorded as accepted debt above; unchanged.

### What this says about the review chain

Sixteen work-package review cycles passed this mission. The post-merge review, looking at the
whole diff at once, still found that the ADR's central test gave the wrong answer for a real
service and that three false claims survived in files no WP owned. Per-WP review is structurally
incapable of seeing either: the first requires applying the test to workloads outside the
mission's scope, the second requires looking at files the mission never touched.

## Findings raised BY this report's own review

Both blocking findings were cases of the mission's standard not being applied to itself.
Recorded rather than fixed here, per this WP's scope rule — report it, let the owning WP fix
it. All three below have since been fixed.

**F1 — Q4 of the ADR's five questions was not answerable (owner: WP02).** The constraint
turned on "felix-deployer-recognisable path" and never defined it. The only in-document
referent was `/home/claude/kg-automation`, which the adjacent constraint makes impossible on
office4 — while office4 holds a checkout at `/home/kgale/repos/kg-automation`, the tree this
report was produced in. A reader could not determine whether that was a breach. For a
constraint with no mechanical enforcement, being unactionable is the whole failure.

It survived four review cycles because step 6 above was recorded PASS on borrowed evidence.
**That is the more important half of this finding:** the check that would have caught it was
the one this report declined to actually run.

**F2 — adding the office4 row to `CLAUDE.md` made a neighbouring line false (owner: WP05).**
The Platform table's `Obsidian Sync` row read "across **all devices** including office2";
inserting office4 four rows above made that generalisation sweep in a machine with no vault.
WP05 had established that fact and applied it correctly to the glossary, then missed it in the
file it was editing. Step 5b passed `CLAUDE.md` on the narrow "does the table include office4"
test — satisfied, and beside the point, since FR-014 exists so the repo's highest-traffic file
does not contradict the decision.

**F3 — the fix for F1 introduced a false claim of its own (owner: WP02).** Cycle 3 asserted
the two office4 constraints were "mutually reinforcing" — that with no `claude` user the
recognised path *cannot exist*. False: directory existence is independent of the passwd
database, office4 itself carries `/home/linuxbrew` with no `linuxbrew` user, and
`felix-deployer/` and `lib/` contain zero identity lookups. It also contradicted three
downstream statements that the ADR is the *only* barrier. In a document arguing it is the sole
guard, telling the reader a breach is impossible is exactly the belief that stops anyone
checking.

Provenance worth recording: that reasoning originated in **this mission's own review
feedback**, and was then implemented faithfully. Fidelity to bad feedback does not rescue it.

## Two process notes

**The Quality Gate is literally unmet, on one reading.** spec.md's Quality Gates say "No
broken relative links in the touched files." There are three, in a touched file. The table
row above uses NFR-004's narrower wording — links *introduced or edited by this mission* — 
which passes. Both readings are stated here rather than the convenient one being quietly
chosen. The three are pre-existing and filed as #927.

**The orchestrator broke a rule, twice.** During WP05's cycle-2 fix and again while correcting
this report, `action implement` was **refused** (`dependencies_not_satisfied`) and the work
proceeded anyway, because the claim and the edit were issued in one shell invocation that did
not halt on a non-zero exit. Both were reverted and re-done after a verified claim. The
underlying tool gap — the dependency gate is enforced by `implement` but not by `move-task
--to for_review` — is filed as **#928**. The tool being lenient does not excuse it; the
refusals were unambiguous.

## Corrections to this mission's own record

Recorded because the mission's standard should apply to itself:

1. **WP05's fix commit overstates its evidence.** It says "no `.obsidian` directory anywhere
   under `/home/kgale`." There are six — the git-tracked `docs/.obsidian` vault config,
   replicated per lane worktree. The *conclusion* (office4 is not an Obsidian Sync target) is
   correct and rests on facts that do hold: no `~/second-brain`, Obsidian not installed.
2. **WP03's approved text says office4's sshd posture "is tracked separately in #926."** #926
   is now closed and remediated. The sentence remains accurate — the issue records the
   posture — but a reader may expect it open. Not worth reopening an approved WP.
3. **Three ADR pointers — `DEVELOPER_PORTAL.md`, `architecture/README.md` and `CLAUDE.md` — hard-name
   ADR-0008** and sit outside the ADR index's supersession convention. If 0008 is ever
   superseded they go stale silently. This is a debt the WP prompt created by asking for 0008
   to be named, not a deviation from it.
