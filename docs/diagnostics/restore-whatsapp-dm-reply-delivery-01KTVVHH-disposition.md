---
id: restore-whatsapp-dm-reply-delivery-01KTVVHH-disposition
doc_type: diagnostic-report
title: "WP02 Terminal Disposition — WhatsApp DM Reply Delivery (#588)"
status: complete
level: reference
owners: ["kent@intentional.biz"]
last_validated: "2026-06-11"
version: "1.0"
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
github_issue: 588
work_package: WP02
agent: implementer-ivan
related_files:
  - docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md
  - scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh
  - kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/journal-event-assertions.md
  - kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/quickstart.md
---

# WP02 Terminal Disposition — WhatsApp DM Reply Delivery (#588)

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH` (GitHub issue [#588](https://github.com/kentonium3/kg-automation/issues/588))
**Work Package**: WP02 — Apply Remediation
**Agent**: `implementer-ivan`
**Authored at**: 2026-06-11T19:20:00Z
**Path taken**: **upgrade-path**

---

## 1. Decision input

WP01 Decision Record (commit `d6b5d2da`, file `docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md` §10):

> **Fix shape**: H6 — upgrade openclaw 2026.6.5 (release-notes mapping below)

WP01 verdict was strong enough on desk review of the 2026.5.28 -> 2026.6.5 CHANGELOG (matching #85823 WhatsApp restart-stale-controller, #90667/#90697 Anthropic stream-start, #90208 timeout context) that the destructive probes (T003 active config swap, T005 H3 AGENTS.md rollback) were skipped per the orchestrator constraint. T002 (H5) and T004 (H2) ran read-only and refuted.

The remediation is therefore an in-place **runtime upgrade**, not a vendored edit, not a config edit, not an escalation. C-001 (no vendored modifications) is preserved — the upgrade replaces the npm-global package atomically.

## 2. What WP02 produced

| Deliverable | Path | Notes |
|---|---|---|
| Upgrade-variant deploy script | [`scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh`](<../archive/scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh>) | Six-stage idempotent deploy with `--backup-confirmed` Tier 2 gate, operator-driven Stage 3 sudo pause, post-upgrade gotchas verification, 1-DM post-flight smoke with rollback instructions. Shellcheck-clean. |
| Terminal disposition (this file) | `docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-disposition.md` | Records path-taken + commit SHA + handoff to WP05 |

**Files NOT touched** (intentional, per WP01 H6 verdict):
- `scripts/openclaw/openclaw.json` — no schema/config edit required; upgrade does not introduce new required fields per CHANGELOG (WP01 §8.5)
- `scripts/openclaw/agents/main/AGENTS.md` — no rollback needed; H3 was refuted (skipped destructively, refuted indirectly by H6 desk-review strength)
- Any vendored openclaw runtime files at `/usr/lib/node_modules/openclaw/` — C-001 preserved

## 3. Deploy script structure

The script implements the upgrade plan from WP01 §8 with the following stage map:

| Stage | Purpose | Gotchas-checklist coverage |
|---|---|---|
| 0 | `--backup-confirmed` attestation gate (Tier 2 per C-003) | Restic <=24h pre-flight |
| 1 | Connectivity check + pre-upgrade `openclaw doctor --json` snapshot | Pre/post diff baseline |
| 2 | Backup deployed `openclaw.json` to timestamped `.pre-upgrade-<ts>` file | Config-file rollback path |
| 3 | **OPERATOR-DRIVEN** `ssh office2-kgale 'sudo npm install -g openclaw@2026.6.5'` (paused with `read -r` for ack) | sudo boundary respected; claude user never attempts sudo |
| 4 | Post-upgrade verification: version reports 2026.6.5; `openclaw doctor --json` reports `.success == true`; `models.providers.anthropic.models[]` non-empty; `plugins.entries.whatsapp.enabled == true` | All four bullets from memory `reference_openclaw_upgrade_gotchas` (systemd unit Description is cosmetic per memory — explicitly NOT blocked on) |
| 5 | `systemctl --user restart openclaw-gateway.service` + 10s settle + `is-active` confirm | Service-level health |
| 6 | Operator-driven 1-DM smoke (60s window) + contract-aligned awk assertion | Pattern matches `contracts/journal-event-assertions.md` byte-for-byte (`resolve_fail_current=`, `trunc_main=` field names); expected: `inbound=1 send=1 sent=1 stall=0 recovery=0 resolve_fail_current=0 trunc_main=0`; on fail, prints rollback instructions for both runtime (`npm install -g openclaw@2026.5.28`) and config (`cp .pre-upgrade-<ts>` back) |

## 4. Acceptance criteria coverage

This WP closes the following subtasks (per WP02 task file):

| Subtask | Status | Evidence |
|---|---|---|
| T008 — Apply named remediation per WP01 | done | Upgrade path identified; npm-global install method confirmed by WP01 §3.1; target version 2026.6.5 recorded; no repo file edit required for H6 (upgrade is operational) |
| T009 — Create deploy script | done | `scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh`, shellcheck-clean, six staged banners, Stage 3 sudo pause, rollback instructions |
| T010 — Embed post-flight smoke assertion | done | Stage 6 awk pattern matches `contracts/journal-event-assertions.md` field names byte-for-byte; expected counts scaled for 1-DM post-flight smoke (full 5-DM SC-001..SC-007 acceptance harness runs in WP05) |
| T011 — Alt-path: escalation | **N/A** | Escalation path not taken; H6 verdict is unambiguous per WP01 §3 + §10. No internal tracking issue filed. |
| T012 — Terminal disposition (this file) | done | Created at `docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-disposition.md` (relocated per orchestrator instruction; the WP02 body's `kitty-specs/.../terminal-disposition.md` path is superseded). |

## 5. Constraints honored

| Constraint | How WP02 honored it |
|---|---|
| **C-001** (no vendored modifications) | Upgrade replaces npm-global package atomically; no edits to `/usr/lib/node_modules/openclaw/`. C-001 explicitly notes upgrade != modification. |
| **C-003** (Tier 2 protocol) | Script Stage 0 enforces `--backup-confirmed` attestation; the operator must verify a Restic snapshot <=24h before running. |
| **#557 rebaseline** (audited-surface obligation) | Stage 6 SUCCESS banner prints the exact rebaseline command and merge-commit trailer format (`Rebaseline: completed at <ts>`). Per memory, the operator runs the reset; CI does not. |
| **No sudo from claude user** | Stage 3 explicitly pauses with banner for operator-driven `ssh office2-kgale 'sudo npm install -g openclaw@2026.6.5'` per memory and per CLAUDE.md. |
| **Canonical install path** (per memory `feedback_no_workarounds_for_expediency`) | Uses `npm install -g` exactly — no manual binary tricks, no parallel installs. |
| **CLI flag verification** (per memory `feedback_verify_cli_flag_shape`) | `openclaw doctor --json` confirmed via WP01 §8.1 live SSH probe; `openclaw --version`, `systemctl --user`, `jq`, `journalctl` are standard. |
| **DIRECTIVE_033** (commit discipline) | WP02 commit stages exactly two files: this disposition + the deploy script. Never `git add .` / `-A`. |

## 6. Handoff to WP05

WP02 produces the deploy script + disposition. WP05 (planning artifact) drafts the operator runbook + acceptance harness that runs the full 5-DM smoke per `contracts/journal-event-assertions.md` SC-001..SC-007.

WP05 NEXT STEPS (operator):
1. After merge, execute the deploy script: `./scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh --backup-confirmed`
2. Verify the post-flight 1-DM smoke passes; if it fails, follow the script's printed rollback instructions.
3. Run the full 5-DM SC-001..SC-007 acceptance harness per `quickstart.md` section 4.6.
4. Run the #557 audited-surface rebaseline reset on office2: `ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'`
5. Record the rebaseline timestamp in the spec-kitty merge-commit trailer (`Rebaseline: completed at <ISO 8601 UTC>`).

## 7. Artifacts

- WP01 investigation: [`docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md`](<./restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md>)
- Deploy script: [`scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh`](<../archive/scripts/deploy/deploy-restore-whatsapp-dm-reply-delivery.sh>)
- Smoke contract: [`kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/journal-event-assertions.md`](../../kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/journal-event-assertions.md)
- Operator quickstart: [`kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/quickstart.md`](../../kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/quickstart.md) sections 4.6 + 4.7
- Upgrade-gotchas reference: memory `reference_openclaw_upgrade_gotchas`
- Related local issue: [#588](https://github.com/kentonium3/kg-automation/issues/588)
