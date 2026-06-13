# Research: Felix-deployer ntfy Failure Notifications

This document records the design decisions surfaced during the plan phase and the evidence/alternatives behind each. The corresponding decisions in the spec (Assumptions, Out of Scope) are summarized references; this file is the authoritative rationale.

---

## Decision R-01 — Substrate: ntfy.sh (chosen over openclaw cron throwaway one-shot)

**Decision**: Failure notifications dispatch via HTTPS POST to `https://ntfy.sh/<topic>` using `curl` invoked from `subprocess.run`. The `felix-deployer-alert` openclaw cron name is retired; no cron is registered for the alert path.

**Rationale**: Failure-mode independence. A deploy that fails because it broke openclaw, WhatsApp, or a shared dependency would ALSO break Design A (openclaw cron throwaway one-shot, the original issue's proposal). The failure-notification path must not share substrates with the deploys that might fail. ntfy.sh is operationally independent of openclaw and WhatsApp; the only shared dependencies are outbound TCP and DNS, both of which are needed for git fetch anyway (so failure of those means the applier wasn't going to do anything productive on this tick regardless).

**Alternatives considered**:

- **(A) openclaw cron throwaway one-shot** (`openclaw cron add --at +5s --name <unique> --message <text> --delete-after-run --best-effort-deliver`). The flags exist on openclaw 2026.6.5; verified live via `ssh office2-claude 'openclaw cron add --help'` during specify. Rejected because routing failure notifications through the substrate the deploy itself might break is a known anti-pattern (security-monitor's existing ntfy.sh precedent exists precisely for this reason).
- **(B) ntfy.sh** ✅ chosen.
- **(C) File-at-known-path + separate poller** (the issue's Design B). Rejected because it adds a new periodic component to the system without solving an actual problem ntfy.sh doesn't already solve; and it introduces latency proportional to the poller interval rather than the dispatcher's response time.
- **(D) openclaw direct-message-send surface** (the issue's Design C). The 2026.6.5 surface has no `openclaw send-message` or equivalent — only cron-routed delivery, which inherits Design A's failure-mode coupling.

**Evidence**: 
- Memory `ntfy_notification_pattern`: "ntfy.sh is canonical push-notify substrate (security-monitor precedent); prefer over openclaw cron for new alert paths".
- Live `openclaw cron --help` and subcommand help capture during specify (Sat 2026-06-12 ~23:42 UTC).
- `scripts/office2/security-monitor/audit.sh:243–256` — production curl-to-ntfy POST as the reference pattern.

---

## Decision R-02 — HTTP client: curl via subprocess (not `requests` or `httpx`)

**Decision**: notify.py invokes `curl` via `subprocess.run` with `--max-time 10`, `-X POST`, `-H` for Title/Priority/Tags, `-d @-` for body-on-stdin, and a target URL of `https://ntfy.sh/$FELIX_DEPLOYER_NTFY_TOPIC`.

**Rationale**: 
- Mirrors the existing security-monitor pattern (one substrate, one invocation idiom across the repo).
- Avoids adding a Python HTTP dependency to the deploy library's import graph (the deploy library is loaded at every applier tick; importing `requests` on every tick is observable startup overhead).
- Subprocess-mocking is the established test pattern in `tests/deploy/`.
- No SSL config drift between curl (system) and Python's bundled certificates; curl reuses the OS trust store, same as security-monitor.

**Alternatives considered**:
- `requests` ≥2.x: would require adding `requests` to `requirements.txt` and accepting its dependency tree. Rejected as not justified for a single POST.
- `urllib.request` (stdlib): no new dep but lacks `--max-time`-equivalent simple timeout and lacks SSL trust convenience. Rejected as more code for less safety.
- `httpx`: same as requests with async overhead. Rejected.

---

## Decision R-03 — Topic storage: systemd `EnvironmentFile=` (not env var in unit file, not vault)

**Decision**: The ntfy topic is read from `FELIX_DEPLOYER_NTFY_TOPIC` injected via `EnvironmentFile=-/home/claude/.config/felix-deployer/env`. The `-` prefix makes a missing file non-fatal at unit start. The env file is created on office2 once during the operator's post-merge redeploy (out-of-band setup), not committed.

**Rationale**:
- The topic is private but not a high-value secret: knowing it lets an attacker read failure notifications, not impersonate any service. Treating it as a Tier 2 secret-bearing config is overkill.
- `EnvironmentFile=` is the canonical systemd-user pattern; the `claude` user already manages units this way (verified via `felix-doc-auditor` precedent).
- Keeping it OUT of the systemd unit file means the unit file can stay committed; the topic value lives only on office2.
- The non-fatal `-` prefix means an operator can deploy the fixed applier even if they forget to populate the env file first; the dispatch will log a non-fatal warning rather than the unit failing to start.

**Alternatives considered**:
- **Topic baked into `felix-deployer.service`** as `Environment=FELIX_DEPLOYER_NTFY_TOPIC=...`. Rejected — leaks the topic to the repo if committed; requires uncomitted unit file otherwise.
- **Topic in a shared `~/.config/felix/env`** vault used by multiple services. Rejected — too generic for a private one-purpose topic; security-monitor uses its own `NTFY_TOPIC` env directly. Per-component env files keep blast radius narrow.
- **Topic in Restic-backed secrets file**. Rejected as Tier 2 overkill (see above).

**Implementation note**: The bootstrap script's `--apply` mode does NOT create the env file. The operator runs a one-liner before `--apply` (documented in `quickstart.md`) to write the file. The bootstrap can detect the missing file in `--dry-run` and warn, but does not fail.

---

## Decision R-04 — Applied entry for the redeploy: write fresh `0002-bootstrap-felix-deployer-v2.yaml`, supersedes `0001`

**Decision**: After this mission merges and the operator runs `--rollback` + `--apply` on office2, the bootstrap script's step 6 (applied-entry write — currently step 7 in the broken layout) writes `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml` with `apply_mode: bootstrap`, `name: bootstrap-felix-deployer-v2`, and a `notes:` block explicitly referencing `0001` as superseded. The existing `0001-bootstrap-felix-deployer.yaml` is preserved verbatim as the historical record of the broken-bootstrap event.

**Rationale**:
- Preserves the migration audit trail: a future operator (or a doc-auditor agent) can read `0001` + `0002` and reconstruct "we hit a substrate-drift bug, fixed it, redeployed." Overwriting `0001` would erase this.
- Preserves the deploy discipline's invariant that every apply produces an applied entry. The "skip writing on redeploy" option would break the invariant for this one case.
- `0002` is a distinct manifest name (`bootstrap-felix-deployer-v2`), avoiding any deploy-name-uniqueness concerns in the manifest schema.

**Alternatives considered**:
- **(A) Overwrite `0001` with the new successful state**. Rejected — loses audit trail.
- **(B) Write `0002`, supersedes** ✅ chosen.
- **(C) Skip writing an applied entry on the redeploy**. Rejected — breaks discipline invariant; complicates dashboard / audit scripts that assume every apply has a record.

**Implementation note**: The bootstrap script's step-6 inline-manifest construction is parameterised on `APPLIED_NAME` and `NAME` constants near the top. Updating these constants to `0002-bootstrap-felix-deployer-v2` and `bootstrap-felix-deployer-v2` respectively is a 2-line change.

---

## Decision R-05 — Test pattern: subprocess.run monkeypatch (not real curl in CI)

**Decision**: `tests/deploy/test_notify.py` mocks `subprocess.run` at the `scripts.deploy.felix_deployer.notify.subprocess.run` reference. Each test case provides a `CompletedProcess`-shaped fake (or a `FileNotFoundError`/`OSError` exception) corresponding to one failure mode. No real network egress in CI.

**Rationale**:
- CI runners have no `FELIX_DEPLOYER_NTFY_TOPIC` (intentional — would create a notify-spam vector on PR pushes).
- CI runners have outbound network access but mocking is faster and deterministic.
- The pattern matches `tests/deploy/test_deployer.py`'s existing mock of the `openclaw` invocation; reviewers already know it.

**Alternatives considered**:
- **Live ntfy POST in CI** to a per-PR ephemeral topic. Rejected — leaks repo activity to ntfy.sh, requires topic-cleanup automation, and tests would be flaky on network.
- **`responses` library** (for HTTP mocking). Rejected — not applicable; notify.py uses subprocess curl, not Python HTTP.

---

## Decision R-06 — Error classification taxonomy

**Decision**: `dispatch_failure_notification` returns `LibResult(ok=False, details={"error_code": <code>, ...})` with codes drawn from this closed set:

| `error_code` | When |
|---|---|
| `NTFY_MISSING_TOPIC` | `FELIX_DEPLOYER_NTFY_TOPIC` env var is unset or empty. |
| `NTFY_CURL_MISSING` | `subprocess.run(["curl", ...])` raises `FileNotFoundError`. |
| `NTFY_SPAWN_FAILED` | Other `OSError` from `subprocess.run` (resource-exhaustion class). |
| `NTFY_TIMEOUT` | curl exits with code 28 (`Operation timeout`). |
| `NTFY_NETWORK_UNREACHABLE` | curl exits with code 6 (`Couldn't resolve host`) or 7 (`Failed to connect`). |
| `NTFY_HTTP_ERROR` | curl exits with code 22 (`HTTP page not retrieved`), set by `-f`/`--fail`. Body or HTTP status logged. |
| `NTFY_UNKNOWN` | Any other non-zero curl exit code. |

`LibResult.summary` is a human-readable one-liner; `LibResult.details` carries the `error_code`, the curl returncode, and (when present) a `stderr_excerpt` capped at 200 chars.

**Rationale**:
- Closed enum lets tests assert on `details["error_code"]` instead of brittle string matching.
- Codes map 1:1 to curl exit codes the operator might see in `journalctl -u felix-deployer.service`, so debugging goes from "stderr blob" to "look up the code".
- Distinguishing `NTFY_TIMEOUT` from `NTFY_NETWORK_UNREACHABLE` matters operationally: timeout suggests ntfy.sh slow; unreachable suggests office2 outbound is down.

**Curl invocation shape** (settled here so reviewers and tests align):

```bash
curl --silent --show-error --fail --max-time 10 \
    -H "Title: ${TITLE}" \
    -H "Priority: ${PRIORITY}" \
    -H "Tags: ${TAGS}" \
    -X POST \
    --data-binary @- \
    "https://ntfy.sh/${NTFY_TOPIC}"
```

Body delivered on stdin (`--data-binary @-`) to avoid shell quoting issues with multi-line redacted error summaries.

---

## Decision R-07 — Title and body rendering

**Decision**: See `contracts/ntfy-notification-v1.md` for the canonical wire shape. Summary:

- **Title** (one line, ASCII-safe): `felix-deployer failed: <manifest_name>`
- **Headers**:
  - `Priority: high` (5 — the highest non-emergency level on ntfy)
  - `Tags: warning,rotating_light` (mirrors security-monitor for visual consistency in the operator's ntfy feed)
- **Body** (plain text, multi-line):
  ```
  Phase: <phase>
  Tier: <tier>
  Head: <head_sha[:8]>
  Failed at: <failed_at_iso>

  Error:
  <redacted_error_summary>
  ```

**Rationale**:
- Title is short enough to fit a phone lock-screen preview without truncation.
- Headers match security-monitor so all push notifications in the operator's ntfy app have a consistent visual language.
- Body is structured but plain-text; ntfy's iOS/Android apps render plain text predictably (no markdown rendering surprises).

---

## Decision R-08 — Out of scope: shared ntfy adapter library

**Decision**: Each subsystem (security-monitor, felix-deployer) keeps its own inline curl invocation. No `scripts.felix.notify` shared module is extracted in this mission.

**Rationale**:
- Two callers don't justify a library; three would. The rule-of-three holds.
- Extracting now would create a versioning concern (security-monitor lives outside the deploy package; it ships via a different deploy path) that's premature given how stable both call sites are.
- A future third caller (say, escalation-engine if it ever moves to ntfy) would be the right time to extract.

**Tracking**: If a third caller appears, file an issue with title `Refactor: extract shared ntfy adapter (3rd caller appeared)`. Not pre-filed.

---

## References

- Source issue: kentonium3/kg-automation#595
- Memory: `ntfy_notification_pattern` (canonical push-notify substrate, security-monitor precedent)
- Memory: `feedback_design_phase_research` (probe live during specify+plan)
- Memory: `reference_openclaw_upgrade_gotchas` (openclaw CLI surface drift)
- Live probe artifact: `openclaw cron --help` output captured during specify (in chat log, not a file)
- Parent mission: `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/` (this mission supersedes its FR-009 substrate choice)
- Reference precedent: `scripts/office2/security-monitor/audit.sh:243–256`
