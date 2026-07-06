---
id: felix-bedrock-stabilization
doc_type: charter
title: "Felix Bedrock Stabilization — Reliability, Observability & Coherence"
status: draft
level: overview
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
principles](<./engineering-principles.md>) already encode the bedrock — machine-readable
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
4. **Felix/OpenClaw boundary investigation** — an office2 probe of OpenClaw's actual bundled
   capability surface (the OG skill pack, `gog`), its per-agent tool-policy model, the
   main-agent routing/fallback prose, and the calendar-incident mechanism — because the
   boundary had been *asserted*, never *investigated*. It produced Foundation 0.

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

## 5. The foundations

### Foundation 0 — Define & Enforce the Felix/OpenClaw capability boundary *(upstream prerequisite)*

**Gap (discovered 2026-07-06 by investigation):** the Felix/OpenClaw boundary is **prompt-hoped,
not enforced.** OpenClaw ships a broad **bundled default capability surface** — chiefly `gog`
(Google Workspace: calendar, gmail, drive, contacts, sheets…), plus ~a dozen other bundled
skills — that is **automatically available to *every* agent.** Felix's controlled paths
(main → felix-admin-calendar → `gog` with a payload contract) are enforced **only by AGENTS.md
standing orders** ("Do NOT call `gog` directly"), with **no OpenClaw tool policy** behind them.
So any delegation failure, prompt truncation (#579), or misread punches straight through to the
generic bundled skill — the mechanism behind the "scheduled on Wednesday" calendar incident
("*took care of it directly*" = main fell through to raw `gog`).

**Reframe:** Felix's job is **not** primarily to *add* capabilities OpenClaw lacks — it is to
**govern** OpenClaw's already-broad, **ever-expandable** capability surface (`gog` is one of
*hundreds* of potential skill packs) into controlled, contract-bound, tier-gated, cost-aware
paths, **defaulting capability-overlap to *denial*, not availability.** "Complement, don't
duplicate" (as the charter and roadmap phrased it) is too weak; the accurate rule is
**govern + restrict**, and — critically — **Felix both *defines* the boundary and *owns the
OpenClaw configuration that enforces it***. The enforcement is not Felix-side prompt discipline;
it lives in OpenClaw's own tool/skill/exec policies (in `openclaw.json`, the one *monitored*
audited surface). Because the skill ecosystem is unbounded, only a **default-deny + explicit-
allow-per-agent** model scales — a new skill pack is governed the moment it exists, without a
new decision.

**Confirmed value division (investigated 2026-07-06 from OpenClaw's own install/docs, not
impression).** OpenClaw's README positions it as "a personal AI assistant… the Gateway is just
the control plane — the product is the assistant" — so OpenClaw and Felix *overlap at the
positioning level*; the difference is **depth + governance**, not category.

| Layer | Confirmed value | Classification |
|---|---|---|
| OpenClaw **runtime/orchestration** | gateway; **27+ channels**; multi-agent routing + **per-agent sandbox**; cron; sessions; **tool-policy enforcement *before* the model call**; browser/canvas/code-exec | **HARNESS** — durable, hard-to-replicate |
| OpenClaw **bundled skills (53)** | CLI-wrapper connectors (github/notion/gog/obsidian…) | **MONITOR** — erodes as Claude gains native tool-use |
| OpenClaw **memory-core** | unstructured AI-curated append-only memory + **OpenAI-embedding** vector search | **LOCK DOWN** — confirmed HIGH-risk liability (external OpenAI dependency + cost + #580 noise); Felix uses the *structured* vault instead and should disable it |
| **Felix** | specialized agents, governance, controlled paths, structured vault, cost-discipline, EA intelligence | **the differentiated, durable value** |

Two consequences: **(a)** the "structured Felix vs unstructured second-brain OpenClaw" reading is
*substantiated* — Felix already correctly chose the structured Obsidian vault over OpenClaw's
memory-core; and **(b)** the hard-enforcement mechanism Foundation 0 needs — **per-agent tool
policy enforced before the model call + sandboxing — already exists as a first-class OpenClaw
feature**, so configuring the default-deny boundary *uses OpenClaw's own designed mechanism*
rather than fighting it (a significant de-risk). Felix's durable value (governance +
specialization + structured knowledge) is *strengthened* by the cost regime; OpenClaw's durable
value is the **orchestration substrate**, not its (eroding) connector ecosystem.

**Minimal coherent deliverable (define → configure-to-enforce → author):**
1. **A canonical capability map** — for each request class (calendar, email, tasks, habits,
   inbox, health/notes, file/vault writes, website/dev changes), *who owns it* (a specific
   Felix agent / OpenClaw-default / not-yet-supported) and *the one controlled path*.
   (Investigation draft: **CONTAINED** = tasks/inbox/habits; **AMBIGUOUS/UNCONTROLLED** =
   calendar (gog available to all), email (gog gmail, unowned, F024 pending), file/website
   writes (exec → arbitrary Bash).)
2. **The no-silent-fallback doctrine** — a Felix-owned capability is handled *exclusively*
   through its controlled path; on failure it **fails safe** (report + escalate via the F1
   alerting seam), it does **not** fall through to a generic/default handler. Uncontrolled
   fallback is worse than a clean failure on two axes: **correctness** (a wrong action may go
   uncaught) *and* **cost** (fall-through-and-flail — main improvising through raw `gog`, an
   agent retrying, an LLM working around a missing capability — burns Claude tokens; #662's
   haiku burned **252k tokens** flailing on one failed run). Fail-fast-and-stop is both safer
   and cheaper; F1's usage ledger measures the waste this prevents.
3. **HARD enforcement by configuring OpenClaw itself** (the new, load-bearing part Felix has
   **never used**) — a **default-deny per-agent tool/skill allowlist** in `openclaw.json` so an
   agent *technically cannot* invoke a capability it doesn't own (only felix-admin-calendar may
   call `gog calendar`; main's exec/skill surface is scoped). Managing this config is itself a
   **governed, tier-aware, rebaseline-tracked** change (F2; openclaw.json is the monitored
   surface) — so Foundation 0 and F2 share the same enforcement plane.

**Why upstream:** the three foundations and the #167 agent-authoring family all *assume* a
boundary. #167/#587/#583 **operationalize** it in prompts (the *soft* layer) — but the incident
proves soft-alone fails; the boundary must be *defined* (map + doctrine) and *hard-enforced in
OpenClaw config* first. **Connects to:** F2 (high-stakes surfaces — website/dev changes — are
Tier-2+ and ride the guarded path, not ungoverned `exec`; and the enforcement config is an F2
audited surface), F1 (outcome canaries detect handling by the wrong path — #657 — and the usage
ledger quantifies fallback cost), F3 (the map + doctrine are canonical invariants). Also fixes
the **identity/voice confusion** ("who am I talking to?"): internal delegation/fallback
machinery must never leak into the conversation — Felix presents one voice (#573/#561/#406).

**Sprint-0 research spike — learn OpenClaw's *intended* governance model, don't reverse-engineer
it.** OpenClaw is a mature, popular product that almost certainly ships a *designed* capability-
governance model (per-agent tool policies, skill scoping, exec security tiers) that Felix is
**under-using** — we have been inferring the boundary from deployed config. The spike **reads
OpenClaw's official documentation + curates the community best practices that fit**, with the
explicit discipline of *filtering for single-operator-EA fit* rather than blind adoption (the
hard part is knowing which of the abundant third-party guidance actually fits our scenario).
Deliberately scoped small; it is **not** an OpenClaw fork — the goal is to use OpenClaw's own
supported governance mechanisms correctly.

### Foundation 1 — Health & Observability → *"is a Felix capability silently degraded?"*

**Gap:** components emit health inconsistently or not at all; failures are learned via
secondary effects. Root of the #662 misdiagnosis.

**Minimal coherent substrate (deterministic; extend, don't build new):**
- **Extend `felix-core-digest`** (the #490 deterministic Python signal-extractor, already
  running every 15 min at zero token cost) with a **declarative canary/assertion registry**
  + one **`felix-alert` delivery primitive**.
- **SINGLE CANONICAL ALERT SURFACE ("communication bus") — a first-class requirement, not a
  nice-to-have.** Every alert source publishes to **one** ntfy stream: the in-band canary
  primitive, the felix-deployer failure alerts, the security-monitor, prompt-sync failures,
  and the out-of-band watchdog. **Consolidate the two streams the operator monitors today
  into that one stream** and route all future alerts to it. Rationale: the more surfaces the
  operator must watch, the more toil and the less likely timely detection — reducing *the
  operator's* monitoring load is a core Felix value, not a UX detail. (Severity/topic can be
  a message field or a small set of tags on the *same* stream, not separate streams.)
- Canaries **consume OpenClaw's own telemetry** (cron-run records, session logs, delivery
  status, error events) and add the **EA-semantic layer** OpenClaw cannot provide: "the
  inbox digest OpenClaw marked success actually wrote today's doc"; "the DM-reply actually
  emitted a channel-send" (#652); "prompt-sync isn't N commits behind" (#667); "every
  deployed agent is in drift-check" (#654); "core and channel-plugin versions match" (#628).
- **Semantic filtering + dedup** (the explicit fix for the #512/#634 noise flood) and
  **assert on outcomes, not proxies** (#572 lesson).
- **One out-of-band watchdog (#269)** — a deliberately **disjoint send *path*** (a systemd
  timer that does not route through Felix/OpenClaw, `curl`-ing ntfy directly), because an
  in-band bus can't alert when Felix/OpenClaw itself is down. Critically, its *destination is
  the SAME canonical stream* — disjoint path, shared surface — so the single-stream
  requirement above holds even for the down-detector.
- **Component lifecycle-status contract (#538)** as the shared vocabulary
  (active/suspended/failed/stale/degraded), and **fix the audited-surface mismap (#621)** so
  prompt drift is actually monitored.
- **HARD CONSTRAINT: no LLM in the hot path.** Canaries are file/mtime/attribute/version/
  count assertions. (The #485 doc-auditor suspension proves why.)

**Alerting seam — WhatsApp vs ntfy (route by audience-role, not failure-type).** Two channels,
two roles: **WhatsApp** = Felix communicating with Kent *as the user* in the course of work
(confirmations, clarifying questions, and honest soft-fail/capability-gap transparency — "I
can't do X yet"); **ntfy** (the one communication bus) = the *system* needs Kent *as operator*
(hard failures + silent degradation + the watchdog). Three zones: conversational→WhatsApp
only; system-health→ntfy only; a failure that blocks a user request→both, deliberately, in
each channel's register. The pairing is a **safety property, not redundancy**: WhatsApp is
*agent-emitted, judgment-based, best-effort* ("helpful when possible") and can be missed if an
agent misreasons; **ntfy canaries are deterministic and independent of agent judgment** ("must
always") — they fire even when the agent stays silent or misclassifies a hard failure as a
soft no-op (the #657/#662 trap). Soft-fails accumulate in the deterministic capability-gap
*log* (#651) → an aggregate prioritization signal, **not** per-instance ntfy spam — so the
seam scales role-based (not volume-based) as the capability surface broadens with #670. This
seam is authored as a founding **doctrine invariant** (F3) so every agent applies it
identically, ending the per-agent output-discipline drift (#573/#561/#406).

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

**Defer (for the sprint):** #644/#645/#646 (Obsidian Canvas/graph) — the heavyweight
knowledge-graph; the coherence lens runs on a hand-curated decision list without it.

> **Forward pointer — vectorized/knowledge graphs as a medium-term roadmap item (not sprint
> work).** Deferring the graph *as sprint scope* is distinct from the operator's intent to
> *learn* vectorized-graph concepts and find a **minimal entry point** for them in Felix — as
> an enhanced-development-environment or system-state-awareness capability. The near-term F3
> substrate (flat doctrine file + decision corpus) is deliberately graph-free and sufficient
> at single-operator scale; when a *basic* vectorized-graph application has a clear, bounded
> home in Felix, it becomes the natural evolution of the F3 decision/doctrine corpus (which
> is already the raw material for a typed graph) rather than a parallel build. Tracked as a
> roadmap-level research item, sequenced after the stabilization foundations land.

**Absorbs:** #409, #160(prevention half), and the "which artifact is canonical" question
(#669 + #409 + the deploy-path note) → **one "canonical agent-artifact source of truth"
decision**.

## 6. OpenClaw / Felix boundary discipline

**The boundary is govern-and-restrict, hard-enforced (Foundation 0), not merely
"complement."** OpenClaw's default surface is broad and available-to-all; Felix imposes
controlled, contract-bound, tier-gated paths and defaults overlap to *denial* via per-agent
tool/skill allowlists. Beyond that, every foundation adds only the **EA-semantic layer
OpenClaw does not provide** and consumes OpenClaw's telemetry/config rather than re-emitting or
mutating it. Enforced guardrails:
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
| **0 — Boundary + converge & correct** | cheap, now; install the coherence *practice*; **define the boundary (gates the rest)** | **Foundation 0**: OpenClaw capability/tool-policy research spike → canonical **capability map** + **no-silent-fallback doctrine** + begin **per-agent tool/skill allowlists** (hard enforcement). Plus: verify #323 umask shipped · #667 · #636 · #621 · backlog hygiene (merge #270+#642 · re-parent #671→#137 · split #556→#409 · re-scope #323) · stand up `doctrine.md` + decision markers + a coherence-review step |
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

Most of the reliability/observability/governance work is **convergence** of existing issues:
(1) one coordinating stabilization epic; (2) the #270↔#642 merge and #671→#137 re-parent;
(3) one "canonical agent-artifact source of truth" decision; (4) recording the borrow/defer
calls (#327 over #124; #639 over #551; ledger-now/reports-later) as doctrine. The net-new
*artifacts* there are flat files (`doctrine.md`, `decisions.jsonl`, the coherence-review step,
`felix-usage.jsonl`, `model-prices.json`).

**Two genuinely-new architectural elements** stand apart from that convergence — and both were
*discovered by digging*, not present in the backlog:
- **F3's coherence-enforcement** — a mechanism Felix had in no form (doctrine + decision markers
  + point-cut review). This is the "missing governance."
- **Foundation 0's boundary definition + *hard* enforcement** — the capability map + no-silent-
  fallback doctrine + **per-agent OpenClaw tool/skill allowlists**, a runtime mechanism Felix has
  **never used**. Until now the boundary was prompt-hoped; this makes it real.

So the honest summary is: **mostly operationalization of a sound existing design, plus these two
missing load-bearing pieces** — coherence-enforcement and an enforced boundary. That is a
markedly cheaper and lower-risk investment than a redesign, and it is why a stabilization
*program* (not a re-founding) is the right instrument.

## 11. Next step

On operator sign-off, create the umbrella GitHub epic from this doc, with the multi-sprint
structure and the issue-disposition map as its child/sub-issue plan, and begin Sprint 0.
