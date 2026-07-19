# Contracts

**No API surface.** This mission is a behavior-preserving authoring refactor of markdown workspace prompt files (`felix-admin-tasker` SOUL/USER/TOOLS). It defines no endpoints, schemas, events, or wire contracts.

The closest thing to a "contract" is the #587 file-ownership model (which concern lives in which file) and the content-conservation invariants — both captured in [`../data-model.md`](../data-model.md). The mechanically-checked contract is `validate_workspace.py` (Invariants A + B), reused as-is.
