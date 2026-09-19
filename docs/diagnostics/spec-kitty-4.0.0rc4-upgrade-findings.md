# Spec-Kitty upgrade findings — 3.2.7 → 4.0.0rc4 candidate

**Reporting window**: 2026-09-17 → 2026-09-19
**Host**: Windows 11 Pro 26200 · Python 3.13.7 · `uv tool` install
**Project**: `kentonium3/kg-automation`, `.kittify` schema_version 3, 124 missions
**Prepared for**: spec-kitty QA agents. Read the Findings Register first; each row
links to a kg-automation issue carrying full reproduction and an upstream draft.

---

## Read this first: builds, not version strings

Every finding below is pinned to a **commit**, not a release. spec-kitty does not
yet report version + build together (filed upstream as a future feature), so a
bare version string identifies nothing during pre-release QA.

| Label | Build (commit) | Notes |
|---|---|---|
| 3.2.7 | `fb4e8fa98` | Last PyPI stable. Works on Windows. |
| 4.0.0rc3 | `fbe1109fa` | Tagged + on PyPI. **Unusable on Windows.** |
| 4.0.0rc4 candidate | `619bd1137` | **No tag, no PyPI artifact.** `pyproject.toml` on `main` declares `4.0.0rc4`. This is what we tested. |

Install the candidate by SHA:

```bash
uv tool install --force "git+https://github.com/spec-kitty/spec-kitty.git@619bd11376342abaae67e18588ff12c2def336f1"
```

⚠️ **Windows prerequisite**: `git config --global core.longpaths true`. The
spec-kitty repo contains paths over 260 chars (e.g. a `kitty-specs/.../snapshot-latest.json`
at 182 chars before any prefix). The OS may have `LongPathsEnabled=1` and it still
fails, because Git for Windows defaults `core.longpaths` to false. Symptom:

```text
error: unable to create file kitty-specs/...: Filename too long
fatal: Could not reset index file to revision '619bd1137...'
```

---

## Findings Register

| ID | Finding | Sev | Status | Local | Upstream fix |
|---|---|---|---|---|---|
| F1 | Windows: every command fails `[Errno 13]` — process reads its own held lock | P0 | **FIXED, verified** | [#985](https://github.com/kentonium3/kg-automation/issues/985) | `f0eff4f2e` +5 (#4703, #4714) |
| F2 | Non-TTY stdout silently disables version fetch for explicit `upgrade` queries | P2 | **FIXED, verified** | [#981](https://github.com/kentonium3/kg-automation/issues/981) | `ad4c8cc8e` (#4704) |
| F3 | Prerelease channel resolves to a **yanked** release | P2 | **FIXED, verified** | [#982](https://github.com/kentonium3/kg-automation/issues/982) | `cc945affb` (#4705) |
| F4 | Orientation block always renders `project: unknown` | P2 | **FIXED, verified** | [#983](https://github.com/kentonium3/kg-automation/issues/983) | `68601eea4` (#4706) |
| F5 | Orientation `health` can never report `upgrade-available` | P2 | **FIXED, partial verify** | [#984](https://github.com/kentonium3/kg-automation/issues/984) | `54a5f86f1` (#4707) |
| F6 | `upgrade --yes` still prompts; declined remediation exits 1 on success | P2 | **OPEN** | [#992](https://github.com/kentonium3/kg-automation/issues/992) | — |
| F7 | `upgrade` fails on `_recheck_command_completion`; needs 3 runs | P2 | **OPEN** | [#993](https://github.com/kentonium3/kg-automation/issues/993) | — (known scoped-out follow-up) |
| F8 | Windows `upgrade --dry-run` reports 184 phantom repairs forever | P3 | **OPEN** | [#994](https://github.com/kentonium3/kg-automation/issues/994) | — |
| F9 | `mission-state --fix` rejects legacy `change_mode: regular` | P2 | **OPEN** | [#995](https://github.com/kentonium3/kg-automation/issues/995) | — |
| F10 | Mission-state manifest + quarantined rows written to a **gitignored** path | P2 | **OPEN** | [#996](https://github.com/kentonium3/kg-automation/issues/996) | — |
| F11 | `mission-state --fix` / `--teamspace-dry-run` report counts with no detail | P3 | **OPEN** | [#997](https://github.com/kentonium3/kg-automation/issues/997) | — |
| F12 | Repo unclonable on default Windows git (path length) | env | **WORKED AROUND** | — (this doc) | n/a — set `core.longpaths` |

`FIXED, verified` = observed working on `619bd1137`. `OPEN` = reproduces on `619bd1137`.

---

## Fixed in the rc4 candidate — verification evidence

### F1 · Windows self-held lock (was a total blocker)

On rc3, `ensure_runtime()` held an exclusive `msvcrt.locking()` lock on
`%LOCALAPPDATA%\spec-kitty\cache\.update.lock` and then read that same file with
`Path.read_bytes()`. Windows `msvcrt` locks are **mandatory**, so the OS refused
the owning process's own read. POSIX `flock` is advisory, which is why CI missed
it. `ensure_runtime()` runs from `main_callback`, so the failure was total.

Minimal proof of the signature:

```python
p.read_bytes()                                          # -> b''  fine
fh = open(p, "a+b"); msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
p.read_bytes()                                          # -> PermissionError errno 13
```

On `619bd1137`:

```text
--version  ok 0   doctor channel  ok 0   session-start  ok 0
session-stop  ok 0   config  ok 0
```

Upstream also fixed the two secondary defects we raised: the swallowed
`str(exc)` that dropped `exc.filename`, and `session-start`'s exit-0 contract
(now a startup fast path, since a body-level `try/except` cannot catch a
`main_callback` failure).

### F2–F5 · Upgrade-surface and orientation defects

```text
F2  upgrade --dry-run --json, piped:
    was {'latest_version': None,     'latest_source': 'none', 'fetched_at': None}
    now {'latest_version': '4.0.0rc3','latest_source': 'pypi','fetched_at': '...'}

F3  prerelease resolution:  was 4.2.0a1 (yanked)  ->  now 4.0.0rc3 (live)
    PyPI state still exercises this: 4.1.5 and 4.2.0a1 are yanked; rc1/rc2/rc3 are not.

F4  session-start:  was "project: unknown"  ->  now "project: kg-automation"

F5  health now computed rather than pinned (latest_version resolves).
```

**F5 caveat for QA — please close this gap.** We could **not** observe the
`upgrade-available` branch actually render, because the installed build is newer
than anything published on either channel, so `is_outdated` is correctly `false`
everywhere. What is verified is that the input which made `upgrade-available`
*unreachable* is gone. A QA environment on an older build can confirm the positive
branch.

**Residual on F2, deliberately not reopened.** `upgrade --dry-run --plan-json`
still reports `latest_version: null, latest_source: "none", is_outdated: false` in
its nested `compatibility.cli` block. That is a different path —
`_full_plan_compatibility()` hardcodes `flag_no_nag=True, env_ci=True,
stdout_is_tty=False` with `read_only=True`, and its docstring states the intent:
*"Return the frozen compatibility envelope without network or writes."* Offline is
by design; what carries over is that it renders `is_outdated: false` (an
affirmative claim) rather than distinguishing "not checked".

---

## Open on the rc4 candidate

### F6 · `--yes` does not suppress the TeamSpace prompt, and success exits 1

```bash
spec-kitty upgrade --yes </dev/null   # EOF      -> exit 1
printf 'n\n' | spec-kitty upgrade --yes   # answer n -> exit 1
```

Final line of that same run: `Run 'spec-kitty doctor mission-state --fix' now? [y/N]: Project is already up to date!`

Both a declined optional remediation *and* EOF fail the whole command. `--yes` is
documented as *"Non-interactive confirmation; alias for --force (FR-017)"*.
**Do not gate automation on this exit code.**

### F7 · `upgrade` needs three invocations to converge

Attempt 1 fails with `Completed command output changed: <repo>\.agents\skills`
(emitted twice) plus `Unresolved tool-surface drift in 22 file(s)`. Skills
projection went 15 → 70 → 70 across three runs.

Raised at `managed_skills.py:180 _recheck_command_completion` — the sibling race
the #4703 `ensure_runtime` docstring **explicitly scopes out** as a tracked
follow-up. New information for upstream: it now presents as a **deterministic**
single-process failure on a large multi-agent projection, not a rare concurrent
peer race. The dangerous shape is partial-apply-then-report-failure: attempt 1 had
already advanced the version stamp and modified two `.kittify` manifests while
reporting `Upgrade failed`.

### F8 · Phantom repair count on Windows

After full convergence, `upgrade --dry-run` still reports
`Would repair 184 supporting surface paths` identically on every run, while
`doctor tool-surfaces` exits 0 with zero findings. 184 is exactly the plan's
`chmod` count (`{'chmod': 184, 'create': 340, 'update': 5}`); `os.chmod` on
Windows cannot set a POSIX mode, so those effects never converge. Cosmetic, but
the dry-run can never report a clean project.

### F9 · `change_mode: regular` rejected — 20 TeamSpace blockers unresolvable

```text
Invalid canonical meta.json for <slug>: Invalid change_mode 'regular'; valid values: ['bulk_edit']
```

21 of 124 missions fail, all `01KS*`/`01KT*` era. A valid-values list of
`bulk_edit` alone cannot be right — it would require every mission to be a bulk
edit, when the bulk-edit doctrine treats that as the exceptional case needing an
occurrence map.

⚠️ **Do not "fix" this by editing the 21 `meta.json` files to `bulk_edit`.** That
mislabels ordinary missions and corrupts the field the bulk-edit guardrail keys on.

### F10 · Repair audit trail lands in a gitignored path

`.gitignore:75` ignores `.kittify/migrations/`, so **both** of these live only in
the working tree and a `git clean -xfd` destroys them:

- the run manifest (the only per-mission record of a 171-file mutation, with
  before/after sha256 per file)
- the quarantine holding rows physically removed from **tracked**
  `status.events.jsonl` files

Mitigating: the evicted rows remain recoverable from git because the source files
are tracked. So this is a defence-in-depth failure, not guaranteed loss — but the
artifact presented *as* the record is the one thing git will not protect.

### F11 · Counts without detail

Complete stdout of a 171-file mutation:

```text
Mission-state repair complete (updated=101, unchanged=2, errors=21).
Manifest: .kittify\migrations\mission-state\5189e53ea8fc1ec9.json
```

Complete stdout of the dry-run: `TeamSpace dry-run failed (20 validation errors).`

No mission names, codes or reasons. Root cause recovery required parsing the
(gitignored) manifest's `missions[].validation_errors`. The dry-run writes no
manifest at all, so its 20 errors have no recoverable detail anywhere. Contrast
`doctor tool-surfaces`, which lists every finding with its path — the verbose
style already exists in the same command family.

---

## Mission-state repair outcome (this project)

```text
spec-kitty doctor mission-state --fix
  updated=101  unchanged=2  errors=21   |  171 files changed  |  exit 1

TeamSpace blockers:  38 -> 20
Errors:              38 -> 20
Warnings:           116 -> 116  (unchanged)
Quarantined:         20 rows across 6 missions, all DecisionPointOpened
                     events tagged `quarantined_non_status_event`
```

Open question for QA, not investigated here: **is `DecisionPointOpened` correctly
classified as a non-status event?** Six were evicted from one mission's status log
and they look like legitimate mission history.

---

## Suggested QA follow-ups

1. **Confirm F5's positive branch** on an environment running an older build, so
   `upgrade-available` is reachable.
2. **Does F7 reproduce with a single agent configured?** Our projection covered
   five (`copilot, claude, gemini, codex, antigravity`). If it converges in one run
   with fewer, that localises the race.
3. **Does F8 occur on macOS/Linux?** If the count converges there, it is purely a
   Windows mode-representability issue.
4. **What replaced `change_mode: regular` (F9)?** Nothing in the error names a
   migration path.
5. **Was `.kittify/migrations/` ignored before the quarantine feature existed
   (F10)?** That would make it an unnoticed collision rather than a decision.

---

## Related artifacts

- Restore point for the mission-state repair: git tag
  `pre-mission-state-fix-20260919` (commit `2bc3b749`), plus an out-of-tree
  backup with a `RESTORE.md` procedure.
- Upgrade artifacts commit: `2bc3b749`.
- Each issue listed above embeds a slim upstream-ready draft in a fenced block,
  per the dual-track model in
  [`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>).
  All drafts currently carry `**Submission approved by**: PENDING` and have **not**
  been filed upstream.
