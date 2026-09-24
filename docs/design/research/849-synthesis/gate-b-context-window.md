---
title: "#849 gate (b) — does the ruled model hold arm D's largest prompt?"
doc_type: research
status: measured
owner: claude-office4
last_updated: 2026-09-24
---

# Gate (b): context-window feasibility on office4

Kent's ruling (2026-09-24, via the design lead): before any arm is built, load the ruled model with a
context window ≥ arm D's largest prompt, push one full-length prompt through it, and report the
configured `n_ctx`, peak GTT, and tokens/s at that length. If it does not fit, that is a rubric
amendment to D's specification, not a workaround.

**Result: it does not fit as specified, and the reason is positional, not spatial.** The empirical
run below was made at the largest *valid* context instead, and confirms the memory arithmetic.

## What was measured

| | value |
|---|---|
| model | Qwen3-Next-80B-A3B-Instruct UD-Q4_K_XL (`~/models/gguf/unsloth/…`, SHA256SUMS there) |
| server | `ghcr.io/ggml-org/llama.cpp@sha256:063e88ae…` (server-vulkan, the SOURCE.md known-good image, re-pulled) |
| host | office4, Radeon 8060S via RADV, 62.5 GiB GTT budget, 125 GiB RAM |
| flags | `--ctx-size 262144 --parallel 1 --n-gpu-layers 999 --jinja` |
| **configured `n_ctx`** | **262,144** — the model's `max_position_embeddings`; the largest valid value |
| prompt | B2's D dump, truncated to fit: **255,814 tokens** (entities placed after events, per §2) |
| **prefill** | **1,661.8 s for 255,814 tokens = 153.9 tok/s cumulative** (6.50 ms/token) |
| **generation** | **20.32 tok/s** (128 tokens, 49.2 ms/token) — vs ~43 tok/s at 16k ctx in SOURCE.md |
| **peak GTT** | **51.33 GiB** (sampled every 1 s through load + prefill + generation) |
| wall clock, one question | 1,668 s ≈ 27.8 min, cold (`cache_prompt: false`) |
| output | coherent; cited the `DEC_F_ILLNESS` Decision node by id from the entity block |

Peak GTT against the arithmetic in the loader-side report: weights 42.9 GiB + KV at fp16
(12 full-attention layers × 2 KV heads × 256 dim × 2 bytes = 24 KiB/token) × 255,814 = 48.8 GiB,
plus the ~1.7 GiB llama.cpp overhead SOURCE.md's 16k measurement implied → **50.5 GiB predicted,
51.33 measured**. The arithmetic is good to ~1.6 %, so it can be trusted for planning.

## Why the run cannot proceed as specified

Measured with the real Qwen tokenizer over each question's actual D dump (JSON tokenises at
2.32 chars/token, not the 3.3–3.8 prose gives — the rubric's carried-over ~178k was low by 2.04×):

| Q | D-dump tokens | vs 262,144 |
|---|---|---|
| C1 | 51,398 | fits |
| A | 139,451 | fits |
| F1 | 272,863 | exceeds by 10,719 |
| B1 | 288,041 | exceeds by 25,897 |
| E2 | 329,415 | exceeds by 67,271 |
| E1 | 361,170 | exceeds by 99,026 |
| F2 | 361,659 | exceeds by 99,515 |
| B2 | 362,772 | exceeds by 100,628 |

Six of eight questions exceed the model's trained context. Memory would hold all of them
(weights + KV at 362,772 = 51.2 GiB of 62.5), and llama.cpp accepts `--ctx-size 393216` without
complaint — but the model has never been trained past position 262,144, so everything beyond is
degraded output presented as a result. That failure is silent, which is why this gate stopped at
the config rather than running the invalid configuration.

## Prefill cost grows with context — it is not linear

Cumulative prefill rate over the one run, from the server log (every ~16k tokens):

```
tokens   18k   51k   84k  117k  149k  182k  215k  248k  256k
tok/s    630   515   426   350   284   236   194   161   154   (cumulative)
```

The instantaneous rate over the last 16k-token batch was ~71 tok/s. This is the 12 full-attention
layers doing quadratic work; the 36 linear-attention layers do not grow. Consequences for the run:

- A cold D prompt at ~255k costs ~28 min. Under §2's ask_time ordering with `cache_prompt` **on**,
  later questions share 87–99.9 % of their event tokens with the previous prompt (measured in the
  loader report), so D's per-question cost is dominated by whether that prefix is reused. **The cache
  hit rate is not a nuisance metric here; it is the difference between a 30-minute question and a
  30-second one.**
- Generation at full context is ~2.1× slower than at 16k (20 vs 43 tok/s). §5's wall-clock column
  must be reported at the context each question actually ran at.

## What this does and does not establish

- **Establishes:** the memory arithmetic; the prefill and generation rates at the largest valid
  context; that the ruled serving stack works at 262,144 on office4 with ~11 GiB of headroom.
- **Does not establish:** anything about arm D's *answers*. The prompt was B2's dump with its last
  ~103k event tokens cut off to fit — the model answered a question from a corpus missing its final
  28 %. That output is a capacity probe, not a scored run, and must not be read as one.
- **Not measured:** a YaRN-scaled configuration. That is a different serving config from the one
  Kent ruled, and running it is an Amendment A2 decision, not a gate.

## Options put to the design lead and Kent (Amendment A2, pending)

(a) YaRN / RoPE scaling to ~1M — but §2's invariant is the same model for all three arms; scale D
only and it is no longer the same model, scale all three and every arm moves off the ruled config.
(b) Truncate D — rejected in recommendation: D's role is "honest upper bound on recall", and a
truncated D is an upper bound on nothing.
(c) Re-scope corpus or questions — the corpus is frozen; this would be re-running synthesis.
(d) **Pre-register the failure as a result**: "at this corpus size, on the ruled model, the full-dump
baseline cannot be run for 6 of 8 questions" — a direct finding about where flat-context stops
scaling, and relevant to #692's build direction. Must be registered *now*, not read post-hoc.

Design-lead recommendation to Kent: (d) + (a) as a labelled secondary — native D where it fits
(C1, A), the other six recorded as *exceeds model context* rather than as a score of zero
(the verified-false vs could-not-check distinction), and a YaRN-D variant run separately and
labelled so the comparison still exists.
