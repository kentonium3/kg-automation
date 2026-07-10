# Contracts: Unified Alert Bus

This is a library + CLI, not an HTTP service. The contracts below are the public interfaces every
caller depends on.

## 1. Python API (`scripts.common.alert_bus`)

```python
from scripts.common.alert_bus import emit, Alert, Severity, AlertResult

result: AlertResult = emit(Alert(
    source="felix-deployer/apply",
    severity=Severity.ERROR,
    title="felix-deployer failed: felix-calendar-helper",
    description="Dry-run failed before apply; the deploy script was not executable.",
    action="chmod +x the deploy script and re-queue the manifest.",
    details={
        "manifest": "felix-calendar-helper",
        "phase": "dry_run",
        "head": "0628e279",
        "exit_code": "126",
        "stderr": "<captured stderr — the actual error>",
    },
))
# result.ok -> bool ; never raises
```

**Guarantees**
- `emit()` **never raises** — all failures surface as `AlertResult(ok=False, reason=…)` (D7/NFR-001).
- Only `emit()` (via `delivery.py`) performs ntfy I/O — no other module or caller talks to ntfy (FR-005).
- Construction of an `Alert` with a missing required field (`source`/`severity`/`title`/`description`)
  raises `ValueError` at the call site (programming error), not at delivery time.
- Optional fields absent → still delivered, readable (NFR-003).

## 2. CLI (`python3 -m scripts.common.alert_bus`)

```
python3 -m scripts.common.alert_bus emit \
  --source "security-monitor/audit" \
  --severity warn \
  --title "Felix Security Alert — office2" \
  --description "3 audit finding(s) on 2026-07-10" \
  [--action "<recovery step>"] \
  [--detail key=value ...] \
  [--detail-stdin]                     # read a details blob (e.g. stderr) from stdin

python3 -m scripts.common.alert_bus self-test   # emit a known info alert; exit 0 iff delivered
```

**Contract**
- `--severity` accepts exactly `info|warn|error|critical`.
- `--detail key=value` may repeat; `--detail-stdin` folds piped text into `details["stdin"]`
  (for shell callers passing captured stderr/output).
- Exit codes:
  - `emit` is **best-effort by default → always exits 0** after attempting delivery (logging the
    `AlertResult`), so a cron/audit caller never fails because ntfy was down. Pass `--strict` to make
    `emit` reflect `AlertResult.ok` (non-zero on failure) for callers that want it.
  - `self-test` always reflects delivery (exit non-zero on failure) — it exists to prove the path.
  - The bus itself never raises/crashes regardless of exit code.

## 3. Bash shim (`scripts/common/alert_bus.sh`)

```
scripts/common/alert_bus.sh emit --source ... --severity ... --title ... --description ... [...]
```

- **Sources the topic env-file** (`/home/claude/.config/felix/alert-bus/env`) if present, then
  env-anchors to the checkout and invokes the CLI: `cd /home/claude/kg-automation && python3 -m
  scripts.common.alert_bus "$@"` (proven checkout-cd form; office2 `python3` only — never bare `python`).
  Sourcing the env-file is what lets the cron-launched `audit.sh` (no systemd `EnvironmentFile`) resolve
  the topic.
- **Best-effort by default**: the shim logs and **exits 0** even on delivery failure, so it never fails
  the calling cron/audit regardless of caller `|| true` discipline. (`self-test`/`--strict` still
  reflect failure.)

## 4. ntfy message contract (wire)

For each alert the bus issues one POST equivalent to:

```
POST https://ntfy.sh/$FELIX_ALERT_NTFY_TOPIC
Headers:
  Title:    <rendered title>
  Priority: <low|default|high|max per severity map>
  Tags:     <per severity map, comma-separated>
Body (stdin, --data-binary @-):
  <rendered multi-line body: timestamp (UTC + local) · source · severity ·
   description · Action: <action, if present> · Details: key=value lines
   incl. redacted, truncated stderr>
curl flags: --silent --show-error --fail --max-time 10
```

- Topic resolved solely from `FELIX_ALERT_NTFY_TOPIC`; blank → `AlertResult(ok=False,
  reason="NTFY_MISSING_TOPIC", topic_configured=False)`, no POST attempted.
- No auth header (public-subscribe topic; secrecy is the control).

## 5. Migration contract (behavior preserved)

- Each migrated emitter's **core behavior and health signals are unchanged** (NFR-004): felix-deployer
  still writes its tick log + applied records; health.py still returns a bool used to stamp
  `last_alert_ts` (used by both felix-deployer **and** the indirect consumer `agent-prompt-sync`);
  felix-health-check still returns its `{attempted, sent, detail}` shape; audit.sh still runs its full
  audit and treats notification failure as non-fatal.
- **Adapters (explicit, tested):**
  - felix-health-check: `AlertResult` → `{attempted, sent, detail}` — `attempted = topic_configured`,
    `sent = ok`, `detail = reason or "delivered"`; tested for missing-topic / curl-failure / success so
    `last-run.json` is byte-compatible.
  - health.py / agent-prompt-sync: `AlertResult.ok` → the existing `bool` return so `last_alert_ts`
    stamping is preserved.
- felix-deployer failure alerts carry the **real captured error** (`stderr_excerpt` etc.) in
  `Alert.details`, not just `phase`+`summary` (FR-003/SC-002).
- After migration, **no migrated emitter contains its own curl/ntfy code** (SC-006).
- Enforcement notifier **adds** a `felix-alert` co-emit and **keeps** its WhatsApp + GitHub records
  (FR-009/SC-007).
