# Phase 0 Research: OpenClaw Auth Verifier

**Mission**: `openclaw-auth-verifier-01KV0Y9E`
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

This phase resolved the implicit choices the plan's Technical Context made. No `[NEEDS CLARIFICATION]` markers remain in spec or plan; all open trade-offs are documented below.

---

## Decision: Python stdlib only (no `anthropic` SDK)

**Rationale**: The Anthropic API ping for liveness is a single one-shot HTTP POST with a fixed JSON body, no streaming, no tool use, no caching. The `anthropic` PyPI package would add a dependency the verifier doesn't need, and would require either a virtualenv on office2 or a system-wide install — both of which are extra failure modes for a script whose entire purpose is recovery from a substrate failure. The `urllib.request` call is twenty lines.

**Alternatives considered**:
- `anthropic` PyPI package — rejected for dependency surface (see above).
- `requests` PyPI package — rejected for the same reason.
- A `curl` invocation from bash — rejected because the verifier already has a Python core for SQLite; introducing a second language for the HTTP call doubles the surface and obscures the timeout/error semantics.

## Decision: Bash outer + Python core under `scripts/security/anthropic_verify/` (importable package)

**Rationale**: The bash outer (`anthropic-verify.sh`) handles argument parsing, TTY checks, path validation (`/data/services/openclaw/secrets/anthropic` exists; `~/.openclaw/agents/` exists), and the dispatch to `python3 -m anthropic_verify.core --check` (or `repair`). The Python core does the deterministic work in a way that's directly importable from pytest (`from scripts.security.anthropic_verify.core import discover_agents, fingerprint, ping_anthropic`). This matches the established kg-automation helper pattern (see `scripts/doc_audit/run.py` and the existing `anthropic-rotate.sh`).

**Alternatives considered**:
- Inline Python heredoc inside bash — rejected because it's not directly testable from pytest without subprocess overhead, and the heredoc form makes the Python code harder to lint and harder to mock cleanly in tests.
- Single `anthropic-verify.py` (no bash outer) — rejected because bash is a better fit for argument parsing + TTY checks + path-existence validation, and because the rotation-script-integration path needs a clean bash entry to invoke.

## Decision: Mock at boundaries (sqlite3, urllib, filesystem) — no live Anthropic in tests

**Rationale**: Per the `feedback_live_integration_tests` memory: do NOT propose `--live-probe` test modes. The verifier's deterministic logic (discovery, row counting, sha256, finding emission, exit-code mapping) is fully testable against fixture SQLite databases and mocked `urllib.request.urlopen`. Live Anthropic in CI burns credit, is slow, and provides no signal the mocked test doesn't.

**Alternatives considered**:
- Live Anthropic ping in CI — rejected per memory; cost + slowness + no signal gain.
- Bring up an `openclaw-gateway` instance in CI — rejected as outside CI's scope (the verifier doesn't talk to the gateway; it reads the on-disk substrate directly).

## Decision: Per-sub-agent Anthropic ping is OUT of scope

**Rationale**: A sub-agent's "effective key" is one of:
- The inherited key from `main`'s SQLite (when the sub-agent's `auth_profile_store` is empty — the healthy state).
- The sub-agent's own `auth_profile_store` value (the shadow state — which the verifier already detects from row presence alone, without needing to ping it).

In the healthy case, pinging the sub-agent's effective key is equivalent to pinging `main`'s — the verifier already does that. In the shadow case, the shadow's existence IS the finding, regardless of whether that shadow value also happens to be Anthropic-accepted. So per-sub-agent pings provide no new signal.

**Alternatives considered**:
- Ping every sub-agent's effective key — rejected for no-new-signal + cost (one extra API call per sub-agent per `--check`).

## Decision: `--repair` does NOT auto-restart `openclaw-gateway.service`

**Rationale**: A gateway restart is a side-effect with operational visibility (affects all 6+ agents simultaneously, momentarily disrupts in-flight cron deliveries). Auto-restarting on `--repair` would couple the verifier's "narrow fix" to a "broad system action." The operator should make the gateway-restart decision deliberately, with awareness of in-flight state.

The verifier prints the exact `systemctl --user restart openclaw-gateway.service` command after each `--repair` so the operator doesn't have to remember.

**Alternatives considered**:
- Auto-restart on `--repair` — rejected for coupling + operational-visibility reasons.
- `--repair --restart-gateway` opt-in flag — deferred; if operator pain motivates this later, it's a one-line addition.

## Decision: `--rollback <ts>` in `anthropic-rotate.sh` requires per-rotation manifest

**Rationale**: For `--rollback` to find the three backup files from a specific rotation, the rotation must record their paths in a discoverable place. Approach: at rotation start, `anthropic-rotate.sh` writes `~/.cache/anthropic-rotate/manifest.<ts>.json` listing the backup paths for plaintext file, openclaw.json, and the SQLite-side import-bak. `--rollback <ts>` reads the matching manifest and restores each path.

**Alternatives considered**:
- Reconstruct backup paths by glob pattern — rejected because it can't disambiguate between multiple in-flight rotations (rare but possible) and is fragile to filename convention changes.
- Encode all info in a single composite filename — rejected as fragile.

## Decision: NO daily systemd timer in this mission (scope-bounded per Q1-B + #597 issue body)

**Rationale**: The operator confirmed the verifier is operator-triggered and rotation-script-invoked. A daily timer is a separate concern (operationally: requires `last-check.json` artifact path, signal-driven-monitoring wiring, escalation pipeline). Deferring keeps this mission tightly scoped.

## Decision: NO JSON output mode in this mission

**Rationale**: The only currently-known JSON consumer would be the deferred daily timer. With the timer deferred, JSON output has no consumer. Human-readable output suffices for the operator-triggered surface.

**Out of Scope follow-on**: when the timer ships, add `--json` and convert the human-readable lines into the same structured `Finding` shape the core already produces internally.

## Decision: Discovery is dynamic glob, not hardcoded list

**Rationale**: The 5 current sub-agents (`felix-admin-capture`, `-habits`, `-escalation`, `-tasker`, `-calendar`) are not stable — future missions add or remove agents. A glob-based discovery (`~/.openclaw/agents/*/agent/openclaw-agent.sqlite`) keeps the verifier valid across agent-fleet changes without requiring re-deploy.

**Alternatives considered**:
- Hardcoded list in the helper — rejected as a maintenance burden.
- Read from `openclaw cron list --json` to extract agent IDs — rejected because `openclaw` itself may be partially broken when the verifier is run (it's a recovery tool), so depending on its CLI surface for discovery introduces a circular dependency.

## Decision: NOT calling `openclaw doctor --fix` from the verifier (per spec C-004)

**Rationale**: `openclaw doctor --fix` is the upstream source of shadow rows (it migrates `auth-profiles.json` → SQLite, sometimes with stale values per #596). Having the verifier auto-invoke `doctor --fix` would loop the operator: run verifier → doctor plants shadow → run verifier → shadow detected. The verifier's job is to surface what doctor already planted; `--repair` clears it; the operator's job is to NOT re-run `doctor --fix` until the upstream behavior is fixed.

---

## Open architectural questions resolved

None. All decisions above were made deterministically from the spec + Q1-B + Q2-C + memory references. No remaining `[NEEDS CLARIFICATION]` markers anywhere.

## Risks documented but accepted

1. **urllib 15s default connect timeout** consumes half of NFR-001's 30s budget. Mitigation: set explicit 5s connect timeout in the verifier; total budget remaining for discovery + sha + report = 25s, ample.
2. **Atomic rename behavior on `/data/services/openclaw/secrets/`**: assumes same filesystem (verified: `/data` is a single mount). Documented assumption in spec.
3. **`shutil.copy2` mode/owner preservation**: works under same-user (`claude`) execution; the verifier is always run as the `claude` user (per ssh `office2-claude` invocation pattern).
