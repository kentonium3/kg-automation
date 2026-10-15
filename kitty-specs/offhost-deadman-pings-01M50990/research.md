# Research: Off-host dead-man pings

All facts verified on 2026-10-15 against `main` @ `4dab39e0`.

## R1 — Provider and protocol
- **Decision**: healthchecks.io, chosen in RFC #1069 and confirmed by Kent on 2026-10-15.
- A ping is an HTTPS GET or POST to `https://hc-ping.com/<uuid>` for success and `.../<uuid>/fail` for failure.
- The check alerts after period + grace with no ping, or immediately on `/fail`.
- **Rationale**: the RFC records why the alternatives were rejected: office4/Mac (ADR-0008), GitHub cron (best-effort, needs a write-scoped PAT), and accepting the risk.

## R2 — Where the URL lives, and how the watchers read it
- **Fact**: `felix-canary.service` and `felix-health-check.service` load `EnvironmentFile=-/home/claude/.config/felix/alert-bus/env`. `scripts/office2/*.service` is in the audited `systemd-user-units` surface (`audited-surfaces.json:40`).
- **Decision**: a dedicated file, `/home/claude/.config/felix/deadman/env`, read by the module itself.
- **Rationale**:
  - Adding an `EnvironmentFile=` would touch an audited surface and need a rebaseline.
  - Reusing `alert-bus/env` would mix two secrets with different blast radius and rotation.
  - A self-read is the `alert_bus.sh` precedent.
- **Alternatives**:
  - A unit `EnvironmentFile=` line: rejected (audited, rebaseline).
  - Variables appended to `alert-bus/env`: rejected (mixes credentials).

## R3 — Transport
- **Decision**: `curl` with the URL on stdin through `-K -`. Flags: `--silent --show-error --fail --max-time 5 --retry 0 --output /dev/null`. Subprocess timeout 8 s.
- **Rationale**:
  - The alert bus already uses curl, with the same timeout discipline.
  - `urllib`'s timeout does not bound DNS resolution (`getaddrinfo`), so a dead resolver could stall a tick.
  - A subprocess timeout bounds everything.
  - Passing the URL in argv would expose it in `/proc/<pid>/cmdline` to other local users (`codex`, `kgale`).
- **Alternatives**: urllib (unbounded DNS); requests (new dependency).

## R4 — Delivery signal for `/fail`
- **Facts**:
  - The canary discards `emit_fn`'s `AlertResult` (`run.py:325`).
  - felix-health-check records `delivery = {"attempted", "sent", "detail"}` in `last-run.json` (`run.py:261-280`).
  - `AlertResult.ok` is false on `NTFY_MISSING_TOPIC`, `CURL_*` and `BUS_ERROR:*`.
- **Decision**: the canary counts `getattr(result, "ok", True) is False` into the summary-only field `alerts_undelivered`, which is never persisted. The health check uses `delivery["attempted"] and not delivery["sent"]`.

## R5 — Egress
- **Fact**: no egress allow-list exists. `ollama-ops.md:146` records that UFW egress is permissive.
- **Decision**: the only registration is a new `data-flows.json` flow with destination `hc-ping.com`.

## R6 — Provisioning
- **Fact**: claude-owned secrets under `/home/claude/.config` are provisioned by Kent through `ssh office2-claude` (see `credential-manifest.json`, e.g. `felix-alert-ntfy-topic` expiry notes). `kgale` cannot write into `/home/claude` (mode 0750).
- **Decision**: use a `read -rsp` one-liner run by Kent through `ssh -t office2-claude`. The secret is never echoed or seen by an agent.
