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

> **STATUS UPDATE 2026-07-10 (post-#699 + Step-3 finding):** `gog` is now used by **`main`
> only** (gmail/drive/etc.). `felix-admin-calendar` is a **former** gog owner — #699 migrated
> it onto the Felix calendar helper; it is now `gog`-free. Sections below describing calendar
> as a gog owner are **pre-#699 historical**. Hard containment via exec-allowlist was found
> infeasible (see §8 Step 3); the real lever is sandbox (follow-up issue in §8).

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
| **`gog` is visible to every agent** *(pre-#699 historical — see 2026-07-10 status update)* | `openclaw skills check --agent main` and `--agent felix-admin-calendar` both report gog **"Ready and visible to model"** (26/61 skills visible, identical sets). gog source = `openclaw-bundled`, `Available as command: yes`. | `main` can invoke `gog` directly — **this is the exact mechanism of the "scheduled on Wednesday" calendar fall-through incident.** *(Since Step-2 deploy: gog skill visible only to `main` + `calendar`; since #699: `main` only.)* |
| **exec is wide open** | `openclaw exec-policy show` → effective `tools.exec: security=full, ask=off`; approvals file **missing**. | Every agent has **unrestricted arbitrary-Bash exec** with no approval gate. This is the "file/website writes → arbitrary Bash" uncontrolled surface. |
| **Sandbox is off** | No `sandbox` block anywhere; default `mode: off`. | No runtime isolation; exec runs directly on the gateway host. |
| **Other broad bundled skills are live** | `openclaw skills list` shows 26 ready incl. `github`, `gh-issues`, `notion`, `browser-automation`, `canvas`, `taskflow`, `weather`, `whisper`. | The available surface is far broader than the Felix agents' actual jobs. |

**Documentation fiction to correct:** our `docs/design/architecture/data/service-inventory.json`
documents per-agent `skills` arrays (e.g. calendar `["calendar","gog"]`, tasker
`["task-intelligence","vikunja-api"]`). **These do not exist in the live `openclaw.json`.** The
inventory records intent that was never configured. This must be reconciled (see §9). *(Update
2026-07-10: the calendar `["calendar","gog"]` example is **pre-#699 historical** — post-#699
`felix-admin-calendar.skills` is `[]`; `calendar` was never a real OpenClaw skill and #699
removed `gog` from calendar. The live Step-2 skill sets are recorded in the §8 Step 2 deploy
note.)*

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
| **Calendar** (create/update events) *(pre-#699 historical — see 2026-07-10 status update)* | `felix-admin-calendar` → ~~`gog calendar` (payload contract)~~ **now the Felix calendar helper (google-api-python-client), not gog (#699)** | ~~gog (bundled)~~ **Felix calendar helper** | Post-#699: calendar is `gog`-free; capture reaches calendar inline via `route_calendar_event --create`. (Historical: ❌ UNCONTROLLED — gog visible to all agents; main falls through.) |
| **Tasks** (Vikunja CRUD) | `felix-admin-tasker` → `vikunja_api` skill | vikunja_api (managed) | ⚠️ contained by convention only (no policy) |
| **Escalation** (overdue detection) | `felix-admin-escalation` → `escalation` + `vikunja_api` | vikunja_api | ⚠️ contained by convention only |
| **Habits** (weekly reports) | `felix-admin-habits` → *confirm* | *confirm* | ⚠️ contained by convention only |
| **Inbox capture / routing** | `felix-admin-capture` → `scripts/inbox/*` helpers + delegation | exec (module helpers) | ⚠️ helpers deterministic; but exec is unrestricted |
| **Email** (Gmail) | *unowned* (F024 pending) | gog gmail (bundled) | ❌ **UNCONTROLLED + UNOWNED** — gog gmail available to all |
| **Health / vault notes** | scripts + vault writes | exec / fs | ⚠️ exec unrestricted |
| **File / website / dev changes** | *no controlled path* | exec → arbitrary Bash | ❌ **UNCONTROLLED** — full exec, no sandbox, no approval |
| **Orchestration / routing** | `main` → `sessions_send` to sub-agents | messaging/sessions tools | main also holds gog + exec (should not) |

**Takeaway** *(pre-#699 historical — see 2026-07-10 status update)*: as of the 2026-07-06 spike,
three ❌ UNCONTROLLED surfaces (calendar via ubiquitous gog, email via ubiquitous gog-gmail, and
arbitrary exec) were the load-bearing gaps. **Post-#699 the calendar surface is off gog** (Felix
calendar helper), so the current uncontrolled-`gog` surfaces are **email (`gog gmail`) + drive on
`main` only**, plus arbitrary exec fleet-wide (the §8.3 finding: exec approvals are guardrails,
not isolation). Everything else is contained only by prompt convention — one truncation or
misroute from falling through.

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

> *(pre-#699 historical — see 2026-07-10 status update)* This §6 design intent predates #699.
> Two of its premises are now stale: **`gog` is no longer scoped to `calendar`** — #699 migrated
> calendar onto the Felix calendar helper, so post-#699 `gog` is used by **`main` only**; and
> **`main` did not become a pure router** — §6.1 corrected that (main genuinely needs `exec` for
> delegation + issue-filing and remains the tracked `gog` exception until #680). The illustrative
> JSON below is retained as the original design sketch, not the deployed state.

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
    { id: "felix-admin-calendar",                  // pre-#699 historical: was drafted as the ONLY gog holder; post-#699 calendar is gog-free (Felix calendar helper)
      tools: { profile: "minimal", allow: ["read","exec"],
               exec: { security: "allowlist", ask: "off" } },   // exec scoped to gog invocation (pre-#699 historical)
      skills: ["calendar","gog"] },                // pre-#699 historical — see 2026-07-10 status update; live post-#699 calendar.skills = []
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
| **felix-admin-calendar** *(pre-#699 historical — see 2026-07-10 status update; live post-#699 skills = `[]`, gog-free)* | `["calendar","gog"]` | **yes** | `validate_calendar_event.py` + Felix calendar helper (post-#699; was `gog …`) | ~~**YES — sole owner**~~ **no (former owner; #699 migrated calendar off gog)** |
| **felix-admin-capture** | `[]` *(or `["github"]` if it files issues)* | **yes** | `python3 -m scripts.inbox.*` (many) + delegation | no — routes calendar via `route_calendar_event` helper |
| **felix-admin-tasker** | `["task_intelligence","vikunja_api"]` | **yes** | `python3 -m scripts.enrichment.*` | no |
| **felix-admin-escalation** | `["escalation","vikunja_api"]` | **yes** | `python3 -m scripts.escalation.*` | no |
| **felix-admin-habits** | `["vikunja_api"]` ← **gap resolved** | **yes** | `python3 -m scripts.habits.*` + `observation/log_action.py` | no |

**Corrections to §6's draft this forced:**
- **`main` is NOT a no-exec router.** It delegates by running `openclaw agent` (a shell command) and files issues via a Python helper — so it genuinely needs `exec`. The §6 "messaging profile, deny runtime" design would have broken delegation + issue-filing. Corrected design for main: **keep exec, remove the gog skill** (enforcing the prompt rule it already states), keep github + sessions/messaging.
- **`habits` skills gap resolved** → `["vikunja_api"]`.

**Hard vs soft gog containment (the key mechanism finding):** *(pre-#699 historical + superseded —
see 2026-07-10 status update and the §8.3 Step-3 finding. Two updates: (1) `calendar` is no longer
the gog runner — #699 migrated it onto the Felix calendar helper, so post-#699 `main` is the only
gog consumer; (2) the "exec-hardening is real but non-trivial, do it after skill-scoping" conclusion
below is **upgraded** by §8.3 to "exec-allowlist hard containment is infeasible for this fleet — use
sandbox instead.")*
- **Soft (skills):** removing the gog `SKILL` from a non-calendar agent removes the gog *instructions* from its prompt — low-risk, won't break helpers, and directly shrinks the fall-through surface. But an **exec-capable agent could still run the `gog` binary** (gog is "available as command"; exec is arbitrary Bash). So skill-removal alone is *soft* for exec-capable agents.
- **Hard (exec):** `tools.exec.security` is **per-agent**; the approvals **allowlist is host-level**. Design *(pre-#699)*: **calendar → `security: "full"`** (then-sole gog runner); **every other agent → `security: "allowlist"`** with a host approvals allowlist listing their helpers (`cd`, `python3 -m scripts.*`, `gh`, `openclaw agent`) but **not** `gog`. Non-calendar agents then *technically cannot* run gog. *(§8.3 finding: this allowlist design proved infeasible — sandbox is the correct lever.)*
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

> **✅ DEPLOYED 2026-07-07 (Step 1 of §8).** Applied via `openclaw config patch` (dry-run validated
> first): `agents.defaults.memorySearch.enabled: false`. Verified: config valid, value = `false`,
> gateway restarted healthy. Pre-flight: no agent prompt uses `memory_search`/`memory_get` (safe);
> Restic snapshot `517bc952` within 24h; openclaw.json backed up to `...bak-memcore-20260707T011745Z`.
> Rebaseline: audit flagged **only** `openclaw-config.txt` drift (`1c1`, the expected one-key change),
> rebaselined → "All clear". Key verified against 2026.6.11 bundled `reference/memory-config.md`
> (`enabled`, bool, default `true`; provider defaults to OpenAI when unset — the #580 cause).

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
2. **Per-agent skill-scoping — the low-risk gog-surface win.** *(This step's calendar-holds-gog
   framing is **pre-#699 historical** — see 2026-07-10 status update; #699 later set calendar's
   live skills to `[]`, leaving `main` the only gog holder.)* Set `agents.list[].skills` to the §6.1
   validated sets, with **calendar the only list containing `gog`** *(pre-#699)*. Cleanest form: set
   `agents.defaults.skills` to the fleet's non-gog skill union and override only
   `felix-admin-calendar.skills: ["calendar","gog"]` *(pre-#699; now `[]`)* — removes gog's
   instruction pack from every other agent in one change. **Verify with the deterministic snapshot helper**
   `scripts/openclaw/agents/skills_snapshot.py` (runs `openclaw skills check --agent <id>` per agent,
   extracts the visible-skill set + the `excluded_by_agent_allowlist` count): capture *before*, apply,
   capture *after*, confirm the only delta is "gog removed from every agent except calendar" (and each
   worker keeps its skills). Then behavioral-verify each agent's cron/on-demand job still runs.
   Rebaseline. *(Soft containment — removes gog instructions; does not yet block the binary via exec.)*
   **Baseline (2026-07-07, pre-scoping):** all 6 agents `visible=26, excluded=0`, **all see gog**
   (`office2:/tmp/skills-before-20260707.json`).

   > **✅ PARTIALLY DEPLOYED 2026-07-07 (safe subset; `main` HELD).** *(The calendar=`[gog]` /
   > "gog visible to `main` + `calendar`" state below is **pre-#699 historical** — see 2026-07-10
   > status update. #699 migrated calendar onto the Felix calendar helper and set live
   > `felix-admin-calendar.skills = []`, so post-#699 gog is visible to **`main` only**.)* Applied
   > per-agent `skills` via `openclaw config patch` (built programmatically from live config, all
   > fields preserved, dry-run validated): **capture=`[vikunja_api,github]`, habits=`[vikunja_api]`,
   > tasker=`[task_intelligence, vikunja_api]`, escalation=`[escalation,vikunja_api]`,
   > calendar=`[gog]`** *(pre-#699; now `[]`)*. Snapshot diff confirms gog removed from all 4 workers,
   > retained on calendar *(pre-#699; #699 later removed it)*, main unchanged → **gog then visible
   > only to `main` + `calendar`** *(post-#699: `main` only)*. Gateway restarted healthy; rebaselined
   > "All clear". (Note: `calendar` skill name dropped — no such skill exists in OpenClaw; the real
   > skill is `gog`.)
   >
   > **`main` HELD — trajectory investigation found main is the *live* gog executor** (`exec` tool
   > entries: `gog calendar create/update`, `gog gmail` ×13, `gog drive`, last Jul 5). Removing gog from
   > main would delete Felix's only path for calendar-create, **email, and drive** (email/drive have no
   > owning agent). **Two blockers must clear first** (filed as #675 children): (a) the calendar-create
   > path bypasses felix-admin-calendar — main is the de-facto gog executor despite #579 extracting a
   > calendar agent + main's own AGENTS.md forbidding it (capture still delegates calendar to *main* for
   > `gog calendar create`); (b) email + drive need controlled owners (F024). Until both clear, main
   > keeps gog for **gmail + drive** (blocker (b), F024/#680). *(Update 2026-07-10: blocker (a) is
   > **resolved** — #699 migrated the calendar-create path onto the Felix calendar helper; capture
   > now reaches calendar inline via `route_calendar_event --create`, so the "delegate to main for
   > gog calendar create" path no longer exists. main's remaining gog use is gmail + drive only.)*
3. **Exec-hardening — FINDING: exec-allowlist hard containment is INFEASIBLE for this fleet.**
   (Validated against **OpenClaw 2026.6.11 (e085fa1)** and the bundled doc
   `~/.local/lib/node_modules/openclaw/docs/tools/exec-approvals-advanced.md`. See the
   **Step-3 finding** subsection immediately below — §8.3 — for the full evidence, narrower-knob
   disposition, and the sandbox recommendation.) The intended Step 3 was
   `felix-admin-calendar.tools.exec.security: "full"` with every other agent on
   `security: "allowlist"` + a host approvals allowlist of their exact helpers (excluding `gog`).
   Design-phase research (research.md Decision 1) established this cannot be done as a *no-human,
   no-breakage* control. **Continuation tracked in the sandbox follow-up issue (#704 — see
   Appendix A; filed at mission merge).** *(Note: post-#699 no worker even holds `gog`, so this
   Step is now pure defense-in-depth — a further reason to defer it to the sandbox lever.)*
4. **`skills.allowBundled`** global tightening once per-agent lists are proven — so a newly-bundled
   skill pack is denied fleet-wide by default. **Folded into the sandbox follow-up issue** (Appendix A)
   as a named sub-item rather than left as a separate untracked follow-up.
5. **Sandbox** (`agents.defaults.sandbox.mode: "non-main"`, Docker backend) — **promoted by the
   Step-3 finding from "later defense-in-depth" to the correct hard-containment lever.** A sandbox
   lets a worker run arbitrary code *inside the sandbox* while the `gog` binary is simply absent —
   containment without enumerating every command. **Caveat: `network: none` ≠ no network** — the
   workers legitimately reach the Vikunja API and repo helpers, so the sandbox needs an explicit
   egress policy (allow Vikunja/host, deny Google) plus checkout+venv bind-mounts, not a blanket
   network kill. Scoped in Appendix A.

### 8.3 Step-3 finding — exec approvals are guardrails, not isolation

**Validation basis:** OpenClaw **2026.6.11 (e085fa1)**; bundled doc
`~/.local/lib/node_modules/openclaw/docs/tools/exec-approvals-advanced.md`; per-agent trajectory
evidence from `~/.openclaw/agents/<agent>/sessions/*.trajectory.jsonl` (captured 2026-07-10).

**The honest conclusion (not "no narrower config exists"):** OpenClaw's exec approvals are
**best-effort operator guardrails, not a strong isolation boundary.** **No per-agent allowlist
exists for this fleet today that is simultaneously (a) tight enough to deny `gog`, (b) non-breaking
for the workers' real exec behavior, and (c) free of human-in-the-loop approvals.** OpenClaw's own
security docs say exec approvals do not semantically model every runtime/interpreter path and
recommend sandbox / host isolation for a real boundary.

**Why (falsifiable mechanics from `exec-approvals-advanced.md`):**
- **Redirections are unsupported in allowlist mode** → capture's `cat >> …/inbox-processing-*.md`
  append and habits' `cat > /tmp/weekly_report.py` break.
- **Command substitution `$()` / backticks are rejected** during allowlist parsing.
- **Interpreter inline eval** (`python3 -c "…"`, `python3 << EOF … EOF`) is denied only under
  `tools.exec.strictInlineEval: true` — the setting you must enable to close the escape hatch —
  which then breaks calendar's heredoc and capture's `-c`.
- **Interpreter binding requires "exactly one concrete local file."** The `python3 -m <module>`
  helper form does **not** resolve to a single concrete file path; the doc states that when
  OpenClaw "cannot identify exactly one concrete local file … approval-backed execution is denied
  instead of claiming semantic coverage it does not have." So even the *legitimate* `python3 -m
  scripts.<domain>.*` helper form is at risk of denial under allowlist mode — its viability is
  **unproven**.

The forcing dilemma: an allowlist strict enough to deny `gog` also denies inline eval, heredocs,
redirection, and non-allowlisted script paths — much of what the workers actually do. A looser
allowlist that permits `python3` broadly reintroduces the `gog` escape hatch (an allowlisted
`python3 -c` can `subprocess.run(["gog", …])`). **There is no clean middle with the allowlist
alone.**

**Per-agent exec-form evidence** (observed trajectory `exec` invocations, 2026-07-10):

| Agent | Clean `python3 -m` forms | Also uses (breaks a strict allowlist) |
|---|---|---|
| capture | `cd … && python3 -m scripts.inbox.prescan` | `python3 -c "…"` (inline eval); `cat >> …/inbox-processing-*.md << EOF` (redirection) |
| habits | `python3 -m scripts.habits.{morning_checkin_list,record_completion,parse_morning_reply}` | `cat > /tmp/weekly_report.py << EOF` then runs the scratch script |
| calendar | `python3 -m scripts…` (helper) | `python3 << EOF … EOF` (heredoc inline eval); `python …/log_action.py` |
| tasker | (little/none in sample) | `curl -s -X DELETE -H … <vikunja>` (direct API) |
| escalation | (little/none in sample) | `curl -s -H … <vikunja>` (many); `cat state/…`, `grep`, `date` |

**Explicit disposition of the narrower knobs** (so no reader thinks an obvious config was missed):

- **`argPattern`-scoped `python3 -m scripts.<domain>.*`** — would permit only the clean helper form,
  but (i) relies on the `-m` interpreter binding OpenClaw may deny as "not one concrete local file"
  (unproven), and (ii) does nothing about the workers' *other* real forms (redirection, heredoc,
  curl), which then break. **Rejected** as a non-breaking control.
- **`strictInlineEval: true`** — makes inline eval (`python3 -c`, `python3 << EOF`) require an
  *explicit approval*, not become impossible. In a no-human, cron-driven fleet an approval that
  never comes is a denial → breaks calendar's heredoc + capture's `-c`. **Rejected** as
  non-breaking.
- **`safeBins` / `safeBinProfiles`** — stdin-only text filters (`cut`, `wc`, …); the docs
  explicitly forbid adding interpreters (`python3`, `bash`) here. Irrelevant to `gog`/helper
  containment. **Rejected** as inapplicable.
- **`ask = on-miss`** (approval on allowlist miss) — reintroduces human-in-the-loop for every
  non-listed command; incompatible with the autonomous cron fleet. **Rejected.**

**Recommendation — the correct hard-containment lever is sandbox.**
`agents.defaults.sandbox.mode: "non-main"` (Docker backend) contains the workers by making the
`gog` binary simply *absent* inside the sandbox — no need to enumerate every command they run.
**But sandbox is not free, and `network: none` ≠ no network:** the workers legitimately `curl` the
Vikunja API and run repo helpers that need the kg-automation checkout + Python venv mounted. A
naïve `network: none` sandbox breaks Vikunja access. The follow-up must therefore prove three
properties **separately** (see Appendix A):
1. the `gog` binary is **absent/unreachable** inside the worker sandbox;
2. **Google egress is blocked** (the actual containment goal — *not* the same as blocking all
   network);
3. **required internal paths still work** — Vikunja API reachable, checkout + venv bind-mounted,
   state dirs writable — so each worker's real cron job still runs.

**Alternatives considered and rejected** (research.md Decision 1):
- *Strict allowlist + refactor every worker to helper-only exec* — a large behavioral change to
  five agents (essentially the Bedrock "determinize the agents" thrust), far beyond this mission,
  and still brittle against the `-m` binding uncertainty.
- *Loose `python3` allowlist* — reintroduces the `gog` escape hatch; not containment.
- *Ship nothing, leave undocumented* — wastes the completed research; the next person re-probes
  office2 from scratch.

### 8.4 #675 tracker disposition (recommended; operator confirms at merge)

#675 asked for **technical hard containment** of `gog` on the workers. This mission intentionally
does **not** deliver it — the allowlist route is found infeasible (§8.3) and the sandbox route is
deferred to a follow-up. To keep "docs + a filed issue" from reading as hard-containment
*completion*, the recommended disposition is:

> **Close #675 as RESCOPED** — "allowlist hard-containment found infeasible; the finding + boundary-doc
> reconcile landed (this mission); the remaining hard boundary is **superseded by the sandbox
> follow-up #704**" — with the sandbox issue linked as the continuation.

**Explicitly: "docs + issue" ≠ hard-containment completion.** The operator confirms the
close-vs-keep-open call at merge. (Post-#699, no worker holds `gog` at all, so the residual risk
this defers is pure defense-in-depth, which further supports the rescope.)

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

## Appendix A — Sandbox hard-containment follow-up (issue draft)

Filed as **[#704](https://github.com/kentonium3/kg-automation/issues/704)** (infra) from this
mission; the body below is the source draft. It is the continuation of §8 Step 3 / §8.3; #675 and
§8 Step 3 link to it. This is a **kg-automation-internal** tracking issue (no external/upstream
copy; no `@`-mentions of outsiders).

---

**Title:** `infra: sandbox-based hard containment of gog on Felix worker agents (Foundation-0 Step 3 continuation)`

**Symptom.** The Felix worker agents (`felix-admin-capture`, `-habits`, `-tasker`, `-escalation`)
run with `tools.exec.security: full` — unrestricted arbitrary-Bash exec on the OpenClaw gateway
host. Any worker can invoke the `gog` binary directly (it is "available as command"), bypassing the
one-controlled-path boundary. Step 2 (skill-scoping) removed the `gog` *instruction pack* from the
workers (soft containment), and #699 removed calendar's legitimate `gog` use, but the binary remains
**technically reachable** via exec from every worker. Hard containment is not yet in place.

**Observer.** Foundation-0 Step-3 finding (`docs/design/felix-openclaw-boundary.md` §8.3, this
mission); the office2 exec-policy probe (`openclaw exec-policy show` → `security=full, ask=off`
fleet-wide).

**Cost of doing nothing.** The no-silent-fallback invariant (§5) stays *soft-only* for the workers:
a prompt-injection or misroute that reaches a worker's exec can still shell to `gog` (calendar,
gmail, drive), i.e. the exact fall-through class Foundation-0 exists to close, uncaught and
un-approved. It also burns tokens flailing (cf. #662's 252k-token run). The boundary remains
"contained by convention" for the workers until this lands.

**Why not exec-allowlist.** Established infeasible in §8.3 (OpenClaw 2026.6.11): an allowlist tight
enough to deny `gog` also denies inline eval, heredocs, redirection, and non-allowlisted script
paths — much of what the workers actually do — while a looser allowlist that permits `python3`
broadly reintroduces the `gog` escape hatch. Exec approvals are guardrails, not isolation.

**Scope — the sandbox (`agents.defaults.sandbox.mode: "non-main"`, Docker backend) must prove
THREE properties SEPARATELY** (`network: none` ≠ no network):

1. **`gog` binary absent/unreachable** in the worker sandbox — a worker's attempt to run `gog`
   (calendar/gmail/drive) fails because the binary is not present/on PATH inside the container, not
   merely because a skill is hidden.
2. **Google egress blocked** — network egress to Google endpoints (the actual containment goal) is
   denied by the sandbox network policy. This is **distinct from** blocking all network and must be
   demonstrated as its own property.
3. **Required internal paths still work** — each worker's real cron job still runs: the Vikunja API
   is reachable (workers `curl` it directly), the kg-automation checkout + Python venv are
   bind-mounted, and state dirs are writable. This needs an explicit **egress allowlist** (permit
   Vikunja/host, deny Google) plus a **bind-mount + workspace-access** design — not just
   `mode: non-main`.

**Sub-item — `skills.allowBundled` global tightening (folded in from §8 Step 4).** Set the global
bundled-skill allowlist to just the bundled skills Felix actually uses, so a newly-bundled skill
pack is denied fleet-wide by default (the "governed the moment it exists, without a new decision"
property). Decide and land this alongside the sandbox hardening rather than as a separate untracked
follow-up.

**Out of scope.** `main`'s treatment — `main` legitimately needs `gog` for gmail + drive and
`mode: "non-main"` leaves it uncontained by design; this stays consistent with `main` being the
documented Foundation-0 exception until #680 homes email/drive. Any change to worker business logic
or agent prompts.

**Links.** Supersedes the hard-containment ask of #675 (rescoped — see §8.4). Continuation of
`docs/design/felix-openclaw-boundary.md` §8 Step 3 / §8.3. Bedrock epic #673; #680 (email/drive
owner).

---
