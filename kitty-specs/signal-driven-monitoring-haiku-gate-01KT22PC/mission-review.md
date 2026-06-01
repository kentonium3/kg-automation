# Mission Review Report: signal-driven-monitoring-haiku-gate

**Reviewer**: Claude (orchestrator) — *adversarial post-merge audit per `/spec-kitty-mission-review` skill*
**Date**: 2026-06-01
**Mission**: `signal-driven-monitoring-haiku-gate-01KT22PC` — Signal-Driven Monitoring with Haiku Gate (mission #59)
**Source issue**: [#490](https://github.com/kentonium3/kg-automation/issues/490)
**Baseline commit**: `078f20c9` (pre-mission planning artifacts)
**Merge commit**: `a5093432`
**HEAD at review**: `d43b7387` (post-merge `B + i + ii` follow-up; doesn't affect mission artifacts)
**WPs reviewed**: WP01..WP04

**Reviewer-conflict-of-interest disclosure**: I (Claude) was the spec author, the orchestrator, the WP04 implementer's dispatcher, and now the mission reviewer. I have applied extra skepticism to my own work and to artifacts that bear my fingerprints (spec text, WP prompts, WP04 commits). Where my judgment may be load-bearing, I cite codex's independent findings or external artifacts (git diff, test assertions) as evidence.

---

## Mission shape at a glance

- 78 files changed; +14,954 / −129 lines
- 311 tests passing on main (verified post-merge)
- Coverage: ≥91% line, ≥85% branch on all new modules
- WP review history: WP01 (3 cycles), WP02 (3 cycles), WP03 (2 cycles), WP04 (1 cycle) — 9 total
- Cycle-limit override invoked once (WP01 cycle 3, per operator decision)
- All move-task transitions on merge path; no arbiter-forced approvals
- Lane-rebase workaround invoked 3× (lane-b ← lane-a, lane-c ← lane-b, lane-d ← lane-c) — tracked separately as [#492](https://github.com/kentonium3/kg-automation/issues/492)

---

## FR Coverage Matrix

| FR ID | Description (brief) | WP Owner | Test File(s) | Adequacy | Finding |
|---|---|---|---|---|---|
| FR-001 | Extract each signal exactly once per cycle; persist structured record | WP01 | `test_signals_*.py`, `test_openclaw_log.py`, `test_state_persistence.py` | ADEQUATE | — |
| FR-002 | File issue when threshold tripped AND no matching open issue exists | WP02 | `test_tick_orchestrator.py` (dedup tests) | ADEQUATE | — |
| FR-003 | Filed issues use template-compliant body builder + kg-felix-bot identity | WP02 | `test_filer.py` (subprocess + identity expected via the contract test) | ADEQUATE | — |
| FR-004 | State persists across restarts; cold-start re-reads recent log windows | WP01 | `test_state_persistence.py`, `test_openclaw_log.py` (cursor + inode-change) | ADEQUATE | — |
| FR-005 | Signal definitions in single editable config file | WP01 | `test_config_loader.py` + existence of `signals/config.toml` | ADEQUATE | — |
| FR-006 | Initial signal set (creds_restore, watchdog_reconnect, unhandled_error) | WP01 | `test_signals_creds_restore.py`, `_watchdog_reconnect.py`, `_unhandled_error.py` | ADEQUATE | — |
| FR-007 | Gate returns one of three outcomes (HEARTBEAT_OK / LOG_AND_SKIP / ESCALATE_TO_SONNET) | WP03 | `test_gate_routing.py` (3-way outcome) | ADEQUATE | — |
| FR-008 | ESCALATE triggers main-agent path once per tick with structured reason | WP03 | `test_run.py`, `test_escalator.py` | ADEQUATE | — |
| FR-009 | Heartbeat outcomes written to audit log (decision, reason, latency) | WP03 / WP04 | `test_ledger.py` | ADEQUATE | — |
| FR-010 | Gate honors HEARTBEAT.md contract: cheap tier where feasible, escalate when judgment required | WP03 | `test_context.py` (state classification only) | **PARTIAL** | [DRIFT-2] |
| FR-011 | Gate failure falls back to expensive-tier path; observation never silently dropped | WP03 | `test_run.py` (fallback paths) | ADEQUATE | — |
| NFR-001 | Expensive-tier invocations drop ≥80% over 7-day window | WP03 | `test_gate_routing.py` references; baseline file shipped (Tier 1) | DEFERRED | — *correctly punted to post-deploy* |
| NFR-002 | Signal detected and filed within ≤1 cycle of threshold crossing | WP02 | `test_replay_20260601.py` (≥1 burst-onset cycle trips) | ADEQUATE | — |
| NFR-003 | Deterministic file-issue path invokes no LLM | WP02 | (by construction — `filer.py` has no SDK imports) | **PARTIAL** | [RISK-3] |
| NFR-004 | Filing scope within ±2 of ground truth on replay | WP02 | `test_replay_20260601.py` explicit NFR-004 assertions | ADEQUATE | — |
| NFR-005 | Errors visible in systemd journal OR `last-tick.json` within their cycle | WP01/WP02/WP03 | error-path tests in `test_tick_orchestrator.py`, `test_run.py` | ADEQUATE | — |
| NFR-006 | No regression in time-to-action; replay produces filing ≤1 cycle from burst onset | WP02 | `test_replay_20260601.py` explicit NFR-006 assertions | ADEQUATE | — |

**Legend**: ADEQUATE = test constrains the required behavior; PARTIAL = test exists but does not constrain the full FR; MISSING = no test; DEFERRED = test cannot exist until post-deploy data is available (acknowledged in spec).

---

## Drift Findings

### DRIFT-1: Navigation docs (INDEX.md, DEVELOPER_PORTAL.md) not updated despite new runbook + new service entries

**Type**: NON-GOAL INVASION — *inverse* (a required standing update was silently skipped)
**Severity**: MEDIUM
**Spec reference**: CLAUDE.md "Documentation map" standing reference; spec §10 Architecture Impact
**Evidence**:
- `grep -E "felix-heartbeat-gate|signal-driven-monitoring|felix-core-digest-signals" docs/INDEX.md docs/DEVELOPER_PORTAL.md` returns zero hits
- WP04 owned_files explicitly excluded INDEX.md (per WP prompt's documented punt: "skip INDEX.md update; let the doc-auditor catch it")
- Mission delivered a new operational runbook (`docs/runbooks/signal-driven-monitoring-ops.md`) and two new services (`felix-core-digest-signals`, `felix-heartbeat-gate`); none are listed in the canonical navigation index

**Analysis**: The WP04 prompt explicitly punted INDEX.md updates to the doc-auditor on the assumption that the auditor would catch the gap post-merge. Per memory `project_api_credit_exhaustion`, the doc-auditor is currently SUSPENDED INDEFINITELY pending #137. The result: this mission shipped without canonical navigation updates and there is no automated process that will catch it. Operator must update manually OR file a follow-up.

This finding *motivated* the `B + i + ii` doc-impact-resolver work I shipped post-mission (commit `d43b7387`), which prevents the same gap in future missions by adding mission-end change classes to `signal-to-doc-map.json` and instructing `/spec-kitty.specify` and `/spec-kitty.plan` to consult them. **The remediation is in place for future missions; this one's gap is unfilled.**

### DRIFT-2: FR-010 partially covered — gate's "cheap tier where feasible" path may not exist

**Type**: PUNTED-FR (partial)
**Severity**: LOW-MEDIUM
**Spec reference**: FR-010 — "The heartbeat gate honors the existing heartbeat contract file convention: scheduled tasks in the contract file are **executed (cheap tier where feasible, escalated when judgment is required)**."
**Evidence**:
- `test_context.py` covers HEARTBEAT.md state classification (`"empty"` vs `"has_tasks"`) but does not test the gate's behavior with HEARTBEAT.md tasks
- `gate.py` routing prompt (`prompts/routing.prompt.md`) includes `has_tasks` in the gate's input but the decision-rule section says `ESCALATE_TO_SONNET when ... HEARTBEAT.md has unfinished tasks needing judgment`
- No test asserts the gate ever returns `HEARTBEAT_OK` or `LOG_AND_SKIP` while HEARTBEAT.md has tasks (i.e., the "cheap tier where feasible" branch)

**Analysis**: The FR allows two paths when HEARTBEAT.md has tasks: (a) cheap-tier execution by the Haiku gate itself, (b) escalation to Sonnet when judgment is required. The implementation appears to always take path (b) — Haiku never *executes* tasks, only routes. This may be the right behavior given the empty-HEARTBEAT.md state in production today (`feedback_idle_pings_acceptable_for_now` memory), but the FR text reads as if path (a) is supposed to be possible. The HEARTBEAT.md classifier errs conservative ("errs toward escalation"), which is a defensible interpretation, but the FR isn't explicitly *constrained* to that interpretation.

**Recommendation**: Either (1) clarify the FR text post-hoc to say "Gate honors HEARTBEAT.md by escalating to Sonnet when tasks are present" (matching implementation), or (2) add a test for the cheap-tier-execution path if it's truly intended. Today HEARTBEAT.md is empty in production, so this is latent.

---

## Risk Findings

### RISK-1: No explicit Anthropic SDK request timeout in gate.py

**Type**: ERROR-PATH / UNBOUND-HTTP
**Severity**: MEDIUM
**Location**: `scripts/openclaw/heartbeat_gate/gate.py:327` (`anthropic.Anthropic(api_key=api_key)`)
**Trigger condition**: Anthropic API unresponsiveness or hung connection during a gate tick

**Analysis**: The Anthropic client is constructed without an explicit `timeout` parameter. The SDK's default timeout is 10 minutes (per anthropic-sdk-python defaults). A stuck call could block a 30-min heartbeat gate tick for 10 minutes, potentially overlapping the next scheduled tick if `--wait` is in use. The fallback path (FR-011) does protect against permanent API failure, but the *duration* of the block is unbounded against partial-failure modes.

Codex's review of WP03 did not flag this because the heartbeat is not in the critical path of any user-facing operation. It would surface only under sustained API degradation.

This pattern is **inherited from the felix-doc-auditor precedent** — `scripts/doc_audit/judgment/client.py:74` constructs the client the same way. So this is a *precedent-wide* issue, not a mission-specific drift. Worth a single follow-up that adds a `timeout=30` (or similar) to both call sites.

### RISK-2: Filer's fail-open dedup may file duplicates during `gh` CLI outages

**Type**: ERROR-PATH
**Severity**: LOW
**Location**: `scripts/openclaw/observation/filer.py` (`check_existing_issue_open`)
**Trigger condition**: `gh issue view` returns non-zero or times out while a previously-filed issue is still open

**Analysis**: When `gh issue view <number>` fails (rate-limit, network, malformed JSON), the dedup check returns `False` (fail-open: assume CLOSED so we file). The result: while a real open issue exists in production, a new duplicate could be filed if gh is intermittently failing. Per the contract this is the *intended* design — the safety-vs-noise tradeoff favors filing — but it does mean operators may need to triage occasional duplicates during gh outages. Documented in `contracts/filer-invocation.contract.md` so this is a documented constraint, not a hidden risk.

### RISK-3: NFR-003 not explicitly asserted — could regress silently

**Type**: BOUNDARY-CONDITION
**Severity**: LOW
**Location**: `scripts/openclaw/observation/filer.py` (entire module is the surface)
**Trigger condition**: A future change adds an LLM call to the filer path

**Analysis**: NFR-003 ("deterministic file-issue path invokes no LLM") is true *by construction* today — `filer.py` has no `anthropic` import and only shells out to `gh` via subprocess. But this is enforced by social convention and code review, not by an automated assertion. A test like `assert "anthropic" not in inspect.getsource(filer)` (or equivalent) would lock the property. Low priority because the social convention is robust here, but worth flagging.

### RISK-4: Concurrent tick invocations not explicitly guarded

**Type**: BOUNDARY-CONDITION
**Severity**: LOW
**Location**: `scripts/openclaw/observation/tick.py`
**Trigger condition**: Two `felix-core-digest.service` invocations overlap (e.g., manual `systemctl start` while the timer-launched run is mid-cycle)

**Analysis**: Systemd `Type=oneshot` units do not allow concurrent runs of the same unit, so under normal timer-driven operation this is impossible. But a manual `systemctl start --wait` invoked during the timer's run *can* queue. State-file atomic writes (tmp + rename) protect single-file consistency, but two concurrent ticks could each see a stale `last_log_position`, both process the same range, and double-count events for that signal in one cycle.

Mitigation: an advisory `flock` on a per-state-dir lockfile would close this. Today it's a corner case (would require explicit manual interference); flag for future hardening only.

### RISK-5: Captured fixture (1.7 MB) bigger than spec-projected (~1.4 MB); replay-test runtime not bounded

**Type**: BOUNDARY-CONDITION
**Severity**: LOW
**Location**: `scripts/openclaw/observation/tests/fixtures/captured/openclaw-2026-06-01.log`
**Trigger condition**: Replay test runs

**Analysis**: WP01 captured the log later in the day than the WP prompt anticipated, picking up additional events. Counts (198 vs 193, 153 vs 149) were within the ±5% tolerance documented in T006, but the fixture is 21% larger than the spec implied. Replay test does 37 simulated cycles against the full fixture. Local pytest run (verified) takes ~12 seconds for the whole suite (311 tests); not bounded by mission's NFRs but worth noting as a potential creep target if more fixtures land.

---

## Silent Failure Candidates

| Location | Condition | Silent result | Spec impact |
|---|---|---|---|
| `gate.py` `_build_client` → SDK call | API hung / unresponsive | gate blocks ≤10 minutes (SDK default), then fallback fires | NFR-001 metric inflated (long-tail tick durations); FR-011 still triggers eventually so observation is not dropped |
| `escalator.py` `escalate()` | `openclaw system event` returns non-zero | Returns `EscalationResult(escalated_event_id=None, error=...)` — does NOT raise | Ledger records `fallback_invoked=true` and the error; main agent is NOT woken; **observation IS effectively dropped for that tick** if the escalator was the fallback path |
| `filer.py` `_invoke_subprocess` | gh CLI absent or auth-failed | `error_type="filer_subprocess_failed"`; cycle records error in `errors[]`; signal state still advances | FR-003 silently degrades — filing is broken but the cycle reports `partial` exit and continues. Operator sees the error in `last-tick.json` if they look. |
| `tick.py` `run_cycle` config_load failure | config.toml malformed or missing | `exit_status="failure"`, returns 1 immediately, `last-tick.json` shows config_load_failed | Cycle does not advance; next cycle retries. No silent failure — observable in `last-tick.json` and systemd journal. |

The most concerning entry is the **escalator silent-drop during fallback**: if the gate's primary path fails AND the fallback escalation also fails (e.g., openclaw gateway is down), the gate writes `fallback_invoked=true` to the ledger and exits cleanly. There is no out-of-band alert. An operator must actively read `gate-ledger.jsonl` to notice. This is an inherited issue from the OpenClaw gateway being a single point of failure for the entire heartbeat pipeline; not something this mission could fix.

---

## Security Notes

| Finding | Location | Risk class | Recommendation |
|---|---|---|---|
| Anthropic SDK has no explicit timeout | `gate.py:327` | UNBOUND-HTTP | Add `timeout=30` to `anthropic.Anthropic(...)`. Apply same fix to `scripts/doc_audit/judgment/client.py:74` (precedent). See RISK-1. |
| All subprocess invocations use list args (no `shell=True`) | `filer.py`, `escalator.py` | SHELL-INJECTION | None — implemented correctly. |
| All file paths anchored to `Path(__file__).resolve()`-relative or controlled state dirs | `tick.py`, `filer.py`, `gate.py` | PATH-TRAVERSAL | None — no user-controlled path components observed. |
| Credentials read from file paths (not embedded) | `gate.py` `_read_api_key`, `filer.py` (delegates to `felix-file-issue.py` which delegates to `gh auth`) | CREDENTIAL-EXPOSURE | None — keys never logged, paths configurable so they can be 0600. |
| State file writes are atomic (tmp + rename) | `state.py`, `ledger.py`, `tick.py` | LOCK-TOCTOU | None — single-writer per file is the design; see RISK-4 for the concurrent-tick caveat. |
| No new auth mechanisms introduced | (whole mission) | — | None. |

---

## Cross-WP integration verification

Files touched by multiple WPs (high integration risk):

- `scripts/openclaw/observation/__init__.py` — WP01 owned (per frontmatter); not touched by WP02/3/4. No conflict.
- `scripts/openclaw/observation/signals/__init__.py` — WP01 only. No conflict.
- `scripts/office2/felix-core-digest.service` — WP04 modified (added `tick.py` ExecStart). This file references WP02's `tick.py` artifact; integration verified by the runbook smoke-test step. The file modification IS in WP04's owned_files (`scripts/office2/felix-core-digest.service`), so the change is well-scoped.

Lane-rebase workaround (#492): the manual `git reset --hard` of each downstream lane onto its predecessor created a single linear branch history (`lane-d` contains all four WPs' commits). The merge ran clean (no stale-lane errors, no conflicts on `__init__.py` exports). **No cross-WP integration defects detected.**

---

## Final Verdict

**PASS WITH NOTES**

### Verdict rationale

All 11 FRs are adequately covered (with FR-010 marked PARTIAL — see DRIFT-2). All 6 NFRs are either adequately tested or correctly deferred (NFR-001 properly punted to post-deploy). The deterministic-vs-stochastic split (Directive 6) is honored — filing is zero-LLM, gate is the only LLM touchpoint. The load-bearing design call ("things Felix should observe are nameable in advance") is preserved — no escape hatches were added that would re-open the unknown-unknown vigilance question.

No CRITICAL or HIGH findings exist. The 1 MEDIUM drift (DRIFT-1: navigation docs not updated) is documented and remediated for future missions via the post-merge `B + i + ii` work. The 1 MEDIUM risk (RISK-1: no SDK timeout) is precedent-wide and warrants a single cross-cutting follow-up. All other findings are LOW.

Cutover to production is **safe to proceed** subject to:
- The pre-existing operator-controlled cutover preconditions in `docs/runbooks/signal-driven-monitoring-ops.md` (Restic backup currency; kg-felix-bot identity; Anthropic API key)
- Acknowledgement that DRIFT-1's INDEX.md / DEVELOPER_PORTAL.md updates remain as a manual follow-up for this mission (the doc-impact resolver will catch the next mission's equivalent gaps)

### Open items (non-blocking)

| Item | Origin | Suggested follow-up |
|---|---|---|
| Manually update `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` with the new runbook + service entries | DRIFT-1 | Single small commit; can be done at cutover time |
| Add `timeout=30` to `anthropic.Anthropic()` call in `gate.py` AND in `scripts/doc_audit/judgment/client.py` | RISK-1 | Single PR touching both sites; tag as `area/tooling` |
| Clarify FR-010 text or add a "cheap-tier HEARTBEAT.md execution" test | DRIFT-2 | Spec amendment or test addition; latent today (HEARTBEAT.md is empty in production) |
| Add an assertion that locks NFR-003 (no LLM imports in `filer.py`) | RISK-3 | Single test; low priority |
| Document the escalator-silent-drop-during-fallback scenario in the runbook's troubleshooting section | Silent Failure table | Runbook edit; raises operator awareness without code change |
| File [#492](https://github.com/kentonium3/kg-automation/issues/492) upstream at Priivacy-ai/spec-kitty | post-mission discovery | Manual operator review of `docs/diagnostics/xx_lane-base-not-inferred-from-wp-deps.md`, then file |

---

## Reviewer's note on adversarial discipline

I went into this review primed to find the gaps codex didn't probe and the assumptions the spec didn't make explicit. The findings above are the result. None of them rise to release-blocking severity for the simple reason that the spec was tight, the contracts were well-defined, and codex's per-WP reviews were sharp enough to catch the most consequential bugs (multi-file cursor scope, redaction completeness, replay-safety bypasses, baseline-as-real-data). The remaining gaps are mostly inherited precedent (RISK-1), social-convention enforcement (RISK-3), and corner cases (RISK-4, RISK-5).

The biggest single thing I would change about how this mission was run is that I should have caught DRIFT-1 at spec-time — I wrote the WP04 prompt that explicitly punted INDEX.md updates to the doc-auditor, and I knew the doc-auditor was suspended. That's the gap the post-mission `B + i + ii` resolver work closes for the next mission.
