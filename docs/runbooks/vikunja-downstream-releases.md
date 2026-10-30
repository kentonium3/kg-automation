---
id: vikunja-downstream-releases
title: Vikunja Downstream Development and Releases
doc_type: runbook
level: howto
status: approved
owners: [kgale]
last_updated: '2026-10-30'
revision: v1.2
audience: agents_and_humans
tags: [vikunja, releases]
---

# Vikunja Downstream Development and Releases

## Purpose and authority

Operate `kentonium3/vikunja` as a maintained downstream distribution: ship
Kent's integrated enhancements to testers, contribute focused changes upstream,
and keep current with `go-vikunja/vikunja`. Upstream acceptance does not gate a
downstream release. Kent approved this strategy on 2026-10-30; the first
transition is tracked in [vikunja-harness#45](https://github.com/kentonium3/vikunja-harness/issues/45).
The reusable pipeline backlog is [vikunja-harness#39](https://github.com/kentonium3/vikunja-harness/issues/39).

This runbook documents the agreed operating procedure. It does not install CI,
create registry credentials, publish artifacts, change branch settings or deploy
production. Inspect actual tooling before each use. Kent approves the exact
push, force-push, merge, tag and release action; upstream-facing copy also needs
his approval. Existing classifier refusals remain held, never routed through
another actor or account. Production cutover requires its separate explicit go.

The promotion procedure below reflects Kent's resolved plan decision
`01M676BK24HB12W941ST6NJRDA`: review a PR, then fast-forward the exact tested
commit to fork `main`. It is the required target workflow, not a claim that the
current harness already supports it. Issue #45 must deliver and verify the
push-gate, integration-branch CI and fork-release guards before promotion.

## Branch and release contract

| Surface | Contract |
| --- | --- |
| Fork `main` (default) | Integrated downstream source, including accepted fork features and upstream updates; protected by review and CI. |
| Local `upstream/main` | Remote-tracking reference fetched from the canonical repository; no published mirror branch is required. |
| `feat/<topic>` | Focused contribution branch with only the feature and its prerequisites; upstream PRs target canonical `main`, not fork `main`. |
| `integrate/upstream-<date>` | Temporary branch from fork `main` for merging a recorded upstream SHA and resolving conflicts. |
| Versioned tag/release | Immutable source and downloadable tested artifacts; independent of the moving branch. |
| Office2 deployment | An explicitly accepted artifact digest, which can lag public previews. |

Do not rebase or force-push published fork `main`, move released tags, or use
`gh repo sync ... -b main` to turn the downstream branch back into a mirror.
Feature branches may be rebased with Kent-approved force-with-lease updates;
never apply that policy to `main`. CI staging refs are test infrastructure,
not the user-facing distribution.

### Prerequisite: adapt the harness push gate and fork CI

Before the initial downstream-main promotion, issue #45's mission owner must
update `harness-docs/tools/pushgate.py` and its tests. The existing `check_ref`
policy assumes `main` is an ancestor of canonical `upstream/main` and skips its
harness-leak scan. That policy both refuses downstream-main pushes and leaves
GitHub-UI merges outside the local hook's protection.

Required behavior and evidence:

- Fork `main` gets the same harness/private-path leak scan as `feat/*`, and can
  contain reviewed downstream commits beyond upstream.
- The upstream-only ancestry rule remains in force for `ci-base/*`.
- Scanned `integrate/*` branches may be published to the fork, and `fork-ci`
  must stage and qualify them so the exact candidate commit can obtain green
  fork CI. The old `feat/*`-only route is insufficient. Preserve the candidate
  SHA through qualification and verify the SHA reported by CI; a different
  snapshot or merge commit does not qualify the intended candidate.
- A downstream `main` goes only to the configured fork. Refuse deletion and
  non-fast-forward updates of published `main`, and require green fork CI on
  its exact new commit. `HARNESS_SKIP_CI_GATE` must not bypass that main check;
  existing `feat/*` override semantics do not grant a new main bypass.
- Regression tests prove that a clean downstream-main candidate passes, a main
  candidate with harness/private content fails, and a downstream-only commit
  on `ci-base/*` is refused. Also cover main rewrite/deletion and wrong-remote
  refusals, the no-skip main CI rule, and clean/dirty `integrate/*` qualification.
  Preserve existing feature-branch scan coverage.
- Before promotion, run the same leak scan against the exact CI-green
  integration commit X and retain its full commit SHA, tree SHA and verdict.
  Verify against fresh fork `main` that X is its descendant. If the candidate
  or remote main moves, revalidate ancestry, scan and exact-commit CI as
  applicable. The tested, scanned and promoted commit must all be X.
- A PR into fork `main` provides review and visibility only. Do not use the
  GitHub merge, squash or rebase buttons: they can create a different commit
  from X. Kent approves the exact fast-forward push `git push fork X:main`
  (with the packet's full SHA substituted for X). Afterward verify fork main
  equals X, then close the review PR with the promotion evidence. No force
  push or hook bypass is a promotion route.

This is a prerequisite owned by the full #45 mission, not a gate implementation
delivered by this documentation PR. Preserve classifier and publication gates.
Do not claim downstream-main promotion ready until the reviewed gate change,
tests, exact-commit CI and candidate scan evidence are available.

### Prerequisite: isolate canonical publishing from fork validation

The inherited upstream CI/release workflows are not a ready fork release
pipeline. At the base inspected for #45, main and v* tag events enter `ci.yml`,
which calls `release.yml` with canonical publication and deployment assumptions.
Do not rely on missing upstream secrets or unavailable runners to stop them.

Issue #45's integration mission must gate the canonical release caller in
`ci.yml` and every canonical-only publish/deploy job in `release.yml` with
`if: github.repository == 'go-vikunja/vikunja'`. Keep the fork's validation jobs,
including SQLite/MySQL/PostgreSQL tests, active for exact-SHA qualification.
Review every release job and workflow-call/tag path. Keep this fork-only
divergence in its own commit and off the upstream contribution branches.

Before any downstream-main push or preview tag, inspect the exact candidate X
tree to prove these guards are present, and retain fork CI on X showing the
canonical release jobs skipped while required validation passes. Preview
artifacts use a separately reviewed fork-owned workflow or local build route,
never the inherited canonical `release.yml`. This does not authorize new
registry credentials, Actions-settings changes or workflow execution.

## 1. Establish or resume the downstream line

1. Use the governed Vikunja harness and its current promotion instructions.
   Read its AGENTS/CLAUDE guidance and inspect `promote`/`fork-ci` help before
   execution. One owner coordinates integration; preserve occupied checkouts.
2. Record full SHAs for fork `main`, canonical `main`, the accepted integrated
   RRULE source, existing upstream PR heads, and the deployed artifact. Fetch
   through a verified canonical remote. These are read-only discovery commands:

   ```bash
   git remote -v
   git fetch upstream
   git rev-parse origin/main upstream/main
   gh repo view kentonium3/vikunja --json defaultBranchRef
   ```

3. For the initial transition, assemble all accepted RRULE layers and release
   fixes against a recorded current upstream base through issue #45's full
   mission. Preserve commit/provenance mapping to the accepted Office2 build.
   The existing production acceptance is not invalidated by this source work.
4. Review the complete resulting tree and prepare a review PR into fork `main`.
   Confirm it includes the intended features, excludes harness/private paths,
   and has no accidental workflow, credential, production data or configuration
   additions. Complete both prerequisites above and the release gates below.
   The packet binds review approval, green CI, the leak scan and release-guard
   evidence to the same integration commit X. Kent then approves and performs
   its exact fast-forward push to fork main; do not merge the PR in GitHub.
5. Verify the fork's default branch is `main` and the repository page now shows
   X as the downstream source, then close the review PR with the verified SHA.
   A merge into `ci-base/*` does not satisfy this step.

## 2. Integrate upstream regularly

Fetch regularly and integrate at least weekly while upstream is active;
expedite relevant security and correctness fixes. A fetch is not permission to
merge or deploy. Record the exact upstream SHA selected for each cycle so a
moving upstream branch does not change the candidate during review.

1. From a clean fork `main`, create an integration branch through the applicable
   project workflow. Merge the selected upstream revision into it; preserve
   public downstream history rather than rebasing the whole distribution.
2. Inventory upstream changes and conflicts, particularly migration identifiers
   and order, task models, recurrence/DST behavior, API routes, generated clients,
   frontend repeat controls, dependencies and build/release workflows.
3. Resolve with regression tests. Regenerate derived files using the supported
   commands. Keep intentional downstream behavior explicit; do not blindly take
   either side of a conflict.
4. Test both a supported older installation and the currently deployed downstream
   schema. Never silently renumber an already-applied migration; resolve any
   collision through a reviewed compatibility plan covering both upgrade paths.
5. Run the gates below, review the complete upstream integration diff, and open
   the fork-main review PR. Promote only by the exact-commit fast-forward route
   above after Kent's approval. Preserve evidence and stop on failed gates or
   unresolved migration semantics. No production deployment follows merely
   from this source promotion.

## 3. Maintain upstream contributions separately

Create focused PR branches from a recorded canonical base. Use shared feature
commits or an explicit commit mapping to avoid independently implementing the
same change twice. Keep fork branding, release packaging and unrelated features
out of upstream PRs. Dependent PRs must state their order and prerequisites.

Refresh contribution branches as upstream changes warrant. Their CI and merge
conflicts are tracked independently of the integrated distribution. Check the
actual PR diff, not only GitHub's mergeability indicator. Do not force-push
existing PR branches without Kent's approval of the exact ref update.

When upstream accepts a change, verify semantic equivalence, including squash
or edited merges. In the next integration cycle reconcile duplicate code and
migrations explicitly, retain tests, then retire the contribution branch when
its obligations are complete. Never discard a downstream fix merely because
an upstream PR was marked merged.

Upstream PR maintenance can proceed alongside a downstream preview. It must not
hold a tested preview waiting for maintainer availability or upstream merge.

## 4. Qualify a public candidate

Bind evidence to the final public source SHA and artifact digest, not only to a
private working branch or temporary CI ref. Freeze integration candidate X after
any local merges, qualify and scan X, then promote X unchanged. Tree equivalence
alone does not satisfy the exact-commit CI rule. If changes produce another
commit, qualify and scan that new candidate before considering promotion.

- Required build, lint, typecheck, frontend tests and backend tests pass.
- Fork CI exercises SQLite, MySQL and PostgreSQL. Cancelled or skipped required
  jobs are not passes; known exceptions require explicit recorded disposition.
- The exact X tree contains the canonical publishing guards, and CI on X proves
  required fork validation passed while canonical release jobs were skipped.
- Recurrence, DST, migration and API compatibility tests pass for affected paths.
  `/api/v1` stays frozen; new routes belong under `/api/v2`.
- For this initial refreshed RRULE release, use two distinct private fixtures:
  a retained hash-verified pre-migration snapshot (or a representative legacy
  fixture) for conversion and per-id oracle comparison, and a fresh consistent
  current-production snapshot for upgrade from the already-migrated deployed
  version. Record provenance and expected assertions separately. A fresh
  already-migrated database cannot prove legacy conversion.
  For later releases, select replay coverage according to actual migration risk.
- Complete the mission's required independent reviews, including post-plan and
  post-merge whole-diff review, and resolve significant findings.
- Test the built public artifact on a disposable database. Verify its embedded
  version, frontend, API and recurrence flow. Keep production data out of logs,
  repository files, release assets and public CI.

## 5. Publish a discoverable preview

1. Choose a distinct fork release identifier, for example
   `v2.7.1-kentonium.1-rc.1`. Record the upstream base, downstream SHA and embedded
   runtime version. Verify the build/version parser accepts the chosen format;
   the example is a naming policy, not an existing tag. Never reuse an upstream
   release identity for different fork bytes.
2. Build once from the qualified source. Produce downloadable binaries and a
   container image or image archive using the supported build route. Include
   supported OS/architectures, SHA256 checksums and an artifact-to-source record.
   A private local image or GitHub's source-only archive is not a ready-to-run
   public distribution. Use the separately reviewed fork-owned/local build
   route, not canonical `release.yml`. New registry setup needs separate
   authorization.
3. Stage the exact tag target, assets and release notes for Kent. Notes identify
   fork features, upstream base, compatibility limits, migration/backup warnings,
   installation commands, test procedure and issue-reporting destination.
4. After approval, publish an immutable tag and GitHub prerelease. Verify it is
   published, not a draft, and that public download links work without private
   credentials. Download the published asset, verify its checksum and run the
   documented smoke test against a disposable database. Do not rebuild a
   different artifact for this check.
5. Put a prominent fork explanation and preview link in fork `main`'s README.
   Verify the repository home and Releases page lead a new visitor to the
   current preview. Explain the relationship to canonical Vikunja and keep
   license/provenance notices. Link from upstream PRs only with approved copy.
6. Record release URL, tag/commit, checksums, image digest or archive hash,
   supported platforms, test evidence and known limitations. Public delivery
   closes only when somebody following the published instructions can obtain
   and run that exact version.

## 6. Promote independently to production

A public preview does not automatically update Office2. Select a qualified
artifact, preserve the rollback image and take the fresh write-boundary
snapshot through the governed deployment route. Use
[Vikunja Release Cutover](vikunja-release-cutover.md) for the established
STAGE/ACTIVATE/acceptance/rollback mechanics, with a newly reviewed packet bound
to the new from/to versions. Its 2026-10-30 values are historical and must not be
reused as live facts.

Kent approves the production go separately. Use the same artifact bytes tested
for promotion; verify image digest and embedded version after deployment.
Never run an older image on a database migrated by a newer release. Rollback
restores the matching pre-upgrade database and follows the packet's write
disposition and acceptance checks. Retention cleanup requires the applicable
operator decision, not an assumed expiry.

## Completion record and ownership

The integration owner records source SHAs, conflicts, migrations and test/review
evidence. The contribution owner records PR heads and upstream dispositions.
The release owner records public artifacts and a successful download/run check.
The production owner records deployment and acceptance separately. The program
manager coordinates dependencies and makes both public delivery and production
status explicit; one does not imply the other.

Keep exact-action approvals and release evidence durable. Report failed gates,
unavailable artifacts and classifier denials precisely. Do not relabel an
internal CI branch as a completed public release.
