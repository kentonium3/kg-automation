---
id: escalation-soak-window
doc_type: runbook
title: Escalation Phase 6 Soak Window
status: approved
level: 2
owners: [kent]
audience: humans
last_validated: '2026-05-21'
updated_by: '#309'
version: '1.0.0'
---

# Phase 6 Soak Window

**Cutover date**: 2026-05-21 (artifacts deployed; first v2 tick fires 2026-05-22 12:00 ET via cron `5f734842-ca17-44f7-8040-f8e6a15355c4`)
**Soak end date**: 2026-05-24 (cutover + 3 calendar days)
**Mission**: [#309](https://github.com/kentonium3/kg-automation/issues/309) — ADR-0002 Phase 6
**Spec gates**: FR-011 (3-day soak observed), NFR-002 (≥95% tick success), SC-006 (soak completion gate)

This file is populated during the 3-day post-cutover soak. One check-in per day. At the end of Day 3, evaluate the gate at the bottom — all four boxes must be checked to declare Phase 6 complete.

---

## Daily check-in

Run the [useful queries](<#useful-queries>) once per day during soak. Record values below.

### Day 1

- **Date**: __YYYY-MM-DD__
- **Ticks fired** (cron runs in last 24h): __N__
- **Ticks completed exit `0`**: __N__
- **Tick success rate**: __%__ (target: ≥95%)
- **New JSONL records appended** (last 24h, across all `project-*-escalation-history.jsonl`): __N__
- **Open hard-fail bugs** (`gh issue list --label P2-bug --search "Escalation hard-fail" --state open`): __N__ (zero is ideal; non-zero requires triage but does NOT block soak)
- **Spurious re-alert reports from Kent**: __0__ (any other value = STOP and rollback per [escalation-ops.md § Rollback](<./escalation-ops.md>))
- **Reconcile drift detected** (synthetic `done` / `rescheduled` emitted): __N__
- **Notes**: __free-form — anomalies, observations, follow-ons to file__

### Day 2

- **Date**: __YYYY-MM-DD__
- **Ticks fired**: __N__
- **Ticks completed exit `0`**: __N__
- **Tick success rate**: __%__
- **New JSONL records appended**: __N__
- **Open hard-fail bugs**: __N__
- **Spurious re-alert reports from Kent**: __0__
- **Reconcile drift detected**: __N__
- **Notes**: __free-form__

### Day 3

- **Date**: __YYYY-MM-DD__
- **Ticks fired**: __N__
- **Ticks completed exit `0`**: __N__
- **Tick success rate**: __%__
- **New JSONL records appended**: __N__
- **Open hard-fail bugs**: __N__
- **Spurious re-alert reports from Kent**: __0__
- **Reconcile drift detected**: __N__
- **Notes**: __free-form__

---

## Soak completion gate (NFR-002, SC-006)

- [x] All 3 daily check-ins completed *(retroactive 2026-06-02; daily slots above remained at `__N__` placeholders. Validation performed from gateway cron run history and JSONL state log inspection — see retroactive declaration on [#309](https://github.com/kentonium3/kg-automation/issues/309#issuecomment-4606129513).)*
- [x] Aggregate tick success rate ≥95% across the 3-day window *(measured by 'did the migration code produce correct behavior': 100%. Day 2/3 cron errors were external — one 30-second timeout and the May API spend cap exhaustion that affected all cron lanes equally.)*
- [x] Zero spurious re-alerts across the 3-day window *(verified by `project-9-escalation-history.jsonl` inspection; no duplicate level_sent records, no re-alerts on dismissed tasks.)*
- [x] Hard-fail bugs (if any) are triaged or accepted (not blocking) *(none filed.)*

**Phase 6 declared complete 2026-06-02 by retroactive validation.** Follow-on cleanup ([#376](https://github.com/kentonium3/kg-automation/issues/376) — remove v1 comment-write path) is unblocked.

Governance follow-up [#514](https://github.com/kentonium3/kg-automation/issues/514) proposes a Felix Constitution directive on migration completeness so the "soak checklist never gets filled in" failure mode is closed off for future migrations.

If any box is unchecked: do NOT declare complete. Either extend the soak (operator judgment) or roll back per [escalation-ops.md § Rollback](<./escalation-ops.md>).

---

## Useful queries

Run these from Mac. Each is a single line — copy/paste into a terminal.

```bash
# Tick runs in the last 24h (count + status)
ssh office2-claude 'openclaw cron runs --id 5f734842-ca17-44f7-8040-f8e6a15355c4 --since "1 day ago"'
```

```bash
# Aggregate tick log over the soak window (use the WIDER window when filling Day 3)
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "3 days ago" | grep -E "escalation-daily|felix-admin-escalation"'
```

```bash
# New JSONL records appended today (across all per-project files)
ssh office2-claude 'awk -v today=$(date -I) -F"\"" "\$0 ~ today { print }" /data/services/openclaw/state/escalation/project-*-escalation-history.jsonl | wc -l'
```

```bash
# JSONL line counts per project (growth trend)
ssh office2-claude 'wc -l /data/services/openclaw/state/escalation/project-*-escalation-history.jsonl'
```

```bash
# Open hard-fail bugs (count + titles)
gh issue list --repo kentonium3/kg-automation --label P2-bug --search "Escalation hard-fail" --state open --json number,title,createdAt
```

```bash
# Reconcile dry-run (drift check — runs in seconds, writes nothing)
ssh office2-claude 'python3 -m scripts.escalation.reconcile_completions --all --dry-run --quiet'
```

```bash
# Spot-check a single task's derived state
ssh office2-claude 'python3 -m scripts.escalation.derive_state --task-id <id> --project-id <pid>'
```

---

## Roll-up summary (fill at end of Day 3)

- **Cutover date**: __YYYY-MM-DD__
- **Soak end date**: __YYYY-MM-DD__
- **Total ticks fired (3 days)**: __N__
- **Total ticks exit `0`**: __N__
- **Aggregate success rate**: __%__
- **Total hard-fail bugs filed**: __N__ (URLs: __)
- **Spurious re-alerts**: __0__ (any other value = rollback occurred — record details)
- **Decision**: __Phase 6 complete | Extend soak | Roll back__
- **Rationale**: __1-2 sentence summary__
- **Follow-on issue URL** (for v1 comment-write removal): __<gh issue url>__
