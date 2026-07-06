# Decision Moment `01KWT44MKR753DPB4A71M8QK0C`

- **Mission:** `agent-runtime-env-guardrails-01KWT3GH`
- **Origin flow:** `plan`
- **Slot key:** `plan.design.canonical-anchor-form`
- **Input key:** `canonical_anchor_form`
- **Status:** `resolved`
- **Created:** `2026-07-05T21:49:49.560625+00:00`
- **Resolved:** `2026-07-05T21:53:22.589456+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

Canonical anchor form: reuse gateway PYTHONPATH as declared root (no gateway change) vs add FELIX_REPO_ROOT env var to gateway unit (small Felix-owned drop-in)?

## Options

- reuse_pythonpath
- add_repo_root_var
- Other

## Final answer

reuse_pythonpath — canonical anchor consumes the gateway-declared PYTHONPATH with fail-loud ${PYTHONPATH:?...}; no gateway/systemd change; boundary (no native OpenClaw element altered) preserved

## Rationale

_(none)_

## Change log

- `2026-07-05T21:49:49.560625+00:00` — opened
- `2026-07-05T21:53:22.589456+00:00` — resolved (final_answer="reuse_pythonpath — canonical anchor consumes the gateway-declared PYTHONPATH with fail-loud ${PYTHONPATH:?...}; no gateway/systemd change; boundary (no native OpenClaw element altered) preserved")
