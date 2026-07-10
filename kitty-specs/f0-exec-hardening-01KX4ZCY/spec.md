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
| FR-001 | The **feasibility finding MUST be recorded** in `docs/design/felix-openclaw-boundary.md` (§8 Step 3 plus a dedicated finding subsection): that OpenClaw's per-agent exec **allowlist cannot hard-contain `gog`** on the four non-owner workers without breaking their real exec behavior. It MUST include (a) the per-agent exec-form evidence (inline eval, heredoc, redirection, curl, scratch scripts vs clean `python3 -m`), (b) the governing allowlist-mode constraints from the bundled `exec-approvals-advanced.md` (redirection unsupported; `$()`/backticks rejected; inline eval denied under `strictInlineEval`; `python3 -m` interpreter-binding uncertainty), and (c) the recommendation that **sandbox (`agents.defaults.sandbox.mode: non-main`)** is the correct hard-containment lever. | Pending |
| FR-002 | `docs/design/architecture/data/service-inventory.json` (and its narrative counterpart) MUST be reconciled to the **real deployed config** for all six agents: replace the fictional per-agent `skills` arrays with the actual Step-2-deployed sets, and record each agent's real exec posture (`security: full` fleet-wide today; `gog` scoped to `main` + `calendar`). | Pending |
| FR-003 | The **model drift MUST be corrected**: the inventory records felix-admin-habits and felix-admin-tasker as `sonnet`; live config runs them on `haiku`. Update the JSON and its narrative counterpart to `haiku`. | Pending |
| FR-004 | `main` MUST be **documented as the tracked Foundation-0 exception** — retaining `gog` + broad exec as the only path for email/drive until those capabilities get controlled owners (#680) — in both the boundary design doc and the architecture inventory. | Pending |
| FR-005 | A **follow-up issue MUST be filed** (kentonium3/kg-automation) for **sandbox-based hard containment** — the deferred Foundation-0 hard-boundary path — referencing this finding; and boundary-doc §8 MUST be updated so Step 3 points to that issue as the continuation. | Pending |
| FR-006 | This mission MUST make **no change to `openclaw.json`** or any office2 runtime config; the deployed Step 1–2 boundary is unchanged. The mission footprint is repo documentation plus one GitHub issue. | Pending |

## Non-Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| NFR-001 | **Validator-clean**: the reconciled `service-inventory.json` MUST pass `tooling/scripts/validate_architecture_data.py` (the blocking Docs-CI gate); the JSON is authoritative and the narrative view MUST agree with it. | Pending |
| NFR-002 | **Actionable finding**: the recorded finding MUST cite the OpenClaw version it was validated against (2026.6.11) and the specific bundled doc, and MUST include the concrete per-agent exec-form evidence, so a future sandbox mission can act without re-probing office2. | Pending |
| NFR-003 | **Falsifiable conclusion**: the finding MUST name the specific allowlist-mode mechanics that drive the "insufficient" conclusion (redirection unsupported, inline-eval denial, `-m` binding uncertainty), not merely assert infeasibility. | Pending |
| NFR-004 | **No runtime drift**: after the mission merges, the office2 daily security audit MUST NOT surface new `openclaw-config` drift attributable to this mission (because `openclaw.json` is untouched). | Pending |

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
| **Owner / non-owner** | `felix-admin-calendar` **owns** `gog`; the other four workers are **non-owners**. `main` is a separate documented exception. | — |
| **The finding** | The recorded conclusion that OpenClaw's exec allowlist cannot hard-contain `gog` on the non-owner workers without breaking their real exec behavior. | — |

## Key Entities

- **`docs/design/felix-openclaw-boundary.md`** — the boundary design doc; receives the recorded finding and the §8 Step-3 → sandbox-follow-up pointer.
- **`docs/design/architecture/data/service-inventory.json`** (+ narrative counterpart) — the architecture inventory reconciled to live config; validated by the architecture-data validator.
- **The six agents** — `main` (documented exception), `felix-admin-calendar` (gog owner), and the four non-owner workers `capture` / `tasker` / `escalation` / `habits`.
- **The sandbox follow-up issue** — the deferred hard-containment path, filed in kentonium3/kg-automation and linked from #675 + boundary §8.

## Success Criteria

| ID | Description |
| --- | --- |
| SC-001 | The boundary doc records the exec-allowlist-insufficiency finding with concrete evidence + the sandbox recommendation; a reader can act on it without re-probing office2. |
| SC-002 | `service-inventory.json` matches live config for all six agents (skills, model, exec posture): zero fictional or drifted fields; the architecture-data validator passes. |
| SC-003 | `main` is documented as the tracked exception in both the JSON inventory and the boundary doc. |
| SC-004 | A sandbox hard-containment follow-up issue exists and is linked from #675 and boundary §8. |
| SC-005 | `openclaw.json` is byte-unchanged; no rebaseline is required and no new audit drift is introduced. |

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
- **#679** — calendar routing (closed); establishes `calendar` as gog owner.
- **`docs/design/felix-openclaw-boundary.md`** §6, §6.1, §8 — design source of record; receives the finding.
- **Bundled `~/.local/lib/node_modules/openclaw/docs/tools/exec-approvals-advanced.md`** (OpenClaw 2026.6.11) — the allowlist-mode constraints the finding cites.
