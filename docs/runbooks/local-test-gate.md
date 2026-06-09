---
title: Local Test Gate (pre-push hook)
doc_type: runbook
status: approved
owners: ["@kentonium3"]
last_updated: '2026-06-09'
updated_by: '#571-local-test-gate'
audience: humans
---

# Local Test Gate (pre-push hook)

The repo ships a `.githooks/pre-push` script that runs `make test` before
allowing `git push`. This catches CI failures locally where they're cheaper
to fix.

## One-time setup (per clone)

```bash
git config core.hooksPath .githooks
```

That's it. Subsequent `git push` invocations will run the test suite first.

Verify:

```bash
git config --get core.hooksPath
# expected: .githooks
```

## What the hook does

1. Reads the standard pre-push protocol from stdin to determine whether the
   push actually moves any refs (skips no-ops).
2. Runs `make test` (~50 seconds for the current 3353-test suite).
3. Aborts the push (exit 1) if any test fails. Allows it (exit 0) otherwise.

## Bypass

```bash
git push --no-verify
```

Use ONLY when:

- The test failure is verifiably unrelated to the push (e.g., flaky test you'll
  fix in a follow-up commit)
- The push is a genuine emergency hot-fix where the cost of the local gate
  outweighs the risk (rare)

Don't bypass routinely. If the gate produces false positives often, fix the
underlying test instead.

## Why this exists (#571)

[kentonium3/kg-automation#571](https://github.com/kentonium3/kg-automation/issues/571)
captured the observation: "I don't understand why these tests aren't run
before they are pushed. We have the test locally and can know in advance
if it will fail Docs CI."

The repo's CI tier setup is two workflows:

- `test-ci.yml` — runs `make test` (the full pytest suite)
- `docs-ci.yml` — runs `validate_docs.py` (frontmatter + JSON schema +
  cross-link integrity)

Both run on every push to main. Both fail noisily when they fail. Neither
was running locally before push, so failures appeared only after the push
hit GitHub.

The `.githooks/pre-push` hook closes this gap for `test-ci`. The
`pre-commit` hook (already installed by spec-kitty) handles `docs-ci`
indirectly via its own validations. If you find a class of `docs-ci`
failures the existing pre-commit hook doesn't catch, extend
`.githooks/pre-push` to also run the docs validator (one extra line).

## Maintenance

If the test suite ever takes >2 minutes locally, the gate stops being
ergonomic. Options:

- Split the test suite into "fast" (run on pre-push) + "slow" (CI only)
- Parallelize test discovery (`pytest -n auto` requires `pytest-xdist`)
- Move some tests to nightly cron + skip in pre-push

Don't silently let the hook get slow. Document the threshold here when
the conversation is fresh.

## Cross-references

- [`.githooks/pre-push`](../../.githooks/pre-push) — the hook script itself
- [`Makefile`](../../Makefile) — the `test` target the hook invokes
- [`.github/workflows/test-ci.yml`](../../.github/workflows/test-ci.yml) — the CI side
- kentonium3/kg-automation#571 — originating issue
- kentonium3/kg-automation#537 — the original "tests are the only pre-merge gate" decision
