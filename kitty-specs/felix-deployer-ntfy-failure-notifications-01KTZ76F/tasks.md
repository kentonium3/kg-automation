# Tasks: Felix-deployer ntfy Failure Notifications

**Mission**: `felix-deployer-ntfy-failure-notifications-01KTZ76F`
**Planning base branch**: `main` (per setup-plan resolver)
**Merge target branch**: `main`
**Currently working on**: coordination branch `kitty/mission-felix-deployer-ntfy-failure-notifications-01KTZ76F` (#1716 split-authority workaround)
**Source issue**: kentonium3/kg-automation#595
**Spec**: [spec.md](./spec.md) — 15 FRs, 4 NFRs, 8 Cs
**Plan**: [plan.md](./plan.md) — 7 implementation concerns IC-01..IC-07
**Contract**: [contracts/ntfy-notification-v1.md](./contracts/ntfy-notification-v1.md) — wire-shape contract (already committed during plan phase)

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Rewrite `scripts/deploy/felix-deployer/notify.py` end-to-end for ntfy substrate (new public function `dispatch_failure_notification`, closed `error_code` enum, build_notification helper) | WP01 | | [D] |
| T002 | Add `tests/deploy/test_notify.py` covering payload rendering, secret redaction, ≤500-char truncation, success LibResult shape | WP01 | [P] vs T003 | [D] |
| T003 | Extend `tests/deploy/test_notify.py` with each failure-mode error_code (NTFY_MISSING_TOPIC, NTFY_CURL_MISSING, NTFY_SPAWN_FAILED, NTFY_TIMEOUT, NTFY_NETWORK_UNREACHABLE, NTFY_HTTP_ERROR, NTFY_UNKNOWN) | WP01 | [P] vs T002 | [D] |
| T004 | Update `scripts/deploy/felix-deployer/_tick.py` to call `dispatch_failure_notification` and rename `PHASE_TO_DM_PHASE` → `PHASE_TO_NOTIFY_PHASE` | WP01 | | [D] |
| T005 | Update `tests/deploy/test_deployer.py` for renamed symbols and the new mock-target path | WP01 | | [D] |
| T006 | Add `EnvironmentFile=-/home/claude/.config/felix-deployer/env` to `scripts/deploy/felix-deployer/felix-deployer.service` | WP02 | |
| T007 | Strip step 5 (openclaw cron registration) from `scripts/deploy/deploy-felix-deployer-bootstrap.sh`; renumber subsequent steps and update header docs | WP02 | |
| T008 | Update `--apply` mode of `deploy-felix-deployer-bootstrap.sh` to write `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml` with `notes` referencing 0001 as superseded | WP02 | |
| T009 | Add `scripts/deploy/felix-deployer/env.sample` template with `FELIX_DEPLOYER_NTFY_TOPIC=` placeholder and operator-facing comments | WP02 | |
| T010 | Update `docs/design/architecture/data/data-flows.json` — add `felix-deployer-ntfy-egress` outbound entry; validate against schema | WP03 | [P] vs T011/T012 |
| T011 | Update `docs/design/architecture/data/service-inventory.json` — felix-deployer outbound dep on ntfy.sh; new env-file path | WP03 | [P] vs T010/T012 |
| T012 | Update `docs/design/architecture/data/credential-manifest.json` — add `felix-deployer-ntfy-topic` env credential entry | WP03 | [P] vs T010/T011 |
| T013 | Update narrative markdown counterparts: `data-flows.md`, `data-flows.view.md`, `service-inventory.md`, `credentials-and-secrets.md` | WP03 | |
| T014 | Update `docs/design/felix-capability-roadmap.md` — felix-deployer capability row reflects substrate swap | WP03 | |

Total: 14 subtasks across 3 WPs.

---

## Work Packages

### WP01 — Notify substrate rewrite + tests

- **Goal**: Replace `notify.py`'s broken openclaw-cron dispatch with a working ntfy.sh dispatch. Add comprehensive unit tests for payload rendering, redaction, truncation, and every error-mode code path. Update the single caller (`_tick.py`) and its test.
- **Priority**: P0 — this is the substantive code change the mission exists to deliver.
- **Independent test**: `make test` passes; new test_notify.py covers ≥90% of `notify.py` lines (statement) and ≥80% of branches; existing test_deployer.py continues passing.
- **Included subtasks**: T001, T002, T003, T004, T005
- **Implementation sketch**:
  1. Read the contract at `contracts/ntfy-notification-v1.md` and use its title/body templates verbatim.
  2. Rewrite `notify.py`: new module-level constants for `NTFY_BASE_URL`, header values; new `_render_title()` and `_render_body()` helpers; new `dispatch_failure_notification()` public function; closed `_ERROR_CODES` enum.
  3. Use `subprocess.run(["curl", ...], input=body, capture_output=True, text=True, check=False)` per the curl-invocation shape in the contract.
  4. Map curl exit codes to LibResult `error_code` per the contract's response-handling table.
  5. Write `tests/deploy/test_notify.py` — use `monkeypatch.setattr(notify.subprocess, "run", fake_run)` per existing `tests/deploy/test_deployer.py` style.
  6. Update `_tick.py`: change `from .notify import dispatch_failure_dm` to `from .notify import dispatch_failure_notification`; rename `PHASE_TO_DM_PHASE` to `PHASE_TO_NOTIFY_PHASE` (semantic identical); change the call site; remove `CRON_NAME` import.
  7. Update `tests/deploy/test_deployer.py` — change mock target from `notify.dispatch_failure_dm` to `notify.dispatch_failure_notification`; update assertion symbols.
- **Parallel opportunities**: T002 and T003 can be authored as separate test classes/files conceptually; both touch `tests/deploy/test_notify.py` so they serialize on the file.
- **Dependencies**: none (first WP).
- **Risks**: test brittleness on curl exit-code semantics (mitigation: assert on `LibResult.details["error_code"]`, not on stderr substring); import-time side effects sneaking in (mitigation: NFR-003 explicitly enforced; smoke-import test included).
- **Estimated prompt size**: ~450 lines.

### WP02 — Bootstrap script + systemd + env.sample

- **Goal**: Remove the broken openclaw cron registration from the bootstrap script; add the systemd `EnvironmentFile=` directive; ship `env.sample` so the operator has a template; update the applied-entry write to produce `0002-bootstrap-felix-deployer-v2.yaml`.
- **Priority**: P0 — without this, the post-merge redeploy still fails at step 5.
- **Independent test**: `bash -n scripts/deploy/deploy-felix-deployer-bootstrap.sh` passes (syntax); `./scripts/deploy/deploy-felix-deployer-bootstrap.sh --dry-run` runs end-to-end without invoking `openclaw cron edit/run` and prints the new 6-step (not 7-step) preview; `grep -c 'felix-deployer-alert' scripts/deploy/deploy-felix-deployer-bootstrap.sh` returns 0.
- **Included subtasks**: T006, T007, T008, T009
- **Implementation sketch**:
  1. Add `EnvironmentFile=-/home/claude/.config/felix-deployer/env` to the `[Service]` section of `felix-deployer.service` (the `-` prefix makes it non-fatal).
  2. In `deploy-felix-deployer-bootstrap.sh`:
     - Remove the entire step 5 block (the `openclaw cron edit ...` invocation and surrounding logs).
     - Renumber: step 6 → step 5 (post-flight timer verify); step 7 → step 6 (applied-entry write).
     - Update the file header comment and the `--dry-run` preview text to reflect 6 steps.
     - Update `APPLIED_NAME` constant: `0001-bootstrap-felix-deployer` → `0002-bootstrap-felix-deployer-v2`.
     - Update `NAME` in the inline-manifest heredoc: `bootstrap-felix-deployer` → `bootstrap-felix-deployer-v2`.
     - Add `notes:` block lines referencing `0001-bootstrap-felix-deployer.yaml` as superseded and citing this mission's slug.
     - Remove `OPENCLAW_CRON_NAME` and `ALERT_TEMPLATE_REMOTE` constants (no longer used).
  3. Create `scripts/deploy/felix-deployer/env.sample` with the template, mode 0644.
- **Parallel opportunities**: minimal — single bash file dominates the work.
- **Dependencies**: **None at code-write time** (does not import from notify.py). For OPERATIONAL alignment (Step 5 referencing env file the systemd unit reads), the env file path constant should appear in both `felix-deployer.service` and the bootstrap script's documentation — the path is `/home/claude/.config/felix-deployer/env`.
- **Risks**: heredoc-quoting bugs in the applied-entry write; missed `felix-deployer-alert` references in stale comments. Mitigation: grep verification before commit.
- **Estimated prompt size**: ~380 lines.

### WP03 — Architecture data updates

- **Goal**: Update the canonical JSON architecture-data files for the new outbound HTTP flow and env credential; update narrative markdown counterparts; touch the capability roadmap row.
- **Priority**: P0 — standing requirement from CLAUDE.md ("Any implementation that deploys, modifies, or removes a service, credential, port, or data flow MUST update the relevant files in `docs/design/architecture/data/`").
- **Independent test**: each JSON file validates against its schema; `python tooling/scripts/validate_docs.py` passes for any markdown files touched; `git diff docs/design/architecture/data/*.json | jq` parses cleanly.
- **Included subtasks**: T010, T011, T012, T013, T014
- **Implementation sketch**:
  1. Read the existing entry shapes in each JSON file (the schemas live as `<name>.schema.json` siblings in the same dir). Confirm field names by example, not by guessing.
  2. Author the new entries matching the data-model.md outline (felix-deployer-ntfy-egress in data-flows; outbound_dependencies + environment_files updates in service-inventory; felix-deployer-ntfy-topic in credential-manifest).
  3. Update narrative markdown:
     - `data-flows.md`: new section/row describing the egress flow.
     - `data-flows.view.md`: Mermaid edge from `felix-deployer` to `ntfy.sh` if applicable.
     - `service-inventory.md`: felix-deployer service row reflects env-file dep and outbound URL.
     - `credentials-and-secrets.md`: new entry for FELIX_DEPLOYER_NTFY_TOPIC with rotation policy note.
  4. Update `docs/design/felix-capability-roadmap.md`: felix-deployer capability row reflects "failure-notification substrate: ntfy.sh".
- **Parallel opportunities**: T010, T011, T012 each touch a distinct JSON file → can be authored in parallel. T013 batches the four markdown files. T014 is a single-file edit.
- **Dependencies**: depends on the contract (already committed) for wire-shape source of truth; does NOT depend on WP01 or WP02 code changes (the docs describe the intended end state, not the source files).
- **Risks**: schema-validation failures; off-pattern field shapes. Mitigation: read sibling entries first; don't invent fields.
- **Estimated prompt size**: ~350 lines.

---

## MVP Scope

WP01 IS the MVP. It alone:
- Switches the substrate (FR-001).
- Preserves the failure-isolation invariant (FR-002, NFR-001, C-003).
- Lands the redact-then-truncate guarantee (FR-003).
- Carries the full payload shape (FR-004).
- Retires the dead code path (FR-014).
- Provides regression-test coverage (FR-013, SC-001..SC-003).

WP02 and WP03 are MUST-HAVE for closing the mission per acceptance criteria — but if the mission needed to ship the minimum-viable code change, WP01 alone would do it. WP02 unblocks the post-merge redeploy; WP03 satisfies the standing architecture-doc-update requirement.

---

## Dependencies

- WP01 → WP02: not a hard dependency at code-write time (no imports). WP02 just needs the project to compile so tests run.
- WP01 → WP03: NOT dependent (docs describe end state, not code symbols).
- WP02 → WP03: NOT dependent.

**Lane structure**: Per memory `reference_speckitty_issue_1684` (lane base ignores WP-level dependencies), sequence all three WPs on the same lane. WP01 → WP02 → WP03 strictly serially. Single lane avoids the lane-base-derivation bug entirely.

---

## Parallelization

Minimal cross-WP parallelism within this mission. The 3-WP serial flow is the right shape — total wall-clock dominated by review cycles, not implementation time. Multi-lane would add risk (#1684) for negligible gain.

WITHIN each WP, the [P] markers in the Subtask Index indicate file-local parallelism (e.g., T002/T003 can be co-authored in separate test classes), but a single implementer agent will sequence them anyway.

---

## Next command

`/spec-kitty.implement` to start the implement-review loop. The CLI will dispatch WP01 first.

Per memory `reference_speckitty_3_2_open_p0_p1_bugs`:
- Always use the full mission slug `felix-deployer-ntfy-failure-notifications-01KTZ76F`, never `01KTZ76F` (mid8).
- If `/spec-kitty.analyze` is required by implement gating, skip recording analysis as long as the mission compiles; if gating forces it, re-run between each WP transition (cost: a few minutes of LLM time per transition).
- Read the canonical WP prompt at `kitty-specs/.../tasks/WPxx-slug.md`, never `/tmp/spec-kitty-implement-WPxx.md` (collision risk per #1831).
