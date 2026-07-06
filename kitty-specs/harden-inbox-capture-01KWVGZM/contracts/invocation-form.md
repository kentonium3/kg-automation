# Contract — Agent helper invocation form

**Applies to**: every helper invocation in every active agent prompt
(`scripts/openclaw/agents/<slug>/AGENTS.md` and `.tmpl`).

## Required form

```bash
cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod> [args]
```

and the direct-script analog:

```bash
cd /home/claude/kg-automation && python3 scripts/<path>.py [args]
```

## Rules

1. **Always `cd /home/claude/kg-automation` first.** The OpenClaw `exec` tool runs
   commands in a sanitized subshell that strips `PYTHONPATH`, and the deployed
   workspace cwd (`/data/services/openclaw/<workspace>`) does not contain the
   `scripts/` package. The `cd` makes the command self-resolving.
2. **Never** rely on `${PYTHONPATH:?…}` or a bare `python3 -m scripts.…`. Both fail
   under exec (exit 127 / ModuleNotFoundError respectively).
3. **Never** hardcode an absolute `python3 /home/claude/kg-automation/scripts/x.py`
   form — use the `cd … && python3 scripts/x.py` relative form (keeps args/paths
   consistent and matches the checker's compliant pattern).
4. Multiple helper calls in one command may share a single `cd` via `&&`.
5. Arguments that are absolute paths (vault paths, tempfiles) are unchanged.

## Verification

`python3 -m scripts.openclaw.agents.env_assumptions` returns `ok: no
env-assumption findings` across all active workspaces (exit 0). Any remaining
`${PYTHONPATH:?}` or unanchored `-m scripts` invocation is a finding.
