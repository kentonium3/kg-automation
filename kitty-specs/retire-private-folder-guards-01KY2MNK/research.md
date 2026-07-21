# Research: Retire _private folder guard apparatus

Phase 0 — decisions that resolve the plan's open questions. Format: Decision / Rationale /
Alternatives considered.

## D1 — Remove `validate_privacy_boundary.py` entirely (not repurpose)

- **Decision**: Delete the lint validator and all wiring rather than generalize it.
- **Rationale**: It is a *stale-path* linter — it flags active surfaces that still cite the
  pre-#152 path `02-Growth/_private` as the current rule. Once the whole `04-Growth/_private`
  boundary is gone, there is no "current boundary path" to keep un-stale; the tool guards nothing.
- **Alternatives**: (a) Repurpose it into a general "no raw vault paths in active surfaces" lint —
  rejected: that is a different tool with different scope, and leak prevention is already covered by
  the redaction tests (IC-07). (b) Keep it dormant — rejected: dead CI/pre-commit steps mislead.

## D2 — Remove `validate_workspace` Invariants A + D (not generalize)

- **Decision**: Excise `check_privacy_boundary` (Inv A) + `check_privacy_path_canonical` (Inv D) +
  their exclusive constants (`PRIVACY_TOKEN`, `CANONICAL_PRIVATE_PATH`, `NONCANONICAL_PRIVATE_TOKEN`)
  + owner-set config; delete `test_privacy_pointer.py`; trim the invariant tests.
- **Rationale**: These invariants force a `_private` red-line into every agent prompt. With no
  red-line to enforce, they have no subject. The *other* invariants (output-discipline, staleness,
  byte budgets) are untouched.
- **Alternatives**: Generalize Inv A to "prompt must state the repo boundary" — rejected: the
  second-brain-repo boundary lives in CLAUDE.md + the constitution, not per agent prompt; pushing it
  into prompts is exactly the old "agent reads the rule & complies" model the architecture is moving
  away from (containment/detection over prompt-embedded rules).

## D3 — Generalize the two hygiene guards to "arbitrary vault path" (not minimal-decouple, not delete)

- **Decision**: Keep the alert-output redaction (`hard_fail`) and the refuse-write guard
  (`mark_processed` C-001), decoupled from the specific `_private` folder and expressed as a general
  vault-path rule.
- **Rationale**: Both prevent real problems independent of `_private`: leaking a vault path into a
  surfaced alert, and marking-processed a file outside the allowed inbox area. Banked direction:
  "refuse-write-to-arbitrary-vault-path" / "path-redaction-from-error-messages".
- **Alternatives**: (a) Delete them — rejected: real protection lost. (b) Keep the `_private`
  literal — rejected: couples a live guard to a folder that no longer exists.

## D4 — Reframe the #692/#696 graph-ingest gate to "verify not present" (Kent, discovery)

- **Decision**: In `second-brain-graph-layer.md` + `executive-assistant-architecture.md`, replace
  the "never ingest `_private`" *enforcement gate* with a "verify the private content is not
  present" *verification*, grounded in physical exclusion.
- **Rationale**: Physical exclusion means the private content never reaches office2, so the ingest
  gate is no longer an in-repo rule to enforce — it is a check that the excluded content is, in
  fact, absent from what gets ingested. The runtime check is implemented when the ingest pipeline is
  built (#696); this mission reframes the *model*.
- **Alternatives**: Leave the design docs stating "never ingest `_private`" — rejected (Kent chose
  full reframe): it implies the content could be present and mis-describes the resolved model.

## D5 — Deploy via agent-prompt-sync; rebaseline expected not-required (confirm live)

- **Decision**: Ship prompt edits through the existing agent-prompt-sync pull path (no new
  `deploys/queued/*.yaml`). Treat rebaseline as **not-required**, but confirm against a live
  `audit.sh` run before recording it.
- **Rationale**: `audit.sh` content-hashes `openclaw.json`, not prompt files (#621), so a pure
  prompt-text edit drifts no hashed baseline. Verifying live (not assuming) is required by C-003 and
  the rebaseline obligation.
- **Alternatives**: A dedicated deploy manifest — rejected: prompt sync is the established path; a
  manifest adds ceremony with no baseline to stamp.

## D6 — Ordering safety is already satisfied; re-verify at acceptance

- **Decision**: The `_private` folder is confirmed absent from office2's vault
  (`/home/kgale/second-brain/notes/04-Growth/`, verified 2026-07-21). Re-verify absence at IC-08
  before/at deploy as a belt-and-suspenders acceptance step.
- **Rationale**: The invariant is "no guard removed while data present" (NFR-002). Deletion already
  synced; a final re-check costs nothing and closes the window definitively.
- **Alternatives**: Trust the prior check only — acceptable but the re-check is cheap insurance.

## Open items

None. All Technical-Context unknowns are resolved; no `[NEEDS CLARIFICATION]` markers remain.
