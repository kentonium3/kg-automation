# Phase 0 — Research

**Mission**: `signal-driven-monitoring-haiku-gate-01KT22PC`
**Source issue**: [#490](https://github.com/kentonium3/kg-automation/issues/490)
**Spec**: [`spec.md`](./spec.md)

This document resolves the three open decisions deferred from spec (OD-1, OD-2, OD-3) and records design choices the planner made based on live-probe research of office2 and review of existing precedents.

---

## OD-1: Gate insertion mechanism — RESOLVED

**Decision**: Wrapper-based gate driver (no per-invocation model switch).

**Rationale**: Live-probe of `openclaw system heartbeat enable|disable|last` and `openclaw system event` on office2 confirms there is **no per-invocation model selector** on the OpenClaw heartbeat surface. The agent's model is set in `~/.openclaw/openclaw.json` under `agents.list[id=main].model` and applies to every invocation of that agent.

**Architecture**:
1. Disable OpenClaw's internal heartbeat scheduler (`openclaw system heartbeat disable`) so it does not fire concurrently with our gate.
2. New systemd user timer (`felix-heartbeat-gate.timer`) fires every 30 min (matching the historical cadence).
3. Gate script (Python, Anthropic SDK direct, Haiku 4.5) reads the current heartbeat context (digest snapshot, HEARTBEAT.md, recent novelty markers) and emits one of three outcomes.
4. On `ESCALATE_TO_SONNET`, the gate invokes `openclaw system event --text "<gate reason>" --mode now`, which wakes the existing `main` agent (Sonnet 4.6) with the reason as context. The main agent's invocation path is unchanged from today — only the *trigger* changes.
5. On `HEARTBEAT_OK` or `LOG_AND_SKIP`, the gate writes a structured record to `last-gate-decision.json` and exits.

**Alternatives considered**:
- *Editing OpenClaw config to switch the main agent's model to Haiku for the heartbeat case*: rejected — the model is per-agent, not per-trigger, so this would also affect WhatsApp DM handling.
- *Patching OpenClaw to add a heartbeat-specific model override*: rejected — upstream change, and we already established that OpenClaw upstream changes are out of scope (C-003).

**Reference**: `felix-doc-auditor` post-#343 is the canonical precedent for this Python-driver-as-systemd-oneshot pattern (`docs/runbooks/doc-auditor-driver-ops.md`).

---

## OD-2: Threshold seed values — RESOLVED

**Decision**: Per-signal thresholds for the three FR-006 signals, calibrated against the 2026-06-01 log.

**Ground-truth counts** (from `/tmp/openclaw/openclaw-2026-06-01.log`, hours 00–17 UTC):

| Signal | Total events | Peak 15-min window | Typical noise floor |
|---|---|---|---|
| `whatsapp_creds_restore` | 193 | 14 | 0–2 |
| `web_watchdog_reconnect` (status 499 closures) | 149 | ~10 | 0–1 |
| `web_watchdog_timeout` (message-timeout-detected) | 147 | ~10 | 0–1 |
| `openclaw_unhandled_error` (logLevelName=ERROR) | 6 | 1 | 0 |

**Seed thresholds** (live filing from day one, per OD-3 = B; thresholds set to fire on real bursts but not on baseline noise):

| Signal ID | 15-min cycle threshold | 1-hour rolling threshold | Dedup window |
|---|---|---|---|
| `whatsapp_creds_restore` | ≥6 | ≥18 | 24h while open |
| `web_watchdog_reconnect` | ≥10 | ≥25 | 24h while open |
| `web_watchdog_timeout` | ≥10 | ≥25 | 24h while open |
| `openclaw_unhandled_error` | ≥3 | ≥5 | 24h while open |

On the 2026-06-01 log these thresholds would have fired between 3 and 5 times for the corruption pattern (clustered bursts at 00, 02, 03, 11, 14, 16 UTC), each within ≤1 cycle of the burst onset. None would have fired during the quiet hours.

**Alternatives considered**:
- *Single-window thresholds only (no rolling)*: rejected — rolling window catches "slow drip" patterns that don't peak in any single 15-min window but accumulate.
- *Higher thresholds (≥10 / ≥30) for "extra conservative"*: rejected — would have missed the 12:32–12:35 burst Felix originally reported, undermining the accuracy improvement we're chasing.

**Calibration plan post-rollout**: review the first 7 days of filings. If false-positive rate >10%, raise thresholds. If real incidents are missed, lower them. Threshold values live in a single config file (`config.toml` or equivalent) so changes don't require code edits.

---

## OD-3: Rollout shape — RESOLVED

**Decision**: Option B — live filing from day one with conservative thresholds (per Kent's plan-phase input).

**Implementation**:
- Filings use the normal label set (`P2-bug`, `area/<area>`, `spec: brief`) via the existing `felix-file-issue.py` body builder.
- Thresholds set per OD-2 — conservative enough to avoid noise-floor false positives, low enough to fire on real bursts within one cycle.
- The first 7 days are an observation window: review filings daily, tune thresholds in `config.toml`, redeploy.

**Rationale (per Kent)**: real incidents surface in the live queue immediately; the accuracy value is felt right away; mitigation for over-firing is straightforward (`gh issue close` + threshold tune).

**Alternatives considered**:
- A (observation-only with `felix-debug` label): rejected — extra cutover step; calibration window misses real-time signal value.
- C (hybrid with co-applied debug label): rejected — adds label-management complexity for marginal gain.

---

## Existing-pattern adoption

### Driver architecture: mirror `felix-doc-auditor` post-#343

- **Process model**: stateless Python oneshot per tick; nothing held in memory between ticks.
- **Schedule**: systemd user timer + service (oneshot) per existing pattern.
- **State**: GitHub (open issues, labels) + structured `last-tick.json` for health + JSONL ledger for per-event audit trail.
- **LLM access**: Anthropic SDK direct, not via OpenClaw. Haiku 4.5 with prompt caching.
- **Identity**: `kg-felix-bot` PAT (same as `felix-doc-auditor` per `credential-manifest.json`).
- **Health signal**: `last-tick.json` consumed by future alerting (matches the #327 contract).

This mission's filer is structurally similar to `felix-doc-auditor` but **with zero LLM in the file-issue path** — judgment is needed only for the gate decision in FR-2. The signal extraction, threshold check, dedup, and `gh issue create` invocation are all deterministic.

### Issue-body construction: reuse `felix-file-issue.py`

The filer shells out to `scripts/openclaw/agents/main/felix-file-issue.py` with the appropriate `--type bug`, `--problem-statement-file`, `--observed-context-file`, `--tier-hypothesis`, `--area`, `--priority` arguments. This guarantees that deterministic and LLM-authored filings produce structurally identical issue bodies (validates against `.github/ISSUE_TEMPLATE/bug.md`).

The filer does NOT compose `gh issue create` directly — it uses the existing helper.

### Source code placement

```
scripts/openclaw/observation/
├── summarize.py                 ← EXISTING — agent activity digest (untouched)
├── config.py                    ← EXISTING — agent registry loader (untouched)
├── log_action.py                ← EXISTING (untouched)
├── signals/                     ← NEW — signal-source modules
│   ├── __init__.py
│   ├── openclaw_log.py          ← shared log-tail + grep helpers
│   ├── creds_restore.py         ← FR-006 signal #1
│   ├── watchdog_reconnect.py    ← FR-006 signal #2
│   ├── watchdog_timeout.py      ← FR-006 signal #3 (combined into #2 if log shows 1:1 with reconnect)
│   └── unhandled_error.py       ← FR-006 signal #4 (logLevelName=ERROR)
├── state.py                     ← NEW — per-signal counter persistence
├── filer.py                     ← NEW — invokes felix-file-issue.py with structured args
├── tick.py                      ← NEW — entrypoint orchestrating signal extraction → filing
└── tests/                       ← extend existing with new modules
    ├── test_signals_creds_restore.py
    ├── test_state_persistence.py
    ├── test_filer.py
    └── test_replay_20260601.py  ← integration test against captured log

scripts/openclaw/heartbeat_gate/
├── __init__.py
├── gate.py                      ← entrypoint
├── prompts/
│   └── routing.prompt.md        ← cache-aware prompt for Haiku
├── context.py                   ← assembles digest + HEARTBEAT.md + novelty markers
├── escalator.py                 ← invokes `openclaw system event --mode now`
└── tests/
    ├── test_gate_no_signal.py
    ├── test_gate_with_signal.py
    └── test_gate_failure_fallback.py

scripts/office2/
├── felix-core-digest.service    ← MODIFIED — runs tick.py after summarize.py
├── felix-core-digest.timer      ← unchanged (15 min cadence)
├── felix-heartbeat-gate.service ← NEW
└── felix-heartbeat-gate.timer   ← NEW (30 min cadence)
```

**State directory layout** (per planning default — mirrors `felix-doc-auditor`'s `/data/services/openclaw/felix-doc-auditor-driver/`):

```
/data/services/openclaw/felix-core-digest-signals/
├── state/
│   ├── whatsapp_creds_restore.json
│   ├── web_watchdog_reconnect.json
│   ├── web_watchdog_timeout.json
│   └── openclaw_unhandled_error.json
├── last-tick.json
└── signals-ledger.jsonl            ← append-only per-event ledger

/data/services/openclaw/felix-heartbeat-gate/
├── last-gate-decision.json
└── gate-ledger.jsonl
```

---

## Test strategy

Per planning default:

1. **Unit tests** over fixture log lines (one `.jsonl` fixture per signal source under `tests/fixtures/`). Each signal extractor tested in isolation.
2. **State persistence tests** that write to a tmp directory, simulate restart, and verify count continuity.
3. **Filer tests** that mock the `felix-file-issue.py` subprocess and assert correct argument construction.
4. **Replay integration test** (`test_replay_20260601.py`) that runs the full tick orchestrator against a captured copy of `/tmp/openclaw/openclaw-2026-06-01.log` (copied into `tests/fixtures/captured/`) and asserts:
   - Expected number of filings per signal class
   - Filing scope (count/time-range) matches ground truth within tolerance (per NFR-004 / NFR-006)
   - No filings during the quiet baseline hours
5. **Gate tests** that mock the Anthropic SDK client and assert the gate's routing decisions for: empty digest (→ OK), digest with novel marker (→ ESCALATE with reason), HEARTBEAT.md with task (→ OK at cheap tier or ESCALATE), gate API failure (→ fallback to ESCALATE).

Coverage target: ≥85% line + ≥80% branch on new modules (mirrors `felix-doc-auditor` conventions). Pragma allowed on defensive checks per `reference_pytest_branch_coverage_pragma.md` memory.

---

## Loose periodic checks (email/calendar/mentions)

**Finding**: live-probe of `/data/services/openclaw/data/HEARTBEAT.md` shows the file contains only template text. The "loose periodic checks" described in `AGENTS.md` (email/calendar/mentions polling) are not actively configured today.

**Implication for this mission**: no migration of existing loose-periodic-check work is needed. Today's heartbeat is doing only opportunistic observation. If Kent later wants email/calendar polling, those become explicit cron jobs or new signal definitions — out of scope for this mission per spec §9.

---

## Cost estimate (post-rollout)

| Path | Frequency | LLM tokens (input) | LLM tokens (output) | Daily cost (Sonnet 4.6 / Haiku 4.5) |
|---|---|---|---|---|
| felix-core-digest signal extraction | 96 cycles/day | 0 | 0 | $0 |
| Issue filing (deterministic) | ~1–5/day est | 0 | 0 | $0 |
| Heartbeat gate | 48 ticks/day | ~2K input (Haiku, cached) | ~200 (Haiku) | ~$0.05–0.10/day |
| Escalation to Sonnet | Estimate 2–5/day | ~30K (full context) | ~1K | $0.50–1.50/day |
| **Total est.** | | | | **~$0.55–1.60/day** |

Baseline (current Sonnet heartbeat): ~$3–7/day (rough — actual depends on per-tick context size). The ≥80% reduction target in NFR-001 looks achievable if Sonnet escalations stay ≤5/day.

A pre-rollout token baseline run will be captured per the `felix-doc-auditor` baselines pattern and stored at `docs/design/architecture/baselines/felix-heartbeat-gate-pre-rollout.json` so post-rollout cost can be measured against ground truth, not estimates.
