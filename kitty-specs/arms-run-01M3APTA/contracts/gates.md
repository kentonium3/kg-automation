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

**Dated correction (2026-09-25, design-lead ruling 20260925T033758187296Z4e2f3be79e, on the D-8 runner having
no docker socket):** the gates run in TWO PHASES, both bound into the header.
- **HOST phase** — executed by `substrate run` immediately before launching the runner, after `up` + health:
  `boundary` (the docker self-test with its widening negatives), `substrate_health` (docker-derived rope mode,
  n_ctx, model file, image digests, GRAPH.LIST), `preflight_present_and_matching`. Writes `gate-host.json` =
  `{ts, up_ts, export_content_sha, export_source_commit, preflight_sha, results[…], gate_host_sha}` (sha over the
  canonical JSON without the sha field) into the runs dir, read-only to the runner.
- **CONTAINER phase** — executed by the harness before the header is written: `preflight_present_and_matching`
  recomputed from inside, `prompt_digest`, `question_manifest_digest`, the excluded-material gate + scan,
  `env_clean` (no key, no torch, caches present, NO outbound — the only place it is meaningful),
  `tokenizer_equivalence` against `llama:8080`, `substrate_health_inside` = `/props` re-probe (n_ctx, model file)
  AND verification of `gate-host.json` (its sha recomputes; its export_content_sha / export_source_commit /
  preflight_sha equal what the container computed; every host result passed; host `ts` ≥ `up_ts` and ≤ container
  start — a stale record from a previous stack is refused), `code_hashes`. Writes `gate-container.json` with
  `gate_container_sha`.
  **Amendment (2026-09-25, design-lead msg 20260925T040859392825Zf9b247aec7, from Codex WP04 c6's replay
  finding):** the freshness rule does NOT trust the record's own `up_ts`: the container phase takes the CURRENT
  stack's `up_ts` from the harness (`env.up_ts`), refuses a host record whose `up_ts` differs, then applies
  `cur_up ≤ ts ≤ container_start` on parsed timezone-aware timestamps (a naive timestamp is refused) — so an
  unchanged record from an earlier stack cannot be replayed against a newer one.
- **The header binds `preflight_sha`, `gate_host_sha` and `gate_container_sha`**; WP03's binding validator refuses a
  header missing any. Rejected alternative: nine in-container with a host-written record verified by timestamp only.
