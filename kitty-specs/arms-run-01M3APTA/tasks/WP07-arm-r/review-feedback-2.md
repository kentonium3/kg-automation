VERDICT: APPROVE — Codex read-only review (gpt-6-astra), WP07 cycle 2 on lane-g @d90914dc, 2026-09-25; design-lead delta read APPROVE (20260925T192848220655Zd32fc5a6fc).

Codex: no genuine defects; 21 passed, 1 expected skip; real-corpus probes passed — altered-byte refusal (view_digest), cache reuse, calibration integration reproduced with lane-d's calibration.py (k=3, parity=ok), incoherent limit pairs refused, the gate's carried plan, and the REAL last-line refusal naming permitted 260,096.

Skip record (design-lead ruling 20260925T192232283759Z096e3e655f): the end-to-end `calibration.calibrate(ledger, *arm_r.calibration_inputs(...))` test importorskips `arms849.calibration`, which lives only on lane-d (WP07's declared dependencies are WP01/WP03/WP05; adding WP04 mid-implement was ruled out). Evidence it passes: scratch copy of lane-g's package + tests with lane-d's calibration.py @ff6d2f84 → k=3, parity "ok", availability {C1: 772, A: 2184}, r_tokens_at_k == r_tokens_for exactly; Codex c2 reproduced it independently. The un-skipped run on feat/849-arms-run after all lanes merge is a REQUIRED post-merge checkpoint check; WP09 cannot start before it passes.

Carried forward (non-blocking, design-lead N-2): on the bind path a passed index is retrieved from before assemble() validates it; validate `index.serves(text, view)` before `index.retrieve` (one line) — fold with the next WP07 touch or at post-merge. N-3 is a WP08 requirement (one index_cache object shared by calibration_inputs and bind, identity-asserted) and is recorded in the WP08 brief.

WP07 cycle ledger: c1 REJECT(2 MAJOR + 1 MINOR) + design-lead R-1..R-6/N-1 → c2 APPROVE.
