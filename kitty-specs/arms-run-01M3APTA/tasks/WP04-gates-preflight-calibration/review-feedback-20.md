VERDICT: APPROVE — Codex read-only review (gpt-6-astra, OpenAI) of the WP04 REOPEN, cycle 19, on lane-d @52f4d2e1, 2026-09-26. Implementer: Claude Opus 5.5 (independent vendors). The design lead approved the c18 delta and ruled on each registered-text question: sample-and-hold, the hold ties, and the hold being superseded by a reading at the start. Rubric §5 on main @09b28dc5.

Codex: no findings.
- All 67 sampler tests passed.
- Direct probes passed: precision-loss refusal, offset and fold handling, 60 writer round trips, and 3,000 window-reconstruction cases checked against the registered §5 text.
- Codex's full-suite run hit 204 socket-denied failures in its sandbox, so full regression could not be established there.

Orchestrator evidence on this machine:
- 884 passed under both PYTHONHASHSEED 0 and 3.
- Cross-lane merge of lane-d @52f4d2e1 into the approved lane-h harness @f8451d1a: 1071 passed (standing practice, #1018).

Reopen record:
- c17 (11d9bffc) REJECTED: 4 defects, plus a sample-and-hold finding that the design lead overruled.
- c18 (637d0a5a) REJECTED: sub-µs truncation; the hold-tie finding was ruled option A with no change, and §5 was corrected.
- c19: a regex guard (e22fb7ff) leaked the compact ISO form and was withdrawn before review. It was replaced at 52f4d2e1 by a canonical round-trip property. APPROVE.
