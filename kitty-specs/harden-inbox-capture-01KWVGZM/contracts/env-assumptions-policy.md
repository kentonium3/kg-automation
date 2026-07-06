# Contract — env_assumptions.py policy (inverted; corrects #658)

`scripts/openclaw/agents/env_assumptions.py` classifies helper invocations in agent
prompts. This mission inverts its notion of "compliant" to match runtime reality
(OpenClaw exec strips `PYTHONPATH`). Shared by the Test-CI env-guard and
`validate_workspace.check_runtime_env_assumptions`.

## Compliant (no finding)

```bash
cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod> [args]
cd /home/claude/kg-automation && python3 scripts/<path>.py [args]
```

The checkout-`cd` prefix (path containing `kg-automation`) immediately before a
relative `-m scripts.` / `python3 scripts/….py` invocation is the canonical form.

## Violations (findings)

| Kind | Trigger | Remediation string points to |
|------|---------|------------------------------|
| `BARE_M_SCRIPTS` | `python3 -m scripts.…` NOT preceded by the checkout-`cd` | the checkout-`cd` form |
| `PYTHONPATH_ANCHOR` (new / renamed) | a `${PYTHONPATH:?…}` anchor (fails under exec) | the checkout-`cd` form |
| `HOME_RELATIVE_WRITE` | `>>`/`tee` to a `~`/`$HOME`-relative dest | a canonical absolute path (UNCHANGED, #659) |

Notes:
- The previous `HARDCODED_CD` violation (which flagged `cd /home/claude/kg-automation`)
  is **removed/inverted** — that form is now required, not banned.
- `HARDCODED_ABS_PATH` (absolute `python3 /…/scripts/x.py`) may be retained as a
  style violation steering to the `cd … && python3 scripts/x.py` form — implementer's
  discretion; the load-bearing change is that checkout-`cd` is compliant and
  `${PYTHONPATH:?}` is not.
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
