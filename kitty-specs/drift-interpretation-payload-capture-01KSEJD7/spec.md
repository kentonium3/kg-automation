# Specification: Drift Interpretation Payload Capture

**Mission**: drift-interpretation-payload-capture-01KSEJD7
**Source**: GitHub issue [#404](https://github.com/kentonium3/kg-automation/issues/404) (continuing); follow-up to merged mission #53 (`drift-interpretation-debug-capture`, commit `fbfe2a0f`)
**Mission type**: software-dev
**Target branch**: main

---

## Why this mission exists

Mission #53 (`drift-interpretation-debug-capture`) shipped the env-var-gated debug capture code path in `scripts/doc_audit/judgment/drift_interpretation.py` — `_log_raw_response_if_debug` helper + capture call before every `_RetrySchemaError` raise site + unit tests. That mission's WP02 was scoped to do the operational capture (pull main to office2, enable env var, capture payload, document findings, close #404), but the mission design hit a chicken-and-egg: WP02 needed WP01's code merged to main, while spec-kitty merges at end-of-mission only. WP02 was canceled and the mission merged with WP01 alone.

This mission ships the WP02 work as a standalone mission whose preconditions are now satisfied (`_log_raw_response_if_debug` is on main as of `fbfe2a0f`).

---

## User Scenarios & Testing

### Primary scenario

As the operator of the Felix doc-auditor, Kent needs the captured 200-OK LLM response body that triggers `_RetrySchemaError` so he can decide between three root-cause categories (prompt regression, schema regression, model behavior change). The code path to capture this exists in main; what remains is the operational dance: deploy to office2, enable for one tick, capture, record findings.

### Operational flow

1. Operator pulls main onto office2's `/home/claude/kg-automation`
2. Operator enables `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` on `felix-doc-auditor.service` via a systemd drop-in
3. Operator triggers one `start` on the service; waits ~4 minutes for retries to complete
4. Operator extracts the captured payload from `journalctl` using the prefix `drift_interpretation.schema_fail`
5. Operator analyzes the payload, identifies the raise site and root-cause category
6. Operator commits `docs/diagnostics/drift-interpretation-payload-shape.md` with sanitized findings + analysis + recommended fix shape
7. Operator updates `docs/runbooks/doc-auditor-driver-ops.md` with a short note about the env var
8. Operator removes the env var drop-in, runs a clean post-disable tick to confirm no capture lines
9. Operator closes GitHub issue #404 with a summary comment + link to the diagnostic doc
10. Operator files a follow-up fix issue (if needed) with the recommended fix shape

### Acceptance scenarios

- **AS1**: After deploying to office2 and running one debug-enabled tick, the operator can locate the raw payload in `journalctl` output using `grep drift_interpretation.schema_fail`. (Operational verification.)
- **AS2**: A diagnostic document at `docs/diagnostics/drift-interpretation-payload-shape.md` is committed to main with sections "Captured payload (sanitized)", "Raise-site identification", "Schema vs payload diff", "Root cause hypothesis" (one of: prompt / schema / model — with justification), and "Recommended follow-up fix shape".
- **AS3**: `docs/runbooks/doc-auditor-driver-ops.md` has a short note about `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS`, its exact-match semantics, and a link to the diagnostic doc.
- **AS4**: After the post-disable tick, `journalctl` for the auditor service contains zero `drift_interpretation.schema_fail` lines from that tick, confirming the env var is cleanly removed.
- **AS5**: `felix-doc-auditor.timer` remains `disabled` post-mission (steady state).
- **AS6**: GitHub issue #404 is closed with a comment linking to the diagnostic doc and (if a follow-up is needed) the new fix issue number.

### Edge cases

- **EC1 — no drift event during the trigger tick**: if the doc-auditor queue has no drift-eligible signals during the trigger tick, the capture produces nothing. The operator triggers again (the session's mission commits should provide drift-eligible activity). If repeated triggers produce nothing after 15 min, the operator records that in the diagnostic doc as an "investigation incomplete" stub and files an issue to follow up.
- **EC2 — payload exceeds 4096 bytes and signal is truncated**: if the captured body has all its diagnostic content beyond the 4096 truncation limit, the operator either (a) raises the truncation limit (hot-patch to `_DEBUG_CAPTURE_MAX_BYTES`) or (b) records the truncation observation as a separate finding in the diagnostic doc. Hot-patching the constant requires a new code commit, expanding mission scope; defer to a follow-up unless trivially small.
- **EC3 — Tailscale or office2 unreachable**: retry, then escalate to Kent. Do not fabricate findings.

---

## Requirements

### Functional Requirements

| ID | Description | Status |
|----|-------------|--------|
| FR-001 | Operator MUST deploy main (including commit `fbfe2a0f` or later) to office2's `/home/claude/kg-automation`. | Required |
| FR-002 | Operator MUST set `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1` on `felix-doc-auditor.service` via a systemd user drop-in (non-interactive, no editor required). | Required |
| FR-003 | Operator MUST trigger at least one tick of the doc-auditor service while the env var is set. | Required |
| FR-004 | Operator MUST extract at least one captured `drift_interpretation.schema_fail` log line from `journalctl --user -u felix-doc-auditor.service`. (Or document the "no drift event" outcome per EC1.) | Required |
| FR-005 | Operator MUST author `docs/diagnostics/drift-interpretation-payload-shape.md` with the captured (sanitized) payload, raise-site identification, schema vs payload diff, root-cause hypothesis (one of: prompt / schema / model), and recommended follow-up fix shape. | Required |
| FR-006 | Operator MUST add a short note about the env var to `docs/runbooks/doc-auditor-driver-ops.md`, linking to the diagnostic doc. | Required |
| FR-007 | Operator MUST remove the env var drop-in from office2 after capture; verify clean state via `systemctl --user show`; verify the timer remains `disabled`. | Required |
| FR-008 | Operator MUST close GitHub issue #404 with a summary comment that links to the diagnostic doc and (if applicable) the follow-up fix issue number. | Required |
| FR-009 | If a follow-up fix is needed (almost certainly yes), operator MUST file a new issue with `P1-bug` + `area/felix-core` + `spec: brief` labels, cross-referencing #404 and the diagnostic doc. | Required |

### Non-Functional Requirements

| ID | Description | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The mission MUST NOT modify the doc-auditor code path (no edits to `scripts/doc_audit/`). | `git diff` against the mission's lane branch shows zero changes under `scripts/`. | Required |
| NFR-002 | The mission MUST NOT leave `felix-doc-auditor.timer` enabled. | `systemctl --user is-enabled felix-doc-auditor.timer` returns `disabled` post-mission. | Required |
| NFR-003 | Captured raw LLM payloads MUST NOT be committed unredacted. Sanitization happens before the diagnostic doc is committed. | Diagnostic doc review confirms no repo-internal paths, no commit SHAs, no doc text fragments that could leak content. | Required |

### Constraints

| ID | Description | Status |
|----|-------------|--------|
| C-001 | Office2 access via `ssh office2-claude` only; the `claude` user has no sudo. | Required |
| C-002 | This is NOT a bulk edit. Mission touches 2 files (the diagnostic doc + the runbook). `change_mode: "regular"` set in meta.json. | Required |
| C-003 | Mission scope is operational + documentation only. The fix for whatever root cause is identified is a FOLLOW-UP mission. | Required |

---

## Success Criteria

- **SC-001**: A real captured payload sits in office2's journal AND is recorded (sanitized) in the diagnostic doc.
- **SC-002**: An engineer reading the diagnostic doc can immediately understand whether the failure is prompt / schema / model, and can file the follow-up fix mission from the recommendation.
- **SC-003**: GitHub issue #404 is closed with the right cross-references.
- **SC-004**: Office2 is back to its pre-mission steady state (env var unset, timer disabled).

---

## Out of Scope

- The actual fix for the root cause (follow-up mission).
- Re-enabling the timer long-term (waits for both this mission AND #402 to land — but the actual decision is operator-owned, not mission-owned).
- Generalization of debug capture to other judgment scripts (`audit_interpretation`, `tier_classification`, etc.). Each judgment script can grow its own capture in a separate mission if needed.

---

## Dependencies

- **#53** (merged at `fbfe2a0f`): the code path being exercised. Mission cannot start without the helper symbol on main.
- **office2 access**: `ssh office2-claude` for the operational steps.
- **GitHub issue #404 access**: for closure + follow-up filing.

---

## Discovery Decisions (recorded for audit)

1. **Scope = operational only**: confirmed in the prior mission's discovery. No new decisions needed.
2. **Storage = journal logs only**: same as prior mission. No raw payload committed.
3. **Mission shape = single WP**: the operational sequence is tightly coupled (one ssh session worth of work). One WP avoids spec-kitty's end-of-mission merge model causing another chicken-and-egg.
