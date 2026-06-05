# Contracts: Constitution Risk-Tier Autonomy Guard

This mission introduces no runtime API contracts, CLI contracts, database
contracts, or integration schemas.

The effective contract is documentation/governance behavior:

- `docs/constitution/FELIX-CONSTITUTION.md` must make clear that autonomy level
  never overrides deployed-change risk-tier gates.
- The canonical Tier 0-4 definition remains
  `docs/design/architecture/data/change-risk-taxonomy.json`.
- Tier 0 remains operator-only.
- Tier 1 and Tier 2 retain their required gates where applicable.
