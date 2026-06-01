# Quickstart — Signal-Driven Monitoring with Haiku Gate

**Mission**: `signal-driven-monitoring-haiku-gate-01KT22PC`
**Audience**: Operator (Kent) and any agent that needs to deploy, observe, or extend this system.

---

## What you get

Two cooperating loops on office2:

1. **Signal-extraction loop** (every 15 min, no LLM) — scans OpenClaw logs for defined signal patterns. When a signal trips its threshold, files a GitHub issue via `kg-felix-bot` with accurate event counts and time ranges.
2. **Heartbeat gate loop** (every 30 min, Haiku → optional Sonnet) — replaces OpenClaw's general-purpose Sonnet heartbeat. The gate inspects the latest signal-extraction output and HEARTBEAT.md, decides whether to escalate, and only invokes Sonnet on novel/ambiguous signal.

---

## 30-second health check

```bash
ssh office2-claude 'cat /data/services/openclaw/felix-core-digest-signals/last-tick.json | jq "{exit_status, started_at_utc, errors, issues_filed}"'
```

```bash
ssh office2-claude 'cat /data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json | jq "{outcome, started_at_utc, errors, fallback_invoked}"'
```

Expected for both: `errors == []`, `started_at_utc` within last 30 min.

---

## Force a manual tick

Signal extraction:
```bash
ssh office2-claude 'systemctl --user start --wait felix-core-digest.service'
```

Heartbeat gate:
```bash
ssh office2-claude 'systemctl --user start --wait felix-heartbeat-gate.service'
```

Both are oneshots; `--wait` blocks until they exit.

---

## Add a new signal

1. Edit `scripts/openclaw/observation/signals/config.toml` in the repo.
2. Add a `[signals.<your_signal_id>]` block matching the schema in [`contracts/signal-config.contract.md`](./contracts/signal-config.contract.md).
3. Commit, push.
4. Deploy to office2 (use the existing deploy script — same path as `felix-doc-auditor` deployment).
5. The next 15-min cycle picks it up. No restart needed.

Validate against the 2026-06-01 replay before going live:
```bash
python3 scripts/openclaw/observation/tick.py --dry-run --replay tests/fixtures/captured/openclaw-2026-06-01.log
```

---

## Tune a threshold

1. Edit the relevant `cycle_threshold` / `rolling_threshold` in `config.toml`.
2. Push, deploy.
3. Next cycle uses new values.

Common signals that may need tuning during the first-week observation window: `whatsapp_creds_restore`, `web_watchdog_reconnect`. See [`research.md`](./research.md) §OD-2 for seed values and rationale.

---

## Disable / re-enable

Per signal:
```toml
[signals.<id>]
enabled = false
```

Globally (kill switch — leaves digest summarization running but stops issue filing):
```bash
ssh office2-claude 'systemctl --user stop felix-core-digest.service && systemctl --user disable felix-core-digest.timer'
```

Heartbeat gate kill switch (falls back to OpenClaw's old behavior if you re-enable OpenClaw heartbeats):
```bash
ssh office2-claude 'systemctl --user disable --now felix-heartbeat-gate.timer'
ssh office2-claude 'openclaw system heartbeat enable'   # re-enable old path
```

---

## Investigate a filed issue

Each filing leaves a row in the signals ledger that maps issue → cycle → log evidence:

```bash
ssh office2-claude 'grep ''"issue_number": 491'' /data/services/openclaw/felix-core-digest-signals/signals-ledger.jsonl | jq'
```

This gives you: `cycle_id`, the exact count snapshot at filing time, the signal config that was in effect, and the source log path. To inspect the raw log lines that triggered the filing:

```bash
ssh office2-claude 'grep "restored corrupted WhatsApp creds.json" /tmp/openclaw/openclaw-$(date -u +%Y-%m-%d).log | head -10'
```

---

## Audit gate decisions

To see the gate's recent routing decisions:

```bash
ssh office2-claude 'tail -10 /data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl | jq -c "{started_at_utc, outcome, reason}"'
```

To find the most recent ESCALATE:

```bash
ssh office2-claude 'grep ''"outcome":"ESCALATE_TO_SONNET"'' /data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl | tail -1 | jq'
```

---

## When something looks wrong

| Symptom | First check |
|---|---|
| No issues filed for a known burst | `last-tick.json` `signals_evaluated[*].count_cycle` — did the extractor see the events? If yes, check threshold; if no, check `source_path_pattern` matches the log path. |
| Duplicate issues filed for same signal | `last_filed_issue_ref` state file out of sync with GitHub. Inspect state JSON; if `last_filed_issue_ref` points to a closed issue while a new one was filed, that's correct (dedup on open only). If two new issues for the same open ref, file a P2-bug. |
| Gate always escalates | Check `last-gate-decision.json.fallback_invoked` — sustained `true` = gate side broken (likely Anthropic API or credentials). Inspect `/data/services/openclaw/secrets/anthropic`. |
| Heartbeat never fires | Confirm `openclaw system heartbeat disable` was applied AND `felix-heartbeat-gate.timer` is enabled. Two timers running together would double-fire. |
| `kg-felix-bot` identity mismatch | `felix-file-issue.py` refuses to file when active gh identity isn't kg-felix-bot. Run `ssh office2-claude 'gh auth status'` to verify. |

---

## Cost & token usage

Token usage per gate tick is in `last-gate-decision.json` under `gate_input_tokens`, `gate_cache_hit_tokens`, `gate_output_tokens`. Per-tick math:

```
billed_input = (gate_input_tokens - gate_cache_hit_tokens) + gate_cache_hit_tokens * 0.10
```

For monthly cost estimation: `billed_input × 48 ticks/day × 30 days × Haiku-4.5 input price` plus the equivalent for output.

Sonnet escalations are billed via OpenClaw's existing budget; not separately tracked by the gate.

A pre-rollout baseline lives at `docs/design/architecture/baselines/felix-heartbeat-gate-pre-rollout.json` — re-baseline annually or after any of the conditions listed in `felix-doc-auditor`'s baseline runbook.

---

## Cross-references

- [Spec](./spec.md)
- [Research](./research.md) — design decisions and OD resolutions
- [Data model](./data-model.md)
- [Contract — signal config](./contracts/signal-config.contract.md)
- [Contract — tick signal](./contracts/tick-signal.contract.md)
- [Contract — gate decision](./contracts/gate-decision.contract.md)
- [Contract — filer invocation](./contracts/filer-invocation.contract.md)
- **Architectural precedent**: [`docs/runbooks/doc-auditor-driver-ops.md`](../../docs/runbooks/doc-auditor-driver-ops.md)
- **Source issue**: [#490](https://github.com/kentonium3/kg-automation/issues/490)
