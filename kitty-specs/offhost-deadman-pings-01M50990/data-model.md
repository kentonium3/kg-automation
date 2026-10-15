# Data Model: Off-host dead-man pings

## Env file `/home/claude/.config/felix/deadman/env` (0600, claude:claude)

```
FELIX_DEADMAN_CANARY_URL=https://hc-ping.com/<uuid>
FELIX_DEADMAN_HEALTHCHECK_URL=https://hc-ping.com/<uuid>
```

- Only `KEY=value` lines are read. Blank lines, `#` comments and malformed lines are ignored, and a single surrounding pair of quotes is stripped.
- A variable already in the process environment takes precedence over the file.
- The test-only override `FELIX_DEADMAN_ENV_FILE` points at another file.

## `deadman.ping(label, outcome, *, env=None, env_file=None, run=None) -> PingResult`

| Field | Meaning |
|---|---|
| `label` | `"canary"` or `"healthcheck"`, which select the variable |
| `outcome` | `"success"` or `"fail"`, where `fail` appends `/fail` |
| result `sent` | bool: curl exited 0 |
| result `reason` | `ok`, `unconfigured`, `invalid`, `timeout`, `unreachable`, `http_error`, or `error:<Class>` |

**Invariants**
- `ping` never raises, never prints the URL, and never blocks longer than the subprocess timeout (8 s).
- A URL is valid only if it starts with `https://`, has no whitespace or control characters, contains no `"` or `\`, and is at most 512 characters long. Those characters are rejected outright rather than escaped.
- The single log line goes to stderr, which the journal captures: `deadman <label> <outcome>: <reason>`.

## Watcher outcomes

| Watcher | `success` when | `fail` when | nothing when |
|---|---|---|---|
| felix-canary | the pass status is `success` and `alerts_undelivered == 0` | the status is `error`, any alert is undelivered, or `run_pass` raised | `--dry-run` or `--self-check` |
| felix-health-check | the record is written and `not (delivery.attempted and not delivery.sent)` | the delivery was attempted and not sent, or the record write raised (ping `fail`, then re-raise) | — |

`alerts_undelivered` appears in the canary's returned summary only. It is excluded from the persisted tick signal.
