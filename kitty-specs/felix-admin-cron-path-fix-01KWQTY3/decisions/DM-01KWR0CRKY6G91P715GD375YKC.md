# Decision Moment `01KWR0CRKY6G91P715GD375YKC`

- **Mission:** `felix-admin-cron-path-fix-01KWQTY3`
- **Origin flow:** `plan`
- **Slot key:** `plan.fr1-guardrail.mechanism`
- **Input key:** `fr1_guardrail_mechanism`
- **Status:** `resolved`
- **Created:** `2026-07-05T02:05:52.638595+00:00`
- **Resolved:** `2026-07-05T02:24:14.228697+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Mechanism to make python3 -m scripts.* invocations cwd-independent in the felix-admin agent prompts

## Options

- inline PYTHONPATH prefix
- committed thin wrapper script
- openclaw.json agent env (out of repo)

## Final answer

Env-level: add Environment=PYTHONPATH=/home/claude/kg-automation to scripts/openclaw/openclaw-gateway.service (inherited by all agent subprocesses via the same mechanism that delivers HOME=/home/claude). Guardrail over instruction. No inline prompt prefixes; remove now-inert cwd prose per FR3.

## Rationale

_(none)_

## Change log

- `2026-07-05T02:05:52.638595+00:00` — opened
- `2026-07-05T02:24:14.228697+00:00` — resolved (final_answer="Env-level: add Environment=PYTHONPATH=/home/claude/kg-automation to scripts/openclaw/openclaw-gateway.service (inherited by all agent subprocesses via the same mechanism that delivers HOME=/home/claude). Guardrail over instruction. No inline prompt prefixes; remove now-inert cwd prose per FR3.")
