# Spec-Kitty upgrade findings — 3.2.7 → 4.0.0rc4 (candidate, then released)

**Reporting window**: 2026-09-17 → 2026-09-21
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
| 4.0.0rc4 **released** | `5309c4107` | Tag `v4.0.0rc4` + PyPI wheel, 2026-09-21. **174 commits ahead** of the candidate, `behind_by: 0`. Both report `4.0.0rc4`. |

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
| F6 | `upgrade --yes` still prompts; declined remediation exits 1 on success | P2 | **OPEN — unverifiable on released build (F15)** | [#992](https://github.com/kentonium3/kg-automation/issues/992) | — |
| F7 | `upgrade` fails on `_recheck_command_completion`; needs 3 runs | P2 | **OPEN — unverifiable on released build (F15)** | [#993](https://github.com/kentonium3/kg-automation/issues/993) | — (known scoped-out follow-up) |
| F8 | Windows `upgrade --dry-run` reports 184 phantom repairs forever | P3 | **OPEN — unverifiable on released build (F15)** | [#994](https://github.com/kentonium3/kg-automation/issues/994) | — |
| F9 | `mission-state --fix` rejects legacy `change_mode: regular` | P2 | **FIXED on `5309c4107`** | [#995](https://github.com/kentonium3/kg-automation/issues/995) | — |
| F10 | Mission-state manifest + quarantined rows written to a **gitignored** path | P2 | **OPEN** | [#996](https://github.com/kentonium3/kg-automation/issues/996) | — |
| F11 | `mission-state --fix` / `--teamspace-dry-run` report counts with no detail | P3 | **FIXED on `5309c4107`** | [#997](https://github.com/kentonium3/kg-automation/issues/997) | — |
| F12 | Repo unclonable on default Windows git (path length) | env | **WORKED AROUND** | — (this doc) | n/a — set `core.longpaths` |
| F13 | `GEMINI.md` orientation never refreshes; `tool-surfaces --fix` no-ops | P3 | **FIXED on `5309c4107`** | [#999](https://github.com/kentonium3/kg-automation/issues/999) | — |
| F14 | CLI emits both deprecated `TeamSpace` and current `Team Kitty` | P3 | **OPEN** (unchanged on `5309c4107`) | [#1000](https://github.com/kentonium3/kg-automation/issues/1000) | — |
| F15 | Released rc4: Windows `upgrade` crashes on `os.utime(follow_symlinks=False)` | P1 | **OPEN, blocking** | [#1005](https://github.com/kentonium3/kg-automation/issues/1005) | — |

**Reading the Status column.** `FIXED, verified` = observed working on the candidate build `619bd1137`.
`FIXED on 5309c4107` = still broken on the candidate, confirmed fixed on the released build.
`OPEN` = reproduces on the released build. `unverifiable` = the command under test crashes first (F15).

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
> released-build section further down. F6–F8 could not be re-tested at all (F15).

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
6. **Do other partially-supported tool surfaces share F13's shape** — audited
   but not repairable, with `--fix` exiting 0 regardless? Gemini may not be the
   only one.
7. **How far does the F14 rename reach beyond the CLI?** The hosted dashboard,
   API responses and upstream docs are separate surfaces; the CLI is only one.

---

## Related artifacts

- Restore point for the mission-state repair: git tag
  `pre-mission-state-fix-20260919` (commit `2bc3b749`), plus an out-of-tree
  backup with a `RESTORE.md` procedure.
- Upgrade artifacts commit: `2bc3b749`.
- Each issue listed above embeds a slim upstream-ready draft in a fenced block,
  per the dual-track model in
  [`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>).
  Drafts for #992, #993, #994, #996, #1000 carry Kent's approval (2026-09-19) and are
  cleared for the QA bot; #1005 and #1006 still read `PENDING`. **Nothing has been filed
  upstream** — the QA bot files, not Claude Code.
- #995, #997 and #999 were closed as fixed before filing, so the bot should **not** file
  them: they would report solved bugs.
