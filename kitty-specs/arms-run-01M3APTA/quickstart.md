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

## 2. Build the oracle-free run environment (FR-013)

```bash
python3 -m scripts.research.arms849.substrate export     # git archive HEAD → build/849-run-env/ minus the oracle dir; writes the manifest sha
```

## 3. Bring the substrates up (sandbox note: research.md D-9)

```bash
python3 -m scripts.research.arms849.substrate up          # FalkorDB :16379 + llama-server :18080 on 127.0.0.1, health-checked
```

## 4. Run the primary (resumable; re-run the same command after any interruption)

```bash
cd build/849-run-env && python3 -m scripts.research.run_849_harness --ledger ../849-runs/primary.jsonl
python3 -m scripts.research.run_849_harness --status --ledger build/849-runs/primary.jsonl
```

## 5. Hand-off

```bash
python3 -m scripts.research.run_849_harness --grading-view --ledger build/849-runs/primary.jsonl   # view → views/, seal → seals/
```

## 6. Secondary (only after 5; its own gate runs first)

```bash
python3 -m scripts.research.arms849.substrate up --yarn                                            # n_ctx 393216, rope yarn ×2
cd build/849-run-env && python3 -m scripts.research.run_849_harness --secondary --ledger ../849-runs/secondary-yarn.jsonl
```

## 7. Teardown (SC-008)

```bash
python3 -m scripts.research.arms849.substrate down        # compose down -v --rmi all; verifies nothing remains; GTT < 2 GiB; GGUF kept
```
