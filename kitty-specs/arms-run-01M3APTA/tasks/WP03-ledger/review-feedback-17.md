VERDICT: APPROVE — Codex read-only review (gpt-6-astra), WP03 cycle 17 on lane-c @d1972947 (+ comment-only noqa commit 7326bb1a), 2026-09-25.

Confirmed by adversarial probe: strict type rejection on the persisted header (plan / blinding_seed / model_context_tokens / limit_applied / serving shape), type-aware binding and serving comparison (True≠1, 262144.0≠262144) on resume and on append, byte-identical resume of a legal ledger with calibration and G/R/D scored rows through the JSON round trip; seed 0 is a valid integer and correctly differs from seed 7. 186 tests passed.

Carried forward (not blocking):
[MINOR] scripts/research/arms849/ledger.py:765 — fresh-path open_ledger() with a float/bool/string seed or plan raises ValueError but leaves ledger.jsonl.lock behind (lock released; measurements unaffected) — fix: validate seed and plan before creating directories or opening the lock file. To fold with the next WP03 touch or at the post-merge review.

Cycle ledger for WP03 today: c14 REJECT(3) → c15 REJECT(3) → c16 REJECT(2) → c17 APPROVE(+1 minor); every finding a genuine defect found by probe, every fold with tests proven to fail on the prior code.
