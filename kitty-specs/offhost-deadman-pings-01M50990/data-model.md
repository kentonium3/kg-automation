# Data Model: Off-host dead-man pings

## Env file `/home/claude/.config/felix/deadman/env` (0600, claude:claude)

```
FELIX_DEADMAN_CANARY_URL=https://hc-ping.com/<uuid>
FELIX_DEADMAN_HEALTHCHECK_URL=https://hc-ping.com/<uuid>
```

- Only `KEY=value` lines are read. Blank lines, `#` comments and malformed lines are ignored, and a single surrounding pair of quotes is stripped.
- URLs are read **only** from this file, into a private mapping. They never enter `os.environ`. The test-only override `FELIX_DEADMAN_ENV_FILE` names another file path; it is never a URL.

## `deadman.ping(label, outcome, *, env=None, env_file=None, run=None) -> PingResult`

| Field | Meaning |
|---|---|
| `label` | `"canary"` or `"healthcheck"`, which select the variable |
| `outcome` | `"success"` or `"fail"`, where `fail` appends `/fail` |
| result `sent` | bool: curl exited 0 |
| result `reason` | `ok`, `unconfigured`, `invalid`, `timeout`, `unreachable`, `http_error`, or `error:<Class>` |

**Invariants**
- `ping` never raises, never prints the URL, and never blocks longer than the subprocess timeout (8 s).
- A URL is valid only if all of these hold:
  - `urlsplit` gives scheme `https` and a host;
  - there is no query, fragment or userinfo;
  - there is no whitespace, control character, `"` or `\`, and the URL is at most 512 characters;
  - the final path segment is not `fail`, `start`, `log` or all digits.
- One trailing `/` is stripped. The fail URL is built by `urlunsplit` with `path + "/fail"`.
- Transport: `curl -q ... --proto =https --max-redirs 0 --max-time 5 -K -`, given a minimal environment and the URL on stdin. At most 2 attempts (the second after 2 s), so the worst case is about 18 s.
- The single log line goes to stderr, which the journal captures: `deadman <label> <outcome>: <reason>`.

## Watcher outcomes

| Watcher | `success` when | `fail` when | nothing when |
|---|---|---|---|
| felix-canary | the pass status is `success`, `alerts_undelivered == 0`, and `channel_broken` is false | the status is `error`, the pass raised, any alert this tick was undelivered, or `channel_broken` | `--dry-run` or `--self-check` |
| felix-health-check | the record is written, there is no execution fault, `channel_broken` is false, and not (the status is alerting and `delivery.sent` is false) | the status is alerting and `delivery.sent` is false (covers a missing topic, where `attempted` is false), an execution fault, `channel_broken`, or the record write raised (ping `fail`, then re-raise) | — |

**Superseded by post-plan round 3 (stateless). The round-2 text below is kept for history only.** `channel_ok` = topic configured AND the ntfy `/v1/health` probe answers `{"healthy": true}` AND every delivery this run succeeded. Any probe error counts as not ok. There are no state files.

Round-2 design (dropped): `channel_broken` was true when either held:
- `FELIX_ALERT_NTFY_TOPIC` is absent or blank in the watcher's own environment;
- the watcher's own debt state is set **after** this run's verification attempt.

**Watcher debt state** (`deadman.json` in the watcher's state directory: `{"undelivered_since_utc": iso|null}`, written atomically):
- **Set** when one of the watcher's own deliveries fails this run.
- **While set**, each run first emits one INFO "felix-alert channel verification" alert. If that alert is delivered, the debt clears; if not, it stays.
- **A missing file** means no debt. **An unreadable or corrupt file** means debt.

`alerts_undelivered` appears in the canary's returned summary only. It is excluded from the persisted tick signal.
