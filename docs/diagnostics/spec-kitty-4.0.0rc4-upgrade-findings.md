# Spec-Kitty upgrade findings — 3.2.7 → 4.0.0rc4 (candidate, then released) → rc5 dev → PR #4947 head

**Reporting window**: 2026-09-17 → 2026-09-23
**Host**: Windows 11 Pro 26200 · Python 3.13.7 · `uv tool` install
**Project**: `kentonium3/kg-automation`, `.kittify` schema_version 3, 125 missions
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
| 4.0.0rc4 candidate | `619bd1137` | Untagged build off `main`. The first thing we tested. |
| 4.0.0rc4 **released** | `5309c4107` | Tag `v4.0.0rc4` + PyPI wheel. **174 commits ahead** of the candidate, `behind_by: 0`. Both report `4.0.0rc4`. **`upgrade` is broken on Windows here (F15).** |
| 4.0.0rc5 **dev** | `d57619a90` | Untagged `main`, 35 commits past the rc4 tag. Installed 2026-09-22 to reach surfaces the F15 crash blocked. |
| **PR #4947 head** ⬅ installed | `1ee5f2d32` | Upstream fix branch `fix/windows-upgrade-mode-fidelity` for #4923 + #4927, fetchable as `refs/pull/4947/head`. **Unmerged**; strict superset of `d57619a90` (9 ahead, 0 behind). Installed 2026-09-23. `main` was at `86b282f00` (36 past `d57619a90`) with no rc5 tag; the PR conflicts with it. |

Install any build by SHA (the installed one shown; swap the SHA for the others):

```bash
uv tool install --force "git+https://github.com/spec-kitty/spec-kitty.git@1ee5f2d326ae426f139f9bf778cba74e9653c0f3"
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
| F6 | `upgrade --yes` exits 1 on a successful no-op | P2 | **REPRODUCES on `1ee5f2d32`** — now **traced**: a surface-drift error that the text renderer never prints (see PR #4947 section) | [#992](https://github.com/kentonium3/kg-automation/issues/992) → upstream #4925 (deferred) | `cdde1cb51` (#4775, partial) |
| F7 | `upgrade` fails on `_recheck_command_completion`; needs 3 runs | P2 | **FIXED on `d57619a90`** — converges in one run | [#993](https://github.com/kentonium3/kg-automation/issues/993) | `92a200070` (#4776) |
| F8 | Windows `upgrade --dry-run` reports 184 phantom repairs forever | P3 | **REPRODUCES on `1ee5f2d32`** — PR #4947 relaxes the wrong planner; the 184 are **global-asset** effects (see PR #4947 section) | [#994](https://github.com/kentonium3/kg-automation/issues/994) → upstream #4927 | PR #4947 (open, does not fix) |
| F9 | `mission-state --fix` rejects legacy `change_mode: regular` | P2 | **FIXED on `5309c4107`** | [#995](https://github.com/kentonium3/kg-automation/issues/995) | `b25f45a56` (#4778) |
| F10 | Mission-state manifest + quarantined rows written to a **gitignored** path | P2 | **OPEN** — not in PR #4947 scope | [#996](https://github.com/kentonium3/kg-automation/issues/996) → upstream #4928 | — (#4779 closed, not fixed) |
| F11 | `mission-state --fix` / `--teamspace-dry-run` report counts with no detail | P3 | **FIXED on `5309c4107`** | [#997](https://github.com/kentonium3/kg-automation/issues/997) | `b25f45a56` (#4780) |
| F12 | Repo unclonable on default Windows git (path length) | env | **WORKED AROUND**; upstream #4781 open | — (this doc) | n/a — set `core.longpaths` |
| F13 | `GEMINI.md` orientation never refreshes; `tool-surfaces --fix` no-ops | P3 | **FIXED on `5309c4107`** | [#999](https://github.com/kentonium3/kg-automation/issues/999) | `92a200070` (#4782) |
| F14 | CLI emits both deprecated `TeamSpace` and current `Team Kitty` | P3 | **OPEN** on `1ee5f2d32` (328 occurrences, unchanged) | [#1000](https://github.com/kentonium3/kg-automation/issues/1000) | — (#4783 open) |
| F15 | Released rc4: Windows `upgrade` crashes on `os.utime(follow_symlinks=False)` | P1 | **FIXED on `1ee5f2d32`** (statically verified — all five sites routed through `kernel.no_follow`; crash not reachable on this build to prove dynamically) | [#1005](https://github.com/kentonium3/kg-automation/issues/1005) → upstream #4923 | PR #4947 (open) |

**Reading the Status column.** `FIXED, verified` = observed working on the candidate build `619bd1137`.
`FIXED on <build>` = still broken on the previous build, confirmed fixed on the named one.
`REPRODUCES` / `OPEN on d57619a90` = re-tested on the installed dev build and still present.
Every upstream fix commit named here is an ancestor of `d57619a90` (checked with the GitHub compare API, 2026-09-22).

**Observation, not yet a finding.** `.kittify/metadata.yaml`'s `environment:` block (`platform: darwin`,
macOS 26.3.1, Python 3.13.12) was written at `init` on the Mac on 2026-03-26 and has not been touched by
any upgrade since — three of which ran on this Windows box. Whether that block is init-time provenance
or is meant to track the current host is unclear; not filed.

⚠️ **Terminology note for QA agents.** "TeamSpace" is **deprecated**; the product is **Team Kitty**. This document quotes CLI output verbatim, so `TeamSpace` appears throughout where the CLI emits it — that is evidence for F14, not our usage. Use **Team Kitty** in your own reports and reserve `TeamSpace` for quoted CLI strings and the `--teamspace-dry-run` / `teamspace-blocker` identifiers, which are still the literal names on the command line.

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

> **Read with the register above.** F9, F11 and F13 below describe the *candidate* build and were
> subsequently **fixed on the released build** — kept as the original evidence, superseded by the
> released-build section further down. F6–F8 could not be re-tested on the released build (F15);
> they were re-tested on the rc5 dev build — see that section: F7 fixed, F6 and F8 reproduce.

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

### F13 · `GEMINI.md` orientation never refreshes, and the repair no-ops

`GEMINI.md` still stamps `Spec Kitty v3.2.6` while its three sibling surfaces moved to rc4:

```text
.claude/CLAUDE.md                  Spec Kitty v4.0.0rc4
.github/copilot-instructions.md    Spec Kitty v4.0.0rc4
AGENTS.md                          Spec Kitty v4.0.0rc4
GEMINI.md                          Spec Kitty v3.2.6     <- stale
```

It has survived **five** upgrades across two machines (office4's 3.2.6 → rc1 → rc3, and this box's 3.2.6 → rc4 over three invocations). `doctor tool-surfaces` *detects* it — `! Orientation version stale for gemini` — but the documented repair does nothing:

```text
before: Spec Kitty v3.2.6
spec-kitty doctor tool-surfaces --tool gemini --fix   -> exit=0
after:  Spec Kitty v3.2.6      (file unchanged)
```

The defect is the pairing: a check that fires plus a `--fix` that exits 0 without acting is worse than no check, because it reports success. Not hand-repaired here — it is a generated block.

### F14 · Two product names in one CLI

"TeamSpace" is deprecated; the product is **Team Kitty**. The rc4 build emits both. 325 occurrences across four casings:

```text
    181 teamspace        52 TeamSpace
     69 Teamspace        23 TEAMSPACE
```

`Team Kitty` is already live in user-facing auth strings (*"contact your Team Kitty administrator"*, `auth/flows/refresh.py`) and carries an upstream reference `#3980, Team Kitty launch defaults` — so the new name is intended and partially landed. Meanwhile mission-state, doctor, sync, tracker and saas_client still say TeamSpace, including the public flag `--teamspace-dry-run` and the finding code `teamspace-blocker`, which are breaking changes to rename outright and likely need deprecated aliases.

**Not just upstream:** our own repo carries the deprecated name in `docs/runbooks/teamspace-saas-local-qa-setup.md` (filename and content), `docs/DEVELOPER_PORTAL.md`, `docs/runbooks/spec-kitty-per-repo-upgrade.md` and `scripts/decommission/mac/cleanup.sh`. Deliberately left alone pending upstream settling on the canonical spelling — renaming ours first would just create a second mismatch.

---

## Released rc4 (`5309c4107`) — verification, 2026-09-21

The release is **174 commits ahead** of the candidate, `behind_by: 0`. Both builds report
`spec-kitty-cli version 4.0.0rc4`; only the build distinguishes them. Full verdict and
upstream draft: [#1006](https://github.com/kentonium3/kg-automation/issues/1006).

### Fixed — verified on Windows

**F9 + F11** (`b25f45a56`, #4778 #4780 #4779). The 21 legacy missions are normalized
rather than rejected, and the output now names every failure:

```text
  - audit-interpretation-moment0-01KSBGBS: normalized_change_mode:regular
  … 21 total
```

Zero `Invalid change_mode` errors remain, and `Errored missions:` replaces the bare count.
Net effect on mission state:

```text
before (619bd1137): 124 missions | errors 38 | warnings 116 | blockers 38
              then: 124 missions | errors 20 | warnings 116 | blockers 20
after  (5309c4107): 125 missions | errors  0 | warnings 117 | blockers  0
```

**All Team Kitty blockers cleared** — the outcome F9 was blocking.

**F13** (`92a200070`, #4782 #4776 #4777 #4134). `GEMINI.md` repaired at last:

```text
before: Spec Kitty v3.2.6
doctor tool-surfaces --tool gemini --fix
after:  Spec Kitty v4.0.0rc4
```

### New — F15, blocking

`spec-kitty upgrade` crashes deterministically on Windows with
`NotImplementedError: utime: follow_symlinks unavailable on this platform`
(`skills/installer.py:980`). Narrower than F1 — other commands are fine — but `upgrade`
cannot complete and each attempt leaves `.kittify/command-skills-manifest.json` modified.

The line is **not new**; it exists in the candidate build too. `92a200070` (the F7 fix)
now *reaches* it. A latent Windows defect newly exposed, so a fix should cover the four
sibling `follow_symlinks=False` sites in the same module, not just line 980.

### Unchanged

**F14** — still 328 TeamSpace occurrences against Team Kitty in 14 files.
**F10** — the new run's manifest is still written to the gitignored path.

### Unverifiable — F6, F7, F8

All three describe `upgrade` behaviour, and `upgrade` now crashes before reaching them.
Upstream `cdde1cb51` (#4775) and `92a200070` plausibly address F6 and F7, but that is
**unconfirmed on Windows and is not claimed**. Resolving them needs an rc5 carrying the
F15 fix, or a rollback to `619bd1137` — which restores a working `upgrade` but reinstates
the very bugs under test.

One partial observation, explicitly **not** counted as evidence: the `[y/N]` prompt did not
appear in the released-build run (0, against 1 on the candidate). Confounded — the crash
pre-empted the gate and blockers had been cleared separately. Inconclusive.

---

## rc5 dev build (`d57619a90`) — verification, 2026-09-22

Installed the untagged `main` HEAD specifically to reach surfaces the F15 crash blocked on the
released build. `upgrade` runs here, so F6/F7/F8 could finally be judged.

### F7 — FIXED

`upgrade` converged in a **single** run; runs 2 and 3 were clean no-ops. The three-invocation
requirement is gone. Upstream #4776, fixed by `92a200070`, verified as an ancestor of this build.

### F6 — REPRODUCES, and more cleanly than we first reported

```text
Current version: 4.0.0rc5
Target version:  4.0.0rc5

Project is already up to date!
```
**EXIT=1** — on a clean tree, `current == target`, with no prompt, no gate, no warning and no
errors. Upstream #4775 is CLOSED as completed by `cdde1cb51`, an ancestor of this build. The
**prompt half is genuinely fixed**; only the exit code persists.

Our original report confounded the two: exit 1 arrived alongside a declined Team Kitty prompt,
so prompt-suppression and exit status could not be separated. Here there is nothing to decline.

### F8 — REPRODUCES, and this is its first valid test

```text
doctor tool-surfaces  ->  exit=0, 0 missing, 0 stale
dry-run: 'Would repair 184 supporting surface paths (including 0 manifests). …'
dry-run: 'Would repair 184 supporting surface paths (including 0 manifests). …'
```

The issue's premise is "after convergence", which the F15 crash had made unreachable — so this
is the first time it could be tested at all. The count is **184**, the original figure, on a
converged project while the auditor reports clean.

⚠️ Our root cause may be wrong. We blamed unconvergeable `chmod` effects; `92a200070` added
exactly the host-aware relaxation that theory predicts, its convergence half demonstrably works,
and the count did not move.

### F15 — latent, not fixed

Does not reproduce here, but all five `follow_symlinks=False` calls survive (the culprit moved
to line 981). Dormant in `619bd1137`, exposed in `5309c4107`, dormant again in `d57619a90` —
reachability changed, the call never did. The **released** build on PyPI remains broken.

### Unchanged

F10 (gitignored manifest) and F14 (Team Kitty naming, 328 occurrences) both re-verified as
still present.

---

## PR #4947 head (`1ee5f2d32`) — verification, 2026-09-23

Tracking: [#1011](https://github.com/kentonium3/kg-automation/issues/1011). Installed the head of upstream
PR spec-kitty#4947 (`fix/windows-upgrade-mode-fidelity`, Stijn, 2026-09-22), which claims to close #4923
(F15) and #4927 (F8). Chosen over `main` because it is a strict superset of the previously installed
`d57619a90` (compare API: 9 ahead, 0 behind), so any change is attributable to the fix. The PR is
unmerged, unreviewed, CI-green, and conflicts with `main` (base `6b4164dbf`, `main` 30 ahead).

Restore point: tag `pre-upgrade-pr4947-20260923` (= `ff044e93`). Pre-flight: clean tree, no mission
worktrees. Every command below ran with `</dev/null`; exit codes recorded. **The upgrade left the working
tree untouched** — no `.kittify` or orientation file changed, so there are no upgrade artifacts to commit
beyond this document.

### Headline: one of the two fixes does not reach Windows

| | Baseline `d57619a90` | PR head `1ee5f2d32` |
|---|---|---|
| `upgrade --dry-run` | `Would repair 184 …`, exit 0 | **`Would repair 184 …`, exit 0 — byte-identical** |
| `upgrade --yes` ×3 | exit 1, "already up to date" | exit 1, "already up to date" — unchanged |
| `doctor tool-surfaces` | 294 drift findings, exit 0 | byte-identical |
| `doctor mission-state --teamspace-dry-run` | 15 `PAYLOAD_INVALID`, exit 1 | byte-identical |
| `follow_symlinks=False` sites in `skills/installer.py` | 5 | **0** (routed via `kernel.no_follow`) |
| TeamSpace occurrences (F14) | 328 | 328 |
| Orientation stamps (F13) | 4× `v4.0.0rc5` | 4× `v4.0.0rc5` |

### F15 / #4923 — FIXED (statically verified)

All five `chmod`/`utime` sites in `skills/installer.py` (`:172`, `:174`, `:963`, `:969`, `:981` on the
baseline) now call `chmod_no_follow` / `utime_no_follow` from the new `kernel/no_follow.py`, which passes
`follow_symlinks=False` only when the host lists the function in `os.supports_follow_symlinks`. On this
box both `os.utime` and `os.chmod` report unsupported, so the flag is dropped. No direct
`follow_symlinks=False` apply call survives in the module.

Caveat, stated plainly: the crash was **dormant** on the baseline too (reachability, not the call,
changed between builds — see the rc5 section), so this run could not make it fire and then watch it
not fire. The dynamic evidence is only "three `upgrade --yes` runs and one `--json` run, no
`NotImplementedError`". The static evidence is what carries the verdict. The released rc4 wheel on PyPI
remains broken until this merges.

### F8 / #4927 — NOT FIXED: the relaxation was applied to the wrong planner

The PR generalises `windows_dir_mode_only_divergence` (`skills/command_installer.py`) from
directory-only to `directory`/`file`/`symlink`, and its two callers are `skills/installer.py` (project
skill writes, `:508` and the new guard at `:601`) and `tool_surface/providers/managed_skills.py:181`
(the completion re-check). Those are the **project**-skill paths.

The 184 effects come from somewhere else entirely. From `upgrade --dry-run --plan-json` on the PR build:

```text
action:   {'chmod': 184}
owner:    {'global_assets': 184}          phase: {'global_bootstrap': 184}
root_id:  {'global_skills': 144, 'runtime_bootstrap': 40}
reason:   {'Refresh canonical global asset': 184}
before:   {('directory', 0o777): 183, ('file', 0o666): 1}
after:    {('directory', 0o755): 183, ('file', 0o644): 1}
differing fields: {('mode',): 184}
paths:    ~/.agents/skills/** (72)   ~/.claude/skills/** (72)   %LOCALAPPDATA%/spec-kitty/** (40)
```

Every one is a **global** asset — the per-user skill trees and the runtime bootstrap cache — and 183 of
the 184 are **directories**, not files. They are emitted by `runtime/asset_preparation.py`:
`_action()` returns `"chmod"` whenever `before.mode != after.mode` (`:87`), and `asset()` feeds it the
`lstat` mode (`:289`–`:315`). That module contains **no** `is_windows` check and never calls
`windows_dir_mode_only_divergence`; the PR does not touch it (its `src/` diff is exactly
`kernel/no_follow.py`, `skills/command_installer.py`, `skills/installer.py`). The dry-run summary line
counts precisely this planner's output — `cli/commands/upgrade.py:1093` renders
`len(prepare_upgrade_repairs(...).effects)`.

So the PR's own diagnosis ("one phantom `chmod` per managed *file*", 184 == managed file count) was a
coincidence of numbers. On this project the count is 183 directories + 1 file (`cache/version.lock`),
all outside the project root. The PR fix is correct for the project-skill seam it covers — it just is
not the seam the reported number comes from. The #4930 triage comment named
`tool_surface/operations.py` and `tool_surface/bundles/projection.py` as the planning layer to fix;
neither is in the PR, and neither is where these effects originate either.

### F6 / #4925 — REPRODUCES, and is now traced (upstream said it could not be)

`upgrade --yes` exits 1 on this converged project with plain output of just
`Project is already up to date!`. The same command with `--json` explains it:

```json
"status": "failed", "success": false,
"errors": ["Unresolved tool-surface drift in 19 file(s); run 'spec-kitty doctor tool-surfaces' to review."],
"surface_repair": {"repaired": 184, "drifted_reported": 19, "created": 0, "skipped": 0}
```

The 19 are the native agent-profile projections — seven profiles (`analyst-annie`, `comms-cleo`,
`diagram-daisy`, `lexical-larry`, `reviewer-renata`, `scribe-sally`, `synthesizer-sam`) across
`.claude/agents/*.md`, `.codex/agents/*.toml` and `.github/agents/*.agent.md` — which the plan lists as
`consent_required` dispositions ("Would preserve 19 paths requiring separate consent"). The doctor
reports each as `Native agent profile drifted from manifest hash` and exits 0. They were last written by
the released 3.2.6 on 2026-09-06 (`39496bf8`) and are unmodified in git since.

Mechanism, traced in the installed `cli/commands/upgrade.py`:

- `_combined_errors()` (`:873`) folds the surface-drift failure into `result.errors`, and the exit code is
  derived from that outcome — hence exit 1 and `"errors": [...]` under `--json`.
- The text renderer for the no-migrations path, `_display_no_migrations_results()` (`:1002`), prints
  `warnings` and `outcome.activation_errors` **only**. The surface-drift error is not in
  `activation_errors`, so it is never printed. The human sees success text and exit 1.

Upstream's #4925 comment concluded `surface_drift_failed` could not be the cause because
`drifted_reported` "is populated only from `consent_required` dispositions" and our report showed no
errors. Both halves were right; the inference was wrong because the text output hides the error that
`--json` shows. It also refutes the "may resolve downstream of #4927" hope — this exit code is
independent of the chmod effects.

Two defects, one policy question, for upstream to split as they see fit:

1. **Rendering**: the no-migrations text path must print the same errors the JSON path reports.
2. **Contract**: `--yes` is documented as non-interactive confirmation. An operator-preserved drift that
   the command deliberately does not overwrite is reported as a hard failure of a no-op run.
3. **Policy**: whether never-consented agent-profile drift should fail `upgrade` at all, given the
   doctor treats the identical finding as a warning and exits 0.

### Unchanged

F7 (single-run convergence — three consecutive no-op runs), F13 (stamps), F10, F14 all as on the
baseline. The 15 `PAYLOAD_INVALID` mission-state validation issues, first seen today on the baseline
before any install, are byte-identical on the PR build and remain an untriaged observation — they were
0 blockers in the 2026-09-22 run of the same command on the same build. Tracked as [#1012](https://github.com/kentonium3/kg-automation/issues/1012).

### Observation, not a finding

`doctor tool-surfaces` reports 275 `Managed doctrine skill drifted from manifest hash` findings on a
clean, converged tree (plus the 19 agent-profile drifts above), and exits 0. Identical on both builds.
The rc5 section above recorded this command as "0 missing, 0 stale"; that was true and incomplete —
drift was not counted. Whether 275 managed skills genuinely drift on a tree git reports as clean, or
the hash check is line-ending-sensitive on Windows, is not investigated here. Tracked as
[#1013](https://github.com/kentonium3/kg-automation/issues/1013).

---

## Upstream routing map — read before filing anything

These findings are produced under Kent's **personal hat** (discovery and analysis, tracked as
kg-automation issues) and filed upstream under his **spec-kitty work hat** as QA-reported
issues. That is why every upstream issue below carries the `from:qa` label and a title matching
our draft verbatim — they are *these* reports, re-routed, not independent duplicates.

**Before filing, check this table.** A second upstream issue for an already-routed finding
would be a duplicate. Persistence or recurrence against a **closed** upstream issue is filed as
a **new issue referencing the closed one** (Kent, 2026-09-21) — a comment on a closed issue is
easy to miss and does not re-enter triage. Comments stay correct for issues still **open**.
Ready-to-post copy for every outbound action:
[`spec-kitty-upstream-filing-packet-rc4.md`](<./spec-kitty-upstream-filing-packet-rc4.md>).

| Ours | Upstream | Upstream state | Verdict on `d57619a90` (latest build tested) | Filing action |
|---|---|---|---|---|
| #992 (F6) | spec-kitty#4775 → **#4925** | #4925 OPEN, deferred | **reproduces on `1ee5f2d32`, now traced** (renderer drops the drift error) | ✅ **posted 2026-09-23** — [comment on #4925](https://github.com/spec-kitty/spec-kitty/issues/4925#issuecomment-5799118717) (Action B, revised before posting; see packet) |
| #993 (F7) | spec-kitty#4776 | CLOSED completed | fixed, verified | no action |
| #994 (F8) | spec-kitty#4777 → **#4927** | #4927 OPEN, PR #4947 | **reproduces on `1ee5f2d32`** — PR relaxes project-skill seam; effects are global-asset | ✅ **posted 2026-09-23** — [comment on PR #4947](https://github.com/spec-kitty/spec-kitty/pull/4947#issuecomment-5799117052) (Action A, verbatim) |
| #995 (F9) | spec-kitty#4778 | CLOSED completed | fixed, verified | already routed |
| #996 (F10) | spec-kitty#4779 → **#4928** | #4928 OPEN | still present (out of PR scope) | already routed |
| #997 (F11) | spec-kitty#4780 | CLOSED completed | fixed, verified | already routed |
| — (F12) | spec-kitty#4781 | OPEN | still required (`core.longpaths`) | already routed |
| #999 (F13) | spec-kitty#4782 | CLOSED completed | fixed, verified | already routed |
| #1000 (F14) | spec-kitty#4783 (+ epic #4793, #3154) | OPEN | still present | already routed |
| #1005 (F15) | **#4923** | OPEN, PR #4947 | **fixed on `1ee5f2d32`** (static) | ✅ **posted 2026-09-23** — [comment on PR #4947](https://github.com/spec-kitty/spec-kitty/pull/4947#issuecomment-5799117052) (Action A, verbatim) |
| #1006 | **#4930** | OPEN, umbrella | rc4/rc5 verdict | filed 2026-09-22 |
| #1011 | — | via comments A + B | PR #4947 head verdict (this section) | ✅ **both posted 2026-09-23** — [A](https://github.com/spec-kitty/spec-kitty/pull/4947#issuecomment-5799117052) · [B](https://github.com/spec-kitty/spec-kitty/issues/4925#issuecomment-5799118717); `upstream-filed` applied |

~~**Net: five new upstream issues plus one comment** on open #4902.~~ Filed 2026-09-22 as #4923, #4925, #4927, #4928, #4930. **Net after 2026-09-23: two comments, both ✅ POSTED** (Action A on PR #4947 for #4923/#4927; Action B on #4925) — see [`spec-kitty-upstream-filing-packet-pr4947.md`](<./spec-kitty-upstream-filing-packet-pr4947.md>) for the copy and the Action B revision. Baseline anomalies tracked locally as #1012 and #1013 — not for upstream yet. See the
[filing packet](<./spec-kitty-upstream-filing-packet-rc4.md>) for ready-to-post copy, suggested
labels, and a ledger separating already-filed from new.

### Two corrections this mapping surfaced

**#4779 was closed without addressing the placement.** `b25f45a56` closes it on the grounds
that *"triage no longer requires reading the gitignored manifest"*. That resolves the
diagnosability half — our F11 / their #4780 — but leaves the audit trail and the quarantined
rows unversioned, which was F10's actual concern. Re-verified unchanged on `5309c4107`: the
manifest and `quarantine/` still land under `.kittify/migrations/`, ignored by `.gitignore:75`.
This is the one place our verdict and upstream's disagree.

**Our F7 root cause was wrong; upstream's is better.** We attributed the three-run convergence
to the `_recheck_command_completion` `installed_at` race that the #4703 docstring scoped out.
Upstream found a Windows POSIX-mode assertion at the same gate — `os.chmod` cannot represent
`0o755` on a freshly-created `.agents/skills` — and fixed the `installed_at` hash separately.
The symptom report was sound; the diagnosis was not. Worth remembering when writing root-cause
sections: a plausible mechanism that fits the evidence is not necessarily the mechanism.

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

We asked at the time whether `DecisionPointOpened` is correctly classified as a non-status
event. **Answered upstream on 2026-09-22 — it is not.** #4897 (P0, open) shows the consequence
is worse than eviction: `doctor decisions --repair` then empties the decisions ledger, and
`agent decision list` drops from 1 to 0. #4919 (open) is an adjacent defect in the same fold.
Our 20 quarantined rows are still recoverable from git, since the source `status.events.jsonl`
files are tracked (see F10).

---

## Suggested QA follow-ups

1. **Confirm F5's positive branch** on an environment running an older build, so
   `upgrade-available` is reachable.
2. ~~Does F7 reproduce with a single agent configured?~~ Moot — F7 is fixed on
   `d57619a90`, and the root cause was a Windows POSIX-mode assertion, not the race.
3. **Does F8 occur on macOS/Linux?** If the count converges there, it is purely a
   Windows mode-representability issue — though see the rc5 section: the `chmod`
   theory now looks doubtful.
4. ~~What replaced `change_mode: regular` (F9)?~~ Answered by `b25f45a56`: legacy
   values are normalized in place (`normalized_change_mode:regular`), not migrated.
5. **Was `.kittify/migrations/` ignored before the quarantine feature existed
   (F10)?** That would make it an unnoticed collision rather than a decision.
6. **Do other partially-supported tool surfaces share F13's shape** — audited
   but not repairable, with `--fix` exiting 0 regardless? Gemini was fixed; the
   pattern may survive elsewhere.
7. **How far does the F14 rename reach beyond the CLI?** The hosted dashboard,
   API responses and upstream docs are separate surfaces; the CLI is only one.
8. **Is F15 Windows-only?** `os.utime in os.supports_follow_symlinks` is `True` on
   Linux, so almost certainly — a Linux run of the released rc4's `upgrade --yes`
   would settle it.

---

## Related artifacts

- Restore point for the mission-state repair: git tag
  `pre-mission-state-fix-20260919` (commit `2bc3b749`), plus an out-of-tree
  backup with a `RESTORE.md` procedure.
- Upgrade artifacts commits: `2bc3b749` (rc4 candidate), `d2557501` (released rc4),
  `6d004746` (rc5 dev). The PR #4947 head install produced no artifacts (tree untouched).
- Restore points: `pre-mission-state-fix-20260919`, `pre-upgrade-pr4947-20260923`.
- Each issue listed above embeds a slim upstream-ready draft in a fenced block,
  per the dual-track model in
  [`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>).
  **See the Upstream routing map above before filing**, and use the ready-to-post copy in
  [`spec-kitty-upstream-filing-packet-rc4.md`](<./spec-kitty-upstream-filing-packet-rc4.md>).
  #4775–#4783 (nine issues, including #4781 for F12) are already upstream; #992, #994, #996,
  #1005 and #1006 need new filings, and #4902 needs a comment.
