# Research: Retire Vikunja felix-bot (single kent-token model)

Phase 0 decisions. Decision → Rationale → Alternatives.

## R1 — One central-default change, not per-site edits

- **Decision**: repoint `VikunjaClient.DEFAULT_TOKEN_PATH` (`scripts/common/vikunja_client.py:67`)
  to `…/vikunja-api-kent`; all 9 no-token consumers inherit it.
- **Rationale**: C-003 single source of truth; it *is* the "collapse to single-token." Nine
  identical per-site edits would be error-prone and re-introduce drift risk.
- **Alternatives**: pass the kent token at each call site — rejected (nine places to keep in sync).

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

## R6 — Rebaseline: likely NOT required (contradicts the issue body)

- **Decision**: treat rebaseline as **not required**, pending a concrete check at implement.
- **Rationale**: `audited-surfaces.json` patterns cover systemd units, openclaw prompts/config,
  python-deps, docker, ssh keys, and the deploy-pipeline (empty `affected_baselines`). Neither
  `scripts/common/**` nor `credential-manifest.json` matches — no hashed baseline drifts. The
  issue body's "audited surface" note likely conflates the office2 **secret file** with a hashed
  baseline; the secret file's *content* isn't changing (we repoint to an existing file).
- **Alternatives**: assume audited + rebaseline — rejected unless the implement-time check finds
  an actual matching pattern; the merge commit's `Rebaseline:` line records the verified outcome.

## R7 — Attended Tier-2 boundary

- **Decision**: HOLD for the operator before any live change — (1) confirm a Restic snapshot
  within 24h (trigger if not), (2) capture the *before* connectivity baseline of all 9 consumers,
  (3) operator present for the cutover, (4) verify projects 16–20 + all consumers post-cutover.
- **Rationale**: C-004 + the change touches Felix's live task-store auth; the operator flagged it
  attended. Planning artifacts are authored up to this boundary; nothing live happens before it.
