# Research: #849 live runtime: host-reachable endpoints (#1083)

Phase 0 has no open NEEDS CLARIFICATION items. The decisions below are recorded with the code evidence that grounds them (read 2026-11-18 at `cab71a10`).

## R-1 Where the in-network addresses are hard-wired

- **Finding**: `run_849_harness.py:170-171` defines `LLAMA_URL = "http://llama:8080"` and `FALKORDB_ADDR = ("falkordb", 6379)`. `live_runtime` (line ~1534) uses `LLAMA_URL` for the `ServingFacade` and calls `container_health(config)` with its defaults. `_factory_g` calls `arm_g.make_bridge(embedder, text)` with `arm_g.FALKOR_HOST, FALKOR_PORT = "falkordb", 6379` as defaults.
- **Consequence**: three consumers (bridge, facade, health), not one. `_factory_d`/`_factory_r` make no network connections.
- **Decision**: thread one `Endpoints` value to all three (Kent: option A).

## R-2 The override convention already exists

- **Finding**: `tests/research/test_arms849_arm_g.py:2832` (`falkor_endpoint` fixture) reads `ARMS849_FALKOR_HOST`/`ARMS849_FALKOR_PORT`, defaulting the host to `127.0.0.1`. That is why the hybrid-search live node passes from the host while the live-runtime node fails (#1083 evidence).
- **Decision**: mirror it for llama as `ARMS849_LLAMA_HOST`/`ARMS849_LLAMA_PORT` (spec assumption, confirmed by Kent).
- **Alternative rejected**: a single `ARMS849_LLAMA_URL`. It is asymmetric with the FalkorDB convention, and it invites a scheme or path in a value that is only ever host plus port.

## R-3 The llama allowlist needs no change

- **Finding**: `arms849/serving.py:75` has `ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "llama"})`. `ARMS849_LLAMA_HOSTS` is asserted unread (`test_arms849_substrate.py:48,394`; `test_arms849_serving.py:153`).
- **Decision**: no allowlist change (C-002). The host override uses `127.0.0.1`, which is already allowed.

## R-4 The published ports have one source

- **Finding**: `arms849/substrate.py:103` has `FALKOR_PORT, LLAMA_PORT = 16379, 18080`.
- **Decision**: the checker and the test default derive from these constants, never from literals (FR-004).

## R-5 The checker's recorded environment is an allowlist

- **Finding**: `check_849_premerge.py:~275`. `_step` records only `PYTHONHASHSEED`, `ARMS849_CACHE`, `ARMS849_LIVE`, `PYTHONPATH` from the env it runs with. `--verify` (lines ~669-674) checks `required_live["environment"].get("ARMS849_LIVE") == "1"`.
- **Consequence**: setting the overrides in the env without extending the allowlist would run correctly but record nothing. FR-004 would then be unverifiable and FR-005 would reject every real record.
- **Decision**: extend the allowlist with the four override keys, and share one constant mapping between the writer and the verifier.

## R-6 Why the defect went unseen

- **Finding** (#1083): the live node never ran live before 2026-10-23. Every earlier checker run failed before it, at `live-up` (setup.json absent) or on #1037.
- **Implication for this plan**: the end-to-end proof is a real checker run (quickstart), not only unit tests with fakes.

## R-7 Option B (in-container execution) stays rejected

- **Source**: Kent, 2026-10-26, recorded on #1083 (C-003). Not revisited.

## Supply chain

No dependency is added, upgraded or removed, so DIRECTIVE_051 and the supply-chain controls do not apply, and no adversarial-squad pass is required for dependency decisions.
