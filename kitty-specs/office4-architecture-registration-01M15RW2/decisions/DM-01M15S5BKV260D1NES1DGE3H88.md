# Decision Moment `01M15S5BKV260D1NES1DGE3H88`

- **Mission:** `office4-architecture-registration-01M15RW2`
- **Origin flow:** `specify`
- **Slot key:** `specify.environment.commit-hook-python`
- **Input key:** `commit_hook_python_resolution`
- **Status:** `resolved`
- **Created:** `2026-08-29T03:31:39.259487+00:00`
- **Resolved:** `2026-08-29T03:35:01.375501+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

office4's system python3 lacks pyyaml, so the repo pre-commit hook fails and blocks every commit. How should this be resolved?

## Options

- fix-direnv-properly
- PYTHON-seam-for-now
- apt-install-python3-yaml

## Final answer

Full canonical setup: git config core.hooksPath .githooks (per local-test-gate.md:26), .envrc confirmed already direnv-trusted, and the direnv bash hook appended to ~/.bashrc after the brew shellenv block. No workaround used; office4 now matches the documented setup and the #678 doc-validation gate is active.

## Rationale

_(none)_

## Change log

- `2026-08-29T03:31:39.259487+00:00` — opened
- `2026-08-29T03:35:01.375501+00:00` — resolved (final_answer="Full canonical setup: git config core.hooksPath .githooks (per local-test-gate.md:26), .envrc confirmed already direnv-trusted, and the direnv bash hook appended to ~/.bashrc after the brew shellenv block. No workaround used; office4 now matches the documented setup and the #678 doc-validation gate is active.")
