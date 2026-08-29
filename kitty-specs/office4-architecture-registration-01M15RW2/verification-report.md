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
| 4b | `os` / `hardware` provenance | **PASS** | `/etc/os-release` → `NAME="Linux Mint" VERSION="22.3 (Zena)"`; sysfs → `Framework` + `Desktop (AMD Ryzen AI Max 300 Series)`. Both match the recorded values. `uname -a` deliberately not used |
| 5 | ADR registered in all four surfaces | **PASS** | Per-file loop on `0008-three-machine-model` passed for `adr/README.md`, `INDEX.md`, `DEVELOPER_PORTAL.md`, `architecture/README.md` |
| 5b | Adjacent surfaces | **PASS** | glossary names four devices + all four canonical terms; `CLAUDE.md` has the office4 row; signal map's `network-topology-changed` entry names `hardware-inventory.json` — verified with the precise selector **and its inverse** (path appears in no other entry) |
| 5c | Review-only affirmations | **PASS** | ADR 0008 `### Review-only affirmations` covers `adr/0004` (citing `RunSSH: false`) and `phone-termius-setup.md` |
| 6 | ADR answers its five questions | **PASS** | Verified across four independent review cycles |
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
the line, and `spec-kitty merge` exposes no commit-message option (`--strategy`, `--target`,
`--delete-branch`, `--remove-worktree`, `--push`, `--dry-run`, `--json` only). Amending
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

## Corrections to this mission's own record

Recorded because the mission's standard should apply to itself:

1. **WP05's fix commit overstates its evidence.** It says "no `.obsidian` directory anywhere
   under `/home/kgale`." There are six — the git-tracked `docs/.obsidian` vault config,
   replicated per lane worktree. The *conclusion* (office4 is not an Obsidian Sync target) is
   correct and rests on facts that do hold: no `~/second-brain`, Obsidian not installed.
2. **WP03's approved text says office4's sshd posture "is tracked separately in #926."** #926
   is now closed and remediated. The sentence remains accurate — the issue records the
   posture — but a reader may expect it open. Not worth reopening an approved WP.
3. **The two ADR pointers in `DEVELOPER_PORTAL.md` and `architecture/README.md` hard-name
   ADR-0008** and sit outside the ADR index's supersession convention. If 0008 is ever
   superseded they go stale silently. This is a debt the WP prompt created by asking for 0008
   to be named, not a deviation from it.
