---
title: ADR-0007 — Retire Vikunja felix-bot; single kent-token runtime identity
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-07-23'
version: v1.0
audience: agents_and_humans
tags: [860, 831, 750, 715, 717, 304]
---

# ADR-0007 — Retire Vikunja felix-bot; single kent-token runtime identity

**Status**: Accepted
**Date**: 2026-07-23
**Deciders**: Kent Gale
**Supersedes**: [ADR-0002](<./0002-felix-vikunja-task-model.md>) Q6 (the `felix-bot` write-attribution decision). ADR-0002 stays the historical record for the rest of the Felix ↔ Vikunja task model; only its identity-attribution rationale is superseded here.

## Context

[ADR-0002](<./0002-felix-vikunja-task-model.md>) Q6 provisioned a dedicated `felix-bot` Vikunja user so that agent-driven API writes would attribute to a distinct service-account identity, separate from Kent's UI identity (`kent`). At the time this was cheap: Vikunja objects were effectively shared once a project was shared R/W, and `[Felix]`-vs-`kent` in the comment trail plus `created_by: felix-bot` gave a clean human-vs-agent audit split.

Two later facts made that separation expensive rather than cheap:

- **Per-user object scoping (#715 / #717).** Vikunja scopes labels, saved filters, and (as later confirmed) label *attachment* **per user**. A label created by `felix-bot` is invisible in Kent's `kent` UI, and `felix-bot` cannot attach a `kent`-owned label to a task (HTTP 403). #715 was forced to reintroduce a second, kent-scoped token (`vikunja-api-kent`) purely so Felix could perform config/label work Kent must see — a "two-token model" that carried a standing per-user-scoping tax and a live 403 failure surface (#750).

- **Incomplete reads (#860).** Because Vikunja project visibility is also per-user, the `felix-bot` token was **blind to projects it was never shared into** (topic projects 16–20). The runtime ran under `felix-bot` while the #748 drift validator ran under `kent`; the two views silently diverged, and the runtime could not see tasks that were plainly present in Kent's own account. This was a structural blindness, not a bug in any one script.

The net effect: maintaining `felix-bot` as the runtime write identity bought a nominal audit distinction while actively costing correctness (blind reads) and reliability (403s), and it required a second token to paper over the config-write gap. The value proposition of ADR-0002 Q6 had inverted.

## Decision

**Retire the `felix-bot` Vikunja user and the `vikunja-api` token from the runtime path. Consolidate every runtime Felix→Vikunja consumer onto the `kent` token (`vikunja-api-kent`), which becomes the single runtime Vikunja identity.**

Concretely:

1. Runtime token resolution flows through a single seam (`get_vikunja_token_path()` in `scripts/common/vikunja_config.py`, mirroring the existing `get_vikunja_base_url()`), whose default resolves to `vikunja-api-kent`. Every runtime consumer — habits, escalation, enrichment, sync, credential-health writer, inbox scan/apply — authenticates as `kent` through that one point.
2. Runtime Vikunja writes and reads now attribute to the `kent` user. The agent-vs-human attribution distinction at the Vikunja API layer is **deliberately dropped**: it is not worth the per-user-scoping tax, the blind reads, or the second token.
3. The `felix-bot` **Vikunja user is left dormant, not deprovisioned.** Its historical `created_by: felix-bot` attribution on existing tasks/comments is preserved, and it still owns its private Inbox project (14). The `vikunja-api` secret file remains on office2 for that dormant user. Full deprovision (user deletion, Inbox(14) reassignment) is explicitly **out of scope** here — a later cleanup.
4. The `vikunja-api` credential is marked **retired / dormant (non-runtime)** in the credential manifest — not deleted. `vikunja-api-kent` becomes the sole **runtime** Vikunja credential.

This is the natural terminus of the two-token model: #715 had already conceded that config writes attribute to `kent`; #860 showed the read side must also be `kent`; so the last reason to keep `felix-bot` in the runtime path (task-write attribution) is dropped and the seam collapses to one identity.

## Consequences

### Positive

- **Correct reads by construction.** Runtime and the #748 validator now share the `kent` view, so the registry-vs-runtime divergence that hid #860 cannot recur. The runtime gains visibility into projects 16–20 + Inbox(1).
- **The 403 failure surface is gone.** Label attachment and config writes no longer 403 — there is no longer a felix-bot path that lacks permission on kent-owned objects. This **resolves #750**.
- **One token, one identity.** The per-user-scoping tax and the "which token does this consumer use?" ambiguity of the two-token model (#715) are removed. The single resolution point is the only place the runtime identity is declared.
- **Honest credential surface.** The credential manifest and identity model now describe what is actually true — a single runtime Vikunja identity — rather than a two-token split the code kept working around.

### Negative

- **No agent-vs-human attribution at the Vikunja API layer.** Runtime writes attribute to `kent`; a reader can no longer distinguish "Felix wrote this" from "Kent wrote this" via `created_by`. The `[Felix] …` comment-text convention (ADR-0002 Q3) remains the only in-Vikunja signal of agent authorship. This is the accepted cost of the decision — judged worthwhile given the correctness and reliability gains.
- **Dormant residue.** The `felix-bot` user, its Inbox(14), and the `vikunja-api` secret file persist as dormant artifacts until a later cleanup, so the system carries a retired-but-present credential for a while.

### Neutral

- **GitHub `kg-felix-bot` is unaffected.** The GitHub service-account identity (PRs, commits, issue actions) is a separate surface with its own tokens and is **out of scope** — it remains the agent identity on GitHub. Only the *Vikunja* `felix-bot` user is retired from the runtime path.
- **Existing `created_by: felix-bot` history is retained**, unrewritten — a cosmetic inconsistency in the historical record, consistent with ADR-0002's own "existing comments stay attributed to kent" stance.

## Alternatives Considered

### Share projects 16–20 into `felix-bot` instead of flipping to `kent`

Keep `felix-bot` as the runtime identity and simply share the missing topic projects into it. Rejected (Kent, #860): it keeps the two-token tax and the per-user-scoping fragility indefinitely, and every future project would have to be re-shared into `felix-bot` — the same class of blind-read bug would recur on the next unshared project.

### Content-swap the `vikunja-api` file to hold the kent token value

Leave the filename `vikunja-api` in place but put the `kent` token bytes in it. Rejected: it makes the credential surface lie — the file name and the identity it holds would disagree — which is exactly the kind of hidden divergence that produced #860. The seam is flipped honestly instead: the resolution default points at `vikunja-api-kent`.

### Keep the two-token model, just fix the reads

Keep `felix-bot` for writes and `kent` for config/reads. Rejected: #715 already conceded config to `kent` and #860 forces reads to `kent`; retaining `felix-bot` solely for write attribution preserves all the two-token machinery for a single, low-value distinction. Collapsing to one identity is simpler and removes the whole divergence surface.

## Things out of scope

- **Deprovisioning the `felix-bot` Vikunja user** and reassigning/retiring its Inbox project (14) — deferred to a later cleanup (spec C-002). The user is left dormant.
- **The GitHub `kg-felix-bot` identity** (PRs/commits/issues) — separate surface, unchanged (spec C-003).
- **Deleting the `vikunja-api` secret file** on office2 — retained for the dormant user; deletion at operator discretion later.

## References

- [ADR-0002 — Felix ↔ Vikunja task model](<./0002-felix-vikunja-task-model.md>) — superseded on its Q6 identity-attribution rationale; historical record for the rest of the task model.
- [ADR-0005 — Vikunja client standardization](<./0005-vikunja-client-standards.md>) — the shared `VikunjaClient` that now routes the single token seam.
- [`identity-model.md` §Agent Service Accounts](<../identity-model.md#agent-service-accounts>) — the reconciled single-token identity model.
- [`credentials-and-secrets.md`](<../credentials-and-secrets.md>) — the reconciled credential narrative.
- [`data/credential-manifest.json`](<../data/credential-manifest.json>) — `vikunja-api` (retired/dormant), `vikunja-api-kent` (sole runtime).
- kentonium3/kg-automation#860 — incomplete reads under felix-bot (the triggering issue); this ADR records its Phase-2 decision.
- kentonium3/kg-automation#750 — felix-bot 403 on kent-owned label attach (resolved by the flip).
- kentonium3/kg-automation#831 — doc/skill token reconciliation to the kent token.
- kentonium3/kg-automation#715 / #717 — the per-user-scoping two-token model this decision collapses.
- kentonium3/kg-automation#304 — the original ADR-0002 felix-bot rotation this supersedes.

## Decision changes

(Future amendments record here.)
</content>
</invoke>
