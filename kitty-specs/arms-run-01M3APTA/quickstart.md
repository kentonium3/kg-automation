# Quickstart: 849 Lattice Arms and Decisive Run

All commands from the repository root on office4. Nothing here touches office2.

## 0. One-time setup (network allowed here, nowhere later)

```bash
uv pip install --python .venv/bin/python graphiti-core==0.30.2 falkordb==1.7.1 fastembed==0.8.1 openai==3.19.2
uv pip install --python .venv/bin/python --no-deps transformers tokenizers huggingface-hub
python3 -m scripts.research.arms849.substrate setup     # pulls pinned images, fetches + caches bge-small and the Qwen tokenizer, records shas
```

## 1. Gates (read-only, ~minutes)

```bash
python3 -m scripts.research.check_849_seed
python3 -m scripts.research.check_849_oracle              # from the FULL checkout only
python3 -m scripts.research.check_849_freeze
python3 -m scripts.research.check_849_loader
```

## 2. Preflight (full checkout) and the oracle-free export (FR-013, IC-07)

```bash
python3 -m scripts.research.run_849_harness --preflight   # runs the four checkers HERE, writes build/849-runs/preflight.json (bound to the export sha)
python3 -m scripts.research.arms849.substrate export      # git archive HEAD → build/849-run-env/ minus oracle/, seed/, narrative + traceability; content-manifest sha recorded
```

## 3. Bring the substrates up (sandbox note: research.md D-9)

```bash
python3 -m scripts.research.arms849.substrate up          # FalkorDB :16379 + llama-server :18080 on 127.0.0.1, health-checked
```

## 4. Run the primary inside the runner container (resumable; re-run after any interruption)

```bash
python3 -m scripts.research.arms849.substrate run -- --ledger /runs/primary.jsonl   # runner container: mounts ONLY the export (ro), corpus (ro), /runs (rw); compose network only
python3 -m scripts.research.run_849_harness --status --ledger build/849-runs/primary.jsonl
```

## 5. Hand-off

```bash
python3 -m scripts.research.run_849_harness --grading-view --ledger build/849-runs/primary.jsonl   # view → views/, seal → seals/
```

## 6. Secondary (only after 5; its own gate runs first)

```bash
python3 -m scripts.research.arms849.substrate up --yarn                                            # n_ctx 393216, rope yarn ×2
python3 -m scripts.research.arms849.substrate run -- --secondary --primary /runs/primary.jsonl --ledger /runs/secondary-yarn.jsonl
```

## 7. Teardown (SC-008)

```bash
python3 -m scripts.research.arms849.substrate down        # compose down -v --rmi all; verifies nothing remains; GTT < 2 GiB; GGUF kept
```
