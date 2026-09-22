---
title: 'Upstream filing packet: spec-kitty 4.0.0rc4 released + 4.0.0rc5 dev build'
doc_type: note
audience: agents_and_humans
status: active
last_updated: '2026-09-22'
---

# Upstream filing packet — rc4 released (`5309c4107`) and rc5 dev (`d57619a90`)

**For the spec-kitty QA bot.** Five outbound issue filings, ready to post. Four are defects,
one is a verification report. Everything else from this arc is already upstream — see the
do-not-file list at the bottom before acting.

## Why this artifact exists

Discovery and analysis happen under Kent's **personal hat**, tracked as `kentonium3/kg-automation`
issues. Filing upstream happens under his **spec-kitty work hat**, which holds the issue-label
and priority-setting privileges. This packet is the handoff: the personal hat produces approved
copy plus label guidance, the work hat applies it.

## Builds under test

| Label | Build | Notes |
|---|---|---|
| 4.0.0rc4 **released** | `5309c4107` | Tag `v4.0.0rc4` + PyPI wheel. **What users get from PyPI.** |
| 4.0.0rc5 **dev** | `d57619a90` | Untagged `main` HEAD, 35 commits past the rc4 tag. Installed to reach surfaces the rc4 crash blocked. |
| 4.0.0rc4 candidate | `619bd1137` | Untagged, pre-release. Historical baseline. |

Version strings do not distinguish these — `619bd1137` and `5309c4107` both report `4.0.0rc4`.
Every claim below names the build it was tested on.

---

## VERIFIED FIXED — no action needed

Four of our reports are confirmed fixed by direct test. Each closing commit was verified to be
an ancestor of the build it was tested on (reverse `compare` giving `ahead_by=0`, plus direct
membership in the commit range), so these are fixes *present and working*, not merely closed.

| Upstream | Ours | Fix | Verified on | Evidence |
|---|---|---|---|---|
| #4778 | #995 | `b25f45a56` | `5309c4107` | 21 legacy missions now report `normalized_change_mode:regular`; zero `Invalid change_mode`. Blockers 20 → 0. |
| #4780 | #997 | `b25f45a56` | `5309c4107` | `Errored missions:` section names each mission and reason; the bare `errors=21` is gone. |
| #4782 | #999 | `92a200070` | `5309c4107`, again on `d57619a90` | `GEMINI.md` repaired 3.2.6 → 4.0.0rc4 → 4.0.0rc5 after surviving five prior upgrades. |
| #4776 | #993 | `92a200070` | `d57619a90` | `upgrade` converged in a **single** run; runs 2 and 3 were clean no-ops. The three-run requirement is gone. |

#4776 could not be tested on `5309c4107` — the crash in Action 1 blocked it. It was verified
only once that crash stopped occurring on `d57619a90`.

---

## Template conformance

Every body below is the upstream copy from its kg-automation tracking issue, shaped to the
[external bug-report template](<./spec-kitty-bug-report-external-template.md>): `# Bug: {title}`,
`## Summary`, `## Reproduction` (Prerequisites / Steps / Expected / Actual), `## Root Cause`,
`## Workaround Applied`, `## Environment`, attribution + approval footer. No frontmatter, no
priority, no status, no suggested fix, no internal references — all excluded by the template.

Deviations, noted rather than silently applied:

- The three **persistence** filings (Actions 2–4) add `## Build tested`, which the
  [upstream comment template](<./spec-kitty-upstream-comment-template.md>) makes non-negotiable
  for any renewed defect claim. They are new issues rather than comments per procedure, but they
  are still persistence claims, so the build pinning and recurrence-vs-persistence framing carry.
- **Action 5** omits `## Root Cause` and `## Workaround Applied` (both optional per the template)
  — a verification report has neither.

## Procedure

Persistence or recurrence against a **closed** upstream issue is filed as a **new issue
referencing the closed one**, not a comment on it (Kent, 2026-09-21): a comment on a closed
issue is easy to miss and does not re-enter triage. Comments stay correct for issues still open
— which is why #4783 gets no action here.

After each filing, record back on the named kg-automation issue: the upstream URL, plus the
`upstream-filed` label if absent.

## Label taxonomy reference

Verified against `spec-kitty/spec-kitty`, so these are real values: `priority:P0` (release
blocker) · `priority:P1` (stabilization / release confidence) · `priority:P2` · `priority:P3` ·
`from:qa` · `type:bug` · `type:fix` · `type:finding` · `domain:skills` (command/skill rendering,
install, upgrade deployment) · `domain:status` (status event-log & lane state machine) ·
`domain:cli` (control-plane / CLI surface).

---

# Action 1 — FILE NEW ISSUE (never filed; evidence revised 2026-09-22)

**Repo**: `spec-kitty/spec-kitty`
**Local tracking**: kentonium3/kg-automation#1005
**Copy approved**: ❌ **NOT YET** — the body was revised on 2026-09-22 after the defect stopped
reproducing on `d57619a90`. Needs re-approval before posting.
**Title**:

```text
Bug: released 4.0.0rc4 cannot run `upgrade` on Windows — os.utime(..., follow_symlinks=False) on a regular file
```

**Suggested labels**: `from:qa`, `type:bug`, `priority:P1`, `domain:skills`

⚠️ **Priority is yours to set, and the case changed.** This no longer reproduces on `main`, so
it is not blocking current development. But it *does* break the **released** rc4 that PyPI
serves, and the defective code is still present at five call sites — it was dormant in
`619bd1137`, exposed in `5309c4107`, dormant again in `d57619a90`, purely as a function of which
code path reaches it. P1 reflects "released artifact is broken on a platform"; P2 is defensible
if only `main` matters.

**Body** — post verbatim after approval:

---

# Bug: released 4.0.0rc4 cannot run `upgrade` on Windows — `os.utime(..., follow_symlinks=False)` on a regular file

## Summary

`spec-kitty upgrade` fails deterministically on Windows in the **released** 4.0.0rc4 with `NotImplementedError: utime: follow_symlinks unavailable on this platform`. `specify_cli/skills/installer.py:980` applies `os.utime(..., follow_symlinks=False)` to every managed-skill write whose `after.kind` is `"file"` **or** `"symlink"`. For a regular file that flag is semantically unnecessary — there is no symlink to avoid following — and Windows does not support it at all (`os.utime not in os.supports_follow_symlinks`). The surrounding code is already Windows-aware and deliberately avoids the flag on the file path, so this reads as one site missed.

**The defect is latent, not resolved.** It does not reproduce on current `main` (`d57619a90`), but every `follow_symlinks=False` call survives there, the culprit simply moved to line 981. It was dormant in the pre-release candidate `619bd1137`, exposed in the released `5309c4107`, and dormant again in `d57619a90` — purely as a function of which code path reaches it, never because the call was corrected. Reporting it because the released artifact on PyPI is broken on Windows today, and because the same latency that hid it twice can expose it again.

## Reproduction

### Prerequisites

- Windows (observed on Windows 11 Pro 26200)
- `uv tool install --force "spec-kitty-cli==4.0.0rc4"` — the released PyPI wheel, build `5309c4107`
- A project with managed project-skill surfaces to repair

### Steps

```bash
spec-kitty upgrade --yes; echo "exit=$?"
spec-kitty upgrade --yes; echo "exit=$?"    # deterministic
spec-kitty upgrade --project --yes; echo "exit=$?"   # also crashes; not a way around it
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

Three consecutive runs fail. `--version`, `doctor channel`, `session-start`, `config` and `doctor tool-surfaces` all exit 0, so the blast radius is `upgrade` alone — but each failed run leaves `.kittify/command-skills-manifest.json` modified, i.e. partially applied.

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

The file-write branch already avoids the flag — fd-based `chmod_fd()` for new files, bare `path.chmod()` for existing. The trailing `os.utime` reintroduces it for `"file"` as well as `"symlink"`.

Verified on this platform:

```text
os.utime in os.supports_follow_symlinks: False
follow_symlinks=False on a REGULAR FILE: RAISED NotImplementedError: utime: follow_symlinks unavailable on this platform
default (follow_symlinks=True):          OK
```

What changed between builds is reachability, not the call. `92a200070` (closing #4782/#4776/#4777/#4134) altered the repair path so project-skill writes carrying an `mtime_ns` are applied where previously they were not — which is how the released build began reaching a line the candidate never did. That same commit was explicitly hardening Windows mode handling at the twin gate, which makes the miss at this site more actionable.

Sibling `follow_symlinks=False` calls in the same module, still present on `main` at `d57619a90` and differing only in not currently being reached on Windows:

```text
installer.py:172   backup_path.chmod(before.mode, follow_symlinks=False)
installer.py:174   os.utime(backup_path, ns=(before.mtime_ns, before.mtime_ns), follow_symlinks=False)
installer.py:963   path.chmod(after.mode, follow_symlinks=False)
installer.py:969   path.chmod(after.mode, follow_symlinks=False)
installer.py:981   os.utime(path, ns=(after.mtime_ns, after.mtime_ns), follow_symlinks=False)
```

`Path.chmod(follow_symlinks=False)` is likewise unsupported on Windows.

## Workaround Applied

Installed an untagged `main` build (`d57619a90`) by SHA, where the path does not reach the call. That is not available to anyone installing the released version from PyPI.

## Environment

- OS: Windows 11 Pro 26200
- Python: 3.13.7
- spec-kitty-cli: 4.0.0rc4 (pinned tag SHA `5309c4107`), repo `spec-kitty/spec-kitty`
- Install method: `uv tool install --force "spec-kitty-cli==4.0.0rc4"` from PyPI
- Also checked: `main` at `d57619a90` — does not reproduce, call sites unchanged
- Project: `.kittify` schema_version 3, 125 missions

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 5), 2026-09-22.
**Submission approved by**: PENDING — copy revised 2026-09-22, not yet approved.
**Local tracking**: kentonium3/kg-automation#1005.

---

# Action 2 — FILE NEW ISSUE (persistence against closed #4775)

**Repo**: `spec-kitty/spec-kitty`
**References closed issue**: **#4775** — *"Bug: `upgrade --yes` still prompts, and a declined optional remediation exits 1 on a successful upgrade"*
**Local tracking**: kentonium3/kg-automation#992
**Copy approved**: ❌ **NOT YET** — drafted 2026-09-22.
**Title**:

```text
Bug: `upgrade --yes` exits 1 on a successful no-op (persists after #4775 was closed)
```

**Suggested labels**: `from:qa`, `type:bug`, `priority:P2`, `domain:cli`

Mirrors #4775's own `priority:P2`. `domain:cli` rather than `domain:skills` — the defect is the
command's exit contract, not the skills projection.

💡 **This reproduction is cleaner than the original report's.** #4775 was confounded: the exit 1
arrived alongside a declined TeamSpace prompt, so prompt-suppression and exit-code were tangled.
Here there is no prompt, no gate, no warning, a clean tree and `current == target`. A pure no-op
still exits 1. Worth saying so in triage — it isolates the exit-code half cleanly.

**Body** — post verbatim after approval:

---

# Bug: `upgrade --yes` exits 1 on a successful no-op

## Summary

`spec-kitty upgrade --yes` returns exit code 1 on a run that does nothing and reports success. This was reported as #4775 and closed as completed on 2026-09-20 by `cdde1cb51` *("upgrade --yes is fully non-interactive and exits honestly")*. On a newer build the prompt half is fixed — no prompt appears — but the exit code is still 1 where the command's own final line is `Project is already up to date!`. Filing fresh rather than commenting because #4775 is closed.

This reproduction is **cleaner than the original**. #4775's evidence was confounded: exit 1 arrived alongside a declined TeamSpace mission-state prompt, so prompt suppression and exit status were entangled. Here there is no prompt, no gate, no warning, a clean working tree, and `current == target`. A pure no-op exits 1 with nothing to decline.

## Build tested

- `spec-kitty-cli 4.0.0rc5 (main build, SHA d57619a90)` — note `4.0.0rc5` is an in-development version string; the SHA is the build identifier.
- **Persistence, not recurrence**: `d57619a90` is 35 commits ahead of the `v4.0.0rc4` tag and contains `cdde1cb51`, the commit carrying the fix for #4775.

## Reproduction

### Prerequisites

- A project already fully upgraded, so the run has nothing to do
- A clean git working tree, so the "changes left uncommitted" warning does not fire
- No mission-state blockers, so no TeamSpace gate renders (`doctor mission-state --audit` reports 0 blockers)

### Steps

```bash
git status --short          # confirm clean
spec-kitty upgrade --yes </dev/null; echo "EXIT=$?"
```

### Expected Behavior

A run that reports `Project is already up to date!` exits 0. `--yes` is documented as *"Non-interactive confirmation; alias for --force (FR-017)"*, and there is nothing to confirm.

### Actual Behavior

```text
Current version: 4.0.0rc5
Target version:  4.0.0rc5

Project is already up to date!
```

with:

```text
EXIT=1
```

That is the entire output. No prompt, no gate, no warnings, no errors, no diagnostics — a success message and a failure exit code.

Reproduced on three consecutive runs. Also observed exiting 1 on the same build when the tree was dirty and when `current != target`, so the exit code does not appear to depend on either.

## Root Cause

Not traced to a line. `cdde1cb51` addressed the prompt — confirmed fixed, no prompt appears on this build — but the command's exit status still does not reflect the upgrade's own outcome. Since there is no optional remediation to decline in this scenario, the mechanism must differ from the one described in #4775.

## Workaround Applied

Convergence is confirmed by other means and the exit code is ignored: `pending_migrations: []` from `upgrade --dry-run --json`, and `doctor tool-surfaces` exiting 0 with zero findings. Any automation gating on `upgrade`'s exit status would treat every successful run as a failure.

## Environment

- OS: Windows 11 Pro 26200
- Python: 3.13.7
- spec-kitty-cli: 4.0.0rc5 (main build, SHA `d57619a90`), repo `spec-kitty/spec-kitty`
- Install method: `uv tool install` from git, pinned to the full commit SHA
- Project: `.kittify` schema_version 3, 125 missions, 0 mission-state blockers

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 5), 2026-09-22.
**Submission approved by**: PENDING — copy not yet approved for posting.
**Local tracking**: kentonium3/kg-automation#992.

---

# Action 3 — FILE NEW ISSUE (persistence against closed #4777)

**Repo**: `spec-kitty/spec-kitty`
**References closed issue**: **#4777** — *"Bug: Windows `upgrade --dry-run` permanently reports 184 phantom repairs after convergence"*
**Local tracking**: kentonium3/kg-automation#994
**Copy approved**: ❌ **NOT YET** — drafted 2026-09-22.
**Title**:

```text
Bug: Windows `upgrade --dry-run` still reports 184 phantom repairs after convergence (persists after #4777 was closed)
```

**Suggested labels**: `from:qa`, `type:bug`, `priority:P3`, `domain:skills`

Mirrors #4777's own `priority:P3` and `domain:skills`.

💡 **This is the first clean test of #4777.** It could not be verified on the released rc4 at all,
because the Action 1 crash prevented the project from ever converging — and "after convergence"
is the whole premise. On `d57619a90` the upgrade converges, so the premise finally holds. The
count is **184**, the same number as the original report.

**Body** — post verbatim after approval:

---

# Bug: Windows `upgrade --dry-run` still reports 184 phantom repairs after convergence

## Summary

`spec-kitty upgrade --dry-run` reports `Would repair 184 supporting surface paths` on a fully converged project, identically on every run, while `spec-kitty doctor tool-surfaces` exits 0 with zero missing and zero stale findings. This was reported as #4777 and closed as completed on 2026-09-20 by `92a200070`, whose body states the intended outcome as *"a single upgrade converges (command + doctrine skills) on Windows with no phantom dry-run repairs"*. The single-upgrade convergence half is confirmed fixed. The phantom count is not.

The count is **184** — the same figure as the original report.

## Build tested

- `spec-kitty-cli 4.0.0rc5 (main build, SHA d57619a90)` — note `4.0.0rc5` is an in-development version string; the SHA is the build identifier.
- **Persistence, not recurrence**: `d57619a90` is 35 commits ahead of the `v4.0.0rc4` tag and contains `92a200070`, the commit carrying the fix for #4777.

Worth noting this is the **first clean test** of the issue. It could not be evaluated on the released 4.0.0rc4 (`5309c4107`) at all, because a Windows crash in `upgrade` prevented the project from ever converging — and "after convergence" is the issue's premise. On `d57619a90` the upgrade converges in one run, so the premise finally holds.

## Reproduction

### Prerequisites

- Windows (observed on Windows 11 Pro 26200)
- A project converged on this build: `spec-kitty upgrade --yes` run to completion, `doctor tool-surfaces` clean

### Steps

```bash
spec-kitty upgrade --yes                       # converges in one run
spec-kitty doctor tool-surfaces; echo "exit=$?"
spec-kitty upgrade --dry-run --json | python -c "import json,sys; print(json.load(sys.stdin)['rendered_human'])"
spec-kitty upgrade --dry-run --json | python -c "import json,sys; print(json.load(sys.stdin)['rendered_human'])"
```

### Expected Behavior

On a converged project the dry-run reports no outstanding repairs, consistent with the surface auditor.

### Actual Behavior

```text
doctor tool-surfaces  ->  exit=0, 0 missing findings, 0 stale findings

dry-run: 'Would repair 184 supporting surface paths (including 0 manifests). Would preserve 19 paths requiring separate consent.'
dry-run: 'Would repair 184 supporting surface paths (including 0 manifests). Would preserve 19 paths requiring separate consent.'
```

Byte-identical across runs. The two surfaces disagree: the auditor reports a clean project, the dry-run reports 184 outstanding repairs, and applying an upgrade does not reduce the count.

## Root Cause

Not traced to a line, and the original suspicion may now be wrong. We previously attributed the count to `chmod` effects that cannot converge because `os.chmod` cannot represent a POSIX mode on Windows — 184 was exactly the `chmod` count in the plan (`{'chmod': 184, 'create': 340, 'update': 5}`). `92a200070` introduced a host-aware, directory-scoped relaxation intended to address precisely that, and the convergence half of the fix demonstrably works. So either the relaxation does not reach the dry-run planning path, or the residual 184 has a different cause that happens to match the old figure.

The `(including 0 manifests)` detail may help narrow it: the manifest repairs do converge; only the unnamed supporting paths persist.

## Workaround Applied

`doctor tool-surfaces` is used as the convergence check instead of the dry-run count. The dry-run cannot be used to answer "does this project need an upgrade?", by a human or by automation.

## Environment

- OS: Windows 11 Pro 26200
- Python: 3.13.7
- spec-kitty-cli: 4.0.0rc5 (main build, SHA `d57619a90`), repo `spec-kitty/spec-kitty`
- Install method: `uv tool install` from git, pinned to the full commit SHA
- Project: `.kittify` schema_version 3, 125 missions

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Opus 5), 2026-09-22.
**Submission approved by**: PENDING — copy not yet approved for posting.
**Local tracking**: kentonium3/kg-automation#994.

---

# Action 4 — FILE NEW ISSUE (persistence against closed #4779)

**Repo**: `spec-kitty/spec-kitty`
**References closed issue**: **#4779** — *"Bug: mission-state repair writes its manifest and quarantined rows into a gitignored path"*
**Local tracking**: kentonium3/kg-automation#996
**Copy approved**: ❌ **NOT YET** — drafted 2026-09-21, re-verified on `d57619a90` 2026-09-22.
**Title**:

```text
Bug: mission-state manifest and quarantine still written to a gitignored path (persists after #4779 was closed)
```

**Suggested labels**: `from:qa`, `type:bug`, `priority:P2`, `domain:status`

Mirrors #4779's own labels.

**Body** — post verbatim after approval. Re-verified on `d57619a90`: a fresh
`doctor mission-state --fix` wrote `fa5b161919b7d38b.json` to the same ignored path, so update
the Build tested section to name that build if you prefer the newest evidence.

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

## Workaround Applied

The whole `.kittify/migrations/` tree is copied to an out-of-tree backup directory immediately
after every repair run, alongside a pre-repair git tag, and a restore procedure documents both.
That is the only reason the quarantined rows from an earlier run on this project still exist in
a form independent of the working tree.

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

# Action 5 — FILE NEW ISSUE (verification report)

**Repo**: `spec-kitty/spec-kitty`
**Local tracking**: kentonium3/kg-automation#1006
**Copy approved**: ⚠️ Kent approved an earlier version on 2026-09-21; the body has changed since
(rc5 dev-build results added). Re-read before posting.
**Title**:

```text
Windows verification report: released 4.0.0rc4 (5309c4107) and main d57619a90
```

**Suggested labels**: `from:qa`, `domain:skills`

No `type:` label suggested — this is a verification report, not a defect. `type:finding` is
described as a *"squad or review finding, triaged"*, which this is not. `priority:` omitted; a
report should not compete for fix priority.

💡 **Consider splitting it.** The four confirmations could each go as a short comment on the
issue they confirm — #4776, #4778, #4780, #4782 — which lands each one where its author will
see it. A single report reads better as a release verdict. Your call; the sections are separable.

**Body** — post verbatim:

---
# Windows verification report: released 4.0.0rc4 (`5309c4107`)

## Summary

Windows verification of the released 4.0.0rc4. Three previously-reported defects are confirmed fixed on Windows, one new Windows-blocking defect was found in the upgrade path, and three earlier reports cannot be verified because that new defect blocks the command they describe. Reporting the confirmations explicitly as well as the regression: the #4703 family suggests Windows is not covered by CI, so positive Windows results may be information you do not otherwise have.

Tested build `5309c4107` (tag `v4.0.0rc4`, PyPI wheel), against the prior candidate build `619bd1137` — 174 commits behind, `behind_by: 0`. Both report `spec-kitty-cli version 4.0.0rc4`; only the build distinguishes them.

## Reproduction

This is a verification report rather than a defect report, so "reproduction" here means the
commands that produced each verdict below, on the build named above.

### Prerequisites

- Windows, `uv tool install --force "spec-kitty-cli==4.0.0rc4"`
- A long-lived project with legacy missions (`01KS*`/`01KT*`-era `change_mode: regular`), a
  `GEMINI.md` orientation block stale since 3.2.6, and mission-state blockers present

### Steps

```bash
spec-kitty --version
spec-kitty doctor mission-state --audit          # baseline
spec-kitty doctor mission-state --fix            # exercises #4778 / #4780
spec-kitty doctor mission-state --audit          # end state
grep -m1 -o 'Spec Kitty v[0-9a-zrc.]*' GEMINI.md
spec-kitty doctor tool-surfaces --tool gemini --fix   # exercises #4782
grep -m1 -o 'Spec Kitty v[0-9a-zrc.]*' GEMINI.md
spec-kitty upgrade --yes                         # crashes; see the blocker below
```

### Expected Behavior

The three fixes referenced above hold on Windows, and `upgrade` completes.

### Actual Behavior

The three fixes hold; `upgrade` does not complete. Per-verdict output is given in the sections
that follow.

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

# DO NOT FILE — already upstream and not contested

| Ours | Upstream | State | Verdict | Why no action |
|---|---|---|---|---|
| #993 | spec-kitty#4776 | CLOSED completed | ✅ **verified fixed** on `d57619a90` | Fix confirmed working |
| #995 | spec-kitty#4778 | CLOSED completed | ✅ **verified fixed** on `5309c4107` | Fix confirmed working |
| #997 | spec-kitty#4780 | CLOSED completed | ✅ **verified fixed** on `5309c4107` | Fix confirmed working |
| #999 | spec-kitty#4782 | CLOSED completed | ✅ **verified fixed** on both builds | Fix confirmed working |
| #1000 | spec-kitty#4783, epic #4793, #3154 | **OPEN** | ❌ still present (328 occurrences) | Still open upstream — no closure to contest, nothing new to add |

#4783 stays a comment-shaped case only if something new emerges. As an open issue it needs no
persistence filing: the defect is known and unfixed, and epic #4793 already tracks the rename.

# Verification status at a glance

```text
FIXED, verified      #4776  #4778  #4780  #4782        (4 of our reports)
PERSISTS, filing     #4775  #4777  #4779               (Actions 2, 3, 4)
NEW, filing          #1005 utime                        (Action 1)
OPEN upstream        #4783  naming                      (no action)
```

Every "fixed" verdict was confirmed two ways before being claimed: the closing commit verified
as an ancestor of the tested build (reverse `compare` giving `ahead_by=0`, plus direct membership
in the commit range), and the behaviour re-tested directly. "Closed upstream" and "fixed in the
build we run" are different claims and were checked separately.

# Corrections carried forward

**Our #993 root cause was wrong.** We attributed the three-run convergence to the
`_recheck_command_completion` `installed_at` race that the #4703 docstring scoped out.
`92a200070` found the real cause — a Windows POSIX-mode assertion at the same gate — and fixed
the `installed_at` hash separately as a second defect. The symptom report was sound; the
diagnosis was not.

**Our #994 root cause may also be wrong.** We attributed the phantom count to unconvergeable
`chmod` effects. `92a200070` added exactly the host-aware relaxation that theory predicts, the
convergence half works, and the count is unchanged at 184. Action 3 says so rather than
re-asserting the original theory.

Both are recorded because a mechanism that fits the evidence is not necessarily the mechanism.

# Related

- Full build-pinned register: [`spec-kitty-4.0.0rc4-upgrade-findings.md`](<./spec-kitty-4.0.0rc4-upgrade-findings.md>)
- Reporting workflow and build-ID convention: [`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>)
- Session resume context: [`handoff/2026-09-21-spec-kitty-4.0.0rc4-upgrade.md`](<../handoff/2026-09-21-spec-kitty-4.0.0rc4-upgrade.md>)
