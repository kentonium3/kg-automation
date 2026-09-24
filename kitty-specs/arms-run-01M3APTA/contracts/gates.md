# Contract: pre-run gates

All must pass before the Header is written; each prints its detail; any failure refuses the run.

| Gate | What it asserts |
|---|---|
| `check_849_seed` | seed contracts (existing) |
| `check_849_oracle` | oracle contract (existing) — runs from the FULL checkout before export, never from the run env |
| `check_849_freeze` | rendered corpus clean, probes recover (existing) |
| `check_849_loader` | loader-side pass; prints the three fingerprints (existing) |
| `prompt_hash` | sha256 of `arms849.prompt.REGISTERED_TEXT` == the hash recorded in rubric §3.2 |
| `oracle_absent` | `docs/design/research/849-synthesis/oracle/` does not exist under the run env's root; and no module under `scripts/research/arms849/` contains `oracle` |
| `env_clean` | `OPENAI_API_KEY` unset; FastEmbed model cache present; Qwen tokenizer cache present; no `torch` importable |
| `substrate_health` | FalkorDB answers `GRAPH.LIST`; llama-server `/health` ok and `/props` reports the expected `n_ctx`, model file and (secondary) rope settings |
| `run_env_intact` | export manifest sha matches the source commit's file list |
