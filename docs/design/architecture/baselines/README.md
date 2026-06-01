---
id: baselines-readme
doc_type: reference
title: Architecture Baselines — Index and Methodology
status: approved
audience: humans
last_validated: 2026-05-21
---

# Architecture Baselines

This directory holds **measurement baselines** captured before and after
material architectural changes — the numerators and denominators that
the spec-level NFR acceptance gates compare against.

Each baseline is a versioned JSON document whose `methodology` section
is deliberately self-contained: a future operator should be able to
reproduce the measurement from the JSON alone, six or twelve months
later, without needing to re-derive the procedure.

## Current baselines

| File | Subject | Captured | Mission | Re-measure trigger |
|---|---|---|---|---|
| [`felix-doc-auditor-pre-rework.json`](<./felix-doc-auditor-pre-rework.json>) | felix-doc-auditor under the OpenClaw-mediated agent path (pre-rework) | 2026-05-21 | [`#343` / mission `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX`](../../../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/) — WP07 | WP09 cutover writes `felix-doc-auditor-post-rework.json` and compares per-outcome averages to satisfy spec NFR-001. **Note (2026-05-31)**: the post-rework baseline reflects measured-while-active state; the service has been ⏸ suspended indefinitely since 2026-05-26 (see service entry in `service-inventory.md`). Both baselines remain historically valid; no new measurement is planned until #137 cost-control work re-enables the service. |
| [`felix-heartbeat-gate-pre-rollout.json`](<./felix-heartbeat-gate-pre-rollout.json>) | Sonnet-only heartbeat path (pre-rollout, measured) — 71 heartbeats / $1.69 observed cost over a 14-day pre-cap window (2026-05-05..2026-05-19) | 2026-06-01 | [`#490` / mission `signal-driven-monitoring-haiku-gate-01KT22PC`](../../../../kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/) — WP03/T022 | WP-04 captures `felix-heartbeat-gate-post-rollout.json` from the deployed Haiku gate's `gate-ledger.jsonl` plus any escalation cost. Post-rollout daily cost / pre-rollout daily cost (~$0.121/day) must be ≤0.20 (≤$0.024/day) to satisfy NFR-001 (≥80% reduction). |

When a baseline is superseded (e.g. the scripts-first driver cuts over
and a `-post-rework` file is captured), retain BOTH files: the historic
pre-rework JSON is the audit record for the acceptance gate.

## Schema (v1.0)

Each baseline JSON conforms to the same shape:

```jsonc
{
  "schema_version": "1.0",
  "name": "<file-stem>",
  "captured_at": "<ISO-8601 UTC>",
  "captured_by": "<issue + WP, e.g. #343-WP07>",
  "captured_via": "<one-line provenance description>",
  "subject": {
    "service": "<service name>",
    "implementation": "<which code path this measures>",
    "host": "<host>",
    "model": "<provider/model>",
    "git_sha": "<sha at time of measurement>",
    "git_branch": "<branch>"
    /* additional subject-specific fields (e.g. session_uuid) allowed */
  },
  "measurement_window": { /* time span + tick count */ },
  "measurements": [
    {
      "outcome": "<canonical outcome label>",
      "description": "<one-line explanation>",
      "sample_count": <int>,
      "average_<metric>": <number>,
      /* one `average_*` field per metric of interest */
      "samples": [ /* OR */ "representative_samples": [
        { "tick_id": "...", /* per-sample metrics */ }
      ]
    }
  ],
  "methodology": {
    "summary": "<short prose>",
    "reproduction_steps": [ /* numbered shell-and-or-tool steps */ ],
    "sample_size_guidance": "<text>",
    "future_use": "<how a re-measurement consumes this baseline>"
  },
  "open_caveats": [ "<each caveat as a complete sentence>" ]
}
```

The `methodology.reproduction_steps` array is load-bearing: it is the
contract a future operator (human or agent) follows to produce a
comparable post-rework measurement.

## Toolchain

The helper script that converts an OpenClaw agent session JSONL into
the per-outcome aggregation shape used by the
`felix-doc-auditor-*-rework.json` baselines lives at:

- [`scripts/doc_audit/baselines/measure-tokens.py`](../../../../scripts/doc_audit/baselines/measure-tokens.py)

Usage:

```
python3 scripts/doc_audit/baselines/measure-tokens.py \
    --session /home/claude/.openclaw/agents/felix-doc-auditor/sessions/<uuid>.jsonl \
    --out /tmp/per-outcome.json
```

The script:

- Parses the JSONL one record at a time (no full-file load).
- Identifies tick boundaries via a user-message regex (default:
  `[.*UTC] Cron tick.`).
- Sums per-call `usage.input / output / cacheRead / cacheWrite`
  fields across the assistant messages within each tick.
- Heuristically classifies each tick's outcome from the closing
  assistant message text (`empty` / `debt_only` / `tier_a_apply` /
  `unknown`). Operator should spot-check before promoting.
- Emits either a per-outcome aggregation (default) or per-tick
  records (`--per-tick`).

The same script is used for the WP09 post-rework measurement against
the new driver's records, ensuring like-for-like comparison.

## How to add a new baseline

1. Pick a stable measurement window (typically 24-72h of natural
   traffic, or a synthetic suite for one-shot benchmarks).
2. Run the appropriate measurement script.
3. Author the JSON following the schema above.
4. Add a row to the **Current baselines** table.
5. Cross-reference the baseline from the mission's spec / acceptance
   notes so the NFR gate can find it.
6. Commit. The baseline is now the audit record — do not edit it
   after the fact; supersede it with a new file if a re-measurement
   is required.

## Reading order for related material

- Spec NFR-001 (≥80% token reduction): [`kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md`](../../../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md)
- Research D13 (Cost baseline methodology): in the mission's research index
- Tick-signal contract (post-rework counterpart data source): [`kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md`](../../../../kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/tick-signal.contract.md)
