---
title: "#849 synthesis — the cast: Person nodes, alias lists, and raw handles"
doc_type: research
status: draft
owner: claude-office4
last_updated: 2026-09-24
---

# #849 synthesis — step 1: the cast

Seed material. Everything here is a primitive the arms may see.

## The authoring rule that governs this file

From Arc D's *What survives* (the rule outlived the arc's cut) and the design lead's 2026-09-24
04:04Z ruling:

> The **stream carries raw per-channel handles, never pre-resolved.** The **`Person` node carries
> the alias list.** Synthesis must not resolve handle → Person in the stream.

So `mvale@spec-kitty.example` appears in the email stream exactly as written; nothing in the
stream says it is Marcus. The `aliases` list on `PER_MARCUS` is what makes the resolution
possible, and doing it is the arms' job — deterministically and at $0, per the
identity-resolution rule, which is *why* Arc D was cut as a reasoning test.

**Consequence for me:** every handle below must appear in the stream in its raw form and must
never be annotated. A stream row reading `from: Marcus Vale <mvale@…>` would pre-resolve it and
quietly hand over the one thing Arc C's Person-hub hop is supposed to exercise.

---

## Person nodes

`Person` is ratified (Kent, 2026-09-18) and is a cross-cutting hub: nothing is sourced *from* a
Person, and a Person has no upward edge. `is_contact` landed accepted @ee1311a5 — it is the
$0 lookup Arc E's router needs.

| id | name | relationship | organisation | is_contact | aliases (raw handles as they appear) | arcs |
|---|---|---|---|---|---|---|
| `PER_MARCUS` | Marcus Vale | collaborator | spec-kitty | ☑ | `mvale@spec-kitty.example` · `Marcus Vale` (cal) · `@marcus` (Slack) · `marcus.vale@spec-kitty.example` | A |
| `PER_FRED` | Fred Okafor | collaborator | spec-kitty | ☑ | `fokafor@spec-kitty.example` · `@fred` (Slack) · `Fred Okafor` (cal) | C |
| `PER_DANA` | Dana Reyes | collaborator | spec-kitty | ☑ | `dreyes@spec-kitty.example` · `@dana` (Slack) | C (near-miss 3) |
| `PER_PRIYA` | Priya Raman | collaborator | spec-kitty | ☑ | `praman@spec-kitty.example` · `@priya` (Slack) | F (wk 6 time-zone call) |
| `PER_JOEL` | Joel Whitaker | peer | — | ☑ | `joel.whitaker@example.net` · `+1-555-0142` (WhatsApp) | B (wk 2 birthday), E (friend, wk 21) |
| `PER_CLIENT` | Alina Duarte | client | Intentional | ☑ | `aduarte@duarte-partners.example` | E (meeting request, wk 3) |
| `PER_ACCOUNTANT` | Ray Mbeki | vendor | Mbeki & Co | ☑ | `ray@mbeki-co.example` | E (tax document, wk 17) |
| `PER_CEO` | Sondra Falk | collaborator | spec-kitty | ☑ | `sfalk@spec-kitty.example` · `@sondra` (Slack) | A (near-miss 7a) |

**Two episodes must carry their own justification, or the arcs they belong to
collapse into their main case** (design-lead review, 2026-09-24T04:30Z):

- `PER_CEO`'s Arc A near-miss 7a episode must **state the announcement's
  importance in its own text**. Near-miss 7a is "the exception fires and PT
  moves"; the main arc is "the exception does not fire and PT holds". If the
  episode does not say why the CEO's meeting is high-importance, the two are
  indistinguishable from the corpus and both answers score identically.
- The same applies to Arc A near-miss 4, where Marcus moves the 1:1 *with*
  enough notice *and* a high-importance reason.

All eight are `is_contact: True` — they are precisely the people whose mail must always surface
in E2. That is the **test**, not the tone: E2 near-miss 1 is friendly-looking spam from someone
*not* on this list, and it must not surface.

### Deliberately NOT Person nodes

- **Northside PT** — Arc A's cast lists it as a `vendor`, but it is an organisation, not a human,
  and nothing in any oracle needs to reason about a person there. It is the `counterparty` string
  on the PT `Commitment`s and the calendar-event organiser in the stream. See Q4.
- **The ~25 vendor orgs and ~15 newsletter orgs** of Arc E — these are **episode provenance**
  (sender address on an email), not nodes. No oracle asks anything about them as entities; E2
  only asks whether their mail is digested, filed or dropped. Minting 40 Person nodes for them
  would inflate the graph with entities no question traverses, and would blur the `is_contact`
  test by making non-contacts look structurally identical to contacts.
- **Kent** — the ego is implicit; every edge would otherwise sprout a Kent endpoint (design
  lead's 04:23Z ruling).

---

## Handle → Person resolution table (NOT seeded; for oracle scoring only)

This table is **oracle-side**. It goes in the hidden artifact, not the seed. It is written here
only so the seed author and the oracle author agree, and it will be **moved out** of this file
before the seed is handed to any arm.

**Freeze requirement** (design lead, 04:32Z): the freeze check must grep the *rendered* corpus
for this table's rows, exactly as it does for oracle `must_identify` phrases and seed comment
lines. A resolution table that leaked into what an arm reads would hand over Arc C's Person-hub
hop — the one thing Arc D's cut left this corpus still exercising.

Resolution is deterministic from the alias lists above; no inference is required or measured.

---

## Q4 — organisations are NOT nodes — **RULED** (design lead, 2026-09-24T04:32Z, stability: accepted)

My reading stands. There is **no `Organisation` entity**. An organisation appears in exactly
three places, all already in the ontology:

1. `Person.organisation` — where a human works;
2. `Commitment.counterparty` — a string when the counterparty is an org, a `COMMITTED_TO` edge
   when it is a human;
3. **episode provenance** — the sender address or domain on an email, or the calendar organiser.

Filing offers "by vendor organisation" is a **$0 string operation on the sender domain**, and E2
scores the *decision*, not the mechanism. No oracle question traverses an organisation, so
minting ~40 org nodes would add entities nothing reads and would blur the `is_contact` test by
making non-contacts structurally identical to contacts.

**The trigger for revisiting**, recorded so this is not re-asked: a question that must *traverse*
an org — e.g. *"what have I committed to anyone at Duarte Partners?"*. No such question exists in
#849. Noted in the design doc under §Tier Definitions → PERSON (@ffb8834d).

---

## Next

Cast is complete for the five authored arcs; Q4 is ruled. Arcs A and C are seeded. Q1 is ruled
(standing-practice exception + `EMBODIES`, ratified by Kent 2026-09-24), so **Arc F is
unblocked**. Remaining: seeds for F, B and E, then the Arc E generator, then the hidden oracle.
