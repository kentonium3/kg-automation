---
title: LLM Spend Baseline
doc_type: reference
status: approved
audience: humans
---

# LLM Spend Baseline

> Machine-readable record: [`data/llm-spend-baseline.json`](<./data/llm-spend-baseline.json>) (authoritative)
>
> Source: Kent's manual dashboard sweep in `docs/llm_cost.md`

## Summary (as of 2026-05-15)

- **Monthly burn**: ~$1,157 today → ~$1,177 in ~30 days (Gemini kentgale@gmail.com leaves free tier)
- **Annualized**: ~$14,100/year at current run rate
- **Concentration**: Anthropic API metered is 78% of spend; top 3 services are 98%

## Trend insights

### Anthropic API is the dominant cost and the fastest-growing line

May 10-15 paid invoices averaged $30.11/day — a ~7.5x step-change from the pre-2026-04-09 baseline (~$115/mo trend, which was the original trigger for #137). Auto-replenish triggered 2-3x/day on May 12-14. Per Kent (2026-05-15): this pattern is the new normal, not a project-week spike.

### Codex is absorbed by ChatGPT Plus

No separate Codex CLI charges appear beyond the $21.25/mo ChatGPT Plus subscription. Spec-kitty review cycles (which run Codex) are effectively free at the marginal level. The implication: dev-vs-Felix attribution within the Anthropic API line is even cleaner than expected, since Codex traffic doesn't add a confound to the metered spend.

### Claude Monthly Max envelope is an open optimization question

If some portion of Mac Claude Code usage is already absorbed by the $212.50/mo Max subscription envelope, the $903/mo metered API line is overflow-only. Confirming this is part of #296 (Anthropic workspace separation).

## Sequencing for the cost-awareness epic

Per #137, the baseline established here unblocks the next wave of work:

1. **#276** — Baseline (this artifact) ✓
2. **#296** — Anthropic workspace separation (dev vs felix attribution; zero-code win)
3. **#297** — Cross-provider retrieval tool (automate this sweep)
4. **#138** — Per-agent attribution within the felix workspace (depends on #296)
5. Tiering and budgeting — deferred until per-source signal exists

## Review cadence

**Monthly** — manual until #297 lands. After #297 ships, weekly automated snapshot.
