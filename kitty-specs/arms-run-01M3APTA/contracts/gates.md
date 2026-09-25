# Contract: pre-run gates (two phases, IC-07). Digests compare to REGISTERED CONSTANTS, never "recorded on first run".

**Preflight — run from the FULL checkout, before export.** Writes `preflight.json`.

| Gate | Asserts |
|---|---|
| `check_849_seed`, `check_849_oracle`, `check_849_freeze`, `check_849_loader` | existing checkers; these load the oracle and would pass VACUOUSLY in the export, so they never run there; pass/fail, the three corpus fingerprints, the canonical record-line digest and the export's content-manifest sha are written and digested |

**In-container — before the header is written.** Any failure refuses the run with the detail.

| Gate | Asserts |
|---|---|
| `preflight_present_and_matching` | `preflight.json` present; corpus fingerprints, record-line digest and export sha match this environment; all four preflight gates passed |
| `prompt_digest` | sha256 of the normalised registered text (UTF-8, CRLF→LF, per-line trailing whitespace stripped, exactly one trailing newline, slots `{assembled_context}` and `{question_text}` literal) == the constant registered in rubric §3.2 (A4): `0aa7ee77560b1f5cbbb04a6c3dfa90749dfd79305b4207134c62d9fdd733af45` |
| `question_manifest_digest` | digest of `arms849.questions` == the constant registered in rubric §3 (A4, re-registered @c8237d27): `fe17beef263777261e5d623ed8362ebaaada60ffbb0fd20b10b1f4d7a820c462`; never computed-then-stored |
| `oracle_absent` | the oracle, seed, narrative, worksheet and traceability paths do not exist under the mount; no module under `arms849/` contains `oracle`, `seed/` or `traceability` |
| `boundary` | denied-access test: the original checkout path and every excluded file are unreachable from inside the container; the only mounts are the export (ro), the corpus (ro) and the ledger dir (rw) |
| `env_clean` | `OPENAI_API_KEY` unset; FastEmbed model and Qwen tokenizer caches present; `torch` not importable; no outbound network beyond the compose network |
| `tokenizer_equivalence` | 100 corpus lines tokenised client-side == the pinned server's `/tokenize` (D-11) |
| `substrate_health` | FalkorDB answers `GRAPH.LIST`; llama-server `/health` ok and `/props` reports the expected model file, `n_ctx` and (secondary) rope settings |
| `code_hashes` | sha256 of every `arms849/` file + harness + loader match the header on resume (D-16) |
