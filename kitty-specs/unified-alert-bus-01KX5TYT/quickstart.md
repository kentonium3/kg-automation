# Quickstart: Unified Alert Bus

## Emit an alert (Python)

```python
from scripts.common.alert_bus import emit, Alert, Severity

emit(Alert(
    source="felix-health-check/run",
    severity=Severity.ERROR,
    title="Felix Health Check — office2",
    description="1 service unhealthy: felix-doc-auditor timer inactive.",
    action="systemctl --user status felix-doc-auditor.timer; restart if needed.",
    details={"unhealthy": "felix-doc-auditor.timer", "checked_utc": "2026-07-10T23:00:00Z"},
))
```

## Emit an alert (shell — e.g. from audit.sh)

```bash
AUDIT_SUMMARY="$(head -5 "$FINDINGS")"
/home/claude/kg-automation/scripts/common/alert_bus.sh emit \
  --source "security-monitor/audit" \
  --severity warn \
  --title "Felix Security Alert — office2" \
  --description "${ALERT_COUNT} alert(s) on ${DATE}" \
  --detail summary="${AUDIT_SUMMARY}" || true    # best-effort: never fail the audit
```

## Verify end-to-end

```bash
# On office2 (as claude), with the topic env-file provisioned:
cd /home/claude/kg-automation && python3 -m scripts.common.alert_bus self-test
# exit 0 + an "info" alert appears on the unified thread => delivery OK
```

## Deploy

1. **Mint the topic (operator, out-of-band).** Choose a high-entropy topic id (do not commit it).
   Provision `/home/claude/.config/felix/alert-bus/env` with `FELIX_ALERT_NTFY_TOPIC=<topic>` (0600),
   and ensure each emitter's runtime exports it (felix-deployer env-file, felix-health-check
   `ntfy.env`, security-monitor cron env). Subscribe the new topic in the ntfy phone app.
2. **Queue the manifest.** `deploys/queued/unified-alert-bus.yaml` ships the library + migrated
   emitter code. felix-deployer applies it on its next tick, assigns the applied number, and
   auto-rebaselines the audited surfaces (`scripts/deploy/**`, security-monitor).
3. **Verify** (SC-001..007): run `self-test`; force a felix-deployer failure and confirm the alert
   carries real stderr (SC-002); trigger an enforcement drift event and confirm both the `felix-alert`
   and the GitHub record appear (SC-007); confirm no alert lands on a retired per-component topic.

## Rollback

The bus is additive and emitters migrate one at a time. To roll back a single emitter, `git checkout`
its prior version (its old curl code is in history) and re-queue. Reverting the topic env-file restores
prior routing. No emitter core behavior changes, so rollback carries no service-outage risk.

## Tests

```bash
pytest tests/common/alert_bus -v            # unit tests (subprocess mocked; no live ntfy)
```
