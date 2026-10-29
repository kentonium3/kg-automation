# Quickstart: off-host dead-man pings

## Local

```bash
TMPDIR=/dev/shm .venv/bin/python3 -m pytest tests/common/test_deadman.py tests/canary scripts/office2/felix_health_check tests/office2 -q -p no:cacheprovider
.venv/bin/python3 tooling/scripts/validate_architecture_data.py
```

## Provision (Kent, from his own terminal)

```bash
ssh -t office2-claude 'umask 077; mkdir -p ~/.config/felix/deadman; read -rsp "canary ping URL: " C; echo; read -rsp "health-check ping URL: " H; echo; printf "FELIX_DEADMAN_CANARY_URL=%s\nFELIX_DEADMAN_HEALTHCHECK_URL=%s\n" "$C" "$H" > ~/.config/felix/deadman/env'
```

## Verify (office2)

- Canary journal: `journalctl --user -u felix-canary.service --since -20min | grep deadman` shows `deadman canary success: ok`.
- Fail email test: `cd ~/kg-automation && python3 -m scripts.common.deadman --label canary --outcome fail`. An email should arrive; the next tick clears it.
