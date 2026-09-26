---
affected_files: []
cycle_number: 1
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T01:18:49Z'
reviewer_agent: claude
wp_id: WP03
---

[MAJOR] scripts/research/arms849/ledger.py:287 — Three interrupted attempts with no run rows remain nonterminal — resume schedules an exhausted key and D-10’s halt check misses it — classify exhausted keys without successful outcomes as terminal error, including across resume.
[MAJOR] scripts/research/arms849/ledger.py:278 — Payload fields overwrite validated record type, key, attempt and outcome — an `error` call can persist `ok` with attempt 99, bypassing invariants — reject reserved payload fields and construct authoritative fields last.
[MAJOR] scripts/research/arms849/ledger.py:271 — Multiple results can use the same attempt — consecutive `record()` calls append duplicate attempt numbers, violating I3 — require an unconsumed attempt and reject subsequent results for it.
[MAJOR] scripts/research/arms849/ledger.py:265 — Serving equality is optional and ignores `row["serving"]` — mismatched serving data can enter the ledger unchecked — require and validate the effective serving configuration on every run append.
[MAJOR] scripts/research/arms849/ledger.py:369 — Recovery truncates and rewrites the entire ledger through `write_bytes()` — interruption during recovery can destroy previously durable cells — truncate in place to the last valid byte offset and fsync before appending the recovery event.
[MAJOR] scripts/research/arms849/ledger.py:365 — Valid JSON without a final newline is accepted unchanged — the next append concatenates two JSON objects, corrupting the ledger — explicitly recover an unterminated final record before permitting append.
[MAJOR] scripts/research/arms849/ledger.py:400 — Exceptions during parsing, header construction or initial append leak the lock descriptor — subsequent openers remain refused until process exit — close the descriptor on every unsuccessful open path.
[MAJOR] scripts/research/arms849/ledger.py:300 — Calibration can be written without eight successful G repeat-1 cells — the supplied test even writes it after terminal G failure, contradicting the calibration contract — enforce the complete successful population before writing calibration.
[MAJOR] scripts/research/arms849/ledger.py:278 — Scored rows accept missing required telemetry — summaries silently substitute zero for absent cache measurements, violating D-13 — validate required scored-row measurements before append and test their omission.
[MINOR] scripts/research/arms849/ledger.py:189 — Summary omits the required prompt-token range — T014’s mean/range reporting is incomplete — add the range over scored rows, returning `None` when none exist.
VERDICT: REJECT

Source: Codex read-only review, WP03 cycle 1, 2026-09-25. VERDICT: REJECT.
