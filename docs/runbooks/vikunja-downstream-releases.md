---
id: vikunja-downstream-releases
title: Vikunja Downstream Development and Releases
doc_type: runbook
level: howto
status: approved
owners: [kgale]
last_updated: '2026-10-30'
revision: v1.0
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
4. Review the complete resulting tree and prepare a PR into fork `main`.
   Confirm it includes the intended features, excludes harness/private paths,
   and has no accidental workflow, credential, production data or configuration
   additions. Kent merges after the release gates below pass.
5. Verify the fork's default branch is `main` and the repository page now shows
   the downstream source. A merge into `ci-base/*` does not satisfy this step.

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
   the fork-main PR. Preserve evidence and stop on failed gates or unresolved
   migration semantics. No production deployment occurs from this merge alone.

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
private working branch or temporary CI ref. A later merge commit must be checked
for tree equivalence; changes introduced during merge require renewed checks.

- Required build, lint, typecheck, frontend tests and backend tests pass.
- Fork CI exercises SQLite, MySQL and PostgreSQL. Cancelled or skipped required
  jobs are not passes; known exceptions require explicit recorded disposition.
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
   public distribution. New registry setup needs separate authorization.
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
