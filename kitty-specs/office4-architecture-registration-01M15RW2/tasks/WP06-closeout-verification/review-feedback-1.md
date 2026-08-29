# WP06 Review Feedback — cycle 1

**Verdict**: REQUEST-CHANGES (narrow)
**Date**: 2026-08-29

The reviewer re-ran the entire suite independently — including computing the five-lane merge
themselves — and reproduced nearly every claim to the digit: 4/4 devices, 47 office2-only
services, all four live IPs, the os/hardware provenance, the per-file registration loop, the
signal-map selector *and its inverse*, the diff scope, the 13/13 SC-005 accounting, and the
link sweep at exactly 285/282/3. The merge-safety analysis was independently recomputed and
confirmed: 0 occurrences of the false phrase in the merged tree. The #909 comment's citations
were all checked and none is overstated.

Two findings block, both cases of the mission's standard not being applied to itself.

## 1. MODERATE — step 6 is a laundered PASS

Step 6's evidence reads *"Verified across four independent review cycles."* That cites other
people's work rather than executing the step. Those were WP02's implement-review cycles,
reviewing FR-001–FR-005 compliance; grepping all eight review-cycle artifacts, only one
mentions the placement test, in passing. **Step 6's actual test — can a reader answer five
questions without leaving the document — was never run by anyone.**

And it was hiding a real defect. **Q4 was not answerable**: the constraint turned on
"felix-deployer-recognisable path", which the ADR never defined; the only in-document referent
was `/home/claude/kg-automation`, which the next constraint makes impossible on office4.
Meanwhile office4 holds a checkout at `/home/kgale/repos/kg-automation` — the tree WP06 itself
ran in — and a reader could not tell whether that was a breach.

This is precisely the row the WP prompt warned about: *"an unquantified pass is
indistinguishable from a skipped check."*

**Required fix**: downgrade step 6 from PASS and record the finding. The ADR fix belongs to
WP02 per WP06's own scope rule ("report it and let the owning WP fix it") — and has since been
made, across two further cycles.

## 2. MODERATE — an unadmitted defect the mission introduced

`CLAUDE.md`'s Platform table gained an office4 row four lines above an untouched
*"| Obsidian Sync | Vault sync across **all devices** including office2 |"*. Adding office4 to
that table makes "all devices" sweep it in — falsely.

WP05 established exactly this fact and applied it correctly to the **glossary**, deliberately
leaving its entry at "Mac, iPhone, and office2" and recording why. It did not apply the same
reasoning to `CLAUDE.md`, the file it was editing in the same commit. WP06's step 5b passed
`CLAUDE.md` on the narrow "does the table include office4" test, which is satisfied — but
FR-014's stated purpose is that the repo's highest-traffic file must not contradict the
decision.

**Required fix**: record it in the Findings table. (WP05 has since fixed it.)

## LOW findings, to fold in

- **Self-correction #3 undercounts.** It names two hard-named ADR-0008 pointers
  (`DEVELOPER_PORTAL.md`, `architecture/README.md`); `CLAUDE.md` carries a **third**, added by
  WP05 — and step 5b verified `CLAUDE.md`.
- **The handoff's flag list is presented as exhaustive and is not.** `spec-kitty merge` has 16
  flags; the report names seven and says "only". The conclusion (no commit-message option)
  holds — the reviewer checked every one — but "only" is false in a report whose entire value
  is precision.
- **Step 4b's shown evidence does not demonstrate its own conclusion.** It prints
  `NAME="Linux Mint" VERSION="22.3 (Zena)"` then asserts both match the record, which reads
  `Linux Mint 22.3 (Ubuntu 24.04 noble base)`. The parenthetical *is* legitimately sourced —
  `UBUNTU_CODENAME=noble` is in the same file — but the report does not show that line.
- **The spec's Quality Gate says "No broken relative links in the touched files"** and is
  literally unmet (3, in a touched file). The report's row uses NFR-004's narrower wording and
  discloses all three plus #927 — honest handling, but the tension deserves a sentence.

## Informational, no action

- Quickstart step 8 has no table row; it is covered in its own section with the comment URL.
- `acceptance-matrix.json` is entirely `pending` with placeholder criteria. Not WP06's file,
  but it will block `accept`.
