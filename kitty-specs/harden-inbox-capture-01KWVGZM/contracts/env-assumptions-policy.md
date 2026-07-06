# Contract — env_assumptions.py policy (inverted; corrects #658)

`scripts/openclaw/agents/env_assumptions.py` classifies helper invocations in agent
prompts. This mission inverts its notion of "compliant" to match runtime reality
(OpenClaw exec strips `PYTHONPATH`). Shared by the Test-CI env-guard and
`validate_workspace.check_runtime_env_assumptions`.

## Canonical checkout path (exact)

Define **one** module constant, e.g. `CANONICAL_CHECKOUT = "/home/claude/kg-automation"`,
and **exact-match** it. Do NOT accept "any path containing `kg-automation`" — a
`cd /home/kgale/repos/kg-automation` or `cd /tmp/kg-automation` would pass the checker
but fail on office2 (the OpenClaw checkout is only ever `/home/claude/kg-automation`).

## Compliant (no finding)

```bash
cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod> [args]
cd /home/claude/kg-automation && python3 scripts/<path>.py [args]
```

The exact checkout-`cd` immediately before a relative `-m scripts.` / `python3
scripts/….py` invocation is the canonical form.

## Violations (findings)

| Kind | Trigger | Remediation string points to |
|------|---------|------------------------------|
| `BARE_M_SCRIPTS` | `python3 -m scripts.…` NOT preceded by the exact checkout-`cd` | the checkout-`cd` form |
| `RELATIVE_SCRIPT` (**new**) | `python3 scripts/<path>.py` OR a bare imperative `scripts/<path>.py` NOT preceded by the exact checkout-`cd` | the checkout-`cd` form |
| `PYTHONPATH_ANCHOR` (**new / renamed from HARDCODED_CD**) | a `${PYTHONPATH:?…}` anchor (fails under exec) | the checkout-`cd` form |
| `HOME_RELATIVE_WRITE` | `>>`/`tee` to a `~`/`$HOME`-relative dest | a canonical absolute path (UNCHANGED, #659) |

Notes:
- The previous `HARDCODED_CD` violation (which flagged `cd /home/claude/kg-automation`)
  is **inverted** — the *exact* checkout path is now required, not banned. A
  `kg-automation` path that is NOT the exact canonical stays a violation.
- The new `RELATIVE_SCRIPT` class (Codex post-plan HIGH-2) closes the gap where a
  relative `python3 scripts/x.py` or a bare imperative `scripts/x.py` (e.g. capture
  `AGENTS.md:97` `invoke scripts/openclaw/agents/main/felix-file-issue.py`) would
  otherwise pass yet fail under exec.
- `HARDCODED_ABS_PATH` (absolute `python3 /…/scripts/x.py`) is retained as a violation
  steering to the `cd … && python3 scripts/x.py` form.
- Waiver marker mechanism (`# env-guard: waive <kind>`) and HTML-comment stripping are
  retained.
- Docstring updated to describe the corrected canonical form and cite this mission +
  #662 (correcting #658).

## Test obligations

- `tests/test_env_assumptions.py`: rewrite fixtures/assertions so the checkout-`cd`
  form passes and the `${PYTHONPATH:?}`/bare forms are flagged.
- Test-CI env-guard test: assert the live fleet passes under the new policy.
- `tests/test_validate_workspace.py`: any env-assumption fixture updated to the new
  compliant form.
- Coverage: keep `--cov-branch` above threshold (add `# pragma: no branch` only for
  genuinely unreachable defensive branches, per repo convention).
