---
id: felix-openclaw-boundary
doc_type: design
title: "Felix ⇄ OpenClaw Capability Boundary — map, no-silent-fallback doctrine & enforcement design"
status: draft
level: overview
owners: [kgale]
last_validated: '2026-07-06'
version: '0.2'
tags: [architecture, governance, openclaw, security, boundary, foundation-0]
---

# Felix ⇄ OpenClaw Capability Boundary

> **Status: DRAFT — Foundation 0 spike output (#675).** This is the design deliverable of the
> Sprint-0 Foundation-0 research spike for the [Felix Bedrock Stabilization program](<./felix-bedrock-stabilization.md>)
> (epic #673). It defines the boundary (capability map + no-silent-fallback doctrine) and the
> **concrete `openclaw.json` enforcement design**. It is a design + rollout plan — the actual
> config deployment is a governed, rebaseline-tracked Tier-2 change made separately, on operator
> go/no-go (see §8).

## 1. Why this exists

Foundation 0 of the bedrock program: the Felix/OpenClaw capability boundary was *asserted* but
never *investigated or enforced*. This spike investigated OpenClaw's actual bundled capability
surface and its intended governance model, and found the boundary is **completely unenforced** —
worse than "prompt-hoped." The deliverable is a definition of the boundary and the concrete
mechanism to make it real, using OpenClaw's own designed features (not a fork, not Felix-side
prompt discipline).

## 2. Current state — empirically proven (office2 probe, 2026-07-06, OpenClaw 2026.6.11)

The boundary is **not enforced in any form.** Evidence from the live `openclaw.json` and the
`openclaw` CLI:

| Finding | Evidence | Implication |
|---|---|---|
| **No per-agent capability restriction exists** | Every entry in `agents.list[]` carries only `{id, name, workspace, agentDir, model}`. `agents.defaults` sets only `model` + `workspace`. No `tools`, `skills`, `sandbox`, or `exec` field on any of the 6 agents. | Every agent inherits the same global capability surface. |
| **One global tool profile** | `tools.profile: "coding"` (fleet-wide). | The `coding` profile grants filesystem, runtime (exec), web, sessions, memory + media groups to **all** agents uniformly. |
| **`gog` is visible to every agent** | `openclaw skills check --agent main` and `--agent felix-admin-calendar` both report gog **"Ready and visible to model"** (26/61 skills visible, identical sets). gog source = `openclaw-bundled`, `Available as command: yes`. | `main` can invoke `gog` directly — **this is the exact mechanism of the "scheduled on Wednesday" calendar fall-through incident.** |
| **exec is wide open** | `openclaw exec-policy show` → effective `tools.exec: security=full, ask=off`; approvals file **missing**. | Every agent has **unrestricted arbitrary-Bash exec** with no approval gate. This is the "file/website writes → arbitrary Bash" uncontrolled surface. |
| **Sandbox is off** | No `sandbox` block anywhere; default `mode: off`. | No runtime isolation; exec runs directly on the gateway host. |
| **Other broad bundled skills are live** | `openclaw skills list` shows 26 ready incl. `github`, `gh-issues`, `notion`, `browser-automation`, `canvas`, `taskflow`, `weather`, `whisper`. | The available surface is far broader than the Felix agents' actual jobs. |

**Documentation fiction to correct:** our `docs/design/architecture/data/service-inventory.json`
documents per-agent `skills` arrays (e.g. calendar `["calendar","gog"]`, tasker
`["task-intelligence","vikunja-api"]`). **These do not exist in the live `openclaw.json`.** The
inventory records intent that was never configured. This must be reconciled (see §9).

## 3. Enforcement mechanisms available (OpenClaw's own designed model)

Source: OpenClaw official docs (`docs.openclaw.ai`), version 2026.6.11 (which includes the
v2026.4.29 hardening where configured tool sections no longer implicitly widen restrictive
profiles). The mechanism Foundation 0 needs **already exists** and is first-class:

- **Per-agent tool policy — enforced *before the model call*.** `agents.list[].tools.{profile, allow, deny}`.
  Profiles: `minimal` (only `session_status`), `coding`, `messaging`, `full` (default when unset).
  `deny` wins over `allow`. Tool groups: `group:runtime` (exec/bash), `group:fs` (read/write/edit),
  `group:sessions`, `group:memory`, `group:web`, `group:ui`, `group:messaging`, `group:openclaw`.
  **Critical property:** *"If policy removes a tool, the model does not receive that tool's schema
  for the turn."* Prompt injection cannot bypass it — the tool call never reaches the framework.
  (docs: `/gateway/config-tools`, `/gateway/config-agents`, `/cli/policy`)
- **Per-agent skills.** `agents.defaults.skills: [...]` baseline; `agents.list[].skills: [...]`
  **replaces entirely** (does not merge); `skills: []` = none. `skills.allowBundled: [...]` is a
  **global allowlist for bundled skills** (gog is bundled). Skills are `SKILL.md` instruction packs
  loaded into the prompt — distinct from tools. (docs: `/tools/skills`, `/tools/skills-config`)
- **exec governance.** `agents.list[].tools.exec.{security: deny|allowlist|full, ask: off|on-miss|always, host}`;
  presets via `openclaw exec-policy preset {deny-all|cautious|yolo}`. (docs: `/tools/exec`, `/cli/approvals`)
- **Sandbox (defense-in-depth).** `agents.defaults.sandbox.{mode: off|non-main|all, scope, backend: docker}`;
  Docker backend defaults to `network: none`, read-only root. Tool policy alone is sufficient for
  capability governance; sandbox adds isolation. (docs: `/gateway/sandboxing`)
- **Memory-core kill.** `agents.defaults.memorySearch.{enabled: false}` or `provider: "none"`
  (FTS-only, no embeddings, **no OpenAI calls**); or `plugins.slots.memory: "none"`.
  (docs: `/reference/memory-config`)

**Default posture is all-tools-available**; default-deny is fully supported but must be configured.

## 4. The capability map

For each request class: the owning Felix agent, the one controlled path, and current containment.
(Draft — ownership rows marked *confirm* need a live AGENTS.md cross-check before enforcement.)

| Request class | Owner (controlled path) | Underlying capability | Current containment |
|---|---|---|---|
| **Calendar** (create/update events) | `felix-admin-calendar` → `gog calendar` (payload contract) | gog (bundled) | ❌ **UNCONTROLLED** — gog visible to all agents; main falls through |
| **Tasks** (Vikunja CRUD) | `felix-admin-tasker` → `vikunja_api` skill | vikunja_api (managed) | ⚠️ contained by convention only (no policy) |
| **Escalation** (overdue detection) | `felix-admin-escalation` → `escalation` + `vikunja_api` | vikunja_api | ⚠️ contained by convention only |
| **Habits** (weekly reports) | `felix-admin-habits` → *confirm* | *confirm* | ⚠️ contained by convention only |
| **Inbox capture / routing** | `felix-admin-capture` → `scripts/inbox/*` helpers + delegation | exec (module helpers) | ⚠️ helpers deterministic; but exec is unrestricted |
| **Email** (Gmail) | *unowned* (F024 pending) | gog gmail (bundled) | ❌ **UNCONTROLLED + UNOWNED** — gog gmail available to all |
| **Health / vault notes** | scripts + vault writes | exec / fs | ⚠️ exec unrestricted |
| **File / website / dev changes** | *no controlled path* | exec → arbitrary Bash | ❌ **UNCONTROLLED** — full exec, no sandbox, no approval |
| **Orchestration / routing** | `main` → `sessions_send` to sub-agents | messaging/sessions tools | main also holds gog + exec (should not) |

**Takeaway:** three ❌ UNCONTROLLED surfaces (calendar via ubiquitous gog, email via ubiquitous
gog-gmail, and arbitrary exec) are the load-bearing gaps. Everything else is contained only by
prompt convention — one truncation or misroute from falling through.

## 5. The no-silent-fallback doctrine (invariant)

> **INV — No silent fallback.** A Felix-owned capability is handled *exclusively* through its one
> controlled path (the owning agent + its contract). On failure it **fails safe** — report +
> escalate via the F1 alerting seam (ntfy operator canary + WhatsApp user transparency) — it does
> **not** fall through to a generic/default handler (raw `gog`, an unowned agent, or an LLM
> improvising around a missing capability).
>
> **Rationale — worse on two axes:** *correctness* (a wrong action via the uncontrolled path may
> go uncaught) **and** *cost* (fall-through-and-flail burns tokens; #662's haiku burned 252k tokens
> flailing on one failed run). Fail-fast-and-stop is both safer and cheaper.
>
> **Enforcement:** this invariant is *made real* by §6's per-agent tool/skill policy — an agent that
> doesn't own a capability *technically cannot* invoke it (the model never sees the tool), so there
> is no fall-through path to take. Prompt discipline (AGENTS.md "do not call gog directly") is the
> soft layer; the tool policy is the hard layer. **Both**, because the incident proves soft-alone fails.

This invariant is authored into the F3 `doctrine.md` (#677) as a founding `INV`, alongside the
two-layer invariant (deterministic plumbing the LLM never touches; the LLM never fabricates
infrastructure state).

## 6. Enforcement design — default-deny per-agent (the config to deploy)

Design intent: **least privilege per agent.** Each agent gets only the tools + skills its job
requires; `gog` is scoped to `calendar` (and later an email agent); `exec` is denied or
allowlisted for agents that don't need arbitrary shell; `main` becomes a pure router.

Illustrative `openclaw.json` shape (field names verified against docs; **exact allow/deny lists
must be validated per agent against live AGENTS.md before deploy** — §8):

```json5
agents: {
  defaults: {
    // global least-privilege baseline; per-agent lists REPLACE this
    skills: [],
    memorySearch: { enabled: false }   // kill OpenAI-embedding calls fleet-wide (§7)
  },
  list: [
    { id: "main",                                  // pure router: talk + delegate, no capabilities
      tools: { profile: "messaging",
               allow: ["sessions_send","sessions_list","sessions_spawn","message","session_status"],
               deny: ["group:runtime","group:fs","group:ui"] },
      skills: [] },
    { id: "felix-admin-calendar",                  // the ONLY gog holder
      tools: { profile: "minimal", allow: ["read","exec"],
               exec: { security: "allowlist", ask: "off" } },   // exec scoped to gog invocation
      skills: ["calendar","gog"] },
    { id: "felix-admin-tasker",
      tools: { profile: "minimal", allow: ["read","web_fetch","exec"],
               exec: { security: "allowlist", ask: "off" } },
      skills: ["task_intelligence","vikunja_api"] },
    { id: "felix-admin-escalation",
      tools: { profile: "minimal", allow: ["read","exec"],
               exec: { security: "allowlist", ask: "off" } },
      skills: ["escalation","vikunja_api"] },
    { id: "felix-admin-habits",
      tools: { profile: "minimal", allow: ["read","exec"],
               exec: { security: "allowlist", ask: "off" } },
      skills: [ /* confirm: habits + vikunja_api? */ ] },
    { id: "felix-admin-capture",                   // router + deterministic inbox helpers
      tools: { profile: "minimal", allow: ["read","exec","sessions_send"],
               exec: { security: "allowlist", ask: "off" } },
      skills: [] }
  ]
}
```

**Notes on the design:**
- **gog containment** requires *both* removing the gog **skill** from non-calendar agents (per-agent
  `skills: []`/explicit lists) *and* scoping **exec** (gog is "available as command" → runs via exec).
  Skill-removal alone leaves the `gog` binary callable via exec; exec-allowlist alone leaves the skill
  instructions visible. Do both.
- **exec `allowlist` vs `deny`:** capture/calendar/tasker/etc. run their module helpers (`python3 -m
  scripts.*`) and gog via exec, so they need exec — but scoped to an **allowlist** of the exact
  commands they run, not `full`. `main` needs **no** exec (`deny group:runtime`).
- **`skills.allowBundled`** (global) is a coarser complementary lever: set it to just the bundled
  skills Felix actually uses (`gog`, `github`?), so a newly-bundled skill pack is denied by default
  fleet-wide — the "governed the moment it exists, without a new decision" property.
- **Sandbox** is deferred defense-in-depth: once tool policy is proven stable, consider
  `agents.defaults.sandbox.mode: "non-main"` with the Docker backend. Not required for the boundary;
  tool policy is the load-bearing control.

## 6.1 Pre-flight validation (2026-07-06) — the validated per-agent config

Each agent's real needs were cross-checked against its live prompt sources
(`scripts/openclaw/agents/<agent>/AGENTS.md` + `TOOLS.md`) and helper-invocation evidence. Result:

| Agent | `skills` (final set) | Needs exec? | For what | gog? |
|---|---|---|---|---|
| **main** | `["github"]` *(confirm full set from TOOLS.md before deploy)* | **yes** | `openclaw agent --agent … --message` (delegation) + `felix-file-issue.py` + `gh` | **no** — AGENTS.md:190 already forbids it (*"Do NOT call `gog calendar create` yourself"*) |
| **felix-admin-calendar** | `["calendar","gog"]` | **yes** | `gog …` + `validate_calendar_event.py` | **YES — sole owner** |
| **felix-admin-capture** | `[]` *(or `["github"]` if it files issues)* | **yes** | `python3 -m scripts.inbox.*` (many) + delegation | no — routes calendar via `route_calendar_event` helper |
| **felix-admin-tasker** | `["task_intelligence","vikunja_api"]` | **yes** | `python3 -m scripts.enrichment.*` | no |
| **felix-admin-escalation** | `["escalation","vikunja_api"]` | **yes** | `python3 -m scripts.escalation.*` | no |
| **felix-admin-habits** | `["vikunja_api"]` ← **gap resolved** | **yes** | `python3 -m scripts.habits.*` + `observation/log_action.py` | no |

**Corrections to §6's draft this forced:**
- **`main` is NOT a no-exec router.** It delegates by running `openclaw agent` (a shell command) and files issues via a Python helper — so it genuinely needs `exec`. The §6 "messaging profile, deny runtime" design would have broken delegation + issue-filing. Corrected design for main: **keep exec, remove the gog skill** (enforcing the prompt rule it already states), keep github + sessions/messaging.
- **`habits` skills gap resolved** → `["vikunja_api"]`.

**Hard vs soft gog containment (the key mechanism finding):**
- **Soft (skills):** removing the gog `SKILL` from a non-calendar agent removes the gog *instructions* from its prompt — low-risk, won't break helpers, and directly shrinks the fall-through surface. But an **exec-capable agent could still run the `gog` binary** (gog is "available as command"; exec is arbitrary Bash). So skill-removal alone is *soft* for exec-capable agents.
- **Hard (exec):** `tools.exec.security` is **per-agent**; the approvals **allowlist is host-level**. Design: **calendar → `security: "full"`** (sole gog runner); **every other agent → `security: "allowlist"`** with a host approvals allowlist listing their helpers (`cd`, `python3 -m scripts.*`, `gh`, `openclaw agent`) but **not** `gog`. Non-calendar agents then *technically cannot* run gog.
  - **Caveat (found in `exec-approvals-advanced.md`):** allowlisting `python3` broadly is itself an escape hatch (an allowlisted `python3 -c` could shell to gog). True hard containment wants **script-specific** allowlist entries, and the `python3 -m <module>` form interacts awkwardly with OpenClaw's single-file-operand binding. Also: allowlist mode rejects `$()`/backticks and redirections and requires every `&&` segment to be allowlisted — Felix helpers use `cd … && python3 -m …`, so both segments must be listed. **⇒ exec-hardening is real but non-trivial; treat it as defense-in-depth *after* skill-scoping, not a day-1 step.**

## 7. Memory-core lock-down (hygiene deliverable)

**State (probed):** no top-level `memory`/`memorySearch` config → defaults apply → memorySearch
provider defaults to **OpenAI embeddings**. Per-agent FTS stores exist but are small/stale
(`~/.openclaw/memory/*.sqlite`: escalation/habits/tasker, 356K total, last writes Apr–Jun). The
recurring #580 noise (*"No API key found for provider openai"* ~1×/6–8h) is memory-core **trying**
to embed via OpenAI, failing (no key), and logging — i.e. dormant-but-noisy, exactly the charter's
read.

**Lock-down:** set `agents.defaults.memorySearch.enabled: false` (kills the embedding attempts and
the #580 noise; $0 impact since dormant, but removes the liability if a key were ever added).
Optionally also `plugins.slots.memory: "none"`. Felix uses the **structured Obsidian vault**, not
memory-core. This closes #580 permanently.

## 8. Phased rollout (governed, rebaseline-tracked — operator go/no-go)

`openclaw.json` is the **one monitored audited surface**; changing it is a **Tier-2 out-of-band**
change (manual rebaseline required — not a felix-deployer happy-path). It can also break Felix if
an allowlist is wrong (an agent silently loses a capability it needs). Therefore **phased, verified,
reversible**:

0. **Pre-flight — DONE (§6.1).** Per-agent skill/exec needs validated against live prompt sources;
   `habits` gap resolved; `main`-needs-exec correction made; exec-hardening feasibility resolved.
   Remaining pre-flight nit: confirm `main`'s exact skill set (and whether `capture` files issues)
   from their `TOOLS.md` before writing their explicit `skills` lists.
1. **Memory-core lock-down** (lowest risk, immediate #580 win): `agents.defaults.memorySearch.enabled:false`,
   restart gateway, confirm #580 noise stops. Rebaseline. *(No per-agent analysis needed — deployable now.)*
2. **Per-agent skill-scoping — the low-risk gog-surface win.** Set `agents.list[].skills` to the §6.1
   validated sets, with **calendar the only list containing `gog`**. Cleanest form: set
   `agents.defaults.skills` to the fleet's non-gog skill union and override only
   `felix-admin-calendar.skills: ["calendar","gog"]` — removes gog's instruction pack from every other
   agent in one change. Verify `skills check --agent main` (and each worker) **no longer lists gog**;
   verify each agent's cron/on-demand job still runs. Rebaseline. *(Soft containment — removes gog
   instructions; does not yet block the binary via exec.)*
3. **Exec-hardening — hard containment, defense-in-depth (higher effort, do after step 2 is stable).**
   Per §6.1: `felix-admin-calendar.tools.exec.security: "full"`; every other agent
   `security: "allowlist"` + a host approvals allowlist of their exact helper commands (excluding
   `gog`). Author the allowlist carefully (script-specific entries, not bare `python3`; handle the
   `cd … && python3 -m …` chaining). Verify each agent's real job still runs **and** that a
   non-calendar agent's attempt to run `gog` is denied. Rebaseline per agent.
4. **`skills.allowBundled`** global tightening once per-agent lists are proven — so a newly-bundled
   skill pack is denied fleet-wide by default.
5. **(Later) sandbox** (`agents.defaults.sandbox.mode`) as further defense-in-depth.

Each step: apply → behavioral-verify the agent's real job → rebaseline (out-of-band exception) →
only then proceed. Roll back via the `.bak` if any agent breaks. **No big-bang rewrite.** Steps 1–2
are low-risk and high-value (kill #580 + close the gog *instruction* surface fleet-wide); step 3 is
the harder hard-containment pass.

## 9. Side-findings (file as their own issues / notes)

- **Model doc-drift:** live `habits` + `tasker` = **haiku**, but `service-inventory.json` documents
  **sonnet**. Reconcile → feeds #671 (fleetwide model framework) + a doc-correction.
- **Fictional per-agent `skills` in `service-inventory.json`** (§2) — correct the inventory to
  reflect reality (no per-agent skills configured) *or* deploy §6 to make the doc true. Tie the
  correction to the §8 rollout so doc and reality converge rather than drift again.
- **exec-policy = yolo fleet-wide** and **sandbox off** — captured here; addressed by §6/§8.
- **Secret hygiene:** a Gemini `webSearch` API key sits in plaintext in
  `openclaw.json → plugins.entries.google.config.webSearch.apiKey`. Expected for a local OpenClaw
  config, but confirm `openclaw.json` is never committed to any repo and is covered by the secrets
  posture. (Not reproduced here.)

## 10. What this unblocks

- **F1** (observability): outcome canaries can assert "capability X was handled by its owner, not a
  fall-through" (#657); the usage ledger quantifies fall-through cost this prevents.
- **F2** (change governance): the enforcement config is itself an F2 audited surface — Foundation 0
  and F2 share the same enforcement plane (`openclaw.json`, tier-aware, rebaseline-tracked).
- **F3** (coherence): the capability map + no-silent-fallback doctrine are canonical invariants
  authored into `doctrine.md` (#677).
- **#167 agent-authoring family**: operationalizes the boundary in prompts (the soft layer) on top
  of the hard layer defined here.
