# WP04 reopen review — cycle 18 (lane-d @637d0a5a): REJECT

Reviewer: Codex gpt-6-astra (OpenAI), read-only, 2026-09-26. Implementer: Claude Opus 5.5. 53 sampler tests passed; the other failures in Codex's run were socket-denied in its sandbox. Codex's probes confirmed the c17 fixes 2 to 5, sampling by immutable id, a failed read writing no line, the torn tail, and the tolerance boundaries. RssSampler and GttSampler are unchanged. `readings` is interpretable alongside `in_window_readings`.

## Finding 1 (a reading tying the start drops the hold): NO CHANGE, ruled by the design lead
The design lead ruled option A (bus 20260926T024638869834Z3e75c64d60). The hold SUBSTITUTES for a missing observation at the start, so a reading at exactly the start supersedes it. The freshness bound applies to the hold only when the hold is used. The code was right and the registered text was the defect. Rubric §5 is corrected on main @09b28dc5, and it now carries the -1 s / 0 s / 1 s example. Codex re-checks against @09b28dc5.

## Required fix — finding 2 (genuine)
**[MAJOR]** `datetime.fromisoformat` truncates sub-microsecond precision. A 999 MiB reading at 00:00:01.0000009Z is placed inside a window ending 00:00:01Z. Required: reject any timestamp with more than six fractional-second digits as UNREADABLE (fail-closed, None plus a reason), in both the record and the header. The writer never emits that precision. Add a can-fail regression.
