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
- Exit codes: `0` = delivered; non-zero = delivery failed (for `self-test` and `emit` the CLI reflects
  `AlertResult.ok` so shell callers *can* detect failure, but callers that must stay fail-safe should
  ignore the exit status — the bus itself never crashes).

## 3. Bash shim (`scripts/common/alert_bus.sh`)

```
scripts/common/alert_bus.sh emit --source ... --severity ... --title ... --description ... [...]
```

- Env-anchors to the checkout and invokes the CLI: `cd /home/claude/kg-automation && python3 -m
  scripts.common.alert_bus "$@"` (proven checkout-cd form; office2 `python3` only — never bare `python`).
- Best-effort: a shim/CLI failure must never fail the calling cron/audit (callers `|| true` as today).

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
  `last_alert_ts`; felix-health-check still returns its `{attempted, sent, detail}` shape; audit.sh
  still runs its full audit and treats notification failure as non-fatal.
- After migration, **no migrated emitter contains its own curl/ntfy code** (SC-006).
- Enforcement notifier **adds** a `felix-alert` co-emit and **keeps** its WhatsApp + GitHub records
  (FR-009/SC-007).
