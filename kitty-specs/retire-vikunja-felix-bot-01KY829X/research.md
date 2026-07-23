# Research: Retire Vikunja felix-bot (single kent-token model)

Phase 0 decisions. Decision → Rationale → Alternatives.

## R1 — Consolidate onto the client first, THEN a one-line identity flip (revised, Codex HIGH)

- **Decision**: the mission is a **consolidation**, not a one-line pivot. ~6 runtime domains
  (sync, escalation, enrichment, habits, credential-health) talk to Vikunja with raw HTTP +
  hand-loaded tokens; migrate them all onto the shared `VikunjaClient` (extending it where it
  lacks an op), then flip the single `DEFAULT_TOKEN_PATH` to the kent token.
- **Rationale**: repointing the client default alone leaves the raw-HTTP consumers on felix-bot →
  a **split-brain** (some kent, some felix-bot) that is worse than today's consistent-but-partial
  view. Consolidation is also the Epic #531 boundary / EA-§11 task seam and fixes the design
  inconsistency directly.
- **Alternatives**: flip only the `VikunjaClient` consumers now, migrate the rest later — rejected
  (split-brain, prohibited by NFR-001). A one-line pivot — rejected (undercounts the real surface).

## R1b — Establish the seam, not a formal port (EA-§11 discipline)

- **Decision**: `VikunjaClient` is the seam; do **not** build an abstract `TaskService` port /
  adapter registry now.
- **Rationale**: §11 — "seam now, formal port when a second implementation justifies it; don't
  build elaborate abstractions around an unproven core." No second task backend exists;
  Todoist/Asana is explicitly deferred, and §11 says design the *channel* port first anyway.
- **Alternatives**: introduce a `TaskService` interface + Vikunja adapter now — rejected as
  premature generalization (C-004).

## R2 — Rollback-safe token retirement (operator decision, 2026-07-23)

- **Decision**: retire the felix-bot `vikunja-api` credential from the **manifest + runtime**,
  but leave the actual token **valid** in Vikunja and the felix-bot **user** dormant. Vikunja-side
  revocation + user deprovision are a later cleanup.
- **Rationale**: attended Tier-2 cutover — a valid felix-bot token means reverting the runtime
  commit fully restores prior behavior if a missed consumer surfaces. Attribution history on
  existing tasks is preserved by keeping the user.
- **Alternatives**: revoke now (tooling exists: `scripts/vikunja/revoke_kent_tokens.py`) —
  rejected for this mission (no fall-back); scheduled as the follow-on cleanup.

## R3 — Validator draws its token from the runtime default (FR-004)

- **Decision**: `validate_refs.py` / `vikunja_refs.py` obtain their token from the shared
  `VikunjaClient` default rather than a parallel `DEFAULT_KENT_TOKEN_FILE` constant.
- **Rationale**: the root cause was validator(kent) ≠ runtime(felix-bot). Sharing one default
  makes divergence structurally impossible — the validator always exercises the real runtime view.
- **Alternatives**: leave the parallel constant (both happen to be kent now) — rejected: it would
  silently re-diverge the next time either side's token changed.

## R4 — New record is ADR-0004, not ADR-0003

- **Decision**: write **ADR-0004** (dropped-attribution / single-token), superseding ADR-0002;
  stamp ADR-0002 `Superseded-by: 0004`.
- **Rationale**: `adr/0003-felix-vikunja-sync-architecture.md` already exists — the issue body's
  "ADR-0003" is stale. Next free number is 0004.
- **Alternatives**: none (numbering is factual).

## R5 — Deploy mechanism

- **Decision**: the code cutover lands by **felix-deployer self-pull** (runtime scripts are
  checkout-resident); `SKILL.md` lands via the **agent-skill-sync** pipeline. Add a
  `deploys/queued/<name>.yaml` manifest for auditability + a live-verify hook even though the
  code needs no imperative copy.
- **Rationale**: clients read the token file per-call, so no service restart is needed — the new
  default is live on the next consumer invocation after the pull. The manifest gives the Tier-2
  deploy a recorded, verifiable entry.
- **Alternatives**: pure self-pull with no manifest — workable but loses the auditable deploy
  record + the live-verify convention.

## R6 — Rebaseline NOT required; omit the deploy manifest (revised, Codex MED)

- **Decision**: **omit** a `deploys/queued/*.yaml` for this cutover; record `Rebaseline: not
  required — no audited surface matched`.
- **Rationale**: `scripts/**` and `credential-manifest.json` match no audited-surface pattern.
  Codex correction: a `deploys/queued/*.yaml` *does* match the deploy-pipeline surface
  (`rebaseline_required: true`, empty `affected_baselines`) → adding one would demand a
  deploy-pipeline rebaseline record. But the code is checkout-resident (self-pull) + SKILL.md via
  skill-sync — no imperative deploy action is needed — so we skip the manifest entirely and
  live-verify in the attended step. No manifest ⇒ no audited surface touched ⇒ rebaseline genuinely
  not required.
- **Alternatives**: add a manifest for auditability — rejected (pulls in the deploy-pipeline
  rebaseline for no functional gain; the attended verify covers the live-check).

## R7 — Attended Tier-2 boundary

- **Decision**: HOLD for the operator before any live change — (1) confirm a Restic snapshot
  within 24h (trigger if not), (2) capture the *before* connectivity baseline of all 9 consumers,
  (3) operator present for the cutover, (4) verify projects 16–20 + all consumers post-cutover.
- **Rationale**: C-004 + the change touches Felix's live task-store auth; the operator flagged it
  attended. Planning artifacts are authored up to this boundary; nothing live happens before it.
