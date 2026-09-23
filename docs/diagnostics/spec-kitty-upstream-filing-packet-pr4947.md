---
title: 'Upstream filing packet: spec-kitty PR #4947 head — Windows verification of #4923 / #4927 / #4925'
doc_type: note
audience: agents_and_humans
status: active
last_updated: '2026-09-23'
approved: '2026-09-23'
---

# Upstream filing packet — PR #4947 head (`1ee5f2d32`)

**For the spec-kitty QA bot.** Two outbound posts, both **comments** on existing upstream
artifacts — no new issues. **Copy approved by Kent on 2026-09-23** (kentonium3/kg-automation#1011);
post the bodies below verbatim, filling only the `Submission approved by` date if it is blank.

| Action | Target | What it is | Status |
|---|---|---|---|
| **A** | [spec-kitty/spec-kitty PR #4947](https://github.com/spec-kitty/spec-kitty/pull/4947) | Windows verification of the PR head: #4923 **confirmed fixed**, #4927 **not fixed** with the plan-JSON evidence showing why | ✅ approved — **post** |
| **B** | [spec-kitty/spec-kitty#4925](https://github.com/spec-kitty/spec-kitty/issues/4925) | The re-verification the maintainer asked for, plus the trace of the exit code they said could not be traced on Linux | ✅ approved — **post** |

Evidence and full trace: [`spec-kitty-4.0.0rc4-upgrade-findings.md` § PR #4947 head](<./spec-kitty-4.0.0rc4-upgrade-findings.md#pr-4947-head-1ee5f2d32--verification-2026-09-23>).
Local tracking: kentonium3/kg-automation#1011. Predecessor packet (all filed 2026-09-22):
[`spec-kitty-upstream-filing-packet-rc4.md`](<./spec-kitty-upstream-filing-packet-rc4.md>).

## Why this artifact exists

Same split as the rc4 packet: discovery and analysis under Kent's **personal hat** (tracked as
`kentonium3/kg-automation` issues), filing under his **spec-kitty work hat** (which holds the
`from:qa` label and can comment on the PR as the QA reporter). This packet is the handoff.

## Build under test

| Label | Build | Notes |
|---|---|---|
| **PR #4947 head** | `1ee5f2d32` | Branch `fix/windows-upgrade-mode-fidelity`, fetchable from the main repo as `refs/pull/4947/head`. **Unmerged**, CI green, conflicts with `main`. |
| baseline | `d57619a90` | rc5 dev build the PR head was compared against. The PR head is a strict superset: GitHub compare says 9 ahead, 0 behind. |

Both report `4.0.0rc5`. Install:

```bash
uv tool install --force "git+https://github.com/spec-kitty/spec-kitty.git@1ee5f2d326ae426f139f9bf778cba74e9653c0f3"
```

## Ledger — what is already upstream, and what not to file

| Ours | Upstream | State 2026-09-23 | This packet |
|---|---|---|---|
| #1005 (F15) | #4923 | OPEN, P0, in PR #4947 | **Action A** confirms fixed |
| #994 (F8) | #4927 | OPEN, P3, in PR #4947 | **Action A** reports not fixed, with root-cause evidence |
| #992 (F6) | #4925 | OPEN, P2, deferred by maintainer pending a Windows re-verify | **Action B** supplies it |
| #996 (F10) | #4928 | OPEN, routed to the `silent-destructive-write-hardening` mission | no action — out of PR scope, unchanged |
| #1000 (F14) | #4783 | OPEN | no action — unchanged (328 occurrences) |
| #1006 | #4930 | OPEN umbrella | no action — this arc's results reach it through #4923/#4927/#4925 |
| #993, #995, #997, #999 | #4776, #4778, #4780, #4782 | CLOSED, verified fixed | no action — regressions re-checked on `1ee5f2d32`, still fixed |
| #1012, #1013 | — | local only | **do not file** — baseline anomalies (mission-state `PAYLOAD_INVALID`; doctrine-skill hash drift on a clean tree) recorded 2026-09-23 and not yet root-caused; identical on both builds, so unrelated to the PR |

**Do not open new issues for #4927 or #4925.** Both are open; persistence goes as a comment
(Actions A and B). The rc4 packet's rule — new issue only when the upstream one is *closed* —
does not apply here.

## Template conformance

Both bodies follow the
[upstream comment template](<./spec-kitty-upstream-comment-template.md>): one-line relationship
statement, pinned build with persistence framing, Reproduction (Prerequisites / Steps / Expected /
Actual with verbatim output), Environment, attribution + approval footer. No priority, no labels
requested, no proposed fix, no internal mission/WP references beyond the Local-tracking line.

Deviations, noted rather than silently applied:

- **Action A has two findings in one comment** (#4923 fixed, #4927 not) because the PR is the
  single artifact that claims both. The #4923 part is short and precedes the #4927 reproduction.
  If the bot prefers one finding per post, split at the `## #4927 — still reproduces` heading and
  post the second half on spec-kitty#4927 instead.
- **Action A names the emitting module** (`runtime/asset_preparation.py`) and the counting line
  in `upgrade.py`. That is trace evidence for *where the 184 come from*, not a remediation; the
  template's "no suggested fix" rule is respected — nothing says what to change.
- The comment template's SHA-lookup snippet assumes a pipx venv; this box uses `uv tool`. The
  SHA was read from `spec_kitty_cli-*.dist-info/direct_url.json` under `uv tool dir`. Same
  identifier, different path.

---

## Action A — comment on PR spec-kitty/spec-kitty#4947

**Local tracking**: kentonium3/kg-automation#1011 (covers #1005 and #994)
**Copy approved**: ✅ Kent, 2026-09-23.
**Target**: PR #4947 conversation (not a review; a plain comment).

**Body** — post verbatim:

---

Windows verification of this PR's head, as requested in #4930's triage: #4923 is fixed on this box; #4927 is not, and the dry-run count is unchanged.

## Build tested

- `spec-kitty-cli 4.0.0rc5 (PR #4947 head, SHA 1ee5f2d32)` — installed by full SHA via `refs/pull/4947/head`; `4.0.0rc5` is the in-development string, the SHA is the identifier.
- Persistence check for #4927: newer build than the `d57619a90` cited in #4927, pulled 2026-09-23, and a strict superset of it (GitHub compare: 9 ahead, 0 behind), so the delta is this PR plus 6 unrelated `main` commits.

## #4923 — fixed

`skills/installer.py` on this build contains no direct `follow_symlinks=False` apply call; the five former sites call `chmod_no_follow` / `utime_no_follow`. Three `upgrade --yes` runs and one `upgrade --yes --json` run completed with no `NotImplementedError`. Caveat: the crash was dormant on `d57619a90` too (reachability, not the call, differed between rc4 released and rc5 dev), so this is a static confirmation plus an absence, not a fire-then-not-fire.

## #4927 — still reproduces

### Prerequisites

- Build above; Windows 11 Pro 26200; project `kg-automation` (125 missions), git-clean, `upgrade` converged (three consecutive no-op runs).

### Steps

```bash
spec-kitty upgrade --dry-run </dev/null
spec-kitty upgrade --dry-run --plan-json </dev/null > plan.json
```

### Expected Behavior

Per the PR description, a converged Windows project reports zero supporting-surface repairs.

### Actual Behavior

```text
Would repair 184 supporting surface paths (including 0 manifests). Would
preserve 19 paths requiring separate consent.
Project is already up to date!
```

Byte-identical to the same command on `d57619a90`. The plan's 184 `effects` are all `action: "chmod"`, `owner: "global_assets"`, `phase: "global_bootstrap"`, `reason: "Refresh canonical global asset"`, `root_id` `global_skills` (144) / `runtime_bootstrap` (40); `before`/`after` differ only in `mode` — 183 are **directories** (0o777 → 0o755) and 1 is a file (`cache/version.lock`, 0o666 → 0o644). Paths are `~/.agents/skills/**`, `~/.claude/skills/**`, `%LOCALAPPDATA%/spec-kitty/**` — none under the project root. The summary line counts exactly these effects (`upgrade.py`, `len(prepare_upgrade_repairs(...).effects)`), and they originate in `runtime/asset_preparation.py`, which this PR does not change. So on this project the 184 is not one chmod per managed project file; it is the global-asset bootstrap's per-directory mode comparison.

## Environment

- OS: Windows 11 Pro 10.0.26200
- Python: 3.13.7 (`uv tool` venv)
- spec-kitty-cli: 4.0.0rc5 (PR #4947 head, SHA 1ee5f2d32)
- `os.utime in os.supports_follow_symlinks` → False; `os.chmod` → False

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Fable 5.1), 2026-09-23.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), 2026-09-23.
**Local tracking**: kentonium3/kg-automation#1011.

---

## Action B — comment on spec-kitty/spec-kitty#4925

**Local tracking**: kentonium3/kg-automation#1011 (covers #992)
**Copy approved**: ✅ Kent, 2026-09-23.
**Target**: issue #4925, replying to the maintainer's deferral comment of 2026-09-22 (which asked: *"re-verify on Windows after #4923+#4927 land"*).

**Body** — post verbatim:

---

Re-verified on Windows against the #4923/#4927 PR head as requested: still exits 1, and the cause is now traced — it is the surface-drift error, which the text output never prints.

## Build tested

- `spec-kitty-cli 4.0.0rc5 (PR #4947 head, SHA 1ee5f2d32)` — `4.0.0rc5` is the in-development string; the SHA is the identifier.
- Persistence: newer build than the `d57619a90` in the original report, pulled 2026-09-23, strict superset of it (9 ahead, 0 behind).

## Reproduction against current `main`

### Prerequisites

- Build above; Windows 11; project git-clean and converged (three consecutive `upgrade --yes` no-op runs, no migrations pending).
- The project has 19 native agent-profile projections (`.claude/agents/*.md`, `.codex/agents/*.toml`, `.github/agents/*.agent.md`, seven profiles) that the plan lists as `consent_required` / preserved.

### Steps

```bash
spec-kitty upgrade --yes </dev/null; echo EXIT=$?
spec-kitty upgrade --yes --json </dev/null
```

### Expected Behavior

A no-op `--yes` run on an up-to-date project exits 0; or, if it is to fail, the text output states why.

### Actual Behavior

Text mode:

```text
Current version: 4.0.0rc5
Target version:  4.0.0rc5

Project is already up to date!
EXIT=1
```

JSON mode, same project, same build:

```json
"status": "failed", "success": false,
"errors": ["Unresolved tool-surface drift in 19 file(s); run 'spec-kitty doctor tool-surfaces' to review."],
"surface_repair": {"created": [], "repaired": [184 paths], "drifted_overwritten": [], "drifted_reported": [19 paths], "skipped": []}
```

`doctor tool-surfaces` lists the same 19 as `Native agent profile drifted from manifest hash` and exits 0.

## Response to suggested direction

Your comment concluded `surface_drift_failed` could not be the source because our report showed no errors. The `--json` run shows that `_combined_errors()` does include the surface-drift failure and the exit code follows it, while `_display_no_migrations_results()` renders `warnings` and `activation_errors` only — the surface-drift error is not in `activation_errors`, so text mode never shows it. That also means this exit code does not depend on the #4927 chmod effects: on this build #4927 still reports 184 and #4925 still exits 1, but the `errors` array names only the drift.

## Environment

- OS: Windows 11 Pro 10.0.26200
- Python: 3.13.7 (`uv tool` venv)
- spec-kitty-cli: 4.0.0rc5 (PR #4947 head, SHA 1ee5f2d32)

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & Claude Code (Claude Fable 5.1), 2026-09-23.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), 2026-09-23.
**Local tracking**: kentonium3/kg-automation#1011.

---

## After posting

1. Record each comment URL in kentonium3/kg-automation#1011 and add `upstream-filed` to #1011.
2. Update the routing map in
   [`spec-kitty-4.0.0rc4-upgrade-findings.md`](<./spec-kitty-4.0.0rc4-upgrade-findings.md>)
   (rows #992, #994, #1005) from "in packet" to the posted URLs.
3. Leave `1ee5f2d32` installed on this box (Kent's decision, 2026-09-23) — it carries the #4923
   fix and nothing regressed. Re-test on `main` HEAD once PR #4947 merges; that build is what
   ships as rc5.
