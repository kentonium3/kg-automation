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
- **Exception — the named spec-kitty mission-running repo set** (`kg-automation`, `spec-kitty`,
  `spec-kitty-analyzer`, `spec-kitty-saas`, `spec-kitty-telescope`, `vikunja-harness`): the
  **Spec-Kitty workflow-fault detour protocol** (below) supersedes the *stop-and-ask-how-to-proceed*
  step. There you still fully **capture** the evidence (diagnose + track the issue) and still get
  Kent's sign-off on any **upstream** copy, but you run the detour **autonomously** and only halt
  when there is **no pre-known workaround**. This narrows *where you must halt* — never the duty to
  preserve evidence, and never the ban on silent (improvised) workarounds.
- **Happy-path decisions *within* the prescribed path are fine** and do NOT trigger a stop:
  authoring spec/plan/tasks/matrix artifacts through the workflow, and committing
  workflow-generated status files from the primary checkout, are expected parts of the flow.

## Spec-Kitty build identification — the version string identifies NOTHING (HIGH-STAKES)
- **Never** use a version string to say which spec-kitty build or which repository line is installed —
  not `spec-kitty --version`, not `pyproject.toml`, not `.kittify/metadata.yaml`, not a PyPI listing,
  not a project `CLAUDE.md` orientation banner. Two installs both reporting `3.2.6rc2` were **323
  commits apart**. Identify the build from its provenance record and cite the tuple: **line, SHA, how
  it got here**.
- **We are always ahead of the last official release; that is the steady state, not an exception.**
  The installed build matches a published release on exactly one day — release day, when we
  deliberately run the release-path upgrade *as a test of the release path*. "Version is X, therefore
  build is Y" is wrong on every other day.
- **Numbers do not identify a line.** Multiple spec-kitty lines with disjoint history publish
  overlapping numbers; a cross-repo `compare` between them returns 404, not a distance. Resolve by SHA
  lookup in each repo — HTTP 422 "No commit found" is the test for absence.
- `spec-kitty upgrade`, and plain `pipx upgrade` / `uv tool upgrade`, follow the semver path and **fail
  silently** — a pin plus `--force` is mandatory, and a successful-looking run is not evidence the
  build moved.
- Full procedure (installer paths, the three provenance cases, line resolution):
  `~/repos/spec-kitty-qa/docs/runbooks/spec-kitty-upgrade.md` (v1.3+). Also asserted in
  `~/.claude/CLAUDE.md`. If that runbook's paths do not match the machine you are on, **that is the
  bug — fix the runbook**; never fall back to `--version`.

## Spec-Kitty (and sibling tooling) issue reporting
- Follow the dual-track runbook `~/repos/kg-automation/docs/runbooks/spec-kitty-bug-reporting.md`.
  Do NOT file upstream ad-hoc. Flow: file the INTERNAL status tracker as a
  `kentonium3/kg-automation` issue (template `.github/ISSUE_TEMPLATE/spec-kitty-bug.md`), then
  generate the slim EXTERNAL upstream report from it via
  `docs/diagnostics/spec-kitty-bug-report-external-template.md`.
- Internal kg-automation issues use the `.github/ISSUE_TEMPLATE/` forms (bug / feature / infra /
  docs-debt / research / rfc).

## Spec-kitty workflow-fault detour protocol (named repo set)
- **Applies in:** `kg-automation`, `spec-kitty`, `spec-kitty-analyzer`, `spec-kitty-saas`,
  `spec-kitty-telescope`, `vikunja-harness`. On ANY unexpected spec-kitty (or sibling-tooling)
  workflow fault in these repos, run the protocol
  `~/repos/kg-automation/docs/runbooks/spec-kitty-workflow-fault-protocol.md` **autonomously** —
  do NOT stop to ask how to proceed when a workaround is pre-known. Evidence-preservation is
  unchanged (met by diagnose+track, not by halting).
  1. **Stop the failing action and fully diagnose the root cause** while evidence is fresh (exact
     command+error, state, code inspection); note the spec-kitty build.
  2. **Local issue** (kg-automation): exists → comment noting recurrence on the current build (or
     persistence on a newer build); none → create per `spec-kitty-bug-reporting.md`.
  3. **Upstream:** search (ours or others'). Exists → comment confirming recurrence-same-build /
     persistence-newer-build; if the issue is CLOSED, `@mention` **that program/repo's current
     maintainer** as a safety check — **resolve per-repo, do NOT hardcode a name** (ownership
     varies by program: spec-kitty-CLI, spec-kitty-SaaS, analyzer+telescope [Kent], Vikunja are
     separately owned). **[STOP: show Kent the exact copy before posting.]** None → prep the
     upstream embed in the local issue per the runbook. **[STOP: Kent reviews copy before filing.]**
  4. **Known workaround** (documented in the runbook's registry / a tracked issue / upstream /
     memory) → apply it and continue. An **improvised** workaround is NOT "known" — improvising is
     a prohibited silent workaround → treat as step 5.
  5. **No known workaround → [STOP: present continue-with-a-manual-step vs abandon-mission.]**
- The **only** stops in this set are the two upstream-copy reviews (3) and the no-workaround
  decision (5). Outside the set, the general stop-and-capture rule (stop + surface) applies. Full
  protocol + the Known-Workarounds Registry live in the runbook above.
