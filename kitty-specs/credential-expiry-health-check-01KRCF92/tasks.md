# Tasks: Credential Expiry Health Check

**Mission**: `credential-expiry-health-check-01KRCF92`
**Generated**: 2026-05-11
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Research**: [research.md](./research.md) · **Data model**: [data-model.md](./data-model.md) · **Contracts**: [contracts/](./contracts/) · **Quickstart**: [quickstart.md](./quickstart.md)

**Branch contract**:

- Current branch at tasks start: `main`
- Planning/base branch: `main`
- Final merge target: `main`
- `branch_matches_target`: true

---

## Subtask Index (reference only — not a tracking surface)

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Audit `kentonium3` PAT, add `kentonium3-pat` entry to `credential-manifest.json` (FR-013) | WP01 | — | [D] |
| T002 | Capture live manifest snapshot to `tests/security/fixtures/manifest-valid.json` (post-T001) | WP01 | — | [D] |
| T003 | Create `tests/security/fixtures/manifest-near-expiry.json` (one credential inside warning window) | WP01 | [D] |
| T004 | Create manifest-quality fixtures (missing field, bad cadence, invalid JSON, not-a-dict) | WP01 | [D] |
| T005 | Capture/synthesize activity signal fixtures (tailscale + openclaw) | WP01 | [D] |
| T006 | Create package skeleton `scripts/security/credential_health_check/__init__.py` | WP02 | — | [D] |
| T007 | Implement `manifest.py` (Credential, ManifestQualityIssue, read_manifest, ManifestUnreadableError) per `contracts/manifest-reader.md` | WP02 | — | [D] |
| T008 | Implement `cadence.py` (compute_boundary, is_within_warning_window) per `data-model.md` | WP02 | [P] with T007 | [D] |
| T009 | Write `tests/security/test_manifest.py` against the manifest fixtures | WP02 | — | [D] |
| T010 | Write `tests/security/test_cadence.py` (boundary math, warning-window edge cases) | WP02 | [D] |
| T011 | Implement `signals.py` skeleton with `ActivitySignalFailure` dataclass + reader registry | WP03 | — | [D] |
| T012 | Implement `tailscale_auth_signal(credential)` per `contracts/activity-signal-readers.md` §Reader 1 | WP03 | — | [D] |
| T013 | Implement `whatsapp_session_signal(credential)` + `openclaw channels status` duration parser per §Reader 2 | WP03 | [P] with T012 | [D] |
| T014 | Write `tests/security/test_tailscale_signal.py` against tailscale fixtures | WP03 | — | [D] |
| T015 | Write `tests/security/test_whatsapp_signal.py` + duration-parser unit tests | WP03 | [D] |
| T016 | Implement `github_writer.py` title generation for all 3 variants per `contracts/github-issue-writer.md` | WP04 | — |
| T017 | Implement body templating for all 3 variants (cadence, activity-staleness, manifest-quality batch) | WP04 | — |
| T018 | Implement `dedup_check(title_prefix)` via `gh issue list --search 'in:title …'` | WP04 | — |
| T019 | Implement `create_issue(title, body, labels, assignees)` via `gh issue create` | WP04 | — |
| T020 | Write `tests/security/test_github_writer.py` covering titles, bodies, stubbed `gh` invocations | WP04 | — |
| T021 | Implement `vikunja_writer.py` skeleton: token loader, title + description templating | WP05 | — |
| T022 | Implement `lookup_inbox_project_id()` via Vikunja API | WP05 | — |
| T023 | Implement `create_task(credential, boundary, github_issue_number)` with `due_date = boundary − 7 days` | WP05 | — |
| T024 | Write `tests/security/test_vikunja_writer.py` (templating, due-date math, stubbed API) | WP05 | — |
| T025 | Implement `orchestrator.py`: per-cycle loop tying readers + writers + dedup together | WP06 | — |
| T026 | Implement `__main__.py`: argparse, structured logging, `--dry-run` and `--manifest` flags | WP06 | — |
| T027 | Cycle ID generation + structured log lines per `data-model.md` §CycleLog | WP06 | [P] with T026 |
| T028 | FR-012 wire-up: batched manifest-quality issue per cycle when malformed entries exist | WP06 | — |
| T029 | Write `tests/security/test_orchestrator.py` covering end-to-end orchestration with mocked surfaces | WP06 | — |
| T030 | Author `scripts/office2/credential-health-check.timer` (`OnCalendar=*-*-* 13:00:00`, `Persistent=true`) | WP07 | — |
| T031 | Author `scripts/office2/credential-health-check.service` (Type=oneshot, ExecStart=python3 -m credential_health_check, TimeoutStartSec=10min) | WP07 | — |
| T032 | Author `scripts/office2/deploy/credential-health-check.sh` (modeled on `felix-doc-auditor.sh`) | WP07 | [P] with T030/T031 |
| T033 | Add `credential-health-check` entry to `service-inventory.json` with dependencies + health_check | WP08 | — |
| T034 | Update `service-inventory.md`: Scheduled Jobs row + detail section | WP08 | [P] with T033 |
| T035 | Update `credentials-and-secrets.md` §Security Posture: cross-reference the auditor; note R-003 resolved | WP08 | [P] |

Total: **35 subtasks** across **8 WPs**, average ~4.4 subtasks per WP.

---

## Dependency graph

```
WP01 (foundation)
 ├── WP02 (manifest + cadence)
 │    ├── WP04 (github writer)
 │    └── WP05 (vikunja writer)
 │         └── WP06 (orchestrator + CLI)  ← also depends on WP03, WP04
 ├── WP03 (activity signals)
 │    └── WP06
 └── ... 
       └── WP07 (deploy bundle)
            └── WP08 (architecture docs)
```

**Parallel opportunities**:

- WP02 ∥ WP03 (after WP01)
- WP04 ∥ WP05 (after WP02)
- WP08 mostly orthogonal to WP07 (different file scopes), but sequenced for clarity

**MVP scope**: WP01 + WP02 + WP06 (minus signals/writers) gives a check that reads the manifest and exits — useful for validating the scheduling pipeline but no alerts. **WP01–WP06 is the functional MVP** (the auditor produces alerts). WP07 + WP08 deploy and document.

---

## Work Packages

### WP01 — Foundation: manifest entry + test fixtures

**Goal**: Land FR-013 (add `kentonium3-pat` to the manifest) and prepare all test fixtures the downstream WPs need. No application code yet.

**Priority**: Must run first — every other WP depends on the fixtures.

**Independent test**: After this WP, `cat docs/design/architecture/data/credential-manifest.json | jq '.credentials[] | select(.name == "kentonium3-pat")'` returns a well-formed entry; `ls tests/security/fixtures/` shows all expected fixture files.

**Subtasks**:

- [x] T001 Audit `kentonium3` PAT, add `kentonium3-pat` entry to `credential-manifest.json` (FR-013) (WP01)
- [x] T002 Capture live manifest snapshot to `tests/security/fixtures/manifest-valid.json` (post-T001) (WP01)
- [x] T003 Create `tests/security/fixtures/manifest-near-expiry.json` (one credential inside warning window) (WP01)
- [x] T004 Create manifest-quality fixtures (missing field, bad cadence, invalid JSON, not-a-dict) (WP01)
- [x] T005 Capture/synthesize activity signal fixtures (tailscale + openclaw) (WP01)

**Implementation sketch**: T001 first (manifest mutation requires Kent's input on the PAT's `created_date`, `scope`, etc.); then T002 snapshots the resulting state. T003–T005 can run in parallel after T002.

**Risks**: T001 may surface that Kent's `kentonium3` PAT scope/expiry isn't documented anywhere — that's the whole point of the audit; capture what we can and leave fields that are genuinely unknown as `"unknown"` with a note.

**Dependencies**: none.
**Estimated prompt size**: ~280 lines.
**Prompt**: [`tasks/WP01-foundation-fixtures-and-manifest.md`](tasks/WP01-foundation-fixtures-and-manifest.md)

---

### WP02 — Manifest reader + cadence math

**Goal**: Implement the deterministic data-processing core: `Credential` dataclass, manifest parsing, cadence-boundary math.

**Priority**: Foundation for WP04, WP05, WP06.

**Independent test**: `pytest tests/security/test_manifest.py tests/security/test_cadence.py` passes against all fixtures from WP01.

**Subtasks**:

- [x] T006 Create package skeleton `scripts/security/credential_health_check/__init__.py` (WP02)
- [x] T007 Implement `manifest.py` (Credential, ManifestQualityIssue, read_manifest, ManifestUnreadableError) (WP02)
- [x] T008 Implement `cadence.py` (compute_boundary, is_within_warning_window) (WP02)
- [x] T009 Write `tests/security/test_manifest.py` against the manifest fixtures (WP02)
- [x] T010 Write `tests/security/test_cadence.py` (boundary math, warning-window edge cases) (WP02)

**Note on R-004 revision**: research §R-004 originally chose single-file. Spec-kitty's WP ownership model requires non-overlapping `owned_files`, so this WP introduces a package layout (`scripts/security/credential_health_check/`) with module-per-concern. The package contains five small modules plus `__main__.py`; total LOC is comparable to a single file. Update `research.md` R-004 in this WP to reflect the revised decision.

**Implementation sketch**: T006 lays the package down. T007 and T008 are independent (T008 doesn't need T007's parsing — operates on already-parsed Credential records). T009 and T010 wrap each in tests.

**Risks**: Date arithmetic with `last_reviewed: "2026-04-06"` (string) → boundary calc needs explicit type handling; `datetime.date.fromisoformat` is the path.

**Dependencies**: WP01 (fixtures).
**Estimated prompt size**: ~350 lines.
**Prompt**: [`tasks/WP02-manifest-reader-and-cadence-math.md`](tasks/WP02-manifest-reader-and-cadence-math.md)

---

### WP03 — Activity signal readers (tailscale + whatsapp)

**Goal**: Implement the two `monitor-activity` signal readers per A-004 resolution.

**Priority**: Required for FR-003 monitor-activity behavior.

**Independent test**: `pytest tests/security/test_tailscale_signal.py tests/security/test_whatsapp_signal.py` passes against fixtures.

**Subtasks**:

- [x] T011 Implement `signals.py` skeleton with `ActivitySignalFailure` dataclass + reader registry (WP03)
- [x] T012 Implement `tailscale_auth_signal(credential)` per `contracts/activity-signal-readers.md` §Reader 1 (WP03)
- [x] T013 Implement `whatsapp_session_signal(credential)` + `openclaw channels status` duration parser (WP03)
- [x] T014 Write `tests/security/test_tailscale_signal.py` against tailscale fixtures (WP03)
- [x] T015 Write `tests/security/test_whatsapp_signal.py` + duration-parser unit tests (WP03)

**Implementation sketch**: T011 sets up the shared types. T012 and T013 are independent (different external tools); T013 includes the duration parser (e.g., `2w ago` → `timedelta(days=14)`).

**Risks**: `openclaw channels status` output format is parsed via regex; capture-fixture from live state to anchor the parser. If openclaw changes its output format upstream, the parser test fails loudly (good).

**Dependencies**: WP01 (fixtures).
**Estimated prompt size**: ~320 lines.
**Prompt**: [`tasks/WP03-activity-signal-readers.md`](tasks/WP03-activity-signal-readers.md)

---

### WP04 — GitHub issue writer + dedup

**Goal**: Implement the GitHub-side of the dual-alert path: title generation, body templating, dedup-via-search, issue creation.

**Priority**: Required for any alerts to fire.

**Independent test**: `pytest tests/security/test_github_writer.py` passes; stubbed `gh issue create` invocations have the expected shape.

**Subtasks**:

- [ ] T016 Implement `github_writer.py` title generation for all 3 variants per contract (WP04)
- [ ] T017 Implement body templating for all 3 variants (cadence, activity-staleness, manifest-quality batch) (WP04)
- [ ] T018 Implement `dedup_check(title_prefix)` via `gh issue list --search 'in:title …'` (WP04)
- [ ] T019 Implement `create_issue(title, body, labels, assignees)` via `gh issue create` (WP04)
- [ ] T020 Write `tests/security/test_github_writer.py` covering titles, bodies, stubbed `gh` invocations (WP04)

**Implementation sketch**: T016 + T017 are pure functions over Credential records; T018 + T019 shell out via `subprocess.run(["gh", ...])`. Tests mock `subprocess.run`.

**Risks**: `gh` JSON output schema for `issue list` — pin to the documented `--json number,title` fields. If `gh` is upgraded with a schema change, the parser fails loudly.

**Dependencies**: WP02 (Credential dataclass).
**Estimated prompt size**: ~340 lines.
**Prompt**: [`tasks/WP04-github-issue-writer-and-dedup.md`](tasks/WP04-github-issue-writer-and-dedup.md)

---

### WP05 — Vikunja task writer

**Goal**: Implement the Vikunja-side of the dual-alert path: task creation with `due_date = boundary − 7 days`, cross-ref body.

**Priority**: Required for the escalation-engine path.

**Independent test**: `pytest tests/security/test_vikunja_writer.py` passes; stubbed API call has expected payload.

**Subtasks**:

- [ ] T021 Implement `vikunja_writer.py` skeleton: token loader, title + description templating (WP05)
- [ ] T022 Implement `lookup_inbox_project_id()` via Vikunja API (WP05)
- [ ] T023 Implement `create_task(credential, boundary, github_issue_number)` with `due_date = boundary − 7 days` (WP05)
- [ ] T024 Write `tests/security/test_vikunja_writer.py` (templating, due-date math, stubbed API) (WP05)

**Implementation sketch**: T021 establishes the writer; uses stdlib `urllib.request` rather than `requests` (no external deps). T022 caches Inbox project ID per-process. T023 ties it together.

**Risks**: Vikunja API auth uses bearer token — fail loudly if token file is unreadable; never log the token. Due-date timezone handling — Vikunja expects end-of-day in `America/New_York` per #112 lessons; explicitly construct the ISO-8601 string.

**Dependencies**: WP02 (Credential dataclass).
**Estimated prompt size**: ~290 lines.
**Prompt**: [`tasks/WP05-vikunja-task-writer.md`](tasks/WP05-vikunja-task-writer.md)

---

### WP06 — Orchestrator + CLI + logging

**Goal**: Stitch the components together into a runnable Python entry point with deterministic per-cycle execution and structured logging.

**Priority**: Required to run anything. Final code WP.

**Independent test**: `pytest tests/security/test_orchestrator.py` passes; the package runs end-to-end against fixtures via `python -m credential_health_check --manifest tests/security/fixtures/manifest-near-expiry.json --dry-run`.

**Subtasks**:

- [ ] T025 Implement `orchestrator.py`: per-cycle loop tying readers + writers + dedup together (WP06)
- [ ] T026 Implement `__main__.py`: argparse, structured logging, `--dry-run` and `--manifest` flags (WP06)
- [ ] T027 Cycle ID generation + structured log lines per `data-model.md` §CycleLog (WP06)
- [ ] T028 FR-012 wire-up: batched manifest-quality issue per cycle when malformed entries exist (WP06)
- [ ] T029 Write `tests/security/test_orchestrator.py` covering end-to-end orchestration with mocked surfaces (WP06)

**Implementation sketch**: T025 is the loop body; T026 handles CLI surface; T027 makes logs grep-able from `journalctl`; T028 is the cycle-level FR-012 branch (file one batched issue if any malformed entries). T029 is the integration test with all four external surfaces mocked.

**Risks**: Ordering of GitHub-issue + Vikunja-task creation matters — Vikunja task is created first so the issue body can reference its ID. If task creation fails, skip the credential entirely and log; do not file a one-sided issue.

**Dependencies**: WP02, WP03, WP04, WP05.
**Estimated prompt size**: ~390 lines.
**Prompt**: [`tasks/WP06-orchestrator-cli-and-logging.md`](tasks/WP06-orchestrator-cli-and-logging.md)

---

### WP07 — Deploy bundle (systemd units + deploy script)

**Goal**: Package the runtime: systemd user timer + oneshot service + a deploy script that copies units and arms the timer.

**Priority**: Required to actually run on office2.

**Independent test**: `bash scripts/office2/deploy/credential-health-check.sh` on office2 (as claude user) results in `systemctl --user list-timers --all | grep credential-health-check` showing the next-run.

**Subtasks**:

- [ ] T030 Author `scripts/office2/credential-health-check.timer` (`OnCalendar=*-*-* 13:00:00`, `Persistent=true`) (WP07)
- [ ] T031 Author `scripts/office2/credential-health-check.service` (Type=oneshot, ExecStart=python3 -m credential_health_check, TimeoutStartSec=10min) (WP07)
- [ ] T032 Author `scripts/office2/deploy/credential-health-check.sh` (modeled on `felix-doc-auditor.sh`) (WP07)

**Implementation sketch**: T030 and T031 are unit files modeled exactly on `felix-doc-auditor.{timer,service}`. T032 follows the deploy-script pattern: copy units, daemon-reload, enable --now.

**Risks**: Per #223's lessons, `openclaw.json` has no cron schema and the systemd-user-timer pattern is the modern path — that's already settled. Just don't reintroduce the old anti-pattern.

**Dependencies**: WP06 (code must exist).
**Estimated prompt size**: ~210 lines.
**Prompt**: [`tasks/WP07-deploy-bundle-systemd-units-and-script.md`](tasks/WP07-deploy-bundle-systemd-units-and-script.md)

---

### WP08 — Architecture documentation

**Goal**: Update the live arch docs to reflect the new service per C-007.

**Priority**: Required by C-007 (same-change-set update).

**Independent test**: `python tooling/scripts/validate_docs.py` passes; `service-inventory.json` has a `credential-health-check` entry; `service-inventory.md` Scheduled Jobs row matches; `credentials-and-secrets.md` references the auditor.

**Subtasks**:

- [ ] T033 Add `credential-health-check` entry to `service-inventory.json` with dependencies + health_check (WP08)
- [ ] T034 Update `service-inventory.md`: Scheduled Jobs row + detail section (WP08)
- [ ] T035 Update `credentials-and-secrets.md` §Security Posture: cross-reference the auditor; note R-003 resolved (WP08)

**Implementation sketch**: All three subtasks operate on different files; can be done in parallel within the WP. The JSON entry follows the existing `felix-doc-auditor` shape (type=systemd-timer, schedule, exec_start, dependencies, health_check, config_files).

**Risks**: Bump file-level `last_updated` and `updated_by` on `service-inventory.json` and `credentials-and-secrets.md` to credit #115. Don't forget the Scheduled Jobs row in the markdown narrative.

**Dependencies**: WP07.
**Estimated prompt size**: ~200 lines.
**Prompt**: [`tasks/WP08-architecture-docs.md`](tasks/WP08-architecture-docs.md)

---

## Validation summary

- **8 WPs** total. All within ideal 3-7 subtask range.
- **35 subtasks** total. All FRs (FR-001..FR-013) covered.
- **Estimated prompt sizes**: 200–390 lines. All within 200-500 ideal range; none exceed 700 hard limit.
- **No charter violations** (charter is unresolved; no gates).
- **MVP scope**: WP01–WP06 produces a working, dry-runnable auditor; WP07–WP08 deploy and document.
