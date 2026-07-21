# Contracts — retire-private-folder-guards-01KY2MNK

**No API/interface contracts.** This is a removal/refactor mission: it deletes the `_private`
folder-guard apparatus, generalizes existing hygiene guards, and reframes documentation. It adds
no new endpoints, message schemas, CLI surfaces, or externally-visible interfaces — so there are no
contracts to specify. The behavioral guarantees that DO change (redaction fragments retained,
refuse-outside-inbox-root, validator invariants removed) are captured as tests in the owning WPs
(WP02, WP03) and as acceptance criteria in `../spec.md` (SC-001..006) and `../quickstart.md`.
