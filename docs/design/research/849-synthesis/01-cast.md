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
| `PER_JOEL` | Joel Whitaker | peer | — | ☑ | `joel.whitaker@example.net` · `+1555…` (WhatsApp) | B (wk 2 birthday), E (friend, wk 21) |
| `PER_CLIENT` | Alina Duarte | client | Intentional | ☑ | `aduarte@duarte-partners.example` | E (meeting request, wk 3) |
| `PER_ACCOUNTANT` | Ray Mbeki | vendor | Mbeki & Co | ☑ | `ray@mbeki-co.example` | E (tax document, wk 17) |
| `PER_CEO` | Sondra Falk | collaborator | spec-kitty | ☑ | `sfalk@spec-kitty.example` · `@sondra` (Slack) | A (near-miss 7a) |

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

Resolution is deterministic from the alias lists above; no inference is required or measured.

---

## Q4 — organisation-as-sender: a question for the design lead

Arc A's cast lists **Northside PT** with `relationship: vendor`, and Arc E's lists ~25 vendor
orgs and ~15 newsletter orgs the same way. But `Person` carries `organisation` as an
*attribute*, which reads as "Person = human, org = where they work".

Three things in the corpus are organisation-shaped senders with no human attached: the PT studio
(Arc A), the vendor/newsletter senders (Arc E), and the doctor's office and billing sender
(Arc E's buried-and-missed set).

My reading, and what I have built to unless you correct it: **they are not nodes.** The PT studio
is a `counterparty` string plus a calendar organiser; the Arc E senders are episode provenance.
Nothing in any oracle traverses them, and E2's scored decisions are all reachable from
`is_contact` plus the interest list plus Kent's own bills and appointments — none of which needs
an org node.

The case against my reading: Arc E's automation spec says offers are **auto-filed by vendor
organisation**, which implies the organisation is a first-class thing the router groups by. If
that grouping has to be a graph traversal rather than a string match on the sender domain, then
orgs need to be nodes and `Person` is the wrong type for them.

I do not think it does — filing by sender domain is a $0 string operation and E2 scores the
*decision*, not the mechanism — but it is your call whether the ontology should carry an
organisation entity, and it is cheaper to answer now than after ~5,000 emails are generated.

---

## Next

Cast is complete for the five authored arcs pending Q4. Next bite is the per-arc primitive seed
for **A, B, C, E** — entities and edges only, no asserted conflict, drift or pattern. Arc F's
seed waits on Q1 (the principle-2 / answer-leakage ruling in `00-context-chains.md`).
