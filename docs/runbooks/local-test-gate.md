---
title: Local Test Gate (pre-commit + pre-push hooks)
doc_type: runbook
status: approved
owners: ["@kentonium3"]
last_updated: '2026-07-12'
updated_by: '#719-prepush-gate-removed + pre-commit-validate-docs-unconditional'
audience: humans
---

# Local Test Gate (pre-commit hook)

The repo ships a **pre-commit** hook under `.githooks/` that catches Docs CI
failures locally — where they're cheaper to fix — instead of after they redden
a workflow on `main`. The former **pre-push** `make test` gate was removed
(#719, 2026-07-12) — see below.

| Hook | Runs | Catches | Cost |
|---|---|---|---|
| `.githooks/pre-commit` | the three Docs CI validators (whole-tree, every commit) | `docs-ci.yml` failures | ~4s every commit |
| `.githooks/pre-push` | **nothing (no-op)** — removed #719 | — (code is checked post-push by `test-ci.yml`) | ~0s |

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

All three validators run **unconditionally on every commit** (~4s total):
`validate_privacy_boundary.py` (~0.2s), `validate_architecture_data.py --strict`
(~0.1s), and `validate_docs.py` (~3.9s, a whole-tree frontmatter + secret scan).

`validate_docs.py` used to run **only when the commit staged docs/markdown** (a
code-only commit paid ~0.3s). That was dropped: because the check is whole-tree
but its trigger was per-commit, a frontmatter issue **already in the tree**
(introduced via `--no-verify`, an inactive hook, or a spec-kitty-driven commit)
would slip past a later code-only commit and only surface as a red Docs CI on
push — the pre-commit ↔ Docs-CI **trigger gap**. Running it every commit
re-checks the whole tree and closes that gap. (It does **not** close the
"hook wasn't active at all" gap — that's covered only by the Docs CI backstop.)

If validation fails, the commit is aborted with the finding and the fix
(e.g. add the new `doc_type` to `docs/design/standards/allowed-values.json`).

## pre-push — removed (#719, 2026-07-12)

The pre-push hook is now an intentional **no-op** (`exit 0`). It formerly ran
the full `make test` suite (#571) to keep `main` green, but:

- the suite grew to ~3.5 min (5000+ tests), far past #571's "runnable locally in
  <1 minute" premise, so the per-push tax stopped paying off;
- `test-ci.yml` runs the full suite on `push: [main]` (see below), so **code is
  already checked post-push by CI**;
- doc-frontmatter — the original reason for a local gate — is caught at *commit*
  time by the pre-commit hook, not at push.

Kent accepts an occasional briefly-red `main` (caught by `test-ci.yml` +
fix-forward) in exchange for fast pushes. `felix-deployer` is not gated on
tests, so a briefly-red `main` does not block deploys. To run the suite before
pushing anyway, run `make test` yourself.

This **supersedes** the change-scoped test-selection idea originally tracked in
[#719](https://github.com/kentonium3/kg-automation/issues/719) (removing the
gate is simpler than bucketing tests to changed surfaces).

## Bypass

```bash
git commit --no-verify   # skip the pre-commit doc gate
```

(There is no longer a pre-push gate to bypass — `git push` runs no tests.)

Use `--no-verify` ONLY when a doc-validation failure is verifiably unrelated, or
for a genuine emergency. Don't bypass routinely — `docs-ci.yml` still gates
`main`, so a bypass just moves the churn back to where the pre-commit hook exists
to prevent it. If a gate produces false positives often, fix the underlying
check instead.

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
- [`.githooks/pre-push`](../../.githooks/pre-push) — no-op (test gate removed, #719)
- [`Makefile`](../../Makefile) — `docs-check` + `test` targets
- [`.github/workflows/docs-ci.yml`](../../.github/workflows/docs-ci.yml) — the docs CI side
- [`.github/workflows/test-ci.yml`](../../.github/workflows/test-ci.yml) — the test CI side (checks code post-push)
- kentonium3/kg-automation#678 — pre-commit docs gate
- kentonium3/kg-automation#571 — pre-push test gate (added; removed by #719)
- kentonium3/kg-automation#719 — pre-push test gate removed (code checked post-push by test-ci)
- kentonium3/kg-automation#537 — the original "tests are the only pre-merge gate" decision
