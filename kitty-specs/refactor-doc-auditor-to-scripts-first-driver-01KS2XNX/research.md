# Research: Refactor doc-auditor to scripts-first driver

**Mission**: `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX` (#343)
**Phase**: 0 (research — pre-design)
**Date**: 2026-05-20

This document resolves every outstanding clarification from the spec's Assumptions section and every plan-phase decision raised during the planning interrogation. Decisions here become inputs to Phase 1 (data-model.md, contracts/, quickstart.md).

---

## Environment validation (spec Assumptions 1–7)

All seven spec Assumptions were verified live against office2 during research. Results:

| # | Assumption | Result | Evidence |
|---|---|---|---|
| 1 | Direct Anthropic API access from office2 as `claude` user | ✅ Confirmed | Backup secret file at `/data/services/openclaw/secrets/anthropic` (ASCII text, mode 0640, `sk-ant-api03-...` format, 109 bytes, group `felix`); claude user reads it cleanly. Primary openclaw-native copy at `/home/claude/.openclaw/agents/main/agent/auth-profiles.json` (not needed by new driver). |
| 2 | `gh` CLI auth as `kg-felix-bot` accessible | ✅ Confirmed | `gh auth status` reports active account `kg-felix-bot`, token at `/home/claude/.config/gh/hosts.yml`, scopes `read:org,repo,workflow`. Direct reuse by the new driver — no auth change needed. |
| 3 | `felix-file-issue.py` stable for debt-issue filing | ✅ Confirmed | Verified end-to-end on 2026-05-19 (per session work resolving #291 false-reopen). Helper present at `/home/claude/kg-automation/scripts/openclaw/agents/main/felix-file-issue.py`. |
| 4 | Activity log location writable | ✅ Confirmed | `/home/kgale/second-brain/agents/logs/` is group `secondbrain`, mode `drwxrwxr-x`; live touch-and-delete test as claude user succeeded. |
| 5 | Upstream `Doc audit:` workflow continues | ✅ Confirmed | `.github/workflows/doc-audit-trigger.yml` and `doc-audit-weekly.yml` operational; out-of-scope per spec C-002. |
| 6 | `handle_audit_routing.py` reusable as deterministic kernel | ✅ Confirmed | 36 KB Python at `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py`; CLI-driven, well-structured, takes serialized audit-state JSON; partitions proposals by allowlist; applies edits + commits; files pending-approval; posts summary; closes audit. Exit codes 0–5. |
| 7 | Existing systemd timer cadence + 30-min envelope acceptable | ✅ Acceptable | `OnCalendar=hourly`, `TimeoutStartSec=30min`. No timer change is part of this mission. |

**Bonus discovery — signal-driven pipeline more built-out than spec implied**: research surfaced an existing 12-mapping `signal-to-doc-map.json` artifact and a 323-line `handle_drift_events.py` helper that consumes `audit.sh`-emitted drift events (drift-events.jsonl at `/data/services/security-monitor/logs/`). This is the **second active signal source today**, alongside the GH-Actions commit triggers. The driver must consume both. See D4 below for the adapter design that handles this.

---

## D1: Anthropic SDK + Model + Credential Path

**Decision**: Use the official `anthropic` Python SDK targeting `claude-haiku-4-5`. The driver reads the API key from `/data/services/openclaw/secrets/anthropic` (one-line ASCII file containing the `sk-ant-api03-...` value) at process startup and constructs the SDK client. The key is never logged, never persisted elsewhere, and never echoed.

**Rationale**:
- **Model choice (Haiku 4.5)**: matches today's `anthropic/claude-haiku-4-5` baseline (per spec Q1=A). The ≥80% NFR-001 token reduction is therefore an apples-to-apples comparison driven by prompt-size shrinkage, not a model swap.
- **SDK choice**: the official `anthropic` Python SDK is the canonical surface, supports prompt caching, retries, and rate-limit handling natively. No reason to roll our own HTTP layer.
- **Credential path**: the backup file is already accessible to the claude user (verified). Reading a one-line file is simpler than configuring systemd `EnvironmentFile`, and avoids coupling the driver to openclaw's native auth-profiles.json format (which is what we're trying to escape).

**Alternatives considered**:
- **ENV variable injection via systemd `EnvironmentFile`** — rejected. Would require updating the systemd unit to pass `Environment=ANTHROPIC_API_KEY=...` or `EnvironmentFile=/data/services/openclaw/secrets/anthropic.env`. Adds a moving part that isn't necessary when direct file read works.
- **Reading from openclaw's `auth-profiles.json`** — rejected. Couples the driver to openclaw internals we're explicitly retiring (per spec FR-010).
- **Generic HTTP via `requests`** — rejected. Loses prompt-cache semantics (cache-control headers are SDK-mediated), retry logic, and the official client's rate-limit guidance.

---

## D2: Prompt Caching Strategy

**Decision**: Use Anthropic's ephemeral prompt-cache markers (`cache_control: {"type": "ephemeral"}`) on the boilerplate prefix of each judgment-prompt template. Cache TTL is 5 minutes (default). Cache hit pricing on Haiku 4.5 is ~10% of input-token cost.

**Rationale**:
- Per Q1=D, prompt caching layers on top of model choice.
- Each judgment prompt has a stable boilerplate section (rule recap, output-format guidance, persona framing — the part the LLM needs to interpret the question) and a per-call variable section (the specific diff / file / question being judged).
- Q3=B (full-queue per tick) means multiple judgment calls within the 5-minute TTL window during a non-empty tick. Cache amortization is real, not theoretical.
- Cache-aware structure: place the variable section AFTER the cached boilerplate so the cache prefix is invariant per template.

**Alternatives considered**:
- **No caching** — rejected by Q1=D.
- **Cache-control on every section** — rejected. Cache markers cost token-budget to declare; over-marking reduces effective discount and complicates the prompt structure.
- **Longer TTL via beta cache extension** — rejected. The 5-min TTL aligns with tick frequency anyway; beta features add stability risk for marginal benefit.

---

## D3: Helper Reuse Pattern (subprocess vs library)

**Decision**: Hybrid. Keep `handle_drift_events.py` and `handle_audit_routing.py` as CLI entry points (preserving the existing bash-invocable contract documented in today's AGENTS.md §2 and §7.7), AND refactor each module to expose its building-block functions as importable Python so the new driver can call them directly. Standard `if __name__ == "__main__":` guard pattern. No behavioral change to the CLI surface.

**Rationale**:
- **Zero-disruption**: the CLI invocation continues to work during cutover and after (in case any external consumer still calls them).
- **Test surface**: importable building blocks let the driver mock at the function level rather than at the subprocess level, which is much cleaner for pytest.
- **Subprocess overhead**: each invocation incurs Python startup + GIL warmup + argparse + JSON decode. Per-tick this could add 1–2 seconds across multiple helper calls — non-trivial under high backlog.
- The two helpers are already well-structured Python; this is a refactor of import surface, not a rewrite.

**Alternatives considered**:
- **Subprocess-only (current pattern)** — rejected for the test-surface and overhead reasons above.
- **Library-only (remove CLI entry points)** — rejected. Breaks any external consumer that still invokes them via bash; also makes them less debuggable from the operator's terminal.

---

## D4: Signal-Source Adapter Abstraction

**Decision**: Define a `SignalSource` Protocol (PEP 544 typing.Protocol) with a `pending(self) -> Iterable[Signal]` method returning normalized signal objects. Initial concrete adapters:

- **`GHIssueSignalSource`** — consumes `Doc audit:` and `Weekly doc audit —` GitHub issues. Today this single adapter handles three upstream producers: commit-driven (`doc-audit-trigger.yml`), weekly cron (`doc-audit-weekly.yml`), and signal-driven (issues filed by `handle_drift_events.py` when audit.sh drift events match a mapping in signal-to-doc-map.json).
- **`DriftEventSignalSource`** — wraps `handle_drift_events.py`. Each tick, invokes the helper (or imports its functions per D3) to advance the cursor through `drift-events.jsonl`. Mapped events become GH issues (consumed in the same tick or the next via `GHIssueSignalSource`); unmapped events accumulate in `unmapped-events.jsonl` for future AI review.

The two adapters are composed at the top level by the driver, which iterates through them in priority order (pending-approval decisions first, then new audits, then drift events).

**Rationale**:
- Q3=A: anticipate multi-source from the start.
- Today's pipeline already has multiple effective sources (3 producers feeding the single GH-issue surface; one drift-events JSONL surface). The driver MUST handle both surfaces.
- Future sources (file-watch, package-registry-watch, etc.) can register as additional adapters without touching the driver's orchestration loop.
- Protocol-based (vs ABC-based): more pythonic, no runtime registration ceremony, plays well with mypy/pyright.

**Alternatives considered**:
- **Single concrete signal type** — rejected by Q3=A and by the discovered reality of multiple sources.
- **Plugin architecture (entry points, dynamic discovery)** — rejected. Over-engineering for 2 adapters; we can refactor toward plugins if/when the count crosses ~4.
- **Inheritance-based ABC** — rejected. Protocol is the modern choice; no behavioral inheritance is needed.

---

## D5: Test Strategy

**Decision**: Pytest with three test layers:

1. **Unit** — mocked `gh` subprocess + mocked `anthropic.Anthropic` client + filesystem fixtures. Covers each driver building block in isolation: signal-source adapters, LLM judgment helpers, decision-application logic, tick-signal writer.
2. **Integration (still mocked)** — full driver run with mocked external surfaces but real internal wiring. Covers all 5 tick outcomes (empty, debt-only, Tier-A apply, pending-approval-apply, pending-approval-reject) and the 4 edge cases from spec User Scenarios (LLM outage, rate-limit, missing-file, stuck-lock).
3. **Live smoke** — `tests/doc_audit/test_smoke_live.py` gated by `pytest -m live_smoke` (skipped in CI). Hits real GitHub against a synthetic test audit issue in `kentonium3/kg-automation` (or a sandbox repo) and a real Anthropic API call. Run manually pre-deploy and again post-deploy as part of the verification checklist.

**Rationale**:
- Q4=A. Aligned with existing test patterns: `tests/inbox/` (85 passing tests for a similar shape) and `tests/habits/` (320 passing, 90% coverage).
- Mocked tests give fast feedback in CI; the live smoke is the one fidelity floor that catches integration drift (auth surface, API shape changes, rate-limit behaviour).
- The five tick-outcome scenarios + four edge cases yield ~9 integration tests covering the full spec User Scenarios surface.

**Alternatives considered**:
- **Recorded cassettes (vcrpy)** — rejected. Marginal benefit for ~1–2 KB prompts; adds a dependency.
- **Mocked-only (no live)** — rejected. Drops a critical fidelity floor for a rework whose entire purpose is restoring confidence.
- **Live integration in CI** — rejected. Real credentials in CI is operational debt; live tests run manually or in a designated post-deploy job.

---

## D6: Driver Invocation Contract

**Decision**: Single entry point `python3 scripts/doc_audit/run.py` invoked by systemd as a oneshot. CLI args:

```
python3 scripts/doc_audit/run.py
  [--dry-run]            # print intended actions, do not mutate
  [--once]               # default; process the queue once and exit (matches systemd oneshot)
  [--source <name>]      # restrict to a single signal source (testing)
  [--config <path>]      # override default config path
```

Exit codes:
- `0` — success (queue drained or steady-state)
- `1` — unrecoverable error (no signals processed)
- `2` — partial (some signals processed, some failed — see tick signal for details)

systemd unit `ExecStart` changes from:
```
/usr/bin/openclaw agent --agent felix-doc-auditor --message '...' --timeout 1500
```
to:
```
/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py
```

**Rationale**:
- Mirrors `handle_drift_events.py` and `handle_audit_routing.py` CLI shape — operator continuity.
- Single oneshot per tick matches existing systemd semantics; no change to the timer.
- Exit-code surface (0/1/2) is consumable by systemd's MainPID status reporting AND by future `felix-alert` (#327).
- `--dry-run` is essential for operator confidence during cutover and ongoing investigation.

**Alternatives considered**:
- **Library-only (no CLI)** — rejected. systemd needs an executable; an external Python module wouldn't be the right systemd target.
- **Long-running daemon (poll loop)** — rejected. Today's workload is hourly and bursty; oneshot is correct.
- **Subcommands (`run.py tick`, `run.py status`, etc.)** — rejected for v1. May add later if the surface grows; keep simple now.

---

## D7: Structured Tick Signal Format

**Decision**: JSON artifact at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json`, atomically written (tempfile + os.rename). Schema:

```json
{
  "schema_version": "1.0",
  "timestamp_utc": "2026-05-20T16:00:00Z",
  "status": "success",
  "exit_code": 0,
  "driver_version": "0.1.0",
  "duration_seconds": 7.3,
  "signals_processed": 2,
  "audits_processed": 2,
  "pending_approvals_applied": 0,
  "debt_filed": 1,
  "tier_a_committed": 1,
  "drift_events_consumed": 0,
  "next_scheduled_tick_utc": "2026-05-20T17:00:00Z",
  "errors": []
}
```

Companion: each tick also writes a one-line summary to stdout (consumed by systemd journal), matching the pattern from `handle_drift_events.py`:

```
SUMMARY: status=success audits=2 debt=1 tier_a=1 drift=0 dur=7.3s
```

**Rationale**:
- NFR-004: structured signal consumable by a separate process without parsing LLM prose. JSON + journal line is the lowest-common-denominator format.
- Atomic write ensures any reader sees a complete state (no partial JSON).
- `last-tick.json` is "current state" semantics, not log/history. Trivial for `felix-alert` to consume: read the file, check timestamp + status + exit_code.
- `schema_version` allows future evolution without breaking consumers.

**Alternatives considered**:
- **Append-only JSONL** — rejected. "Current state" is what alerting consumes; history can be reconstructed from systemd journal if needed.
- **systemd journal only (no artifact)** — rejected. Journal queries are slower and harder to integrate; a single JSON file is trivial.
- **Schema-less JSON** — rejected. `schema_version` is cheap insurance.

---

## D8: handle_drift_events.py Cursor Location

**Decision**: Preserve the existing cursor at `/data/services/security-monitor/.drift-events.cursor` (the helper's documented default per its argparse). The driver invokes the helper (or its imported functions) with the same `--cursor` argument as today's AGENTS.md §2 invocation.

**Rationale**:
- Zero-disruption preservation of the existing processed-line position across cutover.
- handle_drift_events.py's atomic cursor-write semantics are already correct (verified in source).
- Moving the cursor would orphan the existing state and risk re-processing every event already filed since 2026-05-14 (when #278 shipped).

**Alternatives considered**:
- **Relocate cursor under driver-owned path** — rejected for the orphaning risk.
- **Reset cursor at cutover** — rejected. Same orphaning effect, plus would re-file every drift event as a duplicate Doc audit: issue.

---

## D9: Drift-Event Processing Cadence

**Decision**: Driver invokes the drift-event processing path (D3 import or D8 subprocess) ONCE per tick, BEFORE the GH-issue signal scan. Preserves today's AGENTS.md §2-before-§3 ordering.

**Rationale**:
- `audit.sh` appends to `drift-events.jsonl` daily at 03:00 UTC. Hourly invocation is over-frequent but harmless — the cursor makes re-runs no-ops when no new events.
- Calling drift-event processing before GH-issue scan means any audit issues filed by drift-event processing are picked up in the SAME tick. Tighter latency than waiting for the next tick.
- Today's AGENTS.md §2-before-§3 ordering is preserved; operator mental model continuity.

**Alternatives considered**:
- **Top-of-day only** — rejected. Adds scheduling complexity for marginal savings; existing pattern is simpler.
- **After GH-issue scan** — rejected. Would force one-tick latency between drift-event detection and audit processing.

---

## D10: Cutover Sequence

**Decision**: 5-step fail-forward deploy when queue is drained:

1. **Pre-flight**: confirm queue state — `gh issue list --label "Doc audit:,status:in-progress" --state open` returns zero results; `gh issue list --label "audit-pending-approval" --state open` is either empty or all entries have decision labels applied.
2. **Merge to main**: driver mission ships its commits including the systemd unit template change at `scripts/office2/felix-doc-auditor.service` (new ExecStart).
3. **Apply on office2**: `scripts/office2/deploy/felix-doc-auditor-driver.sh --apply` — rsyncs driver into `/home/claude/kg-automation/scripts/doc_audit/`, creates `/data/services/openclaw/felix-doc-auditor-driver/`, installs the new systemd unit, `systemctl --user daemon-reload`, removes the openclaw agent registration (deregister via openclaw CLI), deletes `/data/services/openclaw/felix-doc-auditor/` workspace files.
4. **Verification tick**: `systemctl --user start --wait felix-doc-auditor.service` — drives one tick under the new driver; inspect `last-tick.json` and `journalctl --user -u felix-doc-auditor`. If anything is off, NOT auto-reverted (per C-007); operator either patches forward or files a follow-on.
5. **Confirm soak**: monitor `journalctl` and `last-tick.json` over the next 7 days against the 95% NFR-002 threshold.

**Rationale**:
- C-007 fail-forward: no automatic revert.
- C-004 queue-drained: ensures no in-flight pending-approvals get orphaned.
- Verification tick before next cron fire catches deploy errors immediately.
- One-way deletion of openclaw agent files satisfies FR-010 (fully retire).

**Alternatives considered**:
- **Phased dual-path** — rejected per Q1=C and C-007.
- **Revert-on-error** — rejected per C-007 fail-forward.
- **Deploy without queue drain** — rejected per C-004.

---

## D11: Operator Quick-Reference Scope

**Decision**: Update operator quick-reference at three surfaces during this mission:

1. **Memory file** `~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/reference_felix_doc_auditor_ops.md` — rewrite to reflect driver-based ops model.
2. **`docs/design/architecture/felix-d6-survey.md`** — append a note acknowledging that #343 obsoletes the survey's "LOW PRIORITY" verdict for felix-doc-auditor (the survey assessed further helper extraction; #343 changed the orchestration layer above the helpers).
3. **New runbook `docs/runbooks/doc-auditor-driver-ops.md`** — full operator reference covering invocation, structured signal interpretation, where prompt templates live, deploy steps, troubleshooting.

**Rationale**:
- FR-013 spec requirement.
- The d6-survey verdict is misleading post-#343; updating it prevents future confusion about why this rework was needed despite the survey saying "low priority."
- A dedicated runbook gives the operator a single load-bearing reference.

---

## D12: Prompt Template Inventory

Per FR-011, the three LLM judgment prompts (from Q2=C) become checked-in artifacts in `scripts/doc_audit/prompts/`:

- **`prompts/tier_classification.prompt.md`** — given a proposed edit + the candidate file's frontmatter + the audit issue area labels, classify as `tier_a` (frontmatter-only autonomous) or `judgment` (file as docs-debt).
- **`prompts/debt_body_generation.prompt.md`** — given a documented gap (artifact path, gap description, evidence), produce a docs-debt issue body that meets §8 template: Artifact / Gap / Area / Cross-references / Draft outline / Success criteria.
- **`prompts/cross_file_implication.prompt.md`** — given a commit diff + the in-scope file list + the touched-files set, identify any non-touched in-scope docs that may have implied drift.

Each prompt artifact has:
- A header with version + last-updated date
- The boilerplate section (rule recap + output-schema guidance) marked for prompt caching
- The variable-input placeholders
- The expected response schema (JSON for tier_classification and cross_file_implication; markdown body for debt_body_generation)

**Rationale**:
- FR-011 requires checked-in, reviewable prompt artifacts.
- Cache-aware structure per D2.
- Schema in each prompt enables structured response parsing (no need to rely on LLM markdown formatting).

---

## D13: Anthropic Cost Baseline Methodology

**Decision**: Measurement methodology per NFR-001 (≥80% reduction across representative tick mix):

**Baseline measurement** (PRE-cutover):
1. Capture three live ticks of today's openclaw-agent-mediated auditor invocation under a known queue mix (one empty tick, one debt-only tick, one Tier-A apply tick).
2. Sum input + output tokens reported by openclaw's existing telemetry. If openclaw doesn't report tokens, instrument by reading session jsonl and counting via the `anthropic.tokens.count` API endpoint applied to the cumulative session content.
3. Record per-outcome and averaged values in `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json`.

**Post-rework measurement** (POST-cutover):
1. The new driver's tick signal includes input_tokens, output_tokens, and cache_hit_input_tokens fields (parsed from each Anthropic SDK response per call, summed per tick).
2. Capture three ticks under matched outcome distribution.
3. Compute reduction ratio per outcome and on average.
4. Record in `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json`.

**Acceptance**: ≥80% averaged reduction; report per-outcome breakdown.

**Rationale**:
- NFR-001 requires the measurement be repeatable in 6 months — committing the baseline and methodology files makes that automatic.
- Tracking cache_hit_input_tokens separately makes the cache contribution visible.

**Alternatives considered**:
- **Estimate via prompt-size shrinkage only** — rejected. Less rigorous; doesn't account for output tokens or cache effects.
- **Single representative tick** — rejected. Outcome mix matters; a single tick is not representative.

---

## D14: Python Package Layout

**Decision**: `scripts/doc_audit/` becomes a Python package with the following internal structure:

```
scripts/doc_audit/
├── __init__.py
├── run.py                 # CLI entry point (D6)
├── config.py              # config dataclass + load_config()
├── signals/
│   ├── __init__.py
│   ├── base.py            # SignalSource Protocol + Signal dataclass
│   ├── gh_issue.py        # GHIssueSignalSource
│   └── drift_event.py     # DriftEventSignalSource (wraps handle_drift_events.py)
├── judgment/
│   ├── __init__.py
│   ├── client.py          # Anthropic SDK wrapper + prompt-cache helpers
│   ├── tier_classification.py
│   ├── debt_body_generation.py
│   └── cross_file_implication.py
├── prompts/
│   ├── tier_classification.prompt.md
│   ├── debt_body_generation.prompt.md
│   └── cross_file_implication.prompt.md
├── routing/
│   ├── __init__.py
│   └── apply_decisions.py # wraps handle_audit_routing.py imports
├── output/
│   ├── __init__.py
│   ├── tick_signal.py     # writes last-tick.json atomically
│   └── activity_log.py    # appends to /home/kgale/second-brain/agents/logs/
└── README.md              # in-tree dev/test guide
```

**Tests** in `tests/doc_audit/` mirror the package layout (unit per module + integration tests at top-level).

**Rationale**:
- Module separation by concern (signals vs judgment vs routing vs output) maps cleanly to FR boundaries.
- Importable from anywhere via `from doc_audit.signals import GHIssueSignalSource`.
- Prompt artifacts colocated with the code that uses them (FR-011 reviewability).
- Mirrors the structure of existing well-tested packages in the repo.

**Alternatives considered**:
- **Flat module (single run.py file)** — rejected. ~600+ LOC across concerns; hard to test.
- **Multiple top-level packages** — rejected. Premature scaling.

---

## Open Questions

These are flagged for resolution during Phase 1 (data-model / contracts / quickstart) or before merge:

1. **handle_audit_routing.py library refactor scope** — D3 says hybrid (CLI + library). Plan phase needs to determine whether the library refactor lands as part of this mission (touching shared code) or as a follow-on. Recommendation: in-mission, gated on the existing tests passing post-refactor.

2. **Deploy script `felix-doc-auditor-driver.sh`** — does an analogous deploy script exist for the current felix-doc-auditor? D10 step 3 assumes we author one. Check `scripts/office2/deploy/` for existing patterns.

3. **Anthropic prompt caching pricing on Haiku 4.5** — verify the documented 10% cache-hit pricing applies (this is from general knowledge; should confirm against Anthropic's current pricing page before counting on it in D13's measurement plan).

---

## Cross-references

- **Spec**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md`
- **Quality checklist**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/checklists/requirements.md`
- **D6 survey (prior analysis)**: `docs/design/architecture/felix-d6-survey.md`
- **Signal mapping**: `docs/design/architecture/data/signal-to-doc-map.json`
- **Helper-script conventions**: `docs/design/helper-script-conventions.md`
- **Existing helpers (reusable)**: `scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py`, `handle_audit_routing.py`
- **Canonical issue-filing helper**: `scripts/openclaw/agents/main/felix-file-issue.py`
- **Issue**: [#343](https://github.com/kentonium3/issues/343)
- **Epic predecessor**: [#278](https://github.com/kentonium3/issues/278)
- **Future consumer**: [#327](https://github.com/kentonium3/issues/327)
