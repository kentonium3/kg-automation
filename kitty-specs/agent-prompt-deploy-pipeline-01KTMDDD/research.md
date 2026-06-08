# Research: Agent Prompt Deploy Pipeline

**Mission**: `agent-prompt-deploy-pipeline-01KTMDDD`
**Phase**: 0 (Outline & Research)
**Date**: 2026-06-08

## Decisions Locked at Discovery Time

The following decisions were resolved during `/spec-kitty.specify` discovery and live-environment probing (per **DIR-006**). Each is captured here so the implementation phase does not re-litigate.

### D-001 — Architecture: office2 pull (not Mac push, not GitHub Actions)

- **Decision**: User-level systemd timer on office2 fires every 5 minutes. Each tick performs `git pull --ff-only` inside `/home/claude/kg-automation`, then the helper compares MD5s and atomically copies drifted files into `/data/services/openclaw/<deploy-dir>/`.
- **Rationale**: The issue body's "user-level systemd timer firing every 5 minutes" implies office2 (systemd is the office2 idiom; launchd is the Mac idiom). office2 is always-on; Mac is not. The office2 git clone at `/home/claude/kg-automation` exists, is current, and is on `main` (verified at design time). Aligns with [[feedback_vikunja_sync_polling_not_webhooks]] operational preference.
- **Alternatives considered**:
  - Mac launchd + scp — fails when Mac is asleep or offline (Kent's road days)
  - GitHub Actions on push-to-main → SSH deploy — fastest propagation but requires `.github/workflows/` change which CLAUDE.md restricts, plus spec-kitty merges create merge commits but no PR (only `pull_request` triggers fire on PRs)
- **Confirmation**: AskUserQuestion 2026-06-08; Kent picked "office2 pull (Recommended)".

### D-002 — Filename allowlist (not glob, not per-agent manifest)

- **Decision**: Helper syncs only files matching the fixed In-Scope Filename Set: `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`.
- **Rationale**: This set covers every canonical agent prompt file present in every repo source dir (verified via `ls scripts/openclaw/agents/<slug>/`). Adding a new file type to deploy would be a future mission decision, not silent drift.
- **Alternatives considered**:
  - `glob('*.md')` — would deploy `AGENTS.md.tmpl`, `USER.md.tmpl`, `TOOLS.md.tmpl` (templates, NOT meant for runtime) and `GOVERNANCE.md` (manually maintained, no repo source for some agents)
  - Per-agent manifest in `service-inventory.json` — adds drift surface (manifest can fall out of sync with directory contents)
- **Excluded patterns**: `HEARTBEAT.md` (deployed-side runtime state, written by a different process), `*.tmpl` (templates), `*.bak*` (backups), `GOVERNANCE.md` (manually managed for the `main` agent only).

### D-003 — Atomic copy via os.replace (no fsync on directory)

- **Decision**: Write source bytes to `<dst>/<name>.tmp.<pid>`, call `os.fsync` on the file descriptor before close, then `os.replace` to `<dst>/<name>`.
- **Rationale**: `os.replace` is atomic on POSIX (per Python docs and ext4 semantics). The fsync on the file descriptor ensures bytes are flushed before rename. Directory-level fsync (`os.fsync(os.open(dst_dir, O_RDONLY))`) would harden against last-tick-window loss on crash but adds I/O overhead; next-tick retry is a free recovery for prompt files (they're version-controlled in git).
- **Alternatives considered**:
  - `shutil.copy2` (preserves more metadata but is not atomic and can leave partial-write destinations)
  - Symlink instead of copy (would couple deployed path to repo path; rejected because Felix agents expect real files at the deploy location and the repo is operator-mutable)
  - Hard link (same issue as symlink; cross-device hard links don't work and `/home/claude/` vs `/data/` may be different filesystems)

### D-004 — Agent discovery from service-inventory.json (not directory glob)

- **Decision**: Helper reads `docs/design/architecture/data/service-inventory.json`, extracts `services[openclaw].agents.<slug>` map, and considers each agent with both `source_in_repo` AND `workspace` populated.
- **Rationale**: `service-inventory.json` is the canonical source per Felix Constitution Directive 5 and [[feedback_architecture_docs_first]]. Auto-discovery: new agents merged in (with both fields populated) are picked up on the next tick. Excluded by construction: felix-doc-auditor (not under `services[openclaw].agents.*` — it's a top-level `systemd-timer` service).
- **Alternatives considered**:
  - Hardcoded agent list — drifts the moment a new agent is added
  - `glob scripts/openclaw/agents/*/` — would include `felix-doc-auditor/` (NOT an openclaw agent at runtime) and `main/` (which has no `source_in_repo` field in JSON, though it has a repo dir — that's a doc-bug fixed in IC-07)

### D-005 — Never delete deployed files (FR-016)

- **Decision**: If a file exists in a deploy dir but NOT in the source dir, the helper leaves it alone with no warning.
- **Rationale**: Deletion is an explicit operator action. Accidentally removing a deployed prompt because a repo file was deleted would be catastrophic. Felix-side conservative deploy posture matches the existing pattern in `scripts/sync/driver.py` (no destructive operations on Vikunja state without explicit signal).
- **Alternatives considered**:
  - Mirror sync (rsync `--delete` style) — too aggressive; one accidental git revert + push could wipe a deployed prompt
  - Two-mode flag (additive default, mirror with `--delete`) — adds attack surface for negligible benefit; deferred to operator manual `rm`

### D-006 — Git pull strategy: ff-only, fail-fast (no merge, no reset)

- **Decision**: `git fetch && git pull --ff-only origin main`. Any non-zero exit = log `git_pull_failed` to audit log + exit code 2 (no file copies attempted).
- **Rationale**: `--ff-only` is the safest pull semantics: it advances HEAD only when fast-forward is possible. Refuses non-ff state (which would indicate manual office2 edits or branch divergence — operator must investigate). Stale-but-consistent deploy is preferable to partially-synced deploy.
- **Alternatives considered**:
  - Plain `git pull` (defaults to merge) — could create unexpected merge commits in the office2 clone
  - `git fetch && git reset --hard origin/main` — would destroy any operator's in-progress changes on office2 (e.g., the currently-untracked `scripts/habits/state/` dir)

### D-007 — Audit log shape: per-file action + per-tick summary

- **Decision**: One JSONL line per file action (copy, skip, error) PLUS one JSONL line per tick summary. All in `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`.
- **Rationale**: Per-file action enables forensic drift analysis ("when did THIS file last sync? what was the MD5 trail?"). Per-tick summary enables high-level health monitoring ("how many ticks succeeded in the last 24h?"). Combined cost: ~26 lines per drift-day tick (5 agents × 5 files + 1 summary), ~26 lines per no-drift tick (all skips + 1 summary). At 12 ticks/hour, ~312 lines/hour worst case. Manageable.
- **Alternatives considered**:
  - Summary only — loses forensic detail
  - Per-file only — high-level health requires re-scanning all entries to compute rates
  - Separate files for actions vs summaries — adds path discovery complexity for the operator

### D-008 — Cadence: 5 minutes (OnUnitInactiveSec)

- **Decision**: systemd timer fires at `OnUnitInactiveSec=300s` (5 min after last tick exits), `OnBootSec=120s` (2 min boot delay), `Persistent=true`.
- **Rationale**: Matches the issue body's recommendation, the `felix-vikunja-sync.timer` precedent, and the Felix operational pattern. `OnUnitInactiveSec` (not `OnCalendar=*/5`) prevents overlapping ticks if a tick runs slow — a known systemd safety pattern.
- **Alternatives considered**:
  - 1-minute cadence — overkill; agent ticks fire every 5+ hours anyway
  - 15-minute cadence — sufficient for normal ops, but spec-kitty merges feel "stuck" for too long
  - `OnCalendar=*/5` — risk of overlapping ticks if a tick takes >5 min (unlikely but not zero with disk-full / network conditions)

## Implementation-Detail Research

These are the small "how do I do X in stdlib" notes that came up during plan authoring. Cited inline to support the implementation WPs.

### R-001 — Atomic file write with stdlib

Pattern:
```python
tmp_path = dst_path.parent / f"{dst_path.name}.tmp.{os.getpid()}"
with open(tmp_path, "wb") as fh:
    fh.write(src_bytes)
    fh.flush()
    os.fsync(fh.fileno())
# Preserve mode if destination existed:
if dst_path.exists():
    mode = dst_path.stat().st_mode
    os.chmod(tmp_path, mode)
os.replace(tmp_path, dst_path)
```

`os.replace` is documented to be atomic on POSIX (the underlying `rename(2)` is atomic per POSIX.1-2017). The temp filename includes `.tmp.<pid>` to avoid collisions across concurrent invocations (won't happen at our cadence but cheap to harden).

### R-002 — MD5 of a file in stdlib

Pattern:
```python
def compute_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
```

64KB chunks are a balanced default (fits comfortably in pagecache; small enough to avoid memory pressure on tiny VMs). MD5 is used for drift detection only (not cryptographic integrity); collision risk on legitimate prompt-file content is effectively zero.

### R-003 — Subprocess git invocation

Pattern:
```python
proc = subprocess.run(
    ["git", "fetch", "origin", "main"],
    cwd=REPO_ROOT,
    capture_output=True,
    text=True,
    check=False,  # we handle non-zero explicitly
)
if proc.returncode != 0:
    audit_append(record_git_pull_failed(stage="fetch", stderr=proc.stderr.strip()))
    return ExitCode.GIT_PULL_FAILED  # 2
```

`check=False` is important — we want to inspect `returncode` rather than catch `CalledProcessError`. `cwd=REPO_ROOT` keeps git operating on the correct clone. `capture_output=True + text=True` makes stderr available as a string for the audit record.

### R-004 — User-level systemd unit testing

The unit files are validated by:
1. `systemd-analyze --user verify ~/.config/systemd/user/agent-prompt-sync.{service,timer}` — syntax check
2. `systemctl --user daemon-reload && systemctl --user enable --now agent-prompt-sync.timer` — actually load and start
3. `systemctl --user list-timers | grep agent-prompt-sync` — confirm scheduled

No unit-file tests in CI (CI doesn't have a user-level systemd to run against). Verification is operator-driven, per SC-1/SC-3.

### R-005 — pytest tmp_path for atomic-copy tests

Pattern:
```python
def test_atomic_copy_preserves_mode(tmp_path):
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"hello")
    dst.write_bytes(b"world")
    os.chmod(dst, 0o644)
    atomic_copy(src, dst)
    assert dst.read_bytes() == b"hello"
    assert (dst.stat().st_mode & 0o777) == 0o644
```

`tmp_path` provides an isolated test directory per test function. No `/data/services/` references in tests; no SSH; pure file I/O within the tempdir.

## Validation Notes

- Spec FR mapping: every FR (FR-001 through FR-017) is addressed by exactly one IC in plan.md's Implementation Concern Map. Validated by hand.
- Charter directives mapping: every active directive listed in `.kittify/charter/charter.md` is addressed in plan.md § Charter Check.
- No [NEEDS CLARIFICATION] markers in plan.md or spec.md. Discovery + research resolved all material decisions.
