# Implementation Plan: Inbox atomic-write permission preservation

**Branch**: `main` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/inbox-atomic-write-perm-preservation-01KRFS03/spec.md`
**Source issue**: [#254](https://github.com/kentonium3/kg-automation/issues/254)

## Summary

Fix `_atomic_write` in `scripts/inbox/inject_parse_error_marker.py` and `scripts/inbox/strip_parse_error_marker.py` so the resulting file's mode is the mode of the existing target (when one exists) or `0o664` (when creating a new file), rather than the writer's umask-derived `0o600`. Add a one-line stderr log entry per successful write. Cover both helpers with unit tests using `tmp_path` fixtures.

Approach: duplicate the fix in both helpers (per spec C-002 — Kent chose A: minimal change, no shared module). Each helper's `_atomic_write` will gain a small block that stats the target before `os.replace` and applies the discovered (or default) mode to the temp file. Logging follows the existing `print(..., file=sys.stderr)` convention used throughout `scripts/inbox/` — no new dependencies, no log files, sink is the OpenClaw agent runtime's transcript (already rotation-managed).

## Technical Context

**Language/Version**: Python 3.10+ (matches `bake-tracker` baseline; office2 ships 3.12). Standard library only — `tempfile`, `os`, `stat`, `sys`. No third-party packages added.
**Primary Dependencies**: None new.
**Storage**: Filesystem — `/home/kgale/second-brain/notes/01-Inbox/` on office2. Local repo at `/Users/kentgale/repos/kg-automation/scripts/inbox/` for development.
**Testing**: `pytest` with `tmp_path` fixtures; new file `tests/inbox/test_atomic_write_perms.py`. All 85 existing `tests/inbox/` tests continue to pass unchanged.
**Target Platform**: office2 (Ubuntu 24.04 LTS), Python 3.12. Helpers invoked by the felix-admin-capture OpenClaw agent as the `claude` user.
**Project Type**: Single project — Python scripts under `scripts/inbox/`, tests under `tests/inbox/`.
**Performance Goals**: NFR-001 — mode-preservation step adds ≤5 ms per `_atomic_write` invocation. Measured by comparing pre/post unit-test durations.
**Constraints**: NFR-002 — no `sudo`, no elevated privileges. C-001 — UID preservation is out of scope (chown to other uid requires root). C-002 — no shared module; fix duplicated in both helpers.
**Scale/Scope**: 2 production scripts modified; 1 new test file (~60–80 lines); zero deployed services changed beyond the rsync deploy step.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context for `plan` action loaded in compact mode. Governance is present but the resolver reports unresolved tools (`pytest`, `python`). This is a known charter-config quirk (the charter declares tools that aren't in spec-kitty's default registry); it does not block planning per the resolver's diagnostic.

No charter directives identified that conflict with this mission. The change is Tier 3 (Standard) per `docs/design/architecture/data/change-risk-taxonomy.json` — Python script logic, no service/credential/topology impact, so no pre-flight checklist required.

**Gate**: PASS.

## Project Structure

### Documentation (this feature)

```
kitty-specs/inbox-atomic-write-perm-preservation-01KRFS03/
├── plan.md              # This file (/spec-kitty.plan command output)
├── research.md          # Phase 0 output — alignment record (no open clarifications)
├── quickstart.md        # Phase 1 output — verification recipe
├── spec.md              # Mission spec
├── meta.json            # Mission identity
├── checklists/
│   └── requirements.md  # Spec quality checklist (validated green)
└── tasks/               # Populated by /spec-kitty.tasks (later)
```

`data-model.md` and `contracts/` are intentionally omitted — there is no new data model and no API contract to declare.

### Source Code (repository root)

```
scripts/inbox/
├── inject_parse_error_marker.py     # MODIFY: _atomic_write helper
├── strip_parse_error_marker.py      # MODIFY: _atomic_write helper
├── append_routing_entry.py          # unchanged (no atomic-write usage on note files)
├── file_inbox_quality_issue.py      # unchanged
├── prescan.py                       # unchanged
└── routing_log.py                   # unchanged

tests/inbox/
├── test_atomic_write_perms.py       # NEW: unit tests for both helpers' _atomic_write
├── test_callout_marker.py           # unchanged
├── test_routing_log.py              # unchanged
├── test_prescan.py                  # unchanged
├── test_issue_writer.py             # unchanged
└── conftest.py                      # unchanged

scripts/deploy/
└── deploy-149.sh                    # reused for office2 deploy (no changes needed)
```

**Structure Decision**: Standard single-project Python layout already established by mission #185. No new directories; only two existing modules modified and one new test file added.

## Complexity Tracking

*No Charter Check violations. Section intentionally empty.*

## Phase 0: Research / Alignment

See [research.md](research.md). Summary of decisions logged there:

1. **Logging sink**: stderr via `print(..., file=sys.stderr)`. Rejected `logging.RotatingFileHandler` (adds dependency on new log file; existing scripts don't use the `logging` module at all).
2. **Mode default for new files**: `0o664` (group rw, world r). Rationale: parent dir has setgid `secondbrain` group; this default lets any group member (claude, kgale) read+write the file.
3. **No shared helper**: Per spec C-002 / Kent's discovery choice A.
4. **No UID preservation**: Per spec C-001 — root only on Linux.
5. **Test strategy**: `tmp_path` unit tests parameterized over both helper modules. No integration test (deploy + canary covers end-to-end verification per SC-002).

## Phase 1: Design

See [quickstart.md](quickstart.md) for the verification recipe.

### Implementation outline

Each helper's `_atomic_write` becomes:

```python
def _atomic_write(path: Path, content: str) -> None:
    parent = path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        # Preserve original mode (or default group-readable mode for new files)
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
            kind = "preserved"
        except FileNotFoundError:
            mode = 0o664
            kind = "new"
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        print(f"INFO: atomic_write {path} mode={oct(mode)} ({kind})", file=sys.stderr)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
```

### Test plan (FR-005, FR-006)

`tests/inbox/test_atomic_write_perms.py` parameterized over both helper modules:

| Case | Setup | Action | Assertion |
|---|---|---|---|
| Preserve 0o600 | Pre-create target at mode 0o600 | call `_atomic_write` | resulting mode is 0o600 |
| Preserve 0o644 | Pre-create at 0o644 | call `_atomic_write` | resulting mode is 0o644 |
| Preserve 0o664 | Pre-create at 0o664 | call `_atomic_write` | resulting mode is 0o664 |
| New file default | Target does not exist | call `_atomic_write` | resulting mode is 0o664 |
| Atomic invariant | Force exception during write (raise inside `os.fdopen` block) | catch raise | target not modified; no stray temp file |

### Deploy plan

After tests pass locally, push the two modified scripts and the new test file to office2 via the existing `scripts/deploy/deploy-149.sh --apply --backup-confirmed`. Verify scripts are present at `/home/claude/kg-automation/scripts/inbox/` with executable bits intact.

### End-to-end verification (SC-002)

1. Drop a fresh canary note `Inbox 2026-05-13 canary.md` into `~/second-brain/notes/01-Inbox/` on Mac with malformed YAML frontmatter (e.g., unterminated string).
2. Run `ob` sync once on Mac; confirm office2 receives it.
3. Trigger inbox-noon cron once; confirm agent files a quality issue and (manually for now) invokes `inject_parse_error_marker.py`.
4. After marker is injected on office2, observe the resulting file's mode is the same as pre-call (group-readable).
5. Edit the canary on Mac (fix the YAML) and save.
6. Within 5 minutes, confirm the office2 copy has the Mac fix (no manual chmod or rm needed).
7. Cleanup: delete canary from Mac inbox.

## Charter Re-check (post-design)

No new gates raised by the design. Plan remains within Tier 3 standard scope. **Gate**: PASS.

## Next Steps

Run `/spec-kitty.tasks` to materialize this plan into work packages.

**Branch contract reminder**: Current branch `main`. Planning/base branch `main`. Merge target `main`. `branch_matches_target=true`. No branch switching required between specify, plan, and tasks.
