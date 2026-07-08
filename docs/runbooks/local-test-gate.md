---
title: Local Test Gate (pre-commit + pre-push hooks)
doc_type: runbook
status: approved
owners: ["@kentonium3"]
last_updated: '2026-07-08'
updated_by: '#678-precommit-docs-gate'
audience: humans
---

# Local Test Gate (pre-commit + pre-push hooks)

The repo ships two git hooks under `.githooks/` that catch CI failures
locally — where they're cheaper to fix — instead of after they redden a
workflow on `main`:

| Hook | Runs | Catches | Cost |
|---|---|---|---|
| `.githooks/pre-commit` | the Docs CI validators (cost-tiered) | `docs-ci.yml` failures | ~0.3s code-only, ~4s doc commits |
| `.githooks/pre-push` | `make test` (full pytest suite) | `test-ci.yml` failures | ~50s |

## One-time setup (per clone)

```bash
git config core.hooksPath .githooks
```

That's it. Both hooks activate. Verify:

```bash
git config --get core.hooksPath
# expected: .githooks
```

> **Note:** setting `core.hooksPath` makes git use `.githooks/` *exclusively* —
> any hook under `.git/hooks/` (e.g. spec-kitty's generated `pre-commit`
> commit-guard) is bypassed while this is set. That is intentional here; the
> hooks in `.githooks/` are the active gates.

## pre-commit — doc validation (#678)

Runs the same validators as the Docs CI workflow, so a doc-frontmatter problem
(an unknown `doc_type`/`status` enum value, a broken required key, etc.) is
caught at commit time — closest to authoring — and never enters a commit.

It is **cost-tiered** so it isn't friction on every commit:

1. `validate_privacy_boundary.py` (~0.2s) and `validate_architecture_data.py
   --strict` (~0.1s) are cheap and repo-wide, so they **always** run.
2. `validate_docs.py` (~3.9s, a whole-tree frontmatter scan) runs **only when
   the commit stages markdown/docs**. A code-only commit pays ~0.3s.

If validation fails, the commit is aborted with the finding and the fix
(e.g. add the new `doc_type` to `docs/design/standards/allowed-values.json`).

## pre-push — test suite (#571)

1. Reads the pre-push protocol from stdin to skip no-op pushes.
2. Runs `make test` (the full pytest suite).
3. Aborts the push (exit 1) if any test fails.

## Bypass

```bash
git commit --no-verify   # skip the pre-commit doc gate
git push   --no-verify   # skip the pre-push test gate
```

Use ONLY when the failure is verifiably unrelated, or for a genuine emergency
hot-fix. Don't bypass routinely — the CI workflows still gate `main`, so a
bypass just moves the churn back to where these hooks exist to prevent it. If a
gate produces false positives often, fix the underlying check instead.

## Why this exists (#571, #678)

[kentonium3/kg-automation#571](https://github.com/kentonium3/kg-automation/issues/571)
captured it: "I don't understand why these tests aren't run before they are
pushed. We have the test locally and can know in advance if it will fail CI."

Two CI workflows run on every push to `main`:

- `test-ci.yml` — runs `make test` (the full pytest suite).
- `docs-ci.yml` — runs **three** validators: `validate_docs.py` (frontmatter +
  enum membership), `validate_privacy_boundary.py`, and
  `validate_architecture_data.py --strict`.

`.githooks/pre-push` closed the gap for `test-ci` in #571. The `docs-ci` gap
stayed open: an earlier version of this runbook assumed "the pre-commit hook
(installed by spec-kitty) handles docs-ci indirectly" — that was never true.
spec-kitty's hook is a *commit guard* (protected-branch / safe-commit), it does
not run this repo's doc validators, and it is dormant anyway under
`core.hooksPath=.githooks`. So doc-validation failures — most often a new-but-
legitimate `doc_type` tripping the `enum_membership` blocker — reddened `main`
until hand-patched (**#560**: ~2 days red; **#678**: 7 red runs over 5 hours).
`.githooks/pre-commit` closes that gap for real, mirroring what `docs-ci` runs.

`make docs-check` runs the full trio on demand (mirrors the workflow).

## Maintenance

- If the pytest suite exceeds ~2 min locally, split fast/slow or move some to
  nightly cron (see the pre-push hook's own header).
- If `validate_docs.py` grows well beyond ~4s, scope the pre-commit invocation
  to changed files rather than a whole-tree scan.
- Keep `make docs-check` and `.github/workflows/docs-ci.yml` in lockstep: if a
  validator is added to the workflow, add it to the `docs-check` target (and it
  flows into the pre-commit gate).

## Cross-references

- [`.githooks/pre-commit`](../../.githooks/pre-commit) — doc-validation gate
- [`.githooks/pre-push`](../../.githooks/pre-push) — test gate
- [`Makefile`](../../Makefile) — `docs-check` + `test` targets
- [`.github/workflows/docs-ci.yml`](../../.github/workflows/docs-ci.yml) — the docs CI side
- [`.github/workflows/test-ci.yml`](../../.github/workflows/test-ci.yml) — the test CI side
- kentonium3/kg-automation#678 — pre-commit docs gate (this change)
- kentonium3/kg-automation#571 — pre-push test gate
- kentonium3/kg-automation#537 — the original "tests are the only pre-merge gate" decision
