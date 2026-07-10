# Research: Unified Alert Bus

Phase 0 decisions. Grounded in a code survey of the current emitters (see the emitter inventory below)
and the established design intent in `docs/design/felix-bedrock-stabilization.md`,
`docs/design/coherence/doctrine.md`, and RFC #327.

## Emitter inventory (ground truth, 2026-07-10)

| Component | File | Transport | Topic today | Priority/Tags |
|---|---|---|---|---|
| felix-deployer (failure/rebaseline/health) | `scripts/deploy/felix-deployer/notify.py` | `curl` subprocess | `FELIX_DEPLOYER_NTFY_TOPIC` (env) | high / warning,rotating_light |
| felix-deployer health notifier | `scripts/deploy/lib/health.py` (`dispatch_health_notification`) | `curl` subprocess | param env, falls back to deployer topic | high / warning,rotating_light |
| security-monitor audit | `scripts/office2/security-monitor/audit.sh` | raw `curl` | **hardcoded** `felix-office2-k9x4m2` | high / warning,rotating_light |
| felix-health-check | `scripts/office2/felix_health_check/run.py` | `curl` subprocess | `NTFY_TOPIC` (systemd EnvironmentFile) | high / warning,rotating_light |
| enforcement notifier | `scripts/openclaw/enforcement/notification.py` | **WhatsApp + GitHub** (not ntfy) | n/a | n/a |
| doc-auditor | `scripts/office2/deploy/felix-doc-auditor*.sh` | **deploy scripts, not emitters** | n/a | n/a |

All ntfy emitters: no auth (public-subscribe; security = topic secrecy), identical curl flag set
(`--silent --show-error --fail --max-time 10`, `--data-binary @-`), Title/Priority/Tags as HTTP
headers, best-effort (notification failure never fails the tick/cron). All run **natively** on office2
(systemd timers + cron as `claude`), **no docker container**.

## Decisions

### D1 — Scope: migrate the 3 real ntfy emitters; co-emit for enforcement; defer doc-auditor
- **Decision**: Migrate felix-deployer (`notify.py` + `deploy/lib/health.py`), security-monitor
  (`audit.sh`), and felix-health-check (`run.py`). Add a `felix-alert` co-emit to the enforcement
  notifier (keep its WhatsApp+GitHub). Defer doc-auditor ntfy coverage to a follow-up.
- **Rationale**: Code survey showed the issue's "five emitters" was inaccurate — enforcement uses
  WhatsApp+GitHub and doc-auditor's `*.sh` are deploy scripts. Operator decision (2026-07-10) chose the
  co-emit-for-enforcement option to get drift on the unified thread while keeping the mission bounded
  ("one slice dependable, then widen").
- **Alternatives considered**: (a) migrate only 3, defer both non-ntfy components — rejected: loses
  drift visibility Kent wanted; (b) add ntfy to both enforcement and doc-auditor now — rejected:
  doc-auditor has no failure-alert path today, so it adds new alerting logic (more surface/risk).

### D2 — Library home & shape: a package under `scripts/common/`
- **Decision**: `scripts/common/alert_bus/` package (model / render / delivery / `__main__` CLI) +
  `scripts/common/alert_bus.sh` shim.
- **Rationale**: `scripts/common/` is the repo's home for cross-domain shared code (already holds
  `state_log`, `vikunja_client`); `scripts/deploy/lib/` is deploy-specific and `scripts/lib/` does not
  exist. A package (not a flat module) lets model/render/delivery each be unit-tested to the ≥90% bar
  and honors DIRECTIVE_001 separation of concerns.
- **Alternatives considered**: flat `scripts/common/alert_bus.py` — workable with `-m`, but harder to
  hit the coverage bar with focused tests; `scripts/deploy/lib/` — wrong domain (bus is cross-domain).

### D3 — Transport: keep `curl` via subprocess; no new dependency
- **Decision**: The bus posts to ntfy with `curl` via `subprocess`, reusing the proven flag set.
- **Rationale**: Every existing emitter already uses curl; keeping it means zero new pip dependency
  (C-003), identical operational behavior, and a trivial migration. `requests` is not currently a
  guaranteed dependency in these runtimes.
- **Alternatives considered**: `requests`/`httpx` — rejected (new dependency, no benefit for a single
  best-effort POST); `urllib` — workable but curl matches existing behavior and timeout handling.

### D4 — Severity vocabulary → ntfy priority + tags
- **Decision**: `info` / `warn` / `error` / `critical` mapped as in the table in
  [data-model.md](./data-model.md#severity-map). Emitters pass a severity when they call `emit()`.
- **Rationale**: Matches the issue's proposed vocabulary and industry norm; a monotonic priority
  gradient (2→3→4→5) plus distinct tags keeps `error`/`critical` visually distinct from `info`/`warn`
  on one thread (FR-004). Current emitters all hardcode "high" → they map to `error`/`critical` as
  appropriate at each call site.
- **Alternatives considered**: reusing a single "high" priority for everything (status quo) — rejected:
  defeats the "distinguish critical from info on one thread" requirement.

### D5 — Single canonical topic, provisioned out-of-band as a secret
- **Decision**: One env var `FELIX_ALERT_NTFY_TOPIC`; a **new dedicated** high-entropy topic minted by
  the operator and provisioned via an env-file credential (`/home/claude/.config/felix/alert-bus/env`),
  recorded in `credential-manifest.json`, never committed. The bus is the only reader of the env var.
- **Rationale**: ntfy security = topic secrecy, and alerts carry error text/paths, so the topic must be
  a secret high-entropy string (like the existing `felix-office2-k9x4m2`), not a guessable `felix-alert`.
  Env-file provisioning matches the existing `felix-deployer-ntfy-topic` credential pattern. Operator
  chose "mint a new dedicated topic" over reusing an existing one.
- **Alternatives considered**: committing a plaintext `felix-alert` topic — rejected (readable by
  anyone who sees the repo); reusing `felix-deployer` — rejected by operator (deployer-specific
  semantics).

### D6 — Bash shim uses the env-anchored checkout-cd form
- **Decision**: `scripts/common/alert_bus.sh` runs `cd /home/claude/kg-automation && python3 -m
  scripts.common.alert_bus emit "$@"`. audit.sh calls the shim.
- **Rationale**: Keeps a single Python source of truth for ntfy (the shim doesn't re-implement curl in
  bash). The checkout-cd form is the proven pattern from #658/#662 — cron/exec subshells don't inherit
  `PYTHONPATH`, and office2 has only `python3` (no bare `python`). A pure-bash curl shim was rejected
  because it would duplicate delivery logic and violate the single-source invariant (FR-005).

### D7 — Fail-safe delivery contract
- **Decision**: `emit()` returns a structured `AlertResult` and **never raises**; missing topic,
  unreachable endpoint, or curl error yield `AlertResult(ok=False, reason=…)`. The CLI exits non-zero on
  delivery failure only for the operator self-test; library callers get the result object and decide.
- **Rationale**: NFR-001 fail-safe — a delivery problem must never crash/hang an emitter. Mirrors the
  existing best-effort behavior (deployer/health-check already treat notification failure as non-fatal).

### D8 — Redaction & the felix-deployer "real stderr" gap
- **Decision**: Rendering redacts secrets before truncation (preserve existing ordering). The
  felix-deployer migration passes the **actual captured error/stderr** into the Alert `details`, not
  just phase+summary — closing the #699 opacity gap (SC-002).
- **Rationale**: FR-003 + SC-002 are the core symptom the issue exists to fix. Evaluate promoting
  `scripts/deploy/felix-deployer/_verify.redact_secrets` to a shared helper the bus can call.
- **Open for tasks**: whether felix-deployer's failure record already carries stderr to the notify call
  site or the migration must thread it through `_tick.py` — a tasks/implementation detail to verify.

## Charter re-check (post-design)

No new violations introduced by the design. Tier 3 + rebaseline obligation (audited surfaces) recorded.
Architecture-doc + runbook updates captured as IC-08.
