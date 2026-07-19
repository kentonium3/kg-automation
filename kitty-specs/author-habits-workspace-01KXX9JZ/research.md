# Research: Author felix-admin-habits workspace

Phase 0 research. This mission has no open technology choices — the approach is fixed by the #587 standard and the #584/#585 precedents. Research here resolves the mission-specific unknowns.

## Decision 1: Content ownership per file (the move-table source of truth)

- **Decision**: Apply the #587 concern→file ownership model. SOUL = voice/stance; USER = filtered person-view; TOOLS = environment/setup; AGENTS = operating rules/role; IDENTITY = identity card.
- **Rationale**: `docs/design/openclaw-workspace-authoring-standard.md` is the ratified contract (#587). The habits files violate it by cross-contamination even though the validator's four checks pass (the validator checks presence of enforceable privacy + Output Discipline, not full ownership hygiene).
- **Alternatives considered**: Leave as-is (rejected — the false "reporting" claim and inlined volatile IDs are live-staleness hazards; #582 exists to fix them). Fold in behavior improvements (rejected — this is a live daily agent; the spec scopes to behavior-preserving).

## Decision 2: #409 weekly-report conflict — resolved, not reopened

- **Decision**: Keep the single authoritative "weekly report — out of scope" statement in AGENTS (`## Weekly report — out of scope (moved to a deterministic timer)`); remove the duplicate from SOUL. Do not make an ownership decision.
- **Rationale**: #409 is already CLOSED (2026-07-19). Ownership settled on the deterministic `felix-habits-weekly` timer (`scripts.habits.weekly_report_driver`, #723); a dedicated LLM reporting agent was explicitly considered and declined (#796, #605 fabrication risk). Live audit confirms both AGENTS and SOUL currently carry a weekly-out-of-scope block — the SOUL copy is redundant and its presence is the residual "conflict surface." Removing it leaves one coherent statement.
- **Alternatives considered**: Reopen ownership (rejected — settled). Keep both copies (rejected — duplication is the #409 conflict class).

## Decision 3: De-inlining volatile Vikunja IDs is safe (behavior-preserving)

- **Decision**: Remove the `Habits` project `(id=13)` parenthetical and the `Habit task IDs: 14-20 (…)` line from TOOLS.md; instruct name-based resolution.
- **Rationale**: TOOLS.md is an LLM-context prompt file, not runtime config. Inlined numeric IDs are the exact staleness trap #587 bans (the #715/#717 Vikunja restructuring already churned IDs once).
- **Mechanism — CORRECTED per post-plan review (Finding 1)**: The earlier claim that the helpers "resolve by name at runtime" is **inaccurate**. The deterministic tick/reply helpers do **not** read `TOOLS.md` at all: `scripts/habits/morning_checkin_list.py` → `query_active_habits_v2` scopes by `HABITS_PROJECT_ID` sourced from `scripts/common/vikunja_refs.json` (`vikunja_scope`), and the active task universe comes from the sync cache (`/data/services/openclaw/state/sync/task-cache.json`) + `scripts/habits/migrations/phase3-schedule.yaml` + the persisted morning artifact — **not** a name lookup and **not** the TOOLS literals. Because neither the helpers nor the agent treat the TOOLS ids as authority, de-inlining them is behavior-preserving. What TOOLS should say instead: point to `vikunja_refs.json` as the canonical id source; reserve name-based `vikunja_api` resolution for the agent's ad-hoc habit-management path only.
- **Alternatives considered**: Keep the IDs (rejected — staleness trap). Move IDs to a config seam (unnecessary — the canonical seam `vikunja_refs.json` already exists, #748).

## Decision 4: Reuse existing verification tooling (no new deterministic helpers)

- **Decision**: Reuse `validate_workspace.py` for the invariant gate (habits-scoped `ok:true` assertion), a shell/py content-conservation check derived from the move-table, and before/after morning-list helper output for behavior preservation. No new helper/library/skill is introduced.
- **Rationale**: Per helper-script conventions and Directive 6, this mission introduces no new deterministic work — the deterministic surface already exists (#587 validator + the habits helpers). Adding tooling would be over-engineering.
- **Alternatives considered**: A new habits-specific conservation script (rejected — a one-off grep/diff checklist in quickstart suffices, matching #585).

## Decision 5: Deploy path and rebaseline

- **Decision**: Deploy via agent-prompt-sync on merge-to-main (no `deploys/queued/` manifest). Rebaseline "not required" — agent prompt files are not hashed by `audit.sh` (#621). No session rotation / gateway restart (habits is a per-dispatch sub-agent, not the main DM lane).
- **Rationale**: The #636 boundary: felix-deployer manifests are for crons/helpers/systemd/config; agent prompts sync via `deploy_agent_prompts.py`. The #584/#585 missions confirm this path and the #621 rebaseline-not-required outcome for prompt-only changes. Only the main agent's prompt change requires rotate+gateway-restart (#583 SOP); habits does not.
- **Alternatives considered**: Manifest-based deploy (rejected — wrong pipeline for agent prompts). Manual rebaseline (rejected — no hashed surface touched).
- **Open at plan time**: the habits agent's office2 deploy **directory** (slug ≠ deploy dir). Confirm via `find` / the office2 deploy-paths runbook before parity verification (FR-010).
