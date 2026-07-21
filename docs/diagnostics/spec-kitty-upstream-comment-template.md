---
title: Spec-Kitty Upstream Issue Comment Template
doc_type: reference
status: approved
audience: humans
last_updated: '2026-07-21'
version: v1.0
---

# Spec-Kitty Upstream Issue Comment Template

Slim template for **commenting on an EXISTING upstream issue** (`Priivacy-ai/spec-kitty`,
openai/codex, etc.) — as opposed to filing a *new* bug report (that is the
[external bug-report template](<./spec-kitty-bug-report-external-template.md>)). Use this
when we need to add to an issue that is already open: confirm the bug still reproduces,
supply a build identifier that the original report lacked, add fresh evidence, or respond to
a maintainer's request for next steps.

Like the external report template, this is the **source for the paste buffer** that goes
into the upstream tracker — draft it inside the internal `kentonium3/kg-automation` tracking
issue, get operator sign-off on the exact copy, then post. See
[`runbooks/spec-kitty-bug-reporting.md`](<../runbooks/spec-kitty-bug-reporting.md>) for the
dual-track model and the pre-posting approval gate.

## When to use this (vs. a new report)

| Situation | Use |
|---|---|
| A bug we haven't reported before | [external bug-report template](<./spec-kitty-bug-report-external-template.md>) (file a new issue) |
| An open upstream issue still reproduces on our build | **this template** — recurrence/persistence comment |
| The original report gave only a bare version (no build SHA) and a maintainer needs the exact build | **this template** — supply the pinned build |
| New evidence, a cleaner repro, or a trace to add to an open issue | **this template** — evidence comment |
| A maintainer asked for next steps (e.g. a red-first failing-test PR) | **this template** — response comment |

## Why this template exists (2026-07-21)

An upstream maintainer (Stijn, Priivacy-ai/spec-kitty) pushed back on a comment of ours that
referenced a bare `3.2.6`: *"there is no released 3.2.6 — 3.2.6 is the current in-development
version string, so a bare version number doesn't pin the build you hit."* A version string
alone does not identify the build when the CLI is built from `main` (which moves). Every
comment that makes or renews a defect claim **must** pin the build with a 9-char commit SHA
and state whether we are confirming recurrence on the *same* build or persistence on a
*newer* one. This template makes that non-negotiable.

## Non-negotiable: pin the build

Never reference a bare version number. State the exact build tested, using the
**Build-ID convention** from the reporting runbook (9-char short SHA):

- **Off-`main` build:** `spec-kitty-cli X.Y.Z (main build, SHA <9char>)` — e.g.
  `3.2.6 (main build, SHA 1cb51fb32)`. Note in prose that `X.Y.Z` may be an *in-development*
  string, so the SHA is the real identifier.
- **Released tag:** `spec-kitty-cli X.Y.Z (pinned tag SHA <9char>)`.

Get the SHA (git/`main` install):

```bash
python3 -c "import glob,json; f=glob.glob('$HOME/.local/pipx/venvs/spec-kitty-cli/lib/python*/site-packages/spec_kitty_cli-*.dist-info/direct_url.json')[0]; print(json.load(open(f))['vcs_info']['commit_id'][:9])"
```

Then say explicitly which of these the comment is:

- **Recurrence (same build)** — "still reproduces on the same build referenced above (`<SHA>`)."
- **Persistence (newer build)** — "still reproduces on a newer build (`<SHA>`), pulled `<date>`,
  which is ahead of the build in the original report."

If the issue you are commenting on gave only a bare version, open the comment by **supplying
the pinned build** the original report should have carried.

## What this template excludes (same discipline as the external report)

- No frontmatter (the tracker has its own metadata) and no internal frontmatter in the pasted comment
- No priority / status (their triage, their labels)
- No **Suggested Fix / Proposed Remediation** — drop it; the maintainer knows their codebase
- No internal issue / mission / work-package numbers, helper-script names, or memory references
  (the attribution footer's Local-tracking line is the only pointer back to our queue)

## What this template keeps

- A one-line statement of relationship to the issue (confirming / supplying build / adding evidence / responding)
- **Build tested** — pinned per the convention above, with recurrence-vs-persistence framing
- Reproduction **against current `main`** — Prerequisites / Steps / Expected / Actual, output verbatim
- Response to the maintainer's direction — only if the comment answers a specific request; cite the
  issue's own *Suggested direction* and any referenced directive (e.g. `DIRECTIVE_041`), and link the
  red-first PR once it exists
- Environment
- **Attribution + reviewer-approval footer** — same human-in-the-loop declaration as every upstream artifact

## Pre-posting approval (mandatory)

This is copy leaving `kentonium3/kg-automation`, so it is gated: the operator must approve the
**exact comment text** before it is posted upstream — approving the action ("post the comment")
is not approving the wording. Draft it in the internal tracking issue, show Kent, then post.
Never comment upstream on the agent's own initiative. (Internal kg-automation comments are exempt
from pre-review; this gate is specifically for the outbound upstream copy.)

---

## Template body (copy below this line into the upstream issue comment)

{One sentence naming what this comment is: e.g. "Confirming this still reproduces, and pinning the
build the original report was missing." Keep it to a line.}

## Build tested

- `spec-kitty-cli {X.Y.Z} (main build, SHA {9char})` — note: `{X.Y.Z}` is the in-development version
  string; the SHA is the build identifier.
- {Recurrence: "Same build referenced above." / Persistence: "Newer build than the original report;
  pulled {YYYY-MM-DD}, ahead of {prior SHA / bare version} cited earlier."}

## Reproduction against current `main`

### Prerequisites

- {Preconditions: build SHA above, project state, topology — e.g. single_branch, lane-worktree cwd}
- {Workflow position / entry point required to hit the bug}

### Steps

```bash
{exact commands to reproduce, driving the real entry point named in the issue}
```

### Expected Behavior

{What should happen per documentation, command name, or the issue's own stated expectation.}

### Actual Behavior

{What actually happens. Include command output verbatim.}

```text
{command output / error message}
```

## Response to suggested direction

<!--
Optional — include only when the comment answers a maintainer's request or the issue's
"Suggested direction". Acknowledge it by name, cite any referenced directive (e.g.
DIRECTIVE_041), and state concretely what we are doing. If the ask is a red-first failing-test
PR, describe the failing test (what entry point it drives, from what cwd/topology) and link the
PR once opened. Do NOT propose a fix to their internals here.
-->

## Environment

- OS: {e.g., macOS Darwin 25.5.0}
- Python: {e.g., 3.13.x}
- spec-kitty-cli: {X.Y.Z (main build, SHA 9char)}
- {Other relevant tool versions: codex, antigravity, gog, etc.}

---

**Authored by**: Kent Gale (kentonium3/kg-automation) & {agent name — Claude Code (Claude Opus 4.8), Codex (gpt-5.5), Antigravity (gemini-…), etc.}, {YYYY-MM-DD}.
**Submission approved by**: Kent Gale (kentonium3/kg-automation), {YYYY-MM-DD}.
**Local tracking**: kentonium3/kg-automation#{NNN}.
