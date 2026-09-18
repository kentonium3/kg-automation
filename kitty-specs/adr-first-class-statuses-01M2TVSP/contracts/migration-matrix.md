# Contract: corpus migration matrix

Closes post-plan review finding **#4 (blocking)** — implementers must not have to infer any document's
standing. Every row below is derived from evidence cited in the source column; nothing is guessed.

**Applies to**: all nine ADRs, RFC #681 (the other `doc_type: decision` document), and the ADR
authoring template.

**Universal changes** (every row): `doc_type` → `decision`; append a `## Decision log` section, empty
(`*No entries.*`) unless rows are listed below. Bodies are **frozen** — no row edits body prose, and
existing body `Status:` lines are left as historical text. Frontmatter is authoritative (FR-007).

| # | Target status | Seed log rows (`Date · Type · Summary`) | Source / evidence |
|---|---|---|---|
| 0001 | `approved` | — | frontmatter + body + index all agree |
| 0002 | `approved` | `2026-07-23 · amendment · Decision Q6 (identity attribution) superseded by ADR-0007; the remaining decisions stand. · ADR-0007` | Index reads "approved (Q6 superseded by 0007)". **Not** `superseded-by` — ADR-0002 is not superseded as a whole, and `partially_superseded` does not exist (C-004). |
| 0003 | `approved` | `2026-06-09 · amendment · Promoted from Draft to Approved; the #508 operator-review condition set in the body was met on 2026-06-06. · #508, #507` | **Corpus self-disagreement, resolved by Kent 2026-09-18.** Body set its own promotion condition ("operator review on #508 promotes to Accepted"); #508 closed 2026-06-06; both indexes record approved 2026-06-09; Epic #507 shipped via #518/#519/#520 and `sync-driver-ops.md` documents the driver as live. The ADR's own metadata was never updated. |
| 0004 | `approved` | Migrated from the existing `## ACL changes log` — see **Special case** below | That section already holds real history, including an entry that belongs to ADR-0008 |
| 0005 | `approved` | — | frontmatter + body + index agree |
| 0006 | `approved` | — | frontmatter + body + index agree |
| 0007 | `approved` | — | Body says "Accepted", frontmatter says `approved`. Body is frozen and left as-is; frontmatter governs (C-005, FR-007). |
| 0008 | `approved` | `2026-08-29 · erratum · The ADR-0004 review affirmation cites RunSSH:false on office4; that reasoning is backwards in direction — RunSSH:false governs SSH *into* office4, while what widened is office4's ability to reach office2. The conclusion (ADR-0004 unchanged) stands. · ADR-0004 ACL changes log, #931` | **The originating defect.** This erratum was filed in ADR-0004's log and never reached a reader of ADR-0008 — observed live on 2026-09-18. Body also says "Accepted"; same treatment as 0007. |
| 0009 | `proposed` | — | Kent's approval covers the Person entity and the taxonomy work, not ADR-0009's own substance, which remains open on #986. |
| RFC #681 | `draft` | — | `docs/design/research/felix-workspace-api-vs-gog-681.md` — already `doc_type: decision` and already `draft`. Needs only the log section. |
| `docs/_templates/decision.md` | n/a (template) | n/a | Emits `doc_type: reference` and no decision log, so new ADRs would violate the contract at creation. Must emit `decision`, `status: draft`, and an empty log. Regression test over rendered output (review finding #9). |

## Special case — ADR-0004's existing `## ACL changes log`

Closes post-plan review finding **#3 (blocking)**. ADR-0004 already solved this problem locally, three
months before the mission. Its log must not be duplicated, rewritten, or orphaned.

**Complication**: three live files still direct authors to write there — `security-posture.md`,
`signal-to-doc-map.json`, and ADR-0009's References section. ADR-0004's own body text also instructs
that ACL changes "MUST be recorded as an amendment to this ADR ... or a §'ACL changes' appendix here".

**Required handling**:

1. **Preserve** the existing `## ACL changes log` section verbatim. It is frozen body content and holds
   genuine history.
2. **Append** the canonical `## Decision log` after it, carrying forward the entries that are about
   ADR-0004 itself, mapped to the `Type` vocabulary — the 2026-06-09 action change and the 2026-08-29
   `users` narrowing are `amendment`; the office4 SSH enablement is `context`.
3. **Relocate, do not copy**, the entry that is about ADR-0008 — it is seeded into ADR-0008's log
   (row 0008 above). ADR-0004's legacy section is not edited, so the original text stays where it is;
   the canonical entry now also exists in the document it concerns.
4. **Close the legacy route** with a pointer at the top of the canonical log saying future entries go
   there, without rewriting the frozen section.
5. **Update the three external pointers** so new writes are routed to the canonical log.

**Why this is not optional**: appending a second log while three files still point at the first would
leave two competing logs with new traffic flowing to the obsolete one — reproducing the exact failure
this mission exists to fix, in the one place it had already been solved.

## Verification (SC-001)

For each of the eleven rows: standing and complete amendment history are derivable from that document
alone. Specifically — ADR-0002 surfaces its dead Q6; ADR-0003 surfaces its promotion; ADR-0008 surfaces
its own erratum. Asserted by test, not inspection.
