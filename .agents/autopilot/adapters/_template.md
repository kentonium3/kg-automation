# Autopilot Adapter — <REPO NAME> (template)

Copy this to `<repo-slug>.md` and fill in the repo-specific mechanics. The
repo-agnostic rules live in `../felix-dev-autopilot-contract.md`; an adapter
supplies ONLY what differs per repo. If a section does not apply to the repo,
say so explicitly ("N/A — no deploy target") rather than deleting it, so the
agent knows the answer is "nothing," not "unspecified."

## Queue source
- Where the backlog lives (issue tracker / repo + org) and the candidate query.
- Any spec-readiness gate before work starts.

## Gate (must all pass before merge — never merge red)
- The exact test command(s).
- Any doc/data/lint validators run pre-commit and in CI.
- The CI check names to wait on.

## Adversarial review
- Which reviewer (reviewer-renata Opus / Codex / other) and any caveats.

## Deploy motion
- How merged code reaches its running target (self-pull, sync service, package
  publish, CI deploy, none). Distinguish change types if they deploy differently.

## Live-verify
- How to confirm the change is live and behaving on the deployed target.

## Rebaseline / security-baseline rule
- Whether the repo has an audited-surface baseline and when to reset it. N/A if none.

## Change-control tiers / off-limits
- The repo's risk taxonomy (if any) and what is off-limits autonomously.
- Note: Tier-0-style host changes are off-limits by the contract regardless.

## Architecture-docs obligation
- Which docs/data must be updated in the same change for a service/flow/credential
  change. N/A if the repo has no such store.

## Deploy discipline / manifests
- Any required deploy manifest or release process. N/A if none.
