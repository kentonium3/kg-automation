# Cross-Repo Standing Rules

Universal agent rules that apply in EVERY repo, not just kg-automation. Imported into the
global `~/.claude/CLAUDE.md` via `@` so it loads in every session. Keep this short and
imperative — the always-on behavioral layer, not a template library. Longer templates and
protocols are linked, not inlined.

## Public-post copy approval (HIGH-STAKES)
- Before ANY outward post — GitHub issue, PR title/body, PR/issue comment, release notes,
  upstream discussion — show Kent the EXACT copy and get explicit sign-off on the wording
  BEFORE posting. Approving the ACTION ("open the PR") is not approving the COPY. Draft → show → post.
- Same for edits to already-posted public copy: show the change first.
- **Exception — `kentonium3/kg-automation` internal tracking:** posts and edits that stay
  *within* the kg-automation repo (issues, issue comments, PR titles/bodies, PR comments) do
  NOT require pre-review. It is Kent's own tracking repo — nobody else reads it, so the gate
  adds friction without protecting anyone. The exception is **repo-scoped, not
  content-scoped**: any copy destined to leave kg-automation still needs sign-off before it
  goes out — most importantly the embedded upstream drafts filed to `Priivacy-ai/spec-kitty`
  or other external trackers, which remain gated by the pre-filing approval step (see the
  spec-kitty bug-reporting runbook). The no-`@mentions`-of-outsiders rule below still applies.

## Local tracking tickets
- No `@mentions` in local/internal tracking records (kg-automation issues, memories, notes).
  Name people without the `@` so a local record never notifies them.

## Stop-and-capture on unexpected spec-kitty behavior (HIGH-STAKES)
- STOP on **ANY** unexpected spec-kitty (or sibling-tooling) workflow behavior and surface it
  to Kent, **even if you could work around it.** Non-exhaustive triggers:
  - **missing or inconsistent state/status** (an artifact, token, or record that should exist
    doesn't, or disagrees with itself);
  - **authority confusion** — which checkout / branch / actor owns a step (the coordination
    split-authority class: primary vs coord vs lane worktree);
  - **source or location errors** — wrong path, file, or checkout;
  - **ambiguous direction that forces retries or redos** to get a command to do the right thing;
  - **permissions issues**;
  - **unexpected git conditions** — branch, worktree, index, or stale-state anomalies (e.g. a
    merge that lands but leaves the checkout needing manual git surgery);
  - a command that fails, blocks, or produces unexpected output; a gate that won't pass.
  Capture the exact error + command sequence with the surfaced report.
- **The trigger is "having to overcome an unexpected condition," not "being unable to."**
  Silently working around a resolvable anomaly is prohibited: it destroys the evidence that is
  the only way spec-kitty gets better. This is NOT narrowed by auto-drive — auto-drive removes
  per-step approval, never the duty to surface unexpected conditions.
- **Happy-path decisions *within* the prescribed path are fine** and do NOT trigger a stop:
  authoring spec/plan/tasks/matrix artifacts through the workflow, and committing
  workflow-generated status files from the primary checkout, are expected parts of the flow.

## Spec-Kitty (and sibling tooling) issue reporting
- Follow the dual-track runbook `~/repos/kg-automation/docs/runbooks/spec-kitty-bug-reporting.md`.
  Do NOT file upstream ad-hoc. Flow: file the INTERNAL status tracker as a
  `kentonium3/kg-automation` issue (template `.github/ISSUE_TEMPLATE/spec-kitty-bug.md`), then
  generate the slim EXTERNAL upstream report from it via
  `docs/diagnostics/spec-kitty-bug-report-external-template.md`.
- Internal kg-automation issues use the `.github/ISSUE_TEMPLATE/` forms (bug / feature / infra /
  docs-debt / research / rfc).
