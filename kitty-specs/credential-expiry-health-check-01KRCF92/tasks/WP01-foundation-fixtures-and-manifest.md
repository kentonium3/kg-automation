---
work_package_id: WP01
title: Foundation — manifest entry + test fixtures
dependencies: []
requirement_refs:
- FR-013
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-credential-expiry-health-check-01KRCF92
base_commit: e4845c05f322769dc216c2d92ae83e990f09f198
created_at: '2026-05-11T21:53:28.372416+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "21074"
agent: "claude"
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: tests/security/fixtures/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/credential-manifest.json
- tests/security/fixtures/**
tags: []
---

# WP01 — Foundation: manifest entry + test fixtures

## Objective

Add the missing `kentonium3-pat` entry to `credential-manifest.json` and lay down every test fixture the downstream WPs need. No application code in this WP — pure data preparation.

## Context

This is the **first** WP and has no dependencies. Every subsequent WP either depends on the manifest being complete (so the auditor doesn't miss a real credential on day one) or on having concrete fixtures to test against. Getting these right matters more than getting them fast.

- **Spec** anchor: FR-013 (add `kentonium3-pat`); SC-006 (credential present and being tracked post-deploy).
- **Plan** anchor: project structure §`docs/design/architecture/data/credential-manifest.json` and §`tests/security/fixtures/`.
- **Research** anchor: R-001 (monitor-activity signals are programmatic — both signal sources are queryable on office2; live captures define the fixtures).
- **Contracts** anchor: `manifest-reader.md` enumerates the manifest fixtures; `activity-signal-readers.md` enumerates the activity-signal fixtures.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree (path computed by `finalize-tasks` and recorded in `lanes.json`). Implementing agent enters that worktree, makes changes, and the spec-kitty review/merge flow handles return to `main`.

## Subtasks

### T001 — Audit and register `kentonium3-pat` in `credential-manifest.json`

**Purpose**: Bring the manifest into completeness for the cadence-tracked credential set. FR-013.

**Steps**:

1. Read `docs/design/architecture/data/credential-manifest.json` to confirm `kentonium3-pat` is not already present.
2. Construct the new entry, modelled on the existing `kg-felix-bot-pat` entry, with field values appropriate for Kent's personal GitHub PAT:
   - `name`: `"kentonium3-pat"`
   - `type`: `"api-token"`
   - `scope`: `"GitHub classic PAT for kentonium3 (Kent's personal GitHub identity). Used for Kent's manual git operations from Mac and any agent path that needs to operate as kentonium3 rather than kg-felix-bot."`
   - `storage`: `"macOS Keychain (Mac); /home/kgale/.config/gh/hosts.yml (office2-kgale if configured there)"` — confirm during implementation by inspecting `gh auth status` on Mac.
   - `host`: `"mac (primary), office2 (kgale account if configured)"`
   - `used_by`: `["Kent (manual git + gh CLI from Mac)", "any future agent operating as kentonium3"]`
   - `expiry_policy`: `"manual-rotation"`
   - `review_cadence`: `"annual"`
   - `notes`: same shape as `kg-felix-bot-pat` notes — classic PAT, scopes used (typically `repo`, `read:org`, `workflow` — confirm via `gh auth status`).
   - `created_date`: best-known date or `"unknown — predates manifest tracking"` if Kent doesn't recall.
   - `last_reviewed`: today (`2026-05-11`) — this WP's commit is itself the review event for this entry.
   - `expiry_notes`: same boilerplate as `kg-felix-bot-pat` covering the rotation procedure (generate new PAT on github.com, update Keychain, update `gh auth login` on Mac, etc.).
3. If any field genuinely cannot be filled (e.g., `created_date`), use `"unknown"` rather than fabricating a value. Note the gap in the issue commenting on the WP.
4. Bump the manifest's top-level `last_updated` to `2026-05-11` and append `+ #115-foundation` to `updated_by`.

**Files**:

- `docs/design/architecture/data/credential-manifest.json` (modify — add new entry, bump top-level metadata)

**Validation**:

- `python -c "import json; m = json.load(open('docs/design/architecture/data/credential-manifest.json')); names = [c['name'] for c in m['credentials']]; assert 'kentonium3-pat' in names; print('OK')"`
- `python tooling/scripts/validate_docs.py` passes.

**Edge cases**:

- If Kent's `gh auth status` on Mac shows the PAT is fine-grained rather than classic: capture that in the `notes` field. Both types need tracking.
- If the PAT scopes differ from the bot's: list them explicitly in `notes`.

---

### T002 — Capture live manifest snapshot as test fixture

**Purpose**: Establish a "valid manifest" fixture for `tests/security/test_manifest.py` that reflects the manifest's post-T001 shape. Lets the manifest reader unit tests exercise the real schema.

**Steps**:

1. After T001 lands, copy `docs/design/architecture/data/credential-manifest.json` → `tests/security/fixtures/manifest-valid.json`. Do this **after** T001 so the fixture includes the `kentonium3-pat` entry — the fixture's reality should match the live manifest's reality.
2. Add a top-of-file comment-equivalent inside the JSON via a non-functional key (e.g., a top-level `"_fixture_note"` field: `"Snapshot of credential-manifest.json at 2026-05-11 post-#115 WP01."`). Helps future readers know this is a frozen-in-time fixture, not a live source.

**Files**:

- `tests/security/fixtures/manifest-valid.json` (create)

**Validation**:

- `python -c "import json; m = json.load(open('tests/security/fixtures/manifest-valid.json')); assert any(c['name'] == 'kentonium3-pat' for c in m['credentials']); print('OK')"`

---

### T003 — Synthesize a "near-expiry" fixture

**Purpose**: Anchor the orchestrator's positive-detection path. Tests must verify "credential inside 30-day window triggers alert."

**Steps**:

1. Copy `tests/security/fixtures/manifest-valid.json` → `tests/security/fixtures/manifest-near-expiry.json`.
2. Edit exactly one credential entry to put it inside the warning window: set its `last_reviewed` to `(today − 340 days).isoformat()` for an `annual`-cadence credential. With today = 2026-05-11, `last_reviewed = "2025-06-05"` puts the boundary at `2026-06-05`, which is 25 days out — inside the 30-day window.
3. Pick a credential that is unambiguous about being a clean test target (e.g., `kg-felix-bot-pat`). Add a top-level fixture note explaining what's altered.
4. Leave the other credentials unchanged.

**Files**:

- `tests/security/fixtures/manifest-near-expiry.json` (create)

**Validation**:

- Diff against `manifest-valid.json` shows exactly one credential's `last_reviewed` changed plus the `_fixture_note`.

---

### T004 — Manifest-quality fixtures

**Purpose**: Anchor the FR-012 + manifest-quality test paths. Each fixture isolates one failure mode.

**Steps**: Create four files (each is a small standalone JSON or text):

1. `tests/security/fixtures/manifest-missing-last-reviewed.json` — one credential entry without a `last_reviewed` field (but otherwise well-formed). Use a minimal 2-credential manifest so the test is focused.
2. `tests/security/fixtures/manifest-bad-review-cadence.json` — one credential with `review_cadence: "weekly"` (not a recognised value).
3. `tests/security/fixtures/manifest-invalid-json.txt` — a `.txt` file containing genuinely invalid JSON (e.g., `{"credentials": [{ ... missing closing brace`).
4. `tests/security/fixtures/manifest-not-a-dict.json` — top-level array, not a dict (e.g., `[{"name": "foo"}]`).

Each fixture should include a top-level `_fixture_note` (where syntactically valid) explaining the intentional malformation.

**Files**:

- `tests/security/fixtures/manifest-missing-last-reviewed.json` (create)
- `tests/security/fixtures/manifest-bad-review-cadence.json` (create)
- `tests/security/fixtures/manifest-invalid-json.txt` (create)
- `tests/security/fixtures/manifest-not-a-dict.json` (create)

**Validation**:

- The three JSON-parseable files validate with `python -c "import json; json.load(open(...))"` — except `manifest-invalid-json.txt` which should fail to parse (that's the point).

---

### T005 — Activity signal fixtures (live captures + synthetic variants)

**Purpose**: Anchor the WP03 signal-reader tests. Live captures pin the parser to real output; synthetic variants exercise the failure paths.

**Steps**:

1. **Live captures** (run on office2 as the `claude` user during implementation):
   - `ssh office2-claude 'tailscale status --json' > tests/security/fixtures/tailscale-status-running.json` (this captures the current healthy state).
   - `ssh office2-claude 'openclaw channels status' > tests/security/fixtures/openclaw-channels-status-healthy.txt` (captures current healthy state).
2. **Synthetic tailscale variants** (hand-author, modelled on the live `tailscale-status-running.json` structure):
   - `tests/security/fixtures/tailscale-status-needs-login.json` — copy the running fixture, change `"BackendState": "Running"` → `"BackendState": "NeedsLogin"`, blank out user/IP-specific fields if appropriate.
   - `tests/security/fixtures/tailscale-status-stopped.json` — same but `"BackendState": "Stopped"`.
3. **Synthetic openclaw variants** (hand-author, modelled on the live healthy capture):
   - `tests/security/fixtures/openclaw-channels-status-not-connected.txt` — same shape but with `not connected` instead of `connected` in the channel status line.
   - `tests/security/fixtures/openclaw-channels-status-stale.txt` — same shape but with `in:14d 5h ago, out:14d 5h ago` (or similar > 14-day durations).

**Files**:

- `tests/security/fixtures/tailscale-status-running.json` (create from live capture)
- `tests/security/fixtures/tailscale-status-needs-login.json` (create — synthetic)
- `tests/security/fixtures/tailscale-status-stopped.json` (create — synthetic)
- `tests/security/fixtures/openclaw-channels-status-healthy.txt` (create from live capture)
- `tests/security/fixtures/openclaw-channels-status-not-connected.txt` (create — synthetic)
- `tests/security/fixtures/openclaw-channels-status-stale.txt` (create — synthetic)

**Validation**:

- `ls tests/security/fixtures/tailscale-status-*.json | wc -l` → 3
- `ls tests/security/fixtures/openclaw-channels-*.txt | wc -l` → 3
- `python -c "import json; json.load(open('tests/security/fixtures/tailscale-status-running.json'))" succeeds.

---

## Definition of Done

- All five subtasks complete.
- `python tooling/scripts/validate_docs.py` passes (the manifest edit is JSON; the validator should accept it).
- `git status` shows the manifest + the new fixtures directory; nothing else.
- A commit lands with a `docs(security):` prefix referencing #115 and WP01.
- The implementing agent verifies T002's snapshot matches T001's edited manifest by content (the snapshot truly is a snapshot, not stale).

## Risks

- **T001**: The PAT's exact scope/expiry may be uncertain at the time of writing. Capture what is known; use `"unknown"` with a note where genuinely undefined. Don't invent dates.
- **T005**: The live captures contain user-identifying data (Tailscale node ID, public key, IP addresses). These are not sensitive in our threat model (Tailscale-gated network, internal repo). But: do not commit Tailscale auth tokens or anything labeled as a secret. The structured fields we use (BackendState, channel `connected`/`in:`/`out:`) are public from the operator's perspective.

## Reviewer guidance

- Look for: `kentonium3-pat` entry with **all** documented fields populated (or `"unknown"` with a comment).
- Look for: `_fixture_note` at the top of each JSON fixture noting why it exists.
- Look for: the live-capture fixtures are at least 50 bytes (sanity check — empty captures are a silent failure).
- Confirm: `tests/security/fixtures/manifest-near-expiry.json`'s altered credential has a boundary date inside the 30-day window when computed from today's date. The test will only pass on the day the boundary falls in the window — so the fixture should be constructed so it stays in-window for a reasonable timeframe.

## Suggested implement command

```bash
spec-kitty agent action implement WP01 --agent <name>
```

## Activity Log

- 2026-05-11T21:53:31Z – claude – shell_pid=20255 – Assigned agent via action command
- 2026-05-11T21:56:21Z – claude – shell_pid=20255 – WP01 implementation complete: kentonium3-pat manifest entry + all 12 test fixtures, validates clean.
- 2026-05-11T21:56:45Z – claude – shell_pid=21074 – Started review via action command
