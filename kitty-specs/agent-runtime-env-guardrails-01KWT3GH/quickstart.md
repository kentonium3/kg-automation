# Quickstart — Agent runtime-env guardrails

## Run the guard locally (same check CI runs)

```bash
# from the repo root (or with PYTHONPATH set to it)
PYTHONPATH="$(git rev-parse --show-toplevel)" python3 -m pytest \
  scripts/openclaw/agents/tests/test_env_assumptions_guard.py -v
```

Green = no non-waived env-assumption violations across all agent prompts.
A failure names each `path:line kind — remediation`.

## Scan ad hoc

```bash
PYTHONPATH="$(git rev-parse --show-toplevel)" python3 -c \
  "from scripts.openclaw.agents.env_assumptions import scan_agents_root, _default_root; \
   [print(f) for f in scan_agents_root(_default_root())]"
```

## Validate a single workspace (authoring-time check, #587 validator)

```bash
PYTHONPATH="$(git rev-parse --show-toplevel)" python3 -m scripts.openclaw.agents.validate_workspace --json
```

The new `runtime_env_assumptions` check appears alongside `privacy_boundary` and
`output_discipline`; non-zero exit if any workspace has a violation.

## Convert an invocation (canonical form)

```bash
# BEFORE (bare — relies on ambient PYTHONPATH/cwd)
python3 -m scripts.inbox.prescan --self-check
# BEFORE (hardcoded checkout)
cd /home/claude/kg-automation && python3 -m scripts.habits.morning_checkin_list
python3 /home/claude/kg-automation/scripts/openclaw/observation/log_action.py ...

# AFTER (canonical — reuse gateway PYTHONPATH, fail-loud, no hardcoded checkout)
PYTHONPATH="${PYTHONPATH:?run under openclaw-gateway or export the checkout root}" python3 -m scripts.inbox.prescan --self-check
PYTHONPATH="${PYTHONPATH:?...}" python3 -m scripts.habits.morning_checkin_list
python3 "${PYTHONPATH:?...}/scripts/openclaw/observation/log_action.py" ...
```

Remember: edit BOTH the rendered `AGENTS.md` and its `AGENTS.md.tmpl` where a template
exists (capture, tasker).

## Deploy (office2)

Ships via `deploys/queued/0010-agent-runtime-env-guardrails.yaml`; felix-deployer applies
on its next tick and auto-rebaselines the audited surface. Post-deploy health:

```bash
ssh office2-claude 'PYTHONPATH="${PYTHONPATH:?}" python3 -m scripts.inbox.prescan --self-check'   # → ok
ssh office2-claude 'openclaw cron runs --id <habits|escalation|tasker job>'                        # → green
```
