---
title: 'Upstream filing packet: spec-kitty baseline anomalies — dry-run PAYLOAD_INVALID (#1012) and CRLF skill corruption (#1013)'
doc_type: note
audience: agents_and_humans
status: active
last_updated: '2026-09-23'
approved: '2026-09-23'
---

# Upstream filing packet — baseline anomalies #1012 and #1013

**For the spec-kitty QA bot.** Two **new issues** on `spec-kitty/spec-kitty`. **Copy approved by Kent on
2026-09-23** with priorities set; file the bodies below verbatim (see the one marked insertion under each).

| Action | Ours | Type / labels | Priority | What it is | Status |
|---|---|---|---|---|---|
| **C** | [#1013](https://github.com/kentonium3/kg-automation/issues/1013) | `--type Bug` · `from:qa` · `domain:skills` | **`priority:P0`** | CRLF skill sources → installer prepends a second bogus frontmatter to all 275 `SKILL.md`; doctor reports drift, `upgrade`/`--fix` cannot converge | ✅ approved — **file** |
| **D** | [#1012](https://github.com/kentonium3/kg-automation/issues/1012) | `--type Bug` · `from:qa` · `domain:status` | **`priority:P3`** | `--teamspace-dry-run` renders `PAYLOAD_INVALID` rows with no detail; 9.1.6 transition rules reject the CLI's own 2026-03 history with no repair path | ✅ approved — **file** |

File C before D — it is the P0 and the one with a Windows-critical reproduction. Neither is a duplicate: the
2026-09-23 sweep of upstream issues #4888–#4987 found nothing on frontmatter doubling, CRLF sources, or
`PAYLOAD_INVALID` rendering. Nearest neighbours, to cross-reference rather than merge: **#4782** (previous
`doctor tool-surfaces` check-vs-fix mismatch — same shape as C), **#4780** (per-mission detail for
audit-blocker rows — D is the same omission on the payload-error record shape), **#4897 / #4919**
(mission-state fold defects — adjacent to D, different rows).

Root-cause evidence: the 2026-09-23 comments on #1012 and #1013, and the register
[`spec-kitty-4.0.0rc4-upgrade-findings.md`](<./spec-kitty-4.0.0rc4-upgrade-findings.md>) § "Unchanged" /
"Observation". Predecessor packets: [rc4](<./spec-kitty-upstream-filing-packet-rc4.md>),
[PR #4947](<./spec-kitty-upstream-filing-packet-pr4947.md>).

## Filing mechanics (per the 2026-09-23 runbook change)

```bash
gh issue create --repo spec-kitty/spec-kitty --title "<title below>" --body-file <body> \
  --type Bug --label from:qa --label domain:skills --label priority:P0     # Action C
gh issue create --repo spec-kitty/spec-kitty --title "<title below>" --body-file <body> \
  --type Bug --label from:qa --label domain:status --label priority:P3     # Action D
```

`--type Bug` is the native issue type; do **not** apply a `type:bug` label (it still exists and looks right
until a maintainer strips it). Priority labels were set by Kent: P0 for C, P3 for D.

## Build under test

| Label | Build | Notes |
|---|---|---|
| rc5 dev | `d57619a90` | Where both were first observed (2026-09-23 baseline, before any install that day). |
| PR #4947 head | `1ee5f2d32` | Byte-identical reproduction. Currently installed. |

`spec-kitty-events 9.1.6` on both (published 2026-09-01). Both report `4.0.0rc5`; the SHA is the identifier.

## Template conformance

Both bodies follow the [external bug-report template](<./spec-kitty-bug-report-external-template.md>):
`# Bug:` title, Summary, Reproduction (Prerequisites / Steps / Expected / Actual), Root Cause, Workaround
Applied, Environment, attribution + approval footer. No frontmatter, priority, status, suggested fix, or
internal mission/WP references.

Deviations, noted rather than silently applied:

- **`## Workaround Applied` was added after approval**, in both bodies, marked ⚠ below. Kent's direction of
  2026-09-23 — *"do what a normal user would do; nothing special to compensate for conditions the install
  needs to detect and manage on its own"* — is that section's content, so it is recorded as approved by
  that direction. Strike it if verbatim-as-first-approved is preferred; nothing else changed.
- **Root Cause names file:line sites** in both. That is trace evidence (where the two renderings diverge;
  where the early return is), not a remediation — the "no suggested fix" rule is respected.
- C's reproduction assumes a CRLF source. On Windows that is the stock outcome of `uv tool install` from
  git with Git for Windows' default `core.autocrlf=true`; on POSIX it needs a CRLF copy of the source. The
  body says so.

## Ledger — do not file

| Ours | Upstream | Why not |
|---|---|---|
| #992 → #4925 | comment posted 2026-09-23 | The 19 CRLF agent-profile drifts are the `drifted_reported` set behind the local exit 1. That link is stated in C's local comment, not re-filed; the maintainer already has the trace on #4925. |
| #994 → #4927, #1005 → #4923 | PR #4947 comment posted 2026-09-23 | Unrelated to these two. |
| #996 → #4928 | open | Unrelated. |

---

## Action C — new issue (from #1013) — `priority:P0`

**Local tracking**: kentonium3/kg-automation#1013
**Copy approved**: ✅ Kent, 2026-09-23, P0.
**Title**:

```text
Bug: on a CRLF source checkout, skill install prepends a second bogus frontmatter block to every SKILL.md — doctor reports 275 drifts, upgrade/--fix cannot repair them
```

**Body** — file verbatim (⚠ `## Workaround Applied` added after approval, see conformance note):

---

# Bug: CRLF skill sources make the installer prepend a second, bogus frontmatter block to every `SKILL.md`; `doctor tool-surfaces` reports the drift but `upgrade`/`--fix` cannot repair it

## Summary

When the packaged skill sources have CRLF line endings — which is what `uv tool install` from git produces on a Windows box with `core.autocrlf=true` — `ensure_skill_frontmatter()` fails to recognise the existing frontmatter (`^---\n` never matches `---\r\n`) and prepends a new block whose description is the old frontmatter's `name:` line. All 275 installed `SKILL.md` files on this project start with two frontmatter blocks, and every agent that lists skills shows `description: "name: <skill>"`. The verifier renders the expected content through `read_text()` (universal newlines), so it computes the correct hash and reports every file as `Managed doctrine skill drifted from manifest hash`; the installer's pre-check renders it through `read_bytes().decode()`, sees the corrupted bytes as correct, and `upgrade` / `doctor tool-surfaces --fix` change nothing. The project cannot converge.

## Build tested

- `spec-kitty-cli 4.0.0rc5 (main build, SHA d57619a90)`; identical on PR #4947 head `1ee5f2d32`. `4.0.0rc5` is the in-development string; the SHA is the identifier.

## Reproduction

### Prerequisites

- Windows, `core.autocrlf=true` (Git for Windows system default), install from git so the venv's `charter/offering/skills/**/SKILL.md` come out CRLF. Any CRLF source copy should do on any OS.

### Steps

```bash
uv tool install --force "git+https://github.com/spec-kitty/spec-kitty.git@d57619a900277ef388608dca4390c38758a06db0"
spec-kitty upgrade --yes </dev/null            # or: spec-kitty doctor tool-surfaces --fix
head -c 120 .claude/skills/spk-team-sync/SKILL.md | od -c | head
spec-kitty doctor tool-surfaces </dev/null | grep -c 'Managed doctrine skill drifted'
spec-kitty doctor tool-surfaces --fix </dev/null; spec-kitty doctor tool-surfaces </dev/null | grep -c 'Managed doctrine skill drifted'
```

### Expected Behavior

Existing frontmatter is preserved (the docstring says "Existing frontmatter is preserved byte-for-byte"), the installed file hashes to the verifier's expected rendering, and `--fix` converges the doctor to zero drift.

### Actual Behavior

```text
---\nname: spk-team-sync\ndescription: "name: spk-team-sync"\n---\n---\r\nname: spk-team-sync\r\ndescription: "Operate Spec Kitty tracker sync …
275
275        # after --fix: unchanged
```

Source `SKILL.md` in the venv: 1 701 bytes CRLF. Installed: 1 764 bytes, mixed endings, doubled frontmatter, hash equal to the manifest entry (so the manifest is "correct" about corrupted content). Verifier expectation: 1 667 bytes. In-process: `ensure_skill_frontmatter(src.read_bytes().decode())` == disk; `ensure_skill_frontmatter(src.read_text())` != disk. 130 non-`SKILL.md` entries (raw-hashed on both sides) match; all 275 `SKILL.md` entries drift.

## Root Cause

- `skills/command_renderer.py:59` — `_RE_LEADING_FRONTMATTER = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)` is `\n`-only.
- `skills/installer.py:732-734` decodes `read_bytes()` (keeps `\r\n`) before `ensure_skill_frontmatter()`; `skills/verifier.py::_expected_content_hash` uses `read_text()` (normalises to `\n`). Same input, two renderings.
- `tool_surface/providers/managed_skills.py:478` replaces the manifest hash with the verifier's expected hash before probing, so the finding text "drifted from manifest hash" describes a comparison that is not made; and `installer.py:328-332` pre-checks with the installer rendering, so repair never fires.

## Workaround Applied

None, deliberately. Neither the venv nor the checkout was touched: no `core.autocrlf` override, no `.gitattributes` rule, no reinstall with git config scoped to the command. A user installing on a stock Git for Windows would hit exactly this, and the install needs to detect and handle a CRLF source itself rather than rely on the user knowing to compensate. The corrupted venv is kept as the reproduction.

## Environment

- OS: Windows 11 Pro 10.0.26200; Git for Windows with system-scope `core.autocrlf=true`
- Python: 3.13.7 (`uv tool` venv)
- spec-kitty-cli: 4.0.0rc5 (main build, SHA d57619a90)

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Fable 5.1), 2026-09-23.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), 2026-09-23.
**Local tracking**: kentonium3/kg-automation#1013.


---

## Action D — new issue (from #1012) — `priority:P3`

**Local tracking**: kentonium3/kg-automation#1012
**Copy approved**: ✅ Kent, 2026-09-23, P3.
**Title**:

```text
Bug: doctor mission-state --teamspace-dry-run renders PAYLOAD_INVALID rows with no detail, and the transition rules it enforces reject the CLI's own pre-9.1.6 history with no repair path
```

**Body** — file verbatim (⚠ `## Workaround Applied` added after approval, see conformance note):

---

# Bug: `--teamspace-dry-run` renders `PAYLOAD_INVALID` rows with no detail, and enforces transition rules the CLI's own older history cannot satisfy

## Summary

Once a project clears its audit blockers, `spec-kitty doctor mission-state --teamspace-dry-run` validates every synthesised envelope against `spec-kitty-events` 9.1.6 and fails 15 `WPStatusChanged` rows on a 125-mission project. Two problems surface together: the text output prints each failure as `<slug> (): PAYLOAD_INVALID — ` (no reason, no location), and the failing rows are transitions the CLI itself wrote in 2026-03 (`in_progress -> planned` with `force=false`), which no current command can repair. The dry-run therefore cannot be made to pass on this project. These rows were previously masked: the dry-run returns early on audit blockers (fixed by #4778), so the payload class only became visible after that fix.

## Build tested

- `spec-kitty-cli 4.0.0rc5 (main build, SHA d57619a90)`, reproduced identically on PR #4947 head `1ee5f2d32`; `spec-kitty-events 9.1.6` on both. `4.0.0rc5` is the in-development string; the SHA is the identifier.

## Reproduction

### Prerequisites

- A project with WP status history written before `spec-kitty-events` 9.1.6 that contains review-rejection rollbacks recorded with `force: false` (this project has 15 across 10 missions, oldest 2026-03-28).
- `doctor mission-state --audit` reporting `teamspace_blockers: 0` (otherwise the dry-run exits before payload validation).

### Steps

```bash
spec-kitty doctor mission-state --teamspace-dry-run </dev/null; echo EXIT=$?
spec-kitty doctor mission-state --teamspace-dry-run --json </dev/null
```

### Expected Behavior

Each failing row names its artifact, line and violation, matching the per-mission detail #4780 introduced for audit blockers; and a project whose history was produced entirely by spec-kitty commands has a documented path to a passing dry-run.

### Actual Behavior

Text mode:

```text
  - 004-whatsapp-channel (): PAYLOAD_INVALID — 
  - 026-vault-path-registry-and-folder-renumber (): PAYLOAD_INVALID — 
  … 15 rows, every reason and location empty
TeamSpace dry-run failed (15 validation issues).
EXIT=1
```

JSON mode, same run — the detail exists but is never rendered:

```json
{"error": "PAYLOAD_INVALID", "event_id": "01KMTXSPE8BKQYTEQRCCY7GW4S", "mission_slug": "004-whatsapp-channel",
 "model_violations": [{"field": "transition", "violation_type": "transition_rule",
   "message": "review-rejection rollback in_progress -> planned requires force=True"}]}
```

Violation tally: `review-rejection rollback … requires force=True` ×13 (`in_progress`/`in_review`/`approved` → `planned`), `… requires review_ref` ×2. The `004-whatsapp-channel` row was written by `move-task` on 2026-03-28 with `force: false` and a `review_ref`; `--fix` (run 2026-09-19) leaves `force` untouched, and nothing under `migration/` references `transition_rule` or a `force` backfill.

## Root Cause

- `_format_dry_run_error()` reads `message`, `artifact_path`, `line_number`; `PAYLOAD_INVALID` records carry `event_id` + `model_violations` instead, and the location lives in the parallel `row_mappings`. The audit-blocker record shape was fixed for #4780; this record shape was not.
- `teamspace_dry_run()` returns before payload validation whenever `_teamspace_audit_blockers()` is non-empty, so the two error classes are never reported together.
- `spec_kitty_events.status` applies the `force=True` / `review_ref` rules to historical rows with no version or date tolerance, and no migration stamps `force` onto legacy review-rejection rollbacks.

## Workaround Applied

None. Nothing in the local workflow depends on this dry-run except a Team Kitty import/sync, which this project does not perform. The rows are left as written so the condition stays reproducible.

## Environment

- OS: Windows 11 Pro 10.0.26200 (not Windows-specific; the rows are data)
- Python: 3.13.7 (`uv tool` venv)
- spec-kitty-cli: 4.0.0rc5 (main build, SHA d57619a90); spec-kitty-events 9.1.6

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Fable 5.1), 2026-09-23.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), 2026-09-23.
**Local tracking**: kentonium3/kg-automation#1012.


---

## After filing

1. Record each new issue URL on #1013 / #1012 and add `upstream-filed` (the `P0-bug` / `P3-bug` local labels
   are already applied).
2. Add the two rows' URLs to the routing map in
   [`spec-kitty-4.0.0rc4-upgrade-findings.md`](<./spec-kitty-4.0.0rc4-upgrade-findings.md>).
3. Leave the box as is (Kent, 2026-09-23): corrupted venv, CRLF profiles, `1ee5f2d32` installed — all of
   it is the reproduction for the next round of testing.
