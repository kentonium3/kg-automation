# Implementation Plan: Retire Vikunja felix-bot (single kent-token model)

**Branch**: `fix/860-retire-vikunja-felix-bot` | **Date**: 2026-07-23 | **Spec**: [spec.md](./spec.md)
**Input**: `kitty-specs/retire-vikunja-felix-bot-01KY829X/spec.md` | **Source issue**: kentonium3/kg-automation#860 (Epic #531)

## Summary

Drop the Vikunja two-token model. The pivot is a **single central-default change** —
`VikunjaClient.DEFAULT_TOKEN_PATH` in `scripts/common/vikunja_client.py:67` moves from
`/data/services/openclaw/secrets/vikunja-api` (felix-bot) to `…/vikunja-api-kent` — which
flips all 9 no-token consumers at once and *is* the collapse to one token. Around that:
remove the now-moot felix-bot fail-soft branches; make the #748 validator draw its token
from the same default as the runtime (so it can never again validate a view the runtime
doesn't use); write ADR-0004 + reconcile the identity/credentials docs and SKILL.md;
retire the `vikunja-api` credential from the manifest (kent token left as the sole one);
deploy + verify. The felix-bot token stays **valid** in Vikunja (rollback-safe) and the
felix-bot user stays dormant.

## Technical Context

**Language/Version**: Python 3 (office2 python3-only). Docs are Markdown + JSON.
**Primary Dependencies**: the shared `scripts/common/vikunja_client.py` (single default);
the #748 seam (`scripts/common/vikunja_refs.py` / `vikunja_refs.json`, validator
`scripts/vikunja/validate_refs.py`).
**Storage**: office2 secret files `/data/services/openclaw/secrets/{vikunja-api,vikunja-api-kent}`.
**Testing**: existing Vikunja unit/seam tests must stay green; add/adjust for the single-token
default and the removed 403 branch; live before/after connectivity check at deploy.
**Target Platform**: office2. Runtime scripts are **checkout-resident** (`/home/claude/kg-automation`,
self-pulled by felix-deployer) — the code cutover lands via `git pull`, not a file copy.
**Project Type**: single (scripts + docs + architecture data).
**Performance Goals**: n/a (auth-path change).
**Constraints**: Tier-1/2 (C-004) — Restic snapshot + before/after connectivity verification;
single source of truth for the token default (C-003); GitHub identity untouched (C-001).
**Scale/Scope**: 9 runtime consumers; ~1 code default + validator + 4 docs + 1 manifest.

### Environment probe results (DIR-015 — verified live on office2, 2026-07-23)

- Both secret files present + **non-empty**: `vikunja-api` (felix-bot, `claude:claude`) and
  `vikunja-api-kent` (`claude:felix`), each `0600`, 44 bytes. → the central-default repoint
  to `vikunja-api-kent` is viable.
- The #748 validator **already** reads the kent token (`DEFAULT_KENT_TOKEN_FILE = …/vikunja-api-kent`);
  the runtime read the **felix-bot** token — that divergence is the bug. Post-cutover both
  sides are kent, so they converge; the hardening (FR-004) is to make the validator draw the
  token from the *same* `VikunjaClient` default rather than a parallel constant.
- **ADR numbering correction**: `adr/0003-felix-vikunja-sync-architecture.md` already exists.
  The new dropped-attribution record must be **ADR-0004** (the issue body's "ADR-0003" is stale).
- `credential-manifest.json` holds `vikunja-api` (felix-bot) + `vikunja-api-kent` (kent) +
  `vikunja-admin` (UI u/p, stays) + the two `kg-felix-bot-*` GitHub PATs (out of scope, C-001).

### Deploy & rebaseline analysis (to confirm at implement)

- **Code cutover** = checkout-resident: merge → felix-deployer self-pull makes the new default
  live; consumers read the kent token file on next invocation (no service restart — clients
  read the token per-call). **SKILL.md** deploys via the agent-skill-sync pipeline.
- **Rebaseline**: per `audited-surfaces.json`, neither `scripts/common/**` nor
  `credential-manifest.json` matches an audited-surface pattern; a `deploys/queued/*.yaml`
  touch matches the deploy-pipeline surface with empty `affected_baselines`. **Working
  assumption: rebaseline not required** — this contradicts the issue body's "audited surface"
  note, which is flagged for verification (the body may be conflating the office2 secret file
  with a hashed baseline). Confirm before the merge commit's Rebaseline line.
- Whether a `deploys/queued/<name>.yaml` manifest is *needed* (vs. pure self-pull) hinges on
  whether any imperative action is required (agent restart / SKILL.md sync). Decide at plan
  close; default to a manifest for auditability + the live-verify hook.

## Charter Check

*GATE: passed (compact charter; no blocking directives).*

- **DIR-006 (deterministic)**: the cutover is a deterministic config change → no agent judgment. ✅
- **DIR-014 (doc-sync)**: FR-003/FR-005/FR-006 update SKILL.md, ADR-0004, identity-model,
  credentials-and-secrets, credential-manifest.json. ✅
- **DIR-015 (probe)**: office2 probe done above. ✅
- **Engineering principle — single source of truth**: C-003 keeps the token default in one place. ✅
- **Tier-1/2 discipline (C-004)**: Restic snapshot + before/after connectivity verification is
  an explicit HOLD point for the operator (attended). ✅

## Project Structure

```
scripts/common/vikunja_client.py         # MODIFIED — DEFAULT_TOKEN_PATH → vikunja-api-kent (the pivot)
scripts/common/vikunja_refs.py           # MODIFIED — validator token source = the runtime default
scripts/vikunja/validate_refs.py         # MODIFIED — collapse to single token; exercise runtime view
scripts/inbox/route_someday.py           # MODIFIED — remove the felix-bot 403 fail-soft branch (#750)
scripts/**                               # AUDIT — grep VikunjaClient() no-token; any explicit felix-bot plumbing
docs/design/architecture/adr/0004-*.md   # NEW — supersedes ADR-0002 (dropped attribution)
docs/design/architecture/adr/0002-felix-vikunja-task-model.md  # MODIFIED — Superseded-by: 0004
docs/design/architecture/identity-model.md            # MODIFIED — single-token model
docs/design/architecture/credentials-and-secrets.md   # MODIFIED — kent sole runtime token
docs/design/architecture/data/credential-manifest.json# MODIFIED — retire vikunja-api entry (kent sole)
scripts/openclaw/skills/vikunja-api/SKILL.md          # MODIFIED — kent token + v2.4.0 header + health-check (#831)
deploys/queued/retire-vikunja-felix-bot.yaml          # NEW (if imperative deploy needed) — Tier-2, live-verify
```

**Structure Decision**: Single-project. The pivot is one line in the shared client; the rest is
consumer cleanup + the validator-convergence hardening + documentation + manifest.

## Implementation Concern Map

### IC-01 — Runtime cutover (the pivot + consumer cleanup)

- **Purpose**: make every runtime `VikunjaClient()` use the kent token and delete the moot
  felix-bot fail-soft paths.
- **Relevant requirements**: FR-001, FR-002; NFR-003; C-003.
- **Affected surfaces**: `scripts/common/vikunja_client.py` (`DEFAULT_TOKEN_PATH`); remove any
  explicit felix-bot two-token plumbing; `scripts/inbox/route_someday.py` (drop the 403
  fail-soft branch + attach unconditionally); re-grep all 9 consumers to confirm coverage.
- **Sequencing/depends-on**: none.
- **Risks**: a consumer that *intended* felix-bot attribution for writes now writes as kent —
  acceptable per the decision (attribution dropped); confirm no consumer relies on felix-bot
  ownership semantics beyond attribution.

### IC-02 — Validator / registry single-token convergence (FR-004)

- **Purpose**: guarantee the #748 validator can never again validate a view the runtime doesn't use.
- **Relevant requirements**: FR-004; SC-003.
- **Affected surfaces**: `scripts/vikunja/validate_refs.py`, `scripts/common/vikunja_refs.py` —
  draw the token from the shared `VikunjaClient` default (not a parallel `DEFAULT_KENT_TOKEN_FILE`
  constant); drop the two-token vocabulary from the registry/validator.
- **Sequencing/depends-on**: IC-01 (shares the default).
- **Risks**: keep the validator's negative check meaningful (it must still fail on a real
  registry↔runtime divergence).

### IC-03 — Docs / ADR reconciliation (FR-003, FR-005)

- **Purpose**: record the decision and remove two-token references so the docs match reality.
- **Relevant requirements**: FR-003, FR-005; DIR-014.
- **Affected surfaces**: NEW `adr/0004-…md` (supersede ADR-0002; mark 0002 Superseded-by 0004);
  `identity-model.md`; `credentials-and-secrets.md`; `SKILL.md` (kent token guidance + stale
  `v0.24.6`→`v2.4.0` header + health-check example → #831).
- **Sequencing/depends-on**: none (parallel to IC-01/02).
- **Risks**: catch *every* two-token reference (grep `felix-bot`, `vikunja-api\b`, `two-token`).

### IC-04 — Credential manifest retire + deploy + attended verification (FR-006, FR-007, FR-008)

- **Purpose**: retire the felix-bot credential (kent sole), ship, and verify — with the operator
  present for the live cutover.
- **Relevant requirements**: FR-006, FR-007, FR-008; NFR-001, NFR-002; C-004.
- **Affected surfaces**: `credential-manifest.json` (retire the `vikunja-api` entry; note the
  token is left valid in Vikunja + user dormant per FR-007); `deploys/queued/…yaml` if an
  imperative deploy is needed; the security-baseline rebaseline line (per the analysis above).
- **Sequencing/depends-on**: IC-01–03.
- **⛔ ATTENDED HOLD (Tier-2)**: before any live change — confirm a recent Restic snapshot
  (trigger if none in 24h) and capture the **before** connectivity baseline of all 9 consumers;
  then the operator is present for the merge/self-pull cutover; then verify projects 16–20 return
  + all consumers green (SC-002/NFR-001/NFR-003) before closing #860/#831.
- **Risks**: the cutover is the one irreversible-feeling step — mitigated by leaving the felix-bot
  token valid (revert the commit → prior behavior restored).
