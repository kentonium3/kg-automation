# Research: Constitution Risk-Tier Autonomy Guard

## Decision 1: Place the amendment inside Directive 2

**Decision**: Add the risk-tier/autonomy clarification directly under the
Directive 2 autonomy level definitions, before promotion and demotion rules.

**Rationale**: Directive 2 is where a cold-start reader learns what Assisted,
Observed, and Autonomous mean. Placing the clarification there prevents the
reader from inferring that Autonomous grants production-mutation authority.

**Alternatives considered**:
- Add a new standalone directive. Rejected because the issue is interpretive
  context for Directive 2, not a new governance domain.
- Add only a cross-reference later in safety parameters. Rejected because that
  placement is easier to miss when interpreting autonomy.

## Decision 2: Reference the canonical taxonomy instead of copying it

**Decision**: Link to
`docs/design/architecture/data/change-risk-taxonomy.json` as the authoritative
Tier 0-4 source and summarize only the principle-level effect on autonomy.

**Rationale**: The spec requires avoiding duplicated tier definitions that can
drift. The taxonomy JSON already defines tier names, scopes, protocols, and
overridability.

**Alternatives considered**:
- Copy the full tier table into the constitution. Rejected due drift risk.
- Reference only the change-control narrative doc. Rejected because the JSON is
  the canonical machine-readable source.

## Decision 3: Keep companion-doc changes conditional

**Decision**: Inspect `CLAUDE.md`, `.kittify/charter/charter.md`, and
`docs/design/architecture/change-control.md` for consistency, but update only
when a concrete conflict is found.

**Rationale**: These documents already contain risk-tier guidance. Broad
rewriting would add churn without improving the constitution amendment.

**Initial finding**: `CLAUDE.md` and `.kittify/charter/charter.md` already state
the Tier 0-4 protocol and point to the taxonomy. `change-control.md` already
points to the taxonomy and describes pre-flight/post-change verification.

## Decision 4: Treat the mission as Tier 4

**Decision**: No backup, production pre-flight, office2 access, or deployment is
required for this mission.

**Rationale**: The change is governance documentation only and does not mutate
deployed services, runtime configuration, credentials, data, or network/host
surfaces.
