# Felix Foundation-0 Exec-Hardening — Finding & Doc Reconcile

## Purpose

Resolve **Step 3** of the Foundation-0 OpenClaw capability-boundary rollout (#675, Bedrock
epic #673). The intended Step 3 was hard containment of `gog` on the four non-owner worker
agents via per-agent `tools.exec.security: allowlist`. **Design-phase research established
that this is not achievable with the allowlist alone** without breaking the workers' real
exec behavior: the workers do not invoke a fixed set of deterministic helpers — in practice
they use inline eval (`python3 -c`, `python3 << EOF`), output redirection (`cat >> log`),
scratch scripts, and `curl`, all of which OpenClaw's allowlist mode denies. An allowlist
strict enough to block `gog` would also block these real behaviors.

Per operator decision, this mission **banks the unconditional wins and records the finding**
rather than deploying a disruptive or leaky allowlist:

1. **Record the feasibility finding** in the boundary design doc — allowlist-alone is
   insufficient; **sandbox is the appropriate hard-containment lever** — with the concrete
   evidence so a future sandbox mission can act without re-deriving it.
2. **Reconcile the architecture docs** to the real deployed config (service-inventory skills
   fiction + habits/tasker model drift).
3. **Document `main`** as the tracked Foundation-0 exception (retains `gog` + broad exec for
   email/drive until #680).
4. **File a follow-up issue** for sandbox-based hard containment (the deferred path).

**This mission does not modify `openclaw.json`.** The deployed boundary — Steps 1
(memory-core kill) and 2 (skill-scoping / *soft* containment, `gog` visible only to `main`
+ `calendar`) — is unchanged. There is therefore no office2 runtime change, no Tier-2
deploy, and no rebaseline in this mission.

## User Scenarios & Testing

### Primary scenario — a future maintainer picks up hard containment

Someone (or Felix itself) later takes on the sandbox follow-up issue. They open
`docs/design/felix-openclaw-boundary.md` §8 Step 3, read the recorded finding — *why*
exec-allowlist was rejected (with the per-agent exec-form evidence and the specific
allowlist-mode constraints), and *what to do instead* (sandbox `mode: non-main`, no `gog`
binary / no Google network in the worker sandbox) — and can act immediately, without
re-probing office2 or rediscovering the constraint.

### Primary scenario — the architecture docs tell the truth

An agent authoring a future spec consults `service-inventory.json` for what skills and model
each Felix agent has. Post-mission, every field matches live config: the fictional per-agent
`skills` arrays are gone (replaced by the real Step-2 deployed sets), habits and tasker read
`haiku` (not `sonnet`), and `main` is annotated as the tracked gog/exec exception. The
architecture-data validator passes.

### Exception — the reconcile would contradict deployed reality

While reconciling, a discrepancy appears between what the boundary doc claims is deployed and
what the live config actually shows. The JSON (authoritative) is corrected to match **live
config**, not the doc's prior claim, and the narrative follows the JSON. Live config is the
source of truth for "what is deployed."

### Edge — no runtime drift introduced

Because no `openclaw.json` change is made, the security-monitor baselines must remain
undisturbed: the daily audit MUST NOT show new `openclaw-config` drift attributable to this
mission. The mission's footprint is repo docs + one GitHub issue only.

## Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| FR-001 | The **feasibility finding MUST be recorded** in `docs/design/felix-openclaw-boundary.md` (§8 Step 3 plus a dedicated finding subsection): that OpenClaw's exec **approvals are best-effort guardrails, not strong isolation**, and no per-agent allowlist that is simultaneously tight enough to deny `gog`, non-breaking for the workers' real behavior, and free of human-in-the-loop approvals exists for this fleet today. It MUST include (a) the per-agent exec-form evidence (inline eval, heredoc, redirection, curl, scratch scripts vs clean `python3 -m`), (b) the governing allowlist-mode constraints from the bundled `exec-approvals-advanced.md` (redirection unsupported; `$()`/backticks rejected; inline eval requires approval under `strictInlineEval`; `python3 -m` interpreter-binding uncertainty), (c) an **explicit disposition of the narrower knobs** (`argPattern`, `strictInlineEval`, `safeBins`, `ask=on-miss`) explaining why each is rejected, and (d) the recommendation that **sandbox (`agents.defaults.sandbox.mode: non-main`)** is the correct hard-containment lever. | Pending |
| FR-002 | `docs/design/architecture/data/service-inventory.json` (and its narrative counterpart) MUST be reconciled to the **real deployed config** for all six agents — a **full sweep, not just `model`/`skills`**: replace the fictional per-agent `skills` arrays with the actual Step-2-deployed sets (calendar → `[]`), record each agent's real exec posture (`security: full` fleet-wide), **and correct the stale per-agent narrative fields #699's partial reconcile missed** — the `purpose`/`notes`/`components[].purpose`/`depends_on` fields on capture, calendar, main, and the `route/validate_calendar_event` component that still describe the retired pre-#699 "delegate to Felix main for `gog calendar create`" path (post-#699 the calendar is reached inline via `route_calendar_event --create`; calendar invokes the Felix calendar helper, not gog). Also correct the OpenClaw gateway **version** (inventory `v2026.6.5` → live `2026.6.11`). | Pending |
| FR-003 | The **model drift MUST be corrected**: the inventory records felix-admin-habits and felix-admin-tasker as `sonnet-4-6`; live config runs both on `haiku`. Update the JSON and its narrative counterpart to `anthropic/claude-haiku-4-5`. (escalation, main correctly `sonnet-4-6`; capture, calendar correctly `haiku` — no change.) | Pending |
| FR-004 | The **boundary doc's stale `gog`-ownership claims MUST be reconciled across the whole doc** (§2 current-state, §4 capability map, §6 design intent/example, §6.1 pre-flight table, §8 rollout steps) — either rewritten as explicitly-labelled *pre-#699 historical* state or corrected to reality: post-#699 **`gog` is `main`-only** (gmail/drive/etc.); `felix-admin-calendar` is a **former** gog owner, now `gog`-free (Calendar-via-helper). `main` MUST be documented as the tracked Foundation-0 exception (retains `gog` + broad exec for email/drive until #680) in both the boundary doc and the architecture inventory. | Pending |
| FR-005 | A **follow-up issue MUST be filed** (kentonium3/kg-automation, infra template) for **sandbox-based hard containment** — the deferred Foundation-0 hard-boundary path — referencing this finding. It MUST require the sandbox design to prove **three properties separately** (network:none ≠ no network): (i) `gog` binary absent/unreachable in the worker sandbox, (ii) Google egress blocked, (iii) Vikunja API + kg-automation checkout/venv/state paths still work so each worker's real cron job runs; and it MUST fold in the **Step 4 (`skills.allowBundled`) decision** as a named sub-item. Boundary-doc §8 Step 3 MUST link to this issue as the continuation. | Pending |
| FR-006 | This mission MUST make **no change to `openclaw.json`** or any office2 runtime config; the deployed Step 1–2 boundary is unchanged. The mission footprint is repo documentation plus one GitHub issue. | Pending |
| FR-007 | The **#675 tracker disposition MUST be explicit** so "docs + follow-up" does not read as hard-containment *completion*: the mission's closing note recommends closing #675 as **rescoped** (allowlist hard-containment found infeasible; finding + reconcile landed; remaining hard boundary superseded by the sandbox follow-up), with the operator confirming close-vs-keep-open at merge. | Pending |

## Non-Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| NFR-001 | **Validator-clean**: the reconciled `service-inventory.json` MUST pass `tooling/scripts/validate_architecture_data.py` (the blocking Docs-CI gate); the JSON is authoritative and the narrative view MUST agree with it. | Pending |
| NFR-002 | **Actionable finding**: the recorded finding MUST cite the OpenClaw version it was validated against (2026.6.11) and the specific bundled doc, and MUST include the concrete per-agent exec-form evidence, so a future sandbox mission can act without re-probing office2. | Pending |
| NFR-003 | **Falsifiable conclusion**: the finding MUST name the specific allowlist-mode mechanics that drive the "insufficient" conclusion (redirection unsupported, inline-eval denial, `-m` binding uncertainty), not merely assert infeasibility. | Pending |
| NFR-004 | **No runtime drift**: after the mission merges, the office2 daily security audit MUST NOT surface new `openclaw-config` drift attributable to this mission (because `openclaw.json` is untouched). | Pending |
| NFR-005 | **Semantic-consistency check**: because the architecture-data validator proves JSON schema validity but not cross-doc semantic consistency, the mission MUST include a lightweight grep-based acceptance check that the touched architecture docs no longer contain stale present-tense phrases — e.g. `"calendar","gog"`, `sole owner` / `only gog holder` (of calendar), `delegate to Felix main for `gog calendar create``, calendar `executes gog` — except where explicitly labelled pre-#699 historical. | Pending |

## Constraints

| ID | Description | Status |
| --- | --- | --- |
| C-001 | This mission MUST NOT modify `openclaw.json`, exec policy, or any office2 runtime config. It is documentation + a recorded finding + one follow-up issue. No Tier-2 change, no Restic snapshot, no rebaseline. | Active |
| C-002 | Architecture-data edits are authoritative in **JSON**; the narrative markdown view follows the JSON. All edits MUST satisfy the architecture-data validator. | Active |
| C-003 | `main` is OUT of scope for any capability change; it is documented as the tracked exception until #680 homes email/drive. | Active |
| C-004 | **Sandbox design and deployment are OUT of scope** — the sandbox hard-containment path is *filed as a follow-up issue*, not built or deployed in this mission. | Active |
| C-005 | The recorded finding MUST be consistent with the deployed reality (Steps 1–2); this mission does NOT re-litigate or alter skill-scoping. | Active |
| C-006 | Per the cross-repo standing rules, the follow-up issue is a **kg-automation-internal** tracking issue (repo-scoped copy-approval exception applies); no external/upstream copy is produced, and no `@`-mentions of outsiders. | Active |

## Domain Language

| Term | Meaning | Avoid |
| --- | --- | --- |
| **Soft containment** | Skill-scoping (Step 2, deployed): removes the `gog` *instruction pack* from an agent's `skills` list; the binary remains runnable via exec. | — |
| **Hard containment** | Making the `gog` binary *technically unreachable*. This mission finds the exec-allowlist route insufficient and defers hard containment to **sandbox**. | — |
| **`gog` consumer (post-#699)** | `main` is the **only** current `gog` consumer (gmail + drive + contacts/sheets/docs). **No worker uses `gog`** — #699 migrated calendar onto the Felix calendar helper (`felix-admin-calendar` is a former gog owner; it now owns the Calendar capability through the helper, not gog). | calling calendar a "gog owner" in present tense |
| **The finding** | The recorded conclusion that OpenClaw's exec allowlist cannot hard-contain `gog` on the non-owner workers without breaking their real exec behavior. | — |

## Key Entities

- **`docs/design/felix-openclaw-boundary.md`** — the boundary design doc; receives the recorded finding and the §8 Step-3 → sandbox-follow-up pointer.
- **`docs/design/architecture/data/service-inventory.json`** (+ narrative counterpart) — the architecture inventory reconciled to live config; validated by the architecture-data validator.
- **The six agents** — `main` (the only current `gog` consumer + documented exception), `felix-admin-calendar` (former gog owner; now Calendar-via-helper, `gog`-free), and the workers `capture` / `tasker` / `escalation` / `habits` (none use `gog`).
- **The sandbox follow-up issue** — the deferred hard-containment path, filed in kentonium3/kg-automation and linked from #675 + boundary §8.

## Success Criteria

| ID | Description |
| --- | --- |
| SC-001 | The boundary doc records the finding (exec approvals = guardrails not isolation; the narrower knobs disposed of) with concrete evidence + the sandbox recommendation; a reader can act on it without re-probing office2. |
| SC-002 | `service-inventory.json` + narrative match live config for all six agents across **model, skills, per-agent purpose/notes/depends_on, exec posture, and gateway version (`2026.6.11`)**: zero fictional/drifted/stale-gog-path fields; the architecture-data validator passes and the NFR-005 semantic grep is clean. |
| SC-003 | `main` is documented as the tracked exception (only current gog consumer) in both the JSON inventory and the boundary doc; the boundary doc's whole-document gog-ownership sweep is complete (no stale present-tense "calendar owns gog"). |
| SC-004 | A sandbox hard-containment follow-up issue exists (requiring the 3 separately-proven properties + Step 4), and is linked from #675 and boundary §8. |
| SC-005 | `openclaw.json` is byte-unchanged; no rebaseline is required and no new audit drift is introduced. |
| SC-006 | The #675 tracker disposition is explicit (recommend close-as-rescoped, superseded by the sandbox issue) so the finding is not mistaken for hard-containment completion. |

## Assumptions

- Steps 1 (memory-core kill) and 2 (skill-scoping) remain deployed and stable; `gog` is visible only to `main` + `calendar`.
- The trajectory evidence (workers using inline eval / heredoc / redirection / curl / scratch scripts) reflects genuine agent behavior, not a one-off; combined with the documented allowlist-mode constraints it is sufficient to record the finding without a live apply-test. (A future sandbox mission owns the next empirical step.)
- Live office2 config is the source of truth for the reconcile; where the boundary doc or inventory disagrees with live config, live config wins.

## Out of Scope (explicit)

- Any `openclaw.json` / exec-policy / sandbox change — the sandbox path is *filed*, not built.
- Removing `gog` or broad exec from `main` — blocked by #680; main is a documented exception.
- Step 4 (`skills.allowBundled`) — separate follow-up.
- Re-litigating or altering Steps 1–2 (memory-core kill, skill-scoping).
- Any change to worker business logic, `habits-history`/Vikunja data paths, or agent prompts.

## Cross-References

- **#675** — this mission (Foundation-0 Step 3 resolution).
- **#673** — Bedrock Stabilization epic (F0 parent).
- **#677** — F3 no-silent-fallback doctrine.
- **#680** — email/drive controlled owner; keeps `main` a documented exception here.
- **#679** — calendar routing (closed). Note: #679/#699 *ended* calendar's gog use — calendar now owns the Calendar capability via the Felix helper, not gog.
- **`docs/design/felix-openclaw-boundary.md`** §6, §6.1, §8 — design source of record; receives the finding.
- **Bundled `~/.local/lib/node_modules/openclaw/docs/tools/exec-approvals-advanced.md`** (OpenClaw 2026.6.11) — the allowlist-mode constraints the finding cites.
