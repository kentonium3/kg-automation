# Data Model: #849 live runtime: host-reachable endpoints (#1083)

## Endpoints (value object, new)

| Field | Type | Meaning |
|---|---|---|
| `falkordb` | `tuple[str, int]` | FalkorDB host and port that arm G's bridge and the health PING connect to |
| `llama_url` | `str` | llama.cpp base URL (`http://<host>:<port>`) that the serving facade and the health `/health` and `/props` probes use |

- **Immutable** (frozen).
- **Canonical instance**: `IN_NETWORK_ENDPOINTS = Endpoints(("falkordb", 6379), "http://llama:8080")`, built from the existing `FALKORDB_ADDR`/`LLAMA_URL` constants.
- **Invariant I-1 (C-001)**: production code constructs `Endpoints` only as `IN_NETWORK_ENDPOINTS`. No production path builds one from the environment.
- **Invariant I-2 (consistency)**: within one runtime, the bridge, facade and health all read the same `Endpoints` instance.
- **Host instance (test and checker only)**: `Endpoints(("127.0.0.1", substrate.FALKOR_PORT), f"http://127.0.0.1:{substrate.LLAMA_PORT}")`, or the values from the `ARMS849_*` overrides.

## Resources (existing record, extended)

Adds `endpoints: Endpoints = IN_NETWORK_ENDPOINTS` as the last field, with a default, so existing constructions stay valid.

## Checker record: `live-required-nodes` step (existing, extended)

`environment` gains four keys, recorded alongside the existing `ARMS849_LIVE` and `ARMS849_CACHE`:

| Key | Value required by `--verify` |
|---|---|
| `ARMS849_FALKOR_HOST` | `127.0.0.1` |
| `ARMS849_FALKOR_PORT` | `str(substrate.FALKOR_PORT)` (`16379`) |
| `ARMS849_LLAMA_HOST` | `127.0.0.1` |
| `ARMS849_LLAMA_PORT` | `str(substrate.LLAMA_PORT)` (`18080`) |

The step verifies only when all four are present and equal to these values, and `ARMS849_LIVE == "1"`. One shared constant mapping (`HOST_LIVE_ENDPOINT_ENV`) defines both what the checker writes and what the verifier requires.
