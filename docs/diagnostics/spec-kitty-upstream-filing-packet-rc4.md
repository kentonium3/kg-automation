---
title: 'Upstream filing packet: released spec-kitty 4.0.0rc4 (build 5309c4107)'
doc_type: note
audience: agents_and_humans
status: active
last_updated: '2026-09-21'
---

# Upstream filing packet — released 4.0.0rc4 (`5309c4107`)

**For the spec-kitty QA bot.** Three outbound actions, ready to execute. Everything else
from this arc is already upstream — see the do-not-file list at the bottom before acting.

## Why this artifact exists

Discovery and analysis happen under Kent's **personal hat**, tracked as `kentonium3/kg-automation`
issues. Filing upstream happens under his **spec-kitty work hat**, which is the account holding
issue-label and priority-setting privileges. This packet is the handoff between the two: the
personal hat produces approved copy plus label guidance, the work hat applies it.

It is **not** a revival of the per-report paste docs that
[`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>) deprecated in
v1.3. Those were one file per report duplicating an issue body. This is a single consolidated
work order covering three actions across two repos, carrying the label suggestions the bot needs
and the dedupe result that stops it filing eight things when only two are new.

## How to use it

1. Work the actions in order. Each gives the target, the title, suggested labels, and the exact
   body to post.
2. **Labels are suggestions, not instructions** — you hold the privileges, so apply your own
   judgement. Where a call is genuinely arguable it is flagged inline.
3. **All three actions are new issue filings.** Persistence or recurrence against a *closed*
   upstream issue is filed as a new issue referencing the closed one, not as a comment on it
   (Kent, 2026-09-21) — a comment on a closed issue is easy to miss and does not re-enter
   triage. Comments stay correct for issues that are still open.
4. After each action, record back on the named kg-automation issue: the upstream URL, and apply
   `upstream-filed` there if it is not already present.
5. The pre-posting approval gate is satisfied for Actions 1 and 2 — Kent approved that copy on
   2026-09-21. **Action 3's copy is new and needs his sign-off before posting.**

## Label taxonomy reference

Verified against `spec-kitty/spec-kitty` on 2026-09-21, so these are real values:

| Label | Meaning |
|---|---|
| `priority:P0` | Release blocker / must decide before final |
| `priority:P1` | High-value stabilization / bug or release confidence |
| `priority:P2` | Planned enhancement / post-blocker work |
| `priority:P3` | Backlog / future / needs reconfirmation |
| `from:qa` | Filed by a human QA tester |
| `type:bug` / `type:fix` / `type:finding` | defect / defect fix / triaged review finding |
| `domain:skills` | Command/skill rendering, install, upgrade deployment (`src/specify_cli/skills`, `upgrade`) |
| `domain:status` | Status event-log & lane state machine |
| `domain:cli` | Control-plane / CLI command surface |

---

# Action 1 — FILE NEW ISSUE

**Repo**: `spec-kitty/spec-kitty`
**Local tracking**: kentonium3/kg-automation#1005
**Copy approved**: Kent Gale, 2026-09-21
**Title**:

```text
Bug: Windows `upgrade` fails — os.utime(..., follow_symlinks=False) on a regular file (released 4.0.0rc4)
```

**Suggested labels**: `from:qa`, `type:bug`, `priority:P1`, `domain:skills`

`domain:skills` is unambiguous — its own description is *"Command/skill rendering, install,
upgrade deployment (src/specify_cli/skills, upgrade)"*, and the fault is at
`skills/installer.py:980` inside the upgrade path.

⚠️ **Priority is arguable and yours to set.** P1 on the taxonomy's terms ("bug or release
confidence"). A case for **P0** exists: this is a released rc, `upgrade` is wholly broken on
Windows, and 4.0.0 final is next — so if Windows is release-gating, it decides before final.
Against P0: blast radius is one command, not the whole CLI, unlike the rc3 blocker.

**Body** — post verbatim:

---
# Bug: Windows `upgrade` fails — `os.utime(..., follow_symlinks=False)` on a regular file (released 4.0.0rc4)

## Summary

`spec-kitty upgrade` fails deterministically on Windows in the released 4.0.0rc4 with `NotImplementedError: utime: follow_symlinks unavailable on this platform`. `specify_cli/skills/installer.py:980` applies `os.utime(..., follow_symlinks=False)` to every managed-skill write whose `after.kind` is `"file"` or `"symlink"`. For a regular file the flag is semantically unnecessary and Windows does not support it (`os.utime not in os.supports_follow_symlinks`). The surrounding code is already Windows-aware and deliberately avoids the flag on the file path, so this reads as one site missed. Blast radius is `upgrade` only — other commands are fine — but each failed run leaves the project partially applied.

## Reproduction

### Prerequisites

- Windows (observed on Windows 11 Pro 26200)
- `uv tool install --force "spec-kitty-cli==4.0.0rc4"`
- A project with managed project-skill surfaces to repair

### Steps

```bash
spec-kitty upgrade --yes; echo "exit=$?"
spec-kitty upgrade --yes; echo "exit=$?"    # deterministic
```

### Expected Behavior

The upgrade applies its managed-skill writes and converges.

### Actual Behavior

```text
exit=1
NotImplementedError: utime: follow_symlinks unavailable on this platform
```

Call chain, innermost last:

```text
cli/commands/upgrade.py:1826          in upgrade
upgrade/finalize.py:64                in finalize_upgrade
cli/commands/upgrade.py:1128          in _finalizer_step_surface_repair
upgrade/assessment.py:207             in apply_upgrade_repairs
tool_surface/providers/managed_skills.py:353  in apply_composition
tool_surface/providers/managed_skills.py:444  in apply_installation
tool_surface/repair.py:141            in apply_assessments
tool_surface/repair.py:309            in _apply_assessment
tool_surface/providers/managed_skills.py:386  in apply
skills/installer.py:1016              in apply_project_skills
skills/installer.py:980               in _apply_project_skill_write
```

Three consecutive runs fail. `--version`, `doctor channel`, `session-start`, `config` and `doctor tool-surfaces` all exit 0, but each failed upgrade leaves `.kittify/command-skills-manifest.json` modified.

## Root Cause

End of `_apply_project_skill_write`:

```python
    else:
        assert content is not None and after.mode is not None
        if current.kind == "absent":
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, after.mode)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                chmod_fd(stream.fileno(), path, after.mode)
        else:
            atomic_write(path, content)
            path.chmod(after.mode)                      # <- deliberately NO follow_symlinks
    if after.kind in {"file", "symlink"} and after.mtime_ns is not None:
        os.utime(path, ns=(after.mtime_ns, after.mtime_ns), follow_symlinks=False)   # <- line 980
```

The file-write branch already avoids the flag (fd-based `chmod_fd()` for new files, bare `path.chmod()` for existing). The trailing `os.utime` reintroduces it for `"file"` as well as `"symlink"`.

Verified on this platform:

```text
os.utime in os.supports_follow_symlinks: False
follow_symlinks=False on a REGULAR FILE: RAISED NotImplementedError: utime: follow_symlinks unavailable on this platform
default (follow_symlinks=True):          OK
```

**Not a new line.** The same call exists in the rc4 candidate build `619bd1137` (line 971), which upgraded this project successfully. The released build now *reaches* it: `92a200070 fix(tool-surface): repair every detected-stale surface and converge in one run (#4782 #4776 #4777 #4134)` changed the repair path so project-skill writes carrying an `mtime_ns` are applied where previously they were not. A latent Windows defect newly exposed, not newly introduced — so a fix should cover the sibling sites too:

```text
installer.py:173   backup_path.chmod(before.mode, follow_symlinks=False)
installer.py:181   os.utime(backup_path, ns=(before.mtime_ns, before.mtime_ns), follow_symlinks=False)
installer.py:962   path.chmod(after.mode, follow_symlinks=False)
installer.py:968   path.chmod(after.mode, follow_symlinks=False)
```

`Path.chmod(follow_symlinks=False)` is likewise unsupported on Windows, so these are the same defect awaiting a code path that reaches them.

## Workaround Applied

None. The prior candidate build `619bd1137` does not hit this and remains installable by SHA, at the cost of being untagged.

## Environment

- OS: Windows 11 Pro 26200
- Python: 3.13.7
- spec-kitty-cli: 4.0.0rc4 (pinned tag SHA `5309c4107`), repo `spec-kitty/spec-kitty`
- Install method: `uv tool install --force "spec-kitty-cli==4.0.0rc4"` from PyPI
- Project: `.kittify` schema_version 3, 124 missions

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 5), 2026-09-21.
**Submission approved by**: PENDING — not yet approved for upstream filing.
**Local tracking**: kentonium3/kg-automation#1005.

---

# Action 2 — FILE NEW ISSUE

**Repo**: `spec-kitty/spec-kitty`
**Local tracking**: kentonium3/kg-automation#1006
**Copy approved**: Kent Gale, 2026-09-21
**Title**:

```text
Windows verification report: released 4.0.0rc4 (5309c4107)
```

**Suggested labels**: `from:qa`, `domain:skills`

⚠️ **Two judgement calls for you.**

*No `type:` label suggested.* This is a verification report, not a defect — it confirms three
fixes landed on Windows, reports one regression by reference, and records what could not be
tested. `type:finding` is the closest fit but is described as a *"squad or review finding,
triaged"*, which this is not. Consider leaving `type:` off.

*It may belong as comments instead.* The three confirmations could each go as a short comment on
the issue they confirm — #4775, #4776, #4777, #4778, #4780, #4782 — rather than as one new
issue. A single report is easier for a maintainer to read as a release verdict; per-issue
comments land the confirmation where each fix's author will see it. Your call, and the bodies
are separable if you prefer the latter.

`priority:` deliberately omitted — a report does not compete for fix priority.

**Body** — post verbatim:

---
# Windows verification report: released 4.0.0rc4 (`5309c4107`)

## Summary

Windows verification of the released 4.0.0rc4. Three previously-reported defects are confirmed fixed on Windows, one new Windows-blocking defect was found in the upgrade path, and three earlier reports cannot be verified because that new defect blocks the command they describe. Reporting the confirmations explicitly as well as the regression: the #4703 family suggests Windows is not covered by CI, so positive Windows results may be information you do not otherwise have.

Tested build `5309c4107` (tag `v4.0.0rc4`, PyPI wheel), against the prior candidate build `619bd1137` — 174 commits behind, `behind_by: 0`. Both report `spec-kitty-cli version 4.0.0rc4`; only the build distinguishes them.

## Confirmed fixed on Windows

**`b25f45a56` — repair legacy `change_mode` instead of aborting; honest per-mission reporting (#4778 #4780 #4779).** Both halves verified.

The 21 legacy missions that previously aborted the run are now normalized:

```text
  - audit-interpretation-moment0-01KSBGBS: normalized_change_mode:regular
  - audit-interpretation-size-guard-01KSEN9B: normalized_change_mode:regular
  … 21 total
```

Zero `Invalid change_mode` errors remain, and the output now names every failing mission with its reason under `Errored missions:` instead of emitting a bare count. Net effect on a 125-mission project:

```text
before: 124 missions | errors 38 | warnings 116 | blockers 38
        124 missions | errors 20 | warnings 116 | blockers 20
after:  125 missions | errors  0 | warnings 117 | blockers  0
```

All mission-state blockers cleared. The 11 errors seen mid-run were a different, pre-existing data issue (`Cannot rebuild lanes.json … literal-path owned_files entries match zero files`), not a regression.

**`92a200070` — repair every detected-stale surface and converge in one run (#4782 #4776 #4777 #4134).** Verified for the orientation surface: a `GEMINI.md` stale since 3.2.6, untouched by five prior upgrades across two machines, now repairs.

```text
before: Spec Kitty v3.2.6
doctor tool-surfaces --tool gemini --fix
after:  Spec Kitty v4.0.0rc4
```

## New Windows blocker

`spec-kitty upgrade` fails deterministically with `NotImplementedError: utime: follow_symlinks unavailable on this platform` at `skills/installer.py:980`. Reported separately with full root cause. Narrower than the rc3 blocker — other commands are unaffected — but `upgrade` cannot complete and each attempt leaves `.kittify/command-skills-manifest.json` partially applied.

Worth noting the direction of travel: the *released* build is worse on this path than the untagged candidate that preceded it, which upgraded the same project successfully.

## Still present

The CLI emits both the deprecated **TeamSpace** and the current **Team Kitty** — 328 occurrences of the former in four casings (`teamspace` 182, `Teamspace` 69, `TeamSpace` 54, `TEAMSPACE` 23), against Team Kitty in 14 files. Reported separately.

## Blocked on verification

Three earlier Windows reports — `upgrade --yes` prompting and exiting 1 on success, `upgrade` needing three invocations to converge, and a permanent phantom repair count in `upgrade --dry-run` — all describe `upgrade` behaviour and cannot be judged while `upgrade` crashes in its finalizer. `cdde1cb51` (#4775) and `92a200070` plausibly address the first two, but that is unconfirmed on Windows.

One partial observation, explicitly not offered as evidence: the `[y/N]` prompt did not appear in the released-build run, against one occurrence on the candidate build. Confounded — the crash pre-empted the gate and blockers had been cleared separately — so inconclusive.

## Environment

- OS: Windows 11 Pro 26200
- Python: 3.13.7
- spec-kitty-cli: 4.0.0rc4 (pinned tag SHA `5309c4107`), repo `spec-kitty/spec-kitty`
- Install method: `uv tool install --force "spec-kitty-cli==4.0.0rc4"` from PyPI
- Project: `.kittify` schema_version 3, 125 missions

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 5), 2026-09-21.
**Submission approved by**: PENDING — not yet approved for upstream filing.
**Local tracking**: kentonium3/kg-automation#1006.

---

# Action 3 — FILE NEW ISSUE (persistence on a closed issue; needs Kent's copy approval first)

**Repo**: `spec-kitty/spec-kitty`
**References closed issue**: **#4779** — *"Bug: mission-state repair writes its manifest and quarantined rows into a gitignored path"*
**Local tracking**: kentonium3/kg-automation#996
**Copy approved**: ❌ **NOT YET** — drafted 2026-09-21, has not been through the pre-posting
gate. Show Kent the exact wording before posting.

**Procedure note.** Per Kent's direction (2026-09-21): persistence or recurrence against a
**closed** upstream issue is filed as a **new issue referencing the closed one**, not as a
comment on it. A comment on a closed issue is easy to miss and does not re-enter triage.
Comments remain the right shape for an issue that is still **open** — which is why #1000 /
spec-kitty#4783 gets no action here.

**Title**:

```text
Bug: mission-state manifest and quarantine still written to a gitignored path on released 4.0.0rc4 (persists after #4779 was closed)
```

**Suggested labels**: `from:qa`, `type:bug`, `priority:P2`, `domain:status`

Mirrors the labels #4779 carried, since it is the same defect on a newer build. `domain:status`
matches its original classification.

⚠️ **Consider also**: reopening #4779 alongside this issue would keep the history in one place —
but the new issue is the filing of record per the procedure above.

**Body** — post verbatim after approval:

---

# Bug: mission-state manifest and quarantine still written to a gitignored path on released 4.0.0rc4

## Summary

Filing fresh rather than commenting, because the issue this concerns — **#4779** — was closed as completed on 2026-09-20 and the reported behaviour is unchanged on a newer build. `spec-kitty doctor mission-state --fix` still writes both its run manifest and its quarantine under `.kittify/migrations/`, which the shipped `.gitignore` excludes. The audit trail of a destructive repair, and any rows physically evicted from tracked `status.events.jsonl` files, therefore remain outside version control; `git clean -xfd` destroys both. The commit that closed #4779 appears to have addressed a different half of that report — the diagnosability consequence, which was the adjacent #4780 — rather than the placement.

## Build tested

- `spec-kitty-cli 4.0.0rc4 (pinned tag SHA 5309c4107)` — the released `v4.0.0rc4` tag, PyPI wheel.
- **Persistence, not recurrence**: this build is newer than the state #4779 was closed against, and contains `b25f45a56`, the commit carrying `Closes #4779`.

## Reproduction

### Prerequisites

- A project carrying the spec-kitty-supplied `.kittify/migrations/` gitignore entry
- Mission state with rows the repair will quarantine

### Steps

```bash
spec-kitty doctor mission-state --fix
ls -t .kittify/migrations/mission-state/*.json | head -1
git check-ignore -v .kittify/migrations/mission-state/<run_id>.json
ls -d .kittify/migrations/mission-state/quarantine
```

### Expected Behavior

The record of a destructive repair, and any data it removes from tracked files, is version-controlled — or the operator is told plainly that it is not.

### Actual Behavior

```text
newest manifest: .kittify/migrations/mission-state/fcc2a3b30be8c6f7.json
git check-ignore -v  ->  .gitignore:75:.kittify/migrations/   .kittify/migrations/mission-state/fcc2a3b30be8c6f7.json

quarantine dir:  .kittify/migrations/mission-state/quarantine      (same ignored path)
```

Both still ignored. Nothing in the command output indicates the artifacts it points at are untracked.

## Why #4779 may have been closed on different grounds

`b25f45a56` carries `Closes #4778. Closes #4780. Closes #4779.` and states:

> `--fix` and `--teamspace-dry-run` now report per-mission slug + reason in the terminal and `--json` (dry-run parity), so triage no longer requires reading the gitignored manifest.

That fully resolves the diagnosability consequence, and we can confirm it works on Windows — per-mission slug and reason now render. But diagnosability was the subject of #4780. #4779's concern was placement: the record of a destructive mutation, and rows removed from tracked files, are written where git will not keep them. Removing the need to *read* the manifest does not make it durable.

## Mitigation, for weighing severity

The evicted rows remain recoverable from git because the source `status.events.jsonl` files are tracked. So this is a defence-in-depth gap rather than guaranteed data loss — it becomes real loss only for an operator who cleans the working tree without a pre-repair commit, which is plausibly the state someone reaching for a repair tool is in.

## Environment

- OS: Windows 11 Pro 26200
- Python: 3.13.7
- spec-kitty-cli: 4.0.0rc4 (pinned tag SHA `5309c4107`), repo `spec-kitty/spec-kitty`
- Install method: `uv tool install --force "spec-kitty-cli==4.0.0rc4"` from PyPI
- Project: `.kittify` schema_version 3, 125 missions

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 5), 2026-09-21.
**Submission approved by**: PENDING — copy not yet approved for posting.
**Local tracking**: kentonium3/kg-automation#996.

---

# DO NOT FILE — already routed upstream

Checked 2026-09-21. Each of these is already an upstream issue, filed under the work hat
(`from:qa`, titles matching our drafts verbatim). Filing again creates duplicates.

| Ours | Upstream | Upstream state | Our verdict on `5309c4107` |
|---|---|---|---|
| #992 | spec-kitty#4775 | CLOSED completed | unverifiable — #1005 blocks `upgrade` |
| #993 | spec-kitty#4776 | CLOSED completed | unverifiable — #1005 blocks `upgrade` |
| #994 | spec-kitty#4777 | CLOSED completed | unverifiable — #1005 blocks `upgrade` |
| #995 | spec-kitty#4778 | CLOSED completed | ✅ fixed, verified |
| #997 | spec-kitty#4780 | CLOSED completed | ✅ fixed, verified |
| #999 | spec-kitty#4782 | CLOSED completed | ✅ fixed, verified |
| #1000 | spec-kitty#4783, epic #4793, #3154 | **OPEN** | ❌ still present |

#1000 gets no action: spec-kitty#4783 is still **open**, so there is no closure to contest and
nothing new to add — the defect is known and unfixed. If it later closes while the behaviour
persists, that becomes an Action-3-shaped new issue under the same procedure.

#992, #993 and #994 stay open on our side deliberately — the fixes are in the build we run but
cannot be verified while #1005 crashes `upgrade` first. Open means unverified locally, not
unfixed upstream. If you want those confirmations for the record, they need either an rc5
carrying the #1005 fix or a rollback to candidate build `619bd1137`.

# One correction worth carrying

Our #993 root-cause analysis was **wrong**, and upstream's should stand. We attributed the
three-run convergence to the `_recheck_command_completion` `installed_at` race that the #4703
docstring scoped out. `92a200070` found the real cause: a Windows POSIX-mode assertion at the
same gate (`os.chmod` cannot represent `0o755` on a freshly-created `.agents/skills`), and fixed
the `installed_at` hash separately as a second defect. The symptom report was sound; the
diagnosis was not. No action needed — recorded so it is not repeated in a future root-cause
section.

# Related

- Full build-pinned register: [`spec-kitty-4.0.0rc4-upgrade-findings.md`](<./spec-kitty-4.0.0rc4-upgrade-findings.md>)
- Reporting workflow and the mandatory build-ID convention: [`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>)
- Session resume context: [`handoff/2026-09-21-spec-kitty-4.0.0rc4-upgrade.md`](<../handoff/2026-09-21-spec-kitty-4.0.0rc4-upgrade.md>)
