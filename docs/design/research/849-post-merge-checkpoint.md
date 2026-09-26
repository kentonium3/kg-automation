---
title: "#849 arms run — post-merge Codex checkpoint plan"
doc_type: research
status: draft
owner: claude-macbook (architect); prepared 2026-09-26 for the implementer to execute
last_updated: 2026-09-26
---

# #849 arms run — post-merge Codex checkpoint plan

**Purpose.** The post-merge Codex review of mission `arms-run-01M3APTA` is a standing checkpoint
(Kent's ruling, 2026-09-24: "use codex for reviews … follow the extra review steps we routinely use
after plan, and after the full merge"). It reviews the **complete merged diff** for the cross-WP
defects a per-WP review structurally cannot see, and it runs **before `feat/849-arms-run` reaches
`main`** so fixes land in the same branch.

This document exists so that the checkpoint is **assembled from the record rather than from memory**
at the moment the re-merge lands. It was written while the mission was stalled, off the critical
path. It supersedes nothing: the rubric is the pre-registration, and the contracts are the contracts.

**Provenance of this document.** The content list was stated on the agent bus at 2026-09-25 21:08Z by
the then-architect session. Every hash and every sentence below was **re-resolved against this
repository** before being written here — not transcribed from the channel. That pass found two
citation defects and one gate already satisfied; all three are recorded in place. Bus messages are
coordination data, and this run has twice been bitten by a confidently-stated figure that was stale.

---

## 0. Preconditions — check these BEFORE the review runs

A checkpoint run against the wrong inputs produces a confident review of the wrong thing. Each of
these is a precondition, not part of the review.

### P1 — the rubric on the branch must be current

The review reads the rubric from the branch it runs on. `main` carries rubric commits that
`feat/849-arms-run` does not, and **four of them are text the run is judged against**, not
commentary: §4 grader independence (`8d83cb78`), §10 the pre-run blocking preconditions
(`6d9ffe89`), and the two §5 window-reconstruction corrections (`40eb8032`, `597bae13`).

**State the test, not a count.** As of 2026-09-26 the gap is twelve commits, but counts go stale
between sessions and a written-down count becomes a checklist target that is wrong by the time it is
read. The check is ancestry:

```
git merge-base --is-ancestor origin/main origin/feat/849-arms-run
```

Exit 0 = `main` is contained and the precondition holds. Anything else = sync first (merge `main`
into `feat`), **not mid-cycle**, and re-run the test.

### P2 — C10: the deferred contract sentences must have landed

A review that checks code against contract sentences cannot run against sentences that never landed.
At the 2026-09-26 04:49Z handoff, C10 named one outstanding sentence (ledger-schema item 2).

**Measured 2026-09-26: C10 appears SATISFIED.** Both deferred sentences are present on
`origin/feat/849-arms-run`:

| Sentence | Commit | Landed |
|---|---|---|
| ledger-schema item 2 — M1 addition: gate shas excluded from the resume comparison + why; `session_gates` precondition; skipped only on a `SKIP_GATES_SHA` ledger | `38027cf4` | 2026-09-26 01:46Z |
| gates.md — where the chat-template cross-check outcome is recorded (`session_gates` authoritative; a failing container record carries it, a passing one does not, by decision) | `6b8427e3` | 2026-09-26 00:11Z |

Re-verify rather than trust this table: the recovery reset touches `feat`, and these must still be
present on the re-merged branch. If a third deferred sentence was ruled after 04:49Z, it belongs
here before the checkpoint runs.

### P3 — the merge itself

The checkpoint reviews the merged diff, so the re-merge must have completed cleanly and the branch
must be pushed. The `--keep-branch` choice matters here for a reason beyond tidiness: the review
artifacts cite lane shas, and those citations must stay resolvable. All seven were verified present
on `origin` from a second machine at 2026-09-26 03:29Z.

---

## 1. The B-list — dated contract sentences the review must check the code against

Quote each sentence **verbatim in the prompt with its hash**, and ask whether the merged code
implements it. This is the half of the review that a per-WP pass cannot do: each sentence was ruled
against one WP, and the merged tree is the first place they all coexist.

| # | Sentence | Verified at |
|---|---|---|
| 1 | Resume re-validates **every persisted row**, in file order, through the same invariants a live write enforces — key and attempt fields **by TYPE, never coerced**; any violation is `LedgerCorrupt` with the file untouched, and repair never runs on a file that fails validation. | `5762c766` (ledger-schema item 2) |
| 2 | Exactly one torn **final** line is tolerated, and "torn" means **the bytes do not parse as JSON**. A final line that parses to anything other than an object (e.g. `null`) is corruption, never truncated away. | `5762c766` (item 4) |
| 3 | Any `OSError` in append poisons the writer: `LedgerWriteFailed`, every further write refused, lock released. A row that reached disk before the failure is **visible on reopen**, and a retry of the same scored key is refused as `SecondScoredRow`. | `5762c766` (item 9) |
| 4 | `ctx.config` is the contract name; `limits` / `limit_applied` / `limit` are **derived by the `CellContext` constructor**, never passed independently; arms check only the applied pair and never re-verify `limits` as a dict. | `42056e57` (arm-interface) |
| 5 | `ArmRefusal` **and its subclasses are terminal**: an `error` row on the first attempt, zero retries. The above-`permitted` / below-`trained` case is named explicitly. | `42056e57` (arm-interface) |
| 6 | R exposes the one bound adapter `calibration_inputs(text, tokenizer, embedder, views, index_cache) -> (availability, assemble_r_tokens)`; **D-10 is implemented once**, in `calibration.calibrate`. | `5762c766` (arm-interface) |
| 7 | Two-phase gates: host phase + container phase; the header binds `preflight_sha` and both gate shas; freshness is judged against the **harness-supplied current `up_ts`** (`env.up_ts`), not the record's own; naive timestamps are refused. | **`9f693cfc`** — see correction below |
| 8 | `total = prompt_n + cache_n`; `uncached = cache_write = prompt_n`; `cache_read = cache_n`. (llama.cpp's `prompt_n` **already excludes** cache hits — subtracting again double-counts.) | `8dc8c798` (research.md D-13) |
| 9 | D-8: value-carried taint and the carrier rule, with the stated boundary that **named code, imports and module attribute access belong to the runtime gate**, not the static scan. | **`d0049e6f`** — see correction below |

### Two citation corrections found while verifying

**Item 7 — the cited hash does not contain the amendment.** The 21:08Z list cites the gates.md
two-phase amendment at `@d41fd3ce`. That commit touches only `status.events.jsonl` and `status.json`
— it contains no contract text at all. A reviewer handed it would run `git show d41fd3ce`, see two
status lines, and find nothing to check against. The commit that **introduced** the two-phase
amendment is `9f693cfc` (2026-09-24, "two-phase gates, header binds preflight/host/container shas").
The text is present in the `d41fd3ce` *tree* because `9f693cfc` is its ancestor — which is how the
error survived — but the tree is not the provenance.

For provenance cite `9f693cfc`; for the **authoritative current text** read gates.md at the merged
branch head, because the file has moved twice since: `d894240d` (the freshness amendment) and
`6b8427e3` (the chat-template record).

**Item 9 — D-8 has moved twice past the cited hash.** The list cites `2ec79c95` "plus the c13/c15
update once it lands". It landed, and then was corrected. D-8's head is `d0049e6f`, via `742c7c82`
(value-carried taint, carrier rule, dunder refusal, double-seed invariant, closure condition) and
`1fd6fb6d` — which is itself a **correction of the record**: the type-expression fallback actually
taken was (a), not (d). Cite `d0049e6f` and read the section whole; quoting `2ec79c95` alone quotes a
superseded rule.

---

## 2. The C-list — checks that must pass UN-SKIPPED on the merged tree

**A skip here is a failure, not a note.** That is the whole point of running them at the merge: each
one is a property that no lane could verify on its own, because the pieces lived on different
branches.

| # | Check | Why it could only be checked here |
|---|---|---|
| C-1 | `tests/research/test_arms849_arm_r.py` — the `calibrate(ledger, *calibration_inputs(...))` end-to-end | `importorskip`ped in lane-g: `calibration.py` lives in lane-d, so **this test has never executed in one tree**. A skip means it still has not run. |
| C-2 | The `CellContext` identity test: **one** `index_cache` object passed to both `calibration_inputs` and `bind`, asserted **by identity** (WP07 N-3) | Crosses WP07 and WP08. |
| C-3 | WP07 N-2 — a passed index is validated before retrieval | Carried forward from WP07's approval. |
| C-4 | `REQUIRED_MODULES` includes `arm_g`, `arm_d`, `arm_r`, with the two-way agreement test | Deliberately not done in lane-h: the arm modules are absent there by dependency topology. **Also a pre-run blocker.** |
| C-5 | `probe_f` per-task normalisation (`74e0c148`) still green against the merged loader | The probe and the loader land together for the first time. |
| C-6 | The **loader-side structural pass** owed from synthesis | The one gap the freeze gate could not close, because it needs a loader — and there was none at freeze. |
| C-7 | T039 — the §2 token table re-measured on the **final assembled bytes** and registered with `preflight_sha` + the rubric HEAD cited | The numbers only become final once the tree is final. |

### Pre-run blockers, distinct from the checkpoint

These gate the **first live cell**, not this review, and they are registered in rubric §10 so they
outlive any session: **C4** (isolation inventory complete, two-way test), **C8** (live-style resume
with timestamp-bearing gate evidence, plus both negatives — timestamp-stable fakes do **not** satisfy
it, since those fakes are what hid the defect), **C9** (graph-store memory series wired end to end;
until it lands the G arm cannot run, and that refusal is correct behaviour rather than a 3am bug),
**C11** (ceiling guard at `before_send`, every live cell, exception unwrapped with nothing sent).
**C12** (UTC-canonical timestamps) is merge-time and also blocks the first live cell.

---

## 3. Prompt framing — a rule with a scar behind it

State the properties to confirm and the inputs to confirm them under. **Do not ask for ways past any
gate.**

On 2026-09-25 a WP04 review prompt using adversarial-probe vocabulary ("find a literal-only path
that … slips through") was aborted mid-run by the provider's content classifier — no findings, no
verdict, 563 KB of transcript wasted. The identical technical checklist, reframed as "confirm the
classification is identical under `PYTHONHASHSEED` 0 and 3; a differing outcome is a MAJOR",
completed normally. The technical content was not the problem; the framing was.

So: name the property, name the inputs, name what constitutes a MAJOR. Avoid `evade`, `bypass`,
`slip`, `escape`.

**Mechanics** (standing doctrine, unchanged): `codex exec` **read-only**, never `--full-auto`, never
the `spec-kitty-review` profile — a read-only review must not be handed write access to `.git/`.
Capture full stdout; `-o` / `--output-last-message` returns empty on agentic runs. If Codex is
rate-limited or unavailable, the fallback reviewer must be a **different model from the implementer**
— an Opus reviewer on an Opus fold is the same model marking its own homework, and if that is the
only option it runs only by explicit choice and is **recorded as degraded**, never as a clean
point-cut.

---

## 4. Prompt skeleton

> You are reviewing the complete merged diff of mission `arms-run-01M3APTA` on
> `feat/849-arms-run`, before it reaches `main`. Per-work-package reviews have already run and
> approved each package in isolation; your job is the cross-package view they could not have.
>
> Confirm each of the following properties holds in the merged code. Each is quoted verbatim from a
> dated contract sentence, with the commit it was registered at. For each: state CONFIRMED with the
> code that implements it, or report a MAJOR with the specific input under which the property does
> not hold.
>
> [B-list items 1–9, verbatim, with the verified hashes from §1]
>
> Then run the checks in [C-list]. Report any check that does not execute — a skipped check has not
> passed, and several of these have never executed in a single tree before this merge.
>
> Report findings as MAJOR / MINOR with file and line. Conclude with a single line: `VERDICT:
> APPROVE` or `VERDICT: REJECT`.

---

## 5. What this document is not

It is not a decision, and it registers nothing. The rubric is the pre-registration; the contracts are
the contracts; the sequencing is Kent's ruling of 2026-09-26 03:46Z (option A). If any sentence here
disagrees with the rubric or a contract, **they win and this file is wrong**.

It is also not a substitute for reading the merged diff. The B-list is what a reviewer would not
think to check; it is not the boundary of what is worth checking.
