**Issue 1**: `docs/design/architecture/contracts/drift-ledger-schema.md` still identifies itself as a planning artifact instead of the live architecture contract.

The new live file begins with:

> `**Status**: Planning-time draft. The live version will be created at ... during implementation. This file in the mission's contracts/ directory is the spec-kitty planning record...`

That text is correct for the mission planning preview, but incorrect in the destination required by WP02. The WP objective is to lift this contract to the live docs location and establish `docs/design/architecture/contracts/` as the canonical home for living contract docs. As written, an operator opening the new canonical file is told it is not the live contract yet and belongs to the mission `contracts/` directory.

Fix by replacing the planning-only status paragraph with live-doc wording, for example marking the document as the canonical live drift-ledger JSONL schema contract at `docs/design/architecture/contracts/drift-ledger-schema.md`. Keep the rest of the required content intact, including the widened `retry_count` bound, `retry_max` source-of-truth subsection, examples, query examples, backwards compatibility paragraph, and change history.
