---
affected_files: []
cycle_number: 3
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
reproduction_command:
reviewed_at: '2026-05-21T20:29:43Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: `main()` does not consistently honor the CLI contract's exit-code-3 requirement for validation/usage errors. `contracts/cli.md` explicitly includes bad state values under code 3, but `scripts/escalation/record_completion.py` calls `parser.parse_args(argv)` directly at line 886. For flag-driven invalid enum input such as `--state bogus`, argparse raises `SystemExit(2)` and prints the default argparse error instead of returning `3` with a structured stderr line. Fix by routing argparse usage failures through the same structured error path and returning `3` while preserving `--help` as exit `0`. Add a test for an invalid flag-driven `--state` or `--source`.

**Issue 2**: Empty token files bypass the CLI error mapping. `_read_token()` raises `ValueError` for an empty token file at `scripts/escalation/record_completion.py:182`, but `main()` only maps `FileNotFoundError` to exit `3` at lines 932-940. A CLI invocation with an empty token file currently crashes with an uncaught `ValueError` instead of returning a structured validation/usage failure. Either catch this token-load `ValueError` in `main()` and return `3`, or convert it to the existing token-load error type consistently. Add a CLI test that exercises an empty token file through `main()`.

Downstream note: WP05, WP06, and WP07 depend on WP03; those agents should rebase after the fix lands.
