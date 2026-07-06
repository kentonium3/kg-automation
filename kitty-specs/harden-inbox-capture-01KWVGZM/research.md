# Research — Harden Inbox Capture on Sonnet

Phase-0 research for mission `harden-inbox-capture-01KWVGZM`. Findings are from
live read-only probing of office2 (2026-07-06) plus repo inspection.

## D1 — Root cause: OpenClaw `exec` sanitizes the environment (strips PYTHONPATH)

**Decision:** The capture failures are an *environmental* defect, not a pure
model hallucination.

**Evidence:**
- The gateway *process* has `PYTHONPATH=/home/claude/kg-automation` (verified in
  `/proc/<pid>/environ`; set by `openclaw-gateway.service.d/pythonpath.conf`,
  confirmed loaded via `systemctl --user show`).
- But the `exec` tool runs commands in a sanitized subshell that does **not**
  inherit it. The failing cron trajectory (`1c4e9b53…`, 2026-07-06T11:00) shows
  `cd "${PYTHONPATH:?PYTHONPATH unset}"` → **exit 127 "PYTHONPATH unset"**, then a
  fallback `cd /data/services/openclaw/inbox-agent && python3 -m scripts.inbox.prescan`
  → **ModuleNotFoundError** (the workspace cwd has no `scripts/` package).
- The only form that works — **102 successful occurrences** across trajectories —
  is `cd /home/claude/kg-automation && python3 -m scripts.inbox.<mod>`.
- No config knob to disable exec sanitization was found in the minified
  `~/.local/lib/node_modules/openclaw/dist/index.js`.

**Rationale:** A weak model (haiku) hits the exit-127/ModuleNotFoundError and
concludes "scripts don't exist" (the #661 hallucination). A stronger model
recovers by improvising the path — but improvising is itself the LLM leaking into
the plumbing. The correct fix removes the inference entirely.

## D2 — Canonical invocation form: self-contained checkout-cd

**Decision:** All agent prompts invoke helpers as
`cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod>` (and
`cd /home/claude/kg-automation && python3 scripts/<path>.py`). No dependence on an
inherited env var; no path guessing.

**Alternatives considered:**
- `cd "${PYTHONPATH:-/home/claude/kg-automation}" && …` — env-var-with-fallback.
  Works (falls back when stripped) and preserves #658's "reuse gateway PYTHONPATH"
  intent, but since exec *always* strips it the fallback is *always* used, so it is
  functionally identical to hardcoding while being more verbose and still flagged
  by the current checker. Rejected for clarity.
- A workspace wrapper script (e.g. `inbox-agent/bin/felixpy`) that sets cwd/env,
  invoked as `felixpy -m scripts.inbox.prescan`. Keeps prompts path-free but adds a
  deploy artifact per workspace and more moving parts. Rejected for Felix-scale
  (single known host); revisit only if the checkout path ever varies.
- Symlinking/vendoring `scripts/` into each workspace cwd — fragile duplication.
  Rejected.

**Consequence:** The hardcoded `/home/claude/kg-automation` is a deploy invariant
(the repo is always cloned there on office2). Acceptable.

## D3 — Invert the #658 env-assumption checker

**Decision:** `env_assumptions.py` is inverted so the self-contained checkout-cd is
the **compliant** form and the fleet passes. This mission **corrects #658**.

**Evidence:** `env_assumptions.py` currently defines the compliant form as
`cd "${PYTHONPATH:?…}" && python3 -m scripts.…` and flags `cd /home/claude/kg-automation`
as a `HARDCODED_CD` violation (remediation: "replace the hardcoded checkout with
cd ${PYTHONPATH:?…}"). It also flags bare `-m scripts.…`. This checker gates both
Test-CI (`test_env_assumptions_guard.py`) and `validate_workspace`. So the working
form is banned by CI — #658 enforced the broken form fleet-wide.

**New policy:**
- **Compliant:** `cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod>`
  (checkout-cd present, then a relative `-m scripts.` / `python3 scripts/….py`).
- **Violation (BARE_M_SCRIPTS):** a `python3 -m scripts.…` **not** preceded by the
  checkout-cd (the un-anchored form that ModuleNotFoundErrors).
- **Violation (PYTHONPATH_ANCHOR):** the `${PYTHONPATH:?…}` form is now flagged
  (it fails under exec sanitization) with remediation pointing at the checkout-cd.
- `HOME_RELATIVE_WRITE` (stray-dir guard from #659) is **retained unchanged**.

**Scope:** update `env_assumptions.py` (patterns, remediation strings, docstring),
`test_env_assumptions.py`, the Test-CI guard, and `test_validate_workspace.py`.
`check_output_discipline` and `check_privacy_boundary` are untouched.

## D4 — Capture model: anthropic/claude-sonnet-4-6 (already registered)

**Decision:** flip `felix-admin-capture` `model` to `anthropic/claude-sonnet-4-6`.

**Evidence:** `openclaw models list` shows `anthropic/claude-sonnet-4-6`
`configured, alias:sonnet`; it is already in `openclaw.json`
`models.providers.anthropic.models[]` and `agents.defaults.models`. `main` and
`felix-admin-escalation` already run it. **No providers edit needed** — a
one-field flip of the capture agent's `model`. Identity line `:haiku`→`:sonnet`.

## D5 — Deploy story (split; no felix-deployer manifest)

**Decision:** This mission needs **no** `deploys/queued/` manifest.
- **Agent prompts** (`AGENTS.md`) deploy automatically via the agent-prompt-sync
  timer (pulls origin/main every ~5 min, MD5-compares, atomically copies changed
  prompt files into `/data/services/openclaw/<workspace>/`). They deploy once
  `feat/harden-inbox-capture` reaches `main`. Prompts are an **unmonitored**
  audited surface (`audit.sh` does not hash them) → **no rebaseline**.
- **`openclaw.json` model change** is an **out-of-band** manual edit on office2
  (`/home/claude/.openclaw/openclaw.json`; not in any repo-driven pipeline).
  openclaw.json is a **monitored** audited surface → **manual** rebaseline
  (`rm baselines/* && audit.sh`, per `docs/runbooks/security-baseline-ops.md`) —
  the out-of-band exception, not the felix-deployer happy path. The gateway must
  be restarted (or re-read config) for the model change to take effect.

**Rationale:** The issue assumed felix-deployer auto-rebaselines; probing showed
openclaw.json is not in the deployer pipeline, so the reset is manual.

## D6 — Cost / spend observability (NFR-001)

**Decision:** Record the estimate + the observability gap; no new tooling built.

**Findings:** office2 has **no on-box $ spend tracking** — per-message `cost` fields
are zeroed in `api_key` mode; the `model-usage` skill is disabled; there is no
openclaw spend subcommand. Token volume *is* observable per run. The May-2026 $500
cap can only be watched via the Anthropic console.

**Estimate:** capture runs ~4 scheduled/day + on-demand. Sonnet unit price is higher
than haiku, but (a) the deterministic work now lives in helpers (fewer/shorter model
turns) and (b) haiku's *failure* runs burn ~252k tokens flailing on a task that is a
single prescan call — sonnet completing cleanly may **reduce** wasted tokens per run.
Net expected cost impact: modest and possibly favorable on error-heavy days.
Recommendation: watch the Anthropic console for the first week post-deploy.

## D7 — Fleet scope + the `show > failed` clarification

**Decision:** Fix the invocation form in all six active agents (capture,
escalation, habits, calendar, tasker, main). felix-doc-auditor is suspended
(excluded). Occurrence counts (deployed `AGENTS.md`): capture 13, escalation 8,
habits 8, calendar 4, tasker 3, main 1 (+ capture.tmpl 6, tasker.tmpl 1).

**`🛠️ … failed` is not a tool.** It is OpenClaw humanizing the *last failing exec*.
Under `delivery.mode: "announce"` (verified on all four inbox crons), an errored
run surfaces that diagnostic to WhatsApp with no successful fallback
(`fallbackUsed: false`). Eliminating the exec errors (D2) eliminates the alarm —
there is no separate "announce fix" to build. This resolves the original FR-3.

## Open items folded (from #662's "decide during specify/plan")

- Model choice location: stays per-agent in `openclaw.json`; fleetwide framework
  deferred (out of scope).
- Cost bounding for decomposition: N/A — FR-5/Phase-2 decomposition is out of scope.
- Delivery channel: keep WhatsApp announce; the fix is removing exec errors (D7),
  not a channel change.
