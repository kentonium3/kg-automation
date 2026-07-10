# Felix Foundation-0 Exec-Hardening

## Purpose

Complete **Step 3** of the Foundation-0 OpenClaw capability-boundary rollout (#675,
Bedrock epic #673). Steps 1 (memory-core kill) and 2 (skill-scoping) are deployed:
`gog` is scoped out of all five worker agents' *skills* lists and now survives only on
`main` (email/drive) and `felix-admin-calendar` (its sole owner). But skill-scoping is a
**soft** boundary — an exec-capable agent can still run the `gog` *binary* directly.

This mission adds the **hard** boundary: per-agent `tools.exec.security` so the four
non-owner worker agents (capture, tasker, escalation, habits) *technically cannot* invoke
`gog`, while every worker's real cron/on-demand job still runs. It is **feasibility-first**
— the leaky-allowlist caveats in boundary-doc §6.1 (a broad `python3` allowlist is itself
an escape hatch; the `python3 -m <module>` form binds awkwardly to OpenClaw's single-file
operand model; allowlist mode rejects `$()`/backticks/redirection and requires every
`cd … && python3 -m …` segment allowlisted) must be resolved before any deploy. It also
reconciles the architecture docs to the real deployed config, and formally documents
`main` as the tracked Foundation-0 exception until email/drive get controlled owners (#680).

## User Scenarios & Testing

### Primary scenario — a contained worker cannot reach gog, but its real job still runs

felix-admin-habits fires its daily cron. It runs its real helper (`python3 -m
scripts.habits.*`) and completes normally — the exec allowlist permits exactly the
commands it needs. Separately, an operator (or a fault-injection probe) makes that same
agent attempt `gog calendar list`. The OpenClaw exec policy **denies** the call: the
agent has no path to the gog binary. Containment is proven by an actual denied invocation,
not by the mere absence of a skill.

### Primary scenario — the gog owner is unaffected

felix-admin-calendar receives a `create_calendar_event` envelope and runs `gog calendar
create …`. Its exec configuration still permits gog (it is the sole owner). The event is
created. No worker except calendar can do this.

### Exception — feasibility comes back negative

The feasibility spike finds that OpenClaw's allowlist cannot express "permit `python3 -m
scripts.habits.foo` but deny arbitrary `python3`" without leaving an escape hatch that
also permits `gog`. Per operator decision, the mission **STOPS and surfaces** the finding
(recorded verbatim) and the partial-containment-vs-defer-sandbox decision to Kent **before
deploying anything**. It does not autonomously ship a leaky allowlist.

### Exception — a worker's real job breaks after apply

Behavioral verification after apply shows escalation's on-demand job now fails because a
helper command was missing from its allowlist. The change is reverted from the timestamped
`.bak` (each step independently reversible), the allowlist is corrected, and the
apply→verify loop repeats. No worker is left with a capability it needs silently removed.

### Edge — calendar's own containment posture

calendar retains gog, but that does not mean unrestricted exec forever; whether calendar
runs `exec.security: full` or an allowlist that *includes* gog is resolved by the
feasibility spike and recorded. Either way, calendar's real calendar path must keep working.

## Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| FR-001 | A **feasibility finding MUST be produced and recorded before any deploy**: either (a) the exact per-agent exec allowlist that blocks `gog` while permitting each worker's real helper commands, resolving the §6.1 caveats; or (b) an explicit, honest finding that clean hard-containment is not achievable with the allowlist alone. On a **negative** finding the mission MUST STOP and surface the finding plus the partial-containment-vs-defer decision to the operator — it MUST NOT autonomously deploy a leaky/partial allowlist. | Pending |
| FR-002 | After the change deploys, each of the four **non-owner** worker agents (felix-admin-capture, felix-admin-tasker, felix-admin-escalation, felix-admin-habits) MUST be unable to execute `gog`; a real invocation attempt MUST be **denied by the exec policy** (positive proof of containment). | Pending |
| FR-003 | felix-admin-calendar MUST **retain** the ability to execute `gog` (its owned capability) so its real calendar-create/update path continues to function. The chosen mechanism (exec `full` vs allowlist-including-gog) MUST be recorded. | Pending |
| FR-004 | After the change deploys, **each of the five worker agents' real cron/on-demand job MUST run successfully** — behavioral verification against the agent's actual job, not merely config validation. | Pending |
| FR-005 | A **deterministic verification helper** MUST exist that, per agent, reports the effective `tools.exec` security mode and whether `gog` is permitted or denied, emitting diffable human-readable and `--json` output — the exec-policy analogue of the existing `scripts/openclaw/agents/skills_snapshot.py` skills oracle. | Pending |
| FR-006 | `docs/design/architecture/data/service-inventory.json` (and its narrative counterpart) MUST be reconciled to the **real deployed config** for all six agents: remove the fictional per-agent `skills` arrays that do not exist in live config, and record each agent's real exec-security posture. | Pending |
| FR-007 | The **model drift MUST be corrected**: service-inventory records felix-admin-habits and felix-admin-tasker as `sonnet`; live config runs them on `haiku`. Update the inventory and its narrative counterpart to `haiku`. | Pending |
| FR-008 | `main` MUST be **documented as the tracked Foundation-0 exception** — it retains `gog` + broad exec as the only path for email/drive until those capabilities get controlled owners (#680) — in both the boundary design doc and the architecture inventory. | Pending |
| FR-009 | The boundary design doc (`docs/design/felix-openclaw-boundary.md`, §8 Step 3) MUST be updated to record the exec-hardening outcome: the feasibility finding, the final per-agent allowlists actually deployed, and deployment status. | Pending |

## Non-Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| NFR-001 | **Reversibility**: before each apply, a timestamped `.bak` of `openclaw.json` MUST be captured on office2 (per the Step 1/2 precedent), and each step MUST be independently revertible from that backup. | Pending |
| NFR-002 | **Positive containment proof**: FR-002 MUST be demonstrated by an actual denied `gog` invocation for a contained agent, not by the absence of a config key. The verification helper's report is the durable evidence. | Pending |
| NFR-003 | **Verification-helper hygiene**: the helper MUST be self-contained and runnable over stdin (`ssh office2-claude 'python3 - --json' < <helper>`) regardless of office2 repo-sync state, and MUST NOT be counted in the coverage-gate source set (mirrors `skills_snapshot.py`). | Pending |
| NFR-004 | **No silent capability loss**: behavioral verification (FR-004) MUST cover every one of the five workers' real jobs; a change that removes a needed command MUST be caught and corrected before the mission proceeds. | Pending |
| NFR-005 | **Parser robustness**: because the verification helper depends on `openclaw exec-policy`/config output format, its parser MUST fail loudly (not silently pass) if the expected sections are absent, and MUST note the OpenClaw version it was validated against. | Pending |

## Constraints

| ID | Description | Status |
| --- | --- | --- |
| C-001 | `openclaw.json` is the one **monitored Tier-2 audited surface**. The rollout MUST follow apply → behavioral-verify → rebaseline, one reversible step at a time (boundary-doc §8). | Active |
| C-002 | Config changes MUST be applied via the canonical `openclaw config patch --stdin --dry-run` (validate) → apply path, built **programmatically from live config** to preserve every field. Hand-editing `openclaw.json` is prohibited. | Active |
| C-003 | Config key/semantics MUST be verified against the **version-matched bundled docs** (`~/.local/lib/node_modules/openclaw/docs/` on office2), not `docs.openclaw.ai`. | Active |
| C-004 | **`main` is OUT of scope** for any `gog`/exec removal. main remains the only path for email (`gog gmail`) and drive (`gog drive`) until #680 homes those capabilities. Touching main's exec/skills is prohibited in this mission. | Active |
| C-005 | **Step 4 (`skills.allowBundled` global default-deny) and Step 5 (sandbox) are OUT of scope**, deferred to follow-up issues per operator decision. | Active |
| C-006 | Per Tier-2 change control, a **Restic snapshot within 24h** MUST exist (or be triggered) before the `openclaw.json` change is applied. | Active |
| C-007 | The `openclaw.json` change is an **out-of-band office2 config edit**, not a `deploys/queued/` manifest deploy — felix-deployer pulls repo code and cannot patch live `openclaw.json`. Therefore the rebaseline is the **out-of-band manual** procedure (`rm baselines/* && audit.sh` after confirming the read-only audit shows only the expected `openclaw-config` drift). Repo-side deliverables (verification helper, doc reconcile) merge normally. | Active |
| C-008 | Per Felix Constitution Directive 6, all mechanically-verifiable checks (exec-mode read, gog permit/deny) live in the deterministic helper; the agent only orchestrates apply/verify/rebaseline and surfaces findings. | Active |

## Domain Language

| Term | Meaning | Avoid |
| --- | --- | --- |
| **Worker agent** | One of the five non-`main` Felix agents: capture, tasker, escalation, habits, calendar. | "sub-agent" |
| **Owner / non-owner** | calendar is the **owner** of `gog`; the other four workers are **non-owners** and must be hard-contained. | — |
| **Soft boundary** | Skill-scoping (Step 2): removes the gog *instruction pack* from an agent's `skills` list; the binary is still runnable via exec. | — |
| **Hard boundary / hard containment** | Exec-hardening (this mission): per-agent `tools.exec.security` makes the `gog` binary technically unreachable. | — |
| **Out-of-band** | A change applied directly on office2 (here, `openclaw config patch`), invisible to felix-deployer, requiring manual rebaseline. | "manifest deploy" |

## Key Entities

- **`openclaw.json`** — the live six-agent OpenClaw config on office2; the single monitored Tier-2 audited surface. Not in the repo.
- **The six agents** — `main` (documented exception), `felix-admin-calendar` (gog owner), and the four contained workers `felix-admin-capture` / `felix-admin-tasker` / `felix-admin-escalation` / `felix-admin-habits`.
- **Exec policy** — per-agent `tools.exec.security` (`full` | `allowlist` | `deny`) + the host approvals allowlist of permitted commands.
- **Verification helpers** — the existing `scripts/openclaw/agents/skills_snapshot.py` (skills oracle) and the new exec-policy oracle this mission adds.
- **security-monitor baselines** — office2 audit baselines (`/data/services/security-monitor/baselines/`) reset out-of-band after the change.

## Success Criteria

| ID | Description |
| --- | --- |
| SC-001 | Four of the five worker agents (capture, tasker, escalation, habits) cannot execute `gog` — proven by an actual denied invocation; the fifth (calendar) still can. |
| SC-002 | All five workers' real jobs run successfully after the change — zero regressions attributable to exec-hardening. |
| SC-003 | The architecture inventory matches live config for all six agents (skills, model, exec posture): zero fictional or drifted fields remain. |
| SC-004 | The change is fully reversible: a documented revert path plus a timestamped `.bak` exist, and reverting restores the prior working state. |
| SC-005 | The feasibility finding is recorded; if negative, no deploy occurred and the decision was surfaced to the operator. |

## Assumptions

- Steps 1 (memory-core kill) and 2 (skill-scoping) remain deployed and stable; `gog` is already absent from the four non-owner workers' *skills* lists.
- OpenClaw 2026.6.11's per-agent `tools.exec` semantics behave as described in the version-matched bundled reference docs.
- felix-admin-calendar remains gog's sole owner; capture reaches the calendar via the deterministic helper path established when #679 closed.
- The four non-owner workers invoke only their own `python3 -m scripts.<domain>.*` helpers (plus delegation/`gh` where applicable) via exec — enumerable from their live `AGENTS.md`/`TOOLS.md` and trajectory evidence.

## Out of Scope (explicit)

- Removing `gog` or broad exec from `main` — blocked by #680 (email/drive owner); main is a documented exception.
- Step 4 (`skills.allowBundled`) and Step 5 (sandbox) — deferred to follow-up issues.
- Any email/drive owner work (#680, #681 Mail phase) or re-litigating skill-scoping (Step 2, done).
- Changing any `habits-history`/Vikunja data path or agent business logic — this mission only touches exec policy + docs.

## Cross-References

- **#675** — this mission (Foundation-0 Step 3, exec-hardening).
- **#673** — Bedrock Stabilization epic (F0 parent).
- **#677** — F3 no-silent-fallback doctrine (the invariant hard-containment makes real).
- **#680** — email/drive controlled owner; the blocker to releasing `main`'s gog (keeps main in scope-out here).
- **#679** — calendar routing (closed); establishes calendar as gog owner + the deterministic capture→calendar path.
- **`docs/design/felix-openclaw-boundary.md`** §6, §6.1, §8 Step 3 — design source of record.
