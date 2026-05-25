# Implementation Plan: Drift Interpretation Payload Capture

**Mission**: drift-interpretation-payload-capture-01KSEJD7
**Date**: 2026-05-24
**Spec**: [spec.md](spec.md)
**Branch**: target=`main`, planning-base=`main`, merge-target=`main` (matches)

---

## Summary

Single-WP operational mission. Pull main (with mission #53's WP01 code) to office2, enable `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` via a systemd drop-in, trigger one tick, extract the captured payload from `journalctl`, sanitize and analyze, author `docs/diagnostics/drift-interpretation-payload-shape.md`, update `docs/runbooks/doc-auditor-driver-ops.md` with a short env-var note, remove the drop-in and verify clean state, then close GitHub issue #404 and file a follow-up fix issue.

---

## Technical Context

**Language/Version**: n/a — operational + documentation only
**Primary Dependencies**: ssh, systemctl-user, journalctl, gh CLI; office2 venv at `/data/services/openclaw/felix-doc-auditor-driver/venv/`
**Storage**: stderr → journalctl on office2 (transient). Diagnostic doc committed to repo (sanitized).
**Testing**: no automated tests; mission validation is the captured artifact + doc + closure
**Target Platform**: office2 (Ubuntu 24.04 LTS) + macOS for repo edits + GitHub for issue work
**Project Type**: single project
**Performance Goals**: capture + analyze + document within ~30 min of mission start
**Constraints**: timer stays disabled; raw payloads not committed unsanitized; no code edits under `scripts/`
**Scale/Scope**: 2 files modified (1 new diagnostic doc + 1 runbook edit); 1 GH issue closed + 1 filed; office2 systemd drop-in created and removed

---

## Charter Check

Risk tier: **Tier 3 (Standard)** — operational work + documentation. No service deploys, no schema changes, no host config beyond a temporary systemd drop-in. Standard validation: doc review + post-disable verification tick.

Charter governance is unresolved (memory `project_charter_tool_registry_mismatch`). Compact mode.

Architecture doc impact: none (env var note in the doc-auditor runbook is the only doc surface touched besides the diagnostic itself).

**Pass**: Charter Check passes.

---

## Project Structure

### Mission artifacts

```
kitty-specs/drift-interpretation-payload-capture-01KSEJD7/
├── meta.json
├── spec.md
├── plan.md           (this file)
├── tasks.md
├── checklists/
│   └── requirements.md
└── tasks/
    └── WP01-deploy-capture-document-close.md
```

### Source code (repository root)

```
docs/
├── diagnostics/
│   └── drift-interpretation-payload-shape.md   # NEW
└── runbooks/
    └── doc-auditor-driver-ops.md               # MODIFIED (short env-var note)
```

**Structure Decision**: Single project layout. No new directories.

---

## Phase 0 / Phase 1 (consolidated)

This mission's research and design are inherited from merged mission #53. Key references:

- Env var contract: `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` (exact-match) — see #53's `contracts/env-vars.md`
- Log line format: `WARNING drift_interpretation.schema_fail | <error_message> | <raw_response_truncated>`
- Truncation: 4096 bytes
- Raise sites: 11 confirmed by mission #53 implementation (grep `_log_raw_response_if_debug` in `scripts/doc_audit/judgment/drift_interpretation.py`)

Operational decisions specific to this mission:

- **D1 — systemd drop-in path**: non-interactive write to `~/.config/systemd/user/felix-doc-auditor.service.d/debug-capture.conf`. Avoids `systemctl --user edit` (interactive editor). Cleanup = `rm` the file + `daemon-reload`.
- **D2 — diagnostic doc filename**: `docs/diagnostics/drift-interpretation-payload-shape.md` (no `xx_` prefix, no issue number — operational analysis, not an upstream bug report).
- **D3 — tick trigger**: `systemctl --user start felix-doc-auditor.service` (one-shot). Service runs synchronously to completion. With 4-retry × ~50s delays per failing event, expect ~4 min wall-clock per tick.
- **D4 — sanitization scope**: redact repo-internal paths and commit SHAs; preserve JSON/structural shape. Operator's judgment for borderline cases.

No NEEDS CLARIFICATION items.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| No drift event during the trigger tick | Low | Low | Multiple commits today; auditor queue is hot. Retry up to 2x; record "no event" outcome per EC1 if persistent. |
| Captured payload exceeds 4096 bytes with key signal truncated | Low | Low-Medium | Note in diagnostic doc; defer truncation-limit bump to a follow-up unless trivially small. |
| Tailscale or office2 unreachable | Very Low | Medium | Retry once; escalate to Kent. Don't fabricate findings. |
| Sanitization leaks repo content | Low | Medium | Two-pass review before commit; explicit "redacted X" markers in the doc. |
| Office2's `/home/claude/kg-automation` is on a different branch than main | Very Low | Low | `git pull origin main` already executed for prior session work; verify with `git rev-parse HEAD` matches local main HEAD. |

---

## Single WP Decision

This mission ships as **one work package** (WP01). Rationale:

- Operational sequence is tightly coupled (one ssh session worth of work).
- Single WP avoids the chicken-and-egg that killed mission #53's WP02 (no dependent WP needs the WP01 merge mid-mission).
- Per spec-kitty sizing guidance: 7 subtasks per WP is within ideal range.

WP01 has 7 subtasks (T001–T007), mirroring the canceled WP02 structure renumbered.

---

## Branch Contract — Final Restatement

- **Current branch at plan completion**: `main`
- **Planning/base branch**: `main`
- **Merge target**: `main`
- **Matches target**: `true`

---

## Next Suggested Command

`/spec-kitty.tasks` (user must invoke explicitly per the plan command's MANDATORY STOP).
