# Research: Author felix-admin-escalation workspace

Phase 0 output. All items resolved — no open `[NEEDS CLARIFICATION]` markers. This is a well-specified pure refactor with strong precedent (#584 capture, #583 main); research confirms the mechanism facts rather than exploring alternatives.

## D-1: Deploy path for agent prompt files (confirmed, not a manifest)

- **Decision**: Agent prompt files (SOUL/USER/TOOLS/AGENTS/IDENTITY) deploy to office2 via **agent-prompt-sync** on merge-to-`main` — NOT via a `deploys/queued/` manifest / felix-deployer.
- **Rationale**: `deploy_agent_prompts.py` (#567/#136/#636) is a systemd-timer pull pipeline that `git pull --ff-only origin main` every ~5 min and atomically copies the five workspace files to the agent's deploy dir. felix-deployer manifests are for crons/helpers/systemd/config (the #636 boundary). Confirmed live on #584 and #583.
- **Alternatives considered**: a `deploys/queued/` manifest — rejected; it is the wrong pipeline for prompt files and would author a no-op manifest.
- **Consequence for this mission**: no manifest is authored; merge-to-main IS the deploy trigger. Deploy destination is `/data/services/openclaw/data/` (the #583-confirmed agent-prompt-sync dest).

## D-2: Rebaseline obligation (expected "not required")

- **Decision**: Record rebaseline as **"not required"** on the merge commit.
- **Rationale**: `audit.sh` hashes only `openclaw.json`, never the agent AGENTS.md / workspace prompt files (#621 gap — agent prompts are an unmonitored audited surface). Editing SOUL/USER/TOOLS changes no hashed baseline. `setup_vikunja.py` is not an audited surface either.
- **Alternatives considered**: manual rebaseline — unnecessary; nothing hashed changes.
- **Consequence**: merge commit records `Rebaseline: not required — #621 (agent prompt files not hashed by audit.sh)`.

## D-3: Invariant preservation under SOUL reduction (the load-bearing risk)

- **Decision**: When reducing SOUL's `## Privacy boundary` to a one-line stance, the enforceable rule (path + "never access") MUST remain intact in **both** AGENTS.md (`## Privacy boundary`) and TOOLS.md (`## Privacy`) — which it already is. SOUL is not the enforceable home.
- **Rationale**: `validate_workspace.py` Invariant A checks for the enforceable privacy rule in the enforceable home (AGENTS/TOOLS). It currently reports `present in AGENTS.md, TOOLS.md` for escalation — so removing the rule from SOUL does not affect the invariant. Verified at design time: escalation `ok: true`.
- **Alternatives considered**: leaving the full rule in SOUL — rejected; that is exactly the ownership contamination this mission removes (OpenClaw/#587: no security policy in SOUL).
- **Consequence**: FR-003 explicitly requires the AGENTS/TOOLS enforceable copies stay present; NFR-001 gates it.

## D-4: ADD-reference handling (two precedents, consistent)

- **Decision**: Trim the "Kent has ADD and processes best…" *justification* off SOUL's "Structured and chunked" bullet (keep the style rule), and **keep** "ADD (managed)" as a neutral person-fact in USER notes.
- **Rationale**: #584 capture removed the ADD *justification* from SOUL (ADD framing biases the writing) while keeping the pure style rule; #583 main kept "ADD (managed)" in USER as a neutral biographical fact. The two are consistent: SOUL should carry style, not the medical rationale; USER may carry the neutral fact.
- **Alternatives considered**: remove ADD everywhere (would diverge from #583 USER) or keep the SOUL justification (would diverge from #584 SOUL) — both rejected for fleet inconsistency.

## D-5: #724 Goals(11) — harmless no-op today, cleaned for drift-prevention

- **Decision**: Remove `11` from TOOLS.md's `project_id NOT IN (11, 13)` (→ `NOT IN (13)`) and drop the `11 | Goals` exclusion row; remove the dormant `setup_vikunja.py` "Goals" saved-filter block (`project = 11 && done = false`).
- **Rationale**: #717 deleted the Goals project (11). Excluding a non-existent project id matches nothing (harmless), and the dormant setup script is not run in production — so this is drift-prevention, not a live bug. Habits(13) exclusion is unrelated and stays.
- **Consequence**: the runtime candidate set is unchanged (the two former Goals tasks already moved to Intentional LLC(9) in #717 and are intentionally escalation-visible) — reinforcing the zero-behavior-change property (NFR-004).

## D-6: `_private` privacy-path representation — out of scope (deferred to #732)

- **Decision**: Leave escalation's TOOLS.md `_private` path line byte-unchanged.
- **Rationale**: the `/home/kgale/…` vs `~/…` split is a 4-agent fleet inconsistency requiring investigation of the vault's physical location on office2 relative to the `claude` runtime. Fixing only escalation would deepen the split. Filed as #732 (Kent's scope call).
- **Consequence**: C-005; the enforceable path stays present so Invariant A is unaffected.

## D-7: Scope discipline — AGENTS.md untouched, no size tightening

- **Decision**: Do not edit escalation's AGENTS.md or IDENTITY.md; do not tighten the 15KB AGENTS.md.
- **Rationale**: AGENTS already owns the role/authority (`## Authority`/`## Scope`) so no move requires editing it; no hard size-cap test applies to escalation (`test_agents_md_size.py` caps only `main` and `felix-admin-calendar`). Operator scope call: pure refactor, leave AGENTS size (its verbose Output-discipline prose encodes hard-won anti-incident history). IDENTITY is already authored.
- **Consequence**: FR-008; NFR-002 scope discipline gate.
