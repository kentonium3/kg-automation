---
id: felix-bedrock-stabilization
doc_type: design
title: "Felix Bedrock Stabilization — Reliability, Observability & Coherence"
status: draft
level: strategic
owners: [kgale]
last_validated: '2026-07-06'
version: '0.1'
tags: [architecture, reliability, observability, governance, coherence, stabilization]
---

# Felix Bedrock Stabilization — Reliability, Observability & Coherence

> **Status: DRAFT for operator review.** This is the analysis + program charter for a
> multi-sprint stabilization investment. The umbrella GitHub epic is created from this
> doc after review. It is not itself a work item.

## 1. Why this exists

Felix's reliability failures keep recurring in the same shapes, and per-issue fixes keep
re-introducing the same class from a new angle. The precipitating example: the #662
"harden inbox capture" mission diagnosed a capture failure as a *model* problem (haiku),
shipped a haiku→sonnet upgrade, and had to **reverse it the same day** once live probing
showed the true cause was *environmental* (OpenClaw's `exec` tool strips `PYTHONPATH`).
That misdiagnosis was expensive precisely because **no observability layer existed to
mechanically separate an environment failure from a model failure** — and, concurrently,
office2 was silently **28 commits behind on prompt-sync** during that very deploy (a
second silent failure that confounded the diagnosis).

The operator's directive: address agent **reliability and sustainability holistically** —
build the **bedrock design** on which continued capability extension can depend — while
(a) respecting the **OpenClaw/Felix separation of concerns** (Felix complements OpenClaw;
it does not duplicate or modify it), and (b) **guarding against over-engineering** (undue
complexity → fragility + wasteful sysadmin toil, the opposite of what Felix delivers).

## 2. The core finding

**Felix's bedrock is already *designed* but *under-implemented and fragmented*, with no
coherence-enforcement to keep new work aligned.** The 13 ratified [engineering
principles](engineering-principles.md) already encode the bedrock — machine-readable
health-state (#1), "how will we know this broke?" (#9), small guardrails over large
retrofits (#10), no SPOF without recovery (#13) — as do roadmap design principles #4
("never fail silently") and #7 ("central action logging"). The ~40 open reliability /
governance / coherence issues are almost all **partial, overlapping attempts to implement
principles that are already ratified**, approached issue-by-issue, from different angles,
with duplicate epics (#270 vs #642; #516 as umbrella; the #167 authoring family; the
#646 visualization family).

So this is not a "design new architecture" problem. It is a **"converge the fragments
into a few coherent substrates, collapse the duplicates, and install a coherence-check so
it stops re-fragmenting"** problem — a stabilization investment, not a greenfield build.

## 3. Method

Three research passes fed this analysis:
1. **Open corpus** — the ~40 open reliability/governance/coherence issues (excluding the
   spec-kitty *tooling* tracker #627 and the pure EA *capability* features), clustered and
   analyzed for overlaps, boundary respect, and over-engineering risk.
2. **Closed corpus** — 157 relevant issues closed since 2026-04-01, analyzed for
   *recurrence patterns* (the history that per-issue fixes miss).
3. **spec-kitty doctrine survey** — spec-kitty's rapidly-developing doctrine/governance
   machinery, mined for patterns borrowable *at Felix's single-operator scale*.

## 4. Historical pattern evidence (the closed corpus)

The closed record is the strongest argument for the foundations — the same failure classes
recur despite fixes:

- **Silent-delivery / DM-reply break — recurred 3+ times.** #588 → #617 → **#652 (open)**,
  plus #579, #595, #406. Each fix addressed an instance; the *class* (Felix's reply path
  silently fails to send) survived.
- **The observability foundation already failed once, expensively.** #490 built a
  deterministic signal-extractor (good), but when monitoring over-reached into raw OpenClaw
  noise it **flooded the backlog** (#493–504, #554, #590, #634-open — "2884-event burst",
  "creds.json corruption", "reconnect storm"), and #512 **re-filed already-closed issues**.
  Separately the LLM-judgment doc-auditor was **suspended for cost** (#485) after a flood of
  pending-approval tickets (#422–484). **This is the design spec for what F1 must not be.**
- **"Hallucinate when the deterministic substrate is missing" is fleet-wide, not a capture
  bug.** #562 (habits weekly report: cron fires, no helper → *hallucinated data*) is the
  identical class as #661/#662. → a fleet doctrine, not a third per-agent patch.
- **"Monitoring that doesn't actually detect the failure."** #572 (health-check never
  probed liveness), #513 (parsed drifted CLI output), the doc-auditor flood. → F1 must
  assert on *outcomes*, not proxies.
- **Young, fragile deploy substrate.** #567/#618 built the pipeline; #612–615, #595, #552
  were an immediate defect cluster. → the manifest path governs the risky stuff but is not
  itself mature; extend carefully.
- **Governance accreting one directive at a time.** #528, #514, #546, #547, #557. → the
  fragmentation the coherence substrate exists to end.
- **Settled invariants that must not be re-litigated.** #553 (won't-fix: do NOT factor out
  shared agent prompt context — author per-agent, validate shared invariants) is exactly the
  kind of decision the doctrine substrate must canonicalize.

## 5. The three foundations

### Foundation 1 — Health & Observability → *"is a Felix capability silently degraded?"*

**Gap:** components emit health inconsistently or not at all; failures are learned via
secondary effects. Root of the #662 misdiagnosis.

**Minimal coherent substrate (deterministic; extend, don't build new):**
- **Extend `felix-core-digest`** (the #490 deterministic Python signal-extractor, already
  running every 15 min at zero token cost) with a **declarative canary/assertion registry**
  + one **`felix-alert` delivery primitive** (ntfy is the existing substrate).
- Canaries **consume OpenClaw's own telemetry** (cron-run records, session logs, delivery
  status, error events) and add the **EA-semantic layer** OpenClaw cannot provide: "the
  inbox digest OpenClaw marked success actually wrote today's doc"; "the DM-reply actually
  emitted a channel-send" (#652); "prompt-sync isn't N commits behind" (#667); "every
  deployed agent is in drift-check" (#654); "core and channel-plugin versions match" (#628).
- **Semantic filtering + dedup** (the explicit fix for the #512/#634 noise flood) and
  **assert on outcomes, not proxies** (#572 lesson).
- **One out-of-band watchdog (#269)** — deliberately disjoint dependency surface — because
  an in-band bus can't alert when Felix/OpenClaw itself is down.
- **Component lifecycle-status contract (#538)** as the shared vocabulary
  (active/suspended/failed/stale/degraded), and **fix the audited-surface mismap (#621)** so
  prompt drift is actually monitored.
- **HARD CONSTRAINT: no LLM in the hot path.** Canaries are file/mtime/attribute/version/
  count assertions. (The #485 doc-auditor suspension proves why.)

**Absorbs:** #637, #667(alert half), #654, #628, #657(error-envelope guard), #652(delivery
canary), #634(replaced by semantic filtering). **#516** is the research spike whose answer
*is* this build.

**Defer:** **#124 (OpenTelemetry)** — re-implements OpenClaw's telemetry plane; its only
non-duplicative slice is autonomy-audit evidence.

**Cost-observability leverage (operator addition, 2026-07-06).** F1's extractor already
reads cron-run records that carry per-run `usage` + `model` + `provider`. Co-emit a
**`felix-usage.jsonl`** append-only ledger `{ts, agent, model, provider, tokens…, run_id}`
as a byproduct, plus a `model-prices.json` constants table for a token×price *estimate*
(there is no real $ feed — #662 confirmed cost fields are zeroed). **Design F1's emission
contract generically — health-signals and usage-signals are both "signals" on one bus** — so
Epic **#137 (LLM Cost Visibility)** and **#138** become *thin consumers* (aggregate +
threshold), and **#671** (model-per-task policy) is data-backed. Build only the cheap
*collection* primitive now; defer the reporting consumers. One zero-code companion worth
doing in-window: **#296** (Anthropic Workspace dev/felix split) for clean attribution. This
is the flywheel property: one bedrock investment unblocks reliability *and* cost
observability at once.

### Foundation 2 — Tier-aware change/deploy → *"every path that changes office2 is governed"*

**Root cause:** the **two undocumented deploy paths (#636)** — one *governed* (felix-deployer
manifest pipeline; `scripts/deploy/lib/` already does tier-guard + snapshot + record +
rebaseline) and one *ungoverned* (pull-based prompt-sync: no record, no drift audit, the
exact path a Tier-2 effect can ride ungated).

**Critical fact: the guard already exists.** The job is **extend it, not fork it.**

**Minimal substrate (cheapest-first):** #636 (document paths + slug→dir map, keystone) →
#621 (audit mismap, shared with F1) → #639 (extend `scripts/deploy/lib` into one
`tier2_guarded()` primitive, **absorbs #550 + #551**) → #640 (CI signature guard, warn→strict,
reusing the `validate_architecture_data.py` pattern; largely obviates the #270-L3 auditor) →
#666 (one-line backup carve-out).

**Hygiene:** **merge #270 + #642** (same substrate, two ends). #288 (GOVERNANCE.md) already
shipped. #281 is a parallel Directive-6 *discipline* lens (keep). **Do NOT build #551's
parallel `scripts/governance/` stack** — Felix duplicating its own deploy machinery is the
anti-pattern. **Defer #641** (LLM-judgment backstop) until #639/#640 exist; **park #275**
(emergency lane). **#653 is NOT a governance issue** (OpenClaw's own install topology) —
keep standalone (it lands in Sprint 1 with the DM-reply class).

**Priority note:** the manifest path already governs the high-risk Tier-2 mutations, and
Sprint-0's cheap fixes (#636/#621/#667) close most of the pull-path exposure — so the
expensive part of F2 (#639/#640) is **lower priority** than F1/F3.

### Foundation 3 — Coherence & Doctrine → *the antidote to per-issue myopia*

**Gap:** design decisions/invariants are scattered (constitution, principles, AGENTS.md,
memory) with no canonical queryable substrate, no decision-point injection, and no coherence
pre-scan — so a spec (or a mission) can contradict a settled invariant that lives where the
decision process never reads it (the #325 and #662 failure mode).

**Design — borrowed from spec-kitty at Felix scale.** spec-kitty's doctrine engine **never
calls an LLM**: doctrine is inert data, its Python only selects/resolves/records, and the
agent does the thinking — a perfect fit for Felix's deterministic posture. The borrowable
core is **three flat files + two tiny helpers**, each with a practice→machinery path:

| Pattern | PRACTICE (Sprint 0, ~0 build) | MACHINERY (Sprint 2) | Do NOT borrow |
|---|---|---|---|
| **A. Doctrine = scoped invariants** `{id, intent, when, rules, check}` | one `doctrine.md` of `INV-###` stanzas (steal spec-kitty DIRECTIVE_001/003 wording) | `doctrine/*.yaml` + 40-line glob loader | DoctrineService, DRG, 9 artifact kinds |
| **B. Action-scoped injection** | a dict: decision-type → invariant-ids; inject *titles first, bodies on demand* | `actions/<type>/index.yaml` + loader | 5-tier resolver, org-roots, pack manager |
| **C. Decision markers + queryable corpus** | `decisions.jsonl` `{id, question, answer, status, invariants_touched, rationale}` | 4-verb helper + atomic `index.json` | event stream, lamport clocks, SaaS sync |
| **D. Coherence pre-scan** | one adversarial-review step at spec/plan reading C+A; advisory, never a gate | 2–3 lenses at point-cuts | 13-agent orchestration |
| **E. Significance gate** | 3-boolean checklist (architectural? irreversible? cross-cutting?) | tiny pure fn | 6-dimension scorer + RACI |

**Plus** #133 (trimmed canonical agent registry — register `main`, one source of truth, CI
reconciliation) and #587 (workspace authoring standard + deterministic validation). #538 is
also a doctrine artifact. The #167 per-agent authoring family (#582/#583/#585/#586/#635/#584)
sequences *behind* #587 as one shared recipe (honoring #553's per-agent, no-inheritance
decision). The fleet-wide **two-layer invariant** ("deterministic plumbing the LLM never
touches; the LLM never fabricates infrastructure state") — proven fleet-wide by #562+#662 —
is authored as a founding `INV`.

**Defer:** #644/#645/#646 (Obsidian Canvas/graph) — the heavyweight knowledge-graph; the
coherence lens runs on a hand-curated decision list without it.

**Absorbs:** #409, #160(prevention half), and the "which artifact is canonical" question
(#669 + #409 + the deploy-path note) → **one "canonical agent-artifact source of truth"
decision**.

## 6. OpenClaw / Felix boundary discipline

Every foundation adds only the **EA-semantic layer OpenClaw does not provide** and consumes
OpenClaw's telemetry/config rather than re-emitting or mutating it. Enforced guardrails:
- **F1** reads OpenClaw cron-runs/sessions/delivery/error events; it does **not** rebuild them
  (that is why **#124/OTel is deferred** and **#634's raw-log-grep is replaced** by semantic
  assertions).
- **F2** governs *Felix's* changes to office2 (cron, prompts, helpers, service config); it
  does **not** duplicate OpenClaw's own config/deploy, and **#653** (OpenClaw's install
  topology) is kept *out* of the governance substrate.
- **F3** authors *Felix's* own doctrine + agent workspaces; #587/#133 *reconcile against*
  OpenClaw truth (`openclaw agents list`) rather than reaching into it; #553 chose to respect
  OpenClaw's self-contained-workspace model.

## 7. Anti-over-engineering discipline

The governing rule is engineering-principle #10 (small guardrails over large retrofits),
and the closed corpus is the proof: the two most expensive Felix subsystems to date — the
LLM doc-auditor (#485, suspended for cost) and the over-reaching signal-monitor (#490→#634
noise flood) — both failed by adding *ambient LLM judgment* and *raw-telemetry breadth*.
Therefore, across all three foundations:
- **Deterministic in the hot path; LLM judgment only triggered / diff-scoped / cheapest-model
  / never ambient / never a hard gate.**
- **Extend existing machinery** (`felix-core-digest`, `scripts/deploy/lib`, spec-kitty's
  *shapes* not its services) rather than build parallel stacks.
- **Capture data cheaply now; build consumers later** (the usage ledger vs the #137 reports).
- **Explicit deferral list** (below) so deferral is a decision, not an omission.

**Explicitly deferred:** #124 (OTel) · #644/#645/#646 (knowledge-graph) · #641 (LLM-judgment
deploy backstop) · #275 (emergency-lane RFC) · the #137 *reporting* consumers (dashboards,
cross-provider #297, budget-alerting) beyond the cheap collection primitive.

## 8. The multi-sprint program — "Felix Bedrock Stabilization"

Grouped, sequenced sprints; the coherence *practice* (F3 A/C/D/E) is stood up in Sprint 0 and
governs every subsequent sprint.

| Sprint | Grouping | Contents |
|---|---|---|
| **0 — Converge & correct** | cheap, now; install the coherence *practice* | verify #323 umask shipped · #667 · #636 · #621 · backlog hygiene (merge #270+#642 · re-parent #671→#137 · split #556→#409 · re-scope #323) · stand up `doctrine.md` + decision markers + a coherence-review step |
| **1 — Observability + DM-reply** | F1 (deterministic) + cost-collection primitive | extend `felix-core-digest` → canary registry + `felix-alert` + semantic-filter/dedup + #269 watchdog + #538 · **co-emit `felix-usage.jsonl` + `model-prices.json`** · #296 (zero-code) · **DM-reply class #653 + #628** |
| **2 — Coherence machinery** | F3 build | #643-core (A/B/C machinery) + #133 (trimmed) + #587 |
| **3 — Consistent agent authoring** | behind #587 | #167 family (#582/#583/#585/#586/#635/#584) + canonical-source resolution (#669/#409/#160) |
| **later / parallel** | F2 + cost consumers | #639/#640/#666 (lower-pri) · #137/#138/#297/#671-thin (data-backed by Sprint 1) |
| **deferred (explicit)** | over-engineering guard | #124 · #644/#645/#646 · #641 · #275 |

## 9. Issue disposition map

- **Merge:** #270 ⊕ #642 → one governance umbrella. Absorb #550 + #551 → #639. Absorb #556
  (capture half → #670/#651 line; habits half → #409). Absorb #409 + #160-prevention into F3
  doctrine/validation.
- **Re-parent:** #671 → child of #137 (blocked-by #138); strip #671's observability scope into
  #138.
- **Re-scope:** #323 (move-barrier wording → "in-place frontmatter write needs group write";
  **verify the umask fix actually shipped** — it's open while its dependent #325 is closed).
- **Close on convergence:** #516 (its answer is F1) · #556 (superseded) · the "canonical
  agent-artifact source" trio via one decision.
- **Keep standalone:** #653, #628, #668, #665, #269, #538, #649 (shipped precedent).
- **Defer:** #124, #644/#645/#646, #641, #275.

## 10. What is genuinely *new* (kept minimal)

Almost nothing is invented — the issues mostly exist; the work is **convergence**: (1) one
coordinating stabilization epic; (2) the #270↔#642 merge and #671→#137 re-parent; (3) one
"canonical agent-artifact source of truth" decision; (4) recording the borrow/defer calls
(#327 over #124; #639 over #551; ledger-now/reports-later) as doctrine so they are not
re-litigated. The only net-new *artifacts* are the F3 practice files (`doctrine.md`,
`decisions.jsonl`, the coherence-review step) and the F1 `felix-usage.jsonl` +
`model-prices.json` primitives — all flat files.

## 11. Next step

On operator sign-off, create the umbrella GitHub epic from this doc, with the multi-sprint
structure and the issue-disposition map as its child/sub-issue plan, and begin Sprint 0.
