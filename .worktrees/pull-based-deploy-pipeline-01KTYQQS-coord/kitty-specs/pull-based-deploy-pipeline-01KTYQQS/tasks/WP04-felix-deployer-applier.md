---
work_package_id: WP04
title: felix-deployer applier (Python + systemd + DM notify)
dependencies:
- WP02
- WP03
requirement_refs:
- FR-002
- FR-003
- FR-004
- FR-007
- FR-009
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T016
- T017
- T018
- T019
- T020
- T021
agent: "claude:sonnet:implementer-ivan:reviewer"
shell_pid: "34101"
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/felix-deployer/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- scripts/deploy/felix-deployer/__init__.py
- scripts/deploy/felix-deployer/deployer.py
- scripts/deploy/felix-deployer/notify.py
- scripts/deploy/felix-deployer/felix-deployer.service
- scripts/deploy/felix-deployer/felix-deployer.timer
- scripts/deploy/felix-deployer/templates/felix-deployer-alert.txt
- tests/deploy/test_deployer.py
- tests/deploy/test_notify.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else.

## Objective

Build the autonomous office2-side applier: a `Type=oneshot` systemd service triggered by a 5-min timer. The service pulls from main, scans `deploys/queued/`, applies pending manifests through `lib.apply.dry_run_then_apply_gate`, records outcomes, and dispatches a WhatsApp DM on failure via openclaw cron.

## Context

The applier is what makes the discipline real on office2. Read these first:

- `kitty-specs/<slug>/data-model.md` — tick log entries, manifest lifecycle, failure record schema
- `kitty-specs/<slug>/contracts/dm-payload-v1.md` — the openclaw cron payload contract
- `kitty-specs/<slug>/research.md` — R-02 (concurrency: systemd Type=oneshot natural serialization), R-03 (DM via openclaw cron payload synthesis), R-07 (service-inventory shape mirrors felix-doc-auditor)

`felix-doc-auditor` (memory: `reference_felix_doc_auditor_ops`) is the operational precedent — same systemd-user pattern, same `claude` account, same health-signal file. Mirror its shape for consistency.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T016 — Module scaffold

`scripts/deploy/felix-deployer/__init__.py`: empty.

`scripts/deploy/felix-deployer/deployer.py` scaffold:

```python
"""felix-deployer — pull-based deploy applier.

Runs as systemd --user Type=oneshot service; timer fires every 5 min.
Reads deploys/queued/*.yaml, applies through lib.apply.dry_run_then_apply_gate,
records outcome, dispatches DM on failure via openclaw cron.
"""
import sys
from . import _tick

def main() -> int:
    return _tick.run_tick()

if __name__ == "__main__":
    sys.exit(main())
```

Plus a `_tick.py` module that holds the tick logic (separation makes it testable).

### T017 — Tick lifecycle in `deployer.py` / `_tick.py`

The canonical tick sequence:

```python
def run_tick(repo_root=None, log_path=None):
    repo_root = repo_root or pathlib.Path('/home/claude/kg-automation')
    log_path = log_path or pathlib.Path('/data/services/felix-deployer/logs') / f"{date.today():%Y-%m-%d}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    tick_start = datetime.now(timezone.utc).isoformat()
    _log(log_path, {'event': 'tick_start', 'ts': tick_start})

    # 1. git pull
    r = subprocess.run(['git', 'pull', '--ff-only'], cwd=repo_root, capture_output=True, text=True)
    if r.returncode != 0:
        _log(log_path, {'event': 'tick_skip', 'reason': 'git_pull_failed', 'stderr': r.stderr[:200]})
        return 0  # don't crash; next tick retries

    head_sha = _resolve_head_sha(repo_root)

    # 2. Scan queue
    queue = sorted((repo_root / 'deploys' / 'queued').glob('*.yaml'))
    _log(log_path, {'event': 'queue_scanned', 'count': len(queue), 'head_sha': head_sha})

    # 3. Process each in turn
    for manifest_path in queue:
        try:
            manifest = lib.manifest.load_manifest(manifest_path)
        except Exception as exc:
            _record_failure(repo_root, manifest_path, phase='manifest_parse', error=str(exc))
            continue

        result = lib.apply.dry_run_then_apply_gate(manifest, str(manifest_path))
        if result.ok:
            _record_success(repo_root, manifest_path, manifest, head_sha)
            _log(log_path, {'event': 'manifest_processed', 'manifest_name': manifest['name'], 'outcome': 'applied'})
        else:
            phase = result.details.get('phase', 'unknown')
            _record_failure(repo_root, manifest_path, phase=phase, error=result.summary)
            notify.dispatch_failure_dm(manifest=manifest, phase=phase,
                                       error_summary=result.summary, head_sha=head_sha)
            _log(log_path, {'event': 'manifest_processed', 'manifest_name': manifest['name'],
                            'outcome': f'failed_{phase}'})

    _log(log_path, {'event': 'tick_complete', 'ts': datetime.now(timezone.utc).isoformat()})
    return 0
```

`_record_success` does: `lib.applied.write_applied(manifest, apply_mode='manifest')`, `git rm` the queued path, `git add applied/...`, `git commit + push`.

`_record_failure` writes `deploys/failed/<name>-<ts>.yaml` per `data-model.md` failure record schema. Manifest stays in queued.

### T018 — `notify.py`

Synthesize the openclaw payload per `contracts/dm-payload-v1.md`:

```python
def dispatch_failure_dm(manifest, phase, error_summary, head_sha):
    payload = {
        'payload_version': 'v1',
        'manifest_name': manifest['name'],
        'tier': manifest['tier'],
        'phase': phase,
        'error_summary': lib.verify.redact_secrets(error_summary)[:500],
        'head_sha': head_sha,
        'failed_at': datetime.now(timezone.utc).isoformat(),
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
        payload_file = f.name
    r = subprocess.run(['openclaw', 'cron', 'run', 'felix-deployer-alert',
                        '--payload-file', payload_file, '--wait', '--json'],
                       capture_output=True, text=True)
    # Don't fail the tick if DM dispatch fails — log and continue
    os.unlink(payload_file)
    return LibResult(ok=(r.returncode == 0), summary=...)
```

Tests (`tests/deploy/test_notify.py`): mock `subprocess.run`; assert payload schema; assert redact_secrets is applied to error_summary; assert temp file is cleaned up; assert non-zero exit doesn't propagate.

### T019 — Systemd units

`felix-deployer.service`:

```ini
[Unit]
Description=Felix pull-based deploy applier (oneshot)
Documentation=https://github.com/kentonium3/kg-automation/blob/main/docs/runbooks/deploy/discipline.md

[Service]
Type=oneshot
WorkingDirectory=/home/claude/kg-automation
ExecStart=/usr/bin/env python3 -m scripts.deploy.felix_deployer.deployer
StandardOutput=journal
StandardError=journal
```

(Note: replace `felix-deployer` with `felix_deployer` for the Python module path since dashes are not valid in module names. The systemd unit name stays `felix-deployer`.)

`felix-deployer.timer`:

```ini
[Unit]
Description=Schedule felix-deployer every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=felix-deployer.service

[Install]
WantedBy=timers.target
```

### T020 — DM template

`templates/felix-deployer-alert.txt`:

```
🛑 felix-deployer apply failed

manifest: {manifest_name}
tier:     {tier}
phase:    {phase}
head:     {head_sha_short}
when:     {failed_at}

{error_summary}

(Manifest stays in queued/; next applier tick will re-attempt unless you delete it.)
```

This is the template the `felix-deployer-alert` openclaw cron uses to render the WhatsApp message. Field names match `payload_version: v1` schema.

### T021 — `tests/deploy/test_deployer.py`

End-to-end tick test with subprocess mocks:

1. `tick_no_queue_no_pull` — git pull succeeds, queue empty → tick_start + tick_complete in log
2. `tick_git_pull_fails` — git pull non-zero → tick_skip emitted, no further processing
3. `tick_successful_manifest` — one valid manifest, mock entrypoint succeeds → applied file written, git mv recorded
4. `tick_failed_manifest_dispatches_dm` — one manifest, mock entrypoint fails at apply phase → failed file written, notify.dispatch_failure_dm called with correct payload, manifest stays in queue
5. `tick_multiple_manifests_serial` — three manifests, second one fails → first applied, second failed, third still processed

Use `pytest tmp_path` for the repo fixture; `monkeypatch` for subprocess.run mocks.

## Test strategy

- `pytest tests/deploy/test_deployer.py tests/deploy/test_notify.py -v` — green
- Systemd units pass `systemd-analyze verify <file>` (run locally if available; not gating)
- Manual smoke on office2 is deferred to WP05 (bootstrap deploys this)

## Definition of Done

- All 8 owned files exist
- All test scenarios pass
- `deployer.py` does NOT exit non-zero on routine failure paths (only crashes are bugs)
- DM dispatch failure does NOT propagate to tick failure
- Tick log is JSONL, one event per line
- Systemd unit references the correct Python module path (`scripts.deploy.felix_deployer.deployer` with underscore)

## Risks

- **Module name dashes**: directory is `felix-deployer/` (matches systemd unit name) but Python module is `felix_deployer` (underscores required). Verify the import path in the .service file matches the actual module name on disk.
- **git pull failures**: many root causes (merge conflict, network, auth). Applier must tolerate all without crashing. Log and move on.
- **Subprocess inheritance**: under systemd, `os.environ` is minimal. Ensure `git`, `openclaw`, and any other binaries are referenced by absolute path OR `Environment=PATH=...` is set in the .service file.
- **Empty queue + git pull = no changes**: pulling on every tick is wasteful but cheap. Don't optimize prematurely.
- **Logging during failures**: if log directory write fails, the applier should still try to dispatch the DM. The log is operator visibility but failure DM is escalation.

## Reviewer guidance

1. Verify systemd unit's `ExecStart` references the correct module path (with underscores).
2. Confirm `dispatch_failure_dm` ALWAYS calls `redact_secrets` on error_summary.
3. Confirm tick log JSON is parseable line-by-line (no multi-line entries).
4. Verify the deployer doesn't exit non-zero on a single-manifest failure (the tick MUST continue to subsequent manifests; one failure cannot break the queue).
5. Check `notify.py` doesn't propagate temp-file cleanup errors.

## Activity Log

- 2026-06-12T22:39:55Z – claude:sonnet:implementer-ivan:implementer – shell_pid=30948 – Assigned agent via action command
- 2026-06-12T22:50:54Z – claude:sonnet:implementer-ivan:implementer – shell_pid=30948 – Applier scaffold + tick lifecycle + DM notify + systemd units. All test scenarios pass.
- 2026-06-12T22:52:01Z – claude:sonnet:implementer-ivan:reviewer – shell_pid=34101 – Started review via action command
- 2026-06-12T22:54:23Z – user – shell_pid=34101 – Review passed: 21/21 tests green; payload v1 conformant (payload_version literal, redact_secrets before 500-char truncation, tempfile cleanup on all paths); openclaw argv exact ('cron run felix-deployer-alert --payload-file <tmp> --wait --json'); tick lifecycle uses git pull --ff-only, sorted queue, tick_skip on pull failure returning 0, DM dispatch isolated from tick failure via try/except wrap; phase mapping 7->4 pinned by test (snapshot collapses to verification_pre as a sensible pre-apply bucket); systemd Type=oneshot with path-based ExecStart matching actual hyphenated dir, timer OnUnitActiveSec=5min WantedBy=timers.target; no crontab literal; only e41774f8 touched the 8 owned + 2 test files.
