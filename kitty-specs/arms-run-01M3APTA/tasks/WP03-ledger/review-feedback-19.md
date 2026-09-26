VERDICT: APPROVE. This was a Codex read-only review (gpt-6-astra, OpenAI) of the WP03 REOPEN (cycle 18, the M1 ruling) on lane-c @1cfad35e, 2026-09-26. The implementer was Claude Opus 5.5, so reviewer and implementer are from independent vendors.

Codex ran 472 tests, all passing. Its ad-hoc probes confirmed:
- a refused write leaves the file bytes, the rows and the instance gate state unchanged, whether the prior state was absent, failing or passing;
- a failed append leaves the gate state as it was, poisons the writer, and grants no gate permission on reopen;
- the MOST RECENT session_gates governs, across each passing/failing/skipped transition;
- replay never seeds the instance state;
- a resume with different gate shas opens and keeps the creator's values in the header.
No behavioural regression was found, and no existing invariant was weakened by the test adaptations.

Codex raised one MINOR, which is the orchestrator's error and not a defect. The fixture `harness_gates_detail()` returns 13 keys, and the review prompt said the harness writes 14. The prompt was wrong. The harness writes exactly 13 keys: 3 from `session_identity()` and 10 from `SessionGates.as_detail()`. This was verified by instantiating the lane-h harness @f8451d1a. The fixture's "EXACTLY" claim is therefore true, and the brief's "14" is corrected here.

Cross-lane evidence from the orchestrator: 1cfad35e was merged into a throwaway copy of the approved lane-h harness, and the full research suite passed there, 1004 tests.
