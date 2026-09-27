# WP01 review cycle 2 — REVISE

Reviewer: Codex (gpt-6-astra, OpenAI Codex CLI), read-only, cross-vendor. Implementer: Claude Opus 5.5 (python-pedro). 2026-09-27. Scope ff67c8cb..abf3d8fe; properties P1–P13.

## Findings
[MAJOR] scripts/research/arms849/calibration.py:66 — Premise-tainted rows still produce calibration statistics and `k` — `_g_repeat1()` consumes raw `run_rows()` without checking usability. Live and replay probes returned `k=1`, `g_median=1000.0`, and `parity="ok"` after `premise_violated`. The harness also reuses existing calibration through `ensure_calibration()` at run_849_harness.py:449 and `_calibration_obj()` at :467 — Use the guarded scored accessor for calibration inputs, guard existing-calibration consumers, and test both paths immediately and after replay while preserving raw inspection.

Cycle-1 MAJORs (post-violation scoring; grading_rows) verified fixed. Remaining: the calibration path (P12).

VERDICT: REVISE
