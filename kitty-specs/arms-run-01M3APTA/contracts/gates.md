# Contract: pre-run gates (two phases, IC-07)

**Preflight — run from the FULL checkout, before export.** Writes `preflight.json`.

| Gate | Asserts |
|---|---|
| `check_849_seed`, `check_849_oracle`, `check_849_freeze`, `check_849_loader` | existing checkers; these load the oracle and would pass VACUOUSLY in the export, so they never run there; their pass/fail, the three corpus fingerprints and the export's content-manifest sha are written and digested |

**In-container — before the header is written.** Any failure refuses the run with the detail.

| Gate | Asserts |
|---|---|
| `preflight_present_and_matching` | `preflight.json` present; its corpus fingerprints and export sha match this environment; all four preflight gates passed |
| `prompt_digest` | sha256 of the normalised registered text (D-14) == the digest the design lead recorded in rubric §3.2 |
| `question_manifest_digest` | digest of `arms849.questions` == header value (or, on first run, recorded) |
| `oracle_absent` | the oracle, seed, narrative and traceability paths do not exist under the mount; no module under `arms849/` contains `oracle`, `seed/` or `traceability` |
| `boundary` | denied-access test: the original checkout path and the excluded files are unreachable from inside the container; the only mounts are the export (ro), the corpus (ro) and the ledger dir (rw) |
| `env_clean` | `OPENAI_API_KEY` unset; FastEmbed model and Qwen tokenizer caches present; `torch` not importable; no outbound network beyond the compose network |
| `tokenizer_equivalence` | 100 corpus lines tokenised client-side == the pinned server's `/tokenize` (D-11) |
| `substrate_health` | FalkorDB answers `GRAPH.LIST`; llama-server `/health` ok and `/props` reports the expected model file, `n_ctx` and (secondary) rope settings |
| `code_hashes` | sha256 of every `arms849/` file + harness + loader match the header on resume (D-16) |
