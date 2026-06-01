# Contract: Signal configuration file

**Path**: `scripts/openclaw/observation/signals/config.toml`
**Format**: TOML
**Owner**: in-repo; deployed to office2 via the existing deploy script (no direct edits to deployed copy).

## Schema

```toml
[meta]
schema_version = 1

[signals.<signal_id>]
source_kind             = "openclaw_log" | "agent_jsonl" | "systemd_journal"
source_path_pattern     = "<glob or literal path>"
match_pattern           = "<regex or substring>"
match_kind              = "regex" | "substring"
cycle_threshold         = <int ≥ 1>
rolling_window_minutes  = <int, default 60>
rolling_threshold       = <int ≥ cycle_threshold>
dedup_strategy          = "open_issue_present"
dedup_window_hours      = <int, default 24>
priority                = "P1" | "P2"
area_label              = "<area label, e.g. felix-core>"
tier_hypothesis         = "0" | "1" | "2" | "3" | "4" | "unknown"
excerpt_lines           = <int, default 5>
enabled                 = true | false
```

## Seed config (FR-006)

```toml
[meta]
schema_version = 1

[signals.whatsapp_creds_restore]
source_kind             = "openclaw_log"
source_path_pattern     = "/tmp/openclaw/openclaw-*.log"
match_pattern           = "restored corrupted WhatsApp creds.json from backup"
match_kind              = "substring"
cycle_threshold         = 6
rolling_window_minutes  = 60
rolling_threshold       = 18
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 5
enabled                 = true

[signals.web_watchdog_reconnect]
source_kind             = "openclaw_log"
source_path_pattern     = "/tmp/openclaw/openclaw-*.log"
match_pattern           = "web reconnect: connection closed"
match_kind              = "substring"
cycle_threshold         = 10
rolling_window_minutes  = 60
rolling_threshold       = 25
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 5
enabled                 = true

[signals.openclaw_unhandled_error]
source_kind             = "openclaw_log"
source_path_pattern     = "/tmp/openclaw/openclaw-*.log"
match_pattern           = '"logLevelName":"ERROR"'
match_kind              = "substring"
cycle_threshold         = 3
rolling_window_minutes  = 60
rolling_threshold       = 5
dedup_strategy          = "open_issue_present"
priority                = "P2"
area_label              = "felix-core"
tier_hypothesis         = "3"
excerpt_lines           = 8
enabled                 = true
```

## Validation rules (enforced at load time)

- Schema version must match the loader's expected version (1 today).
- `cycle_threshold` and `rolling_threshold` are positive integers; rolling ≥ cycle.
- `source_path_pattern` must be absolute.
- `match_pattern` non-empty.
- `area_label` need not be in the canonical area list (helper warns but proceeds — same behavior as `felix-file-issue.py`).
- `tier_hypothesis` must be one of `"0"`–`"4"` or `"unknown"`.
- Duplicate `signal_id` is a load-time error.

## Hot-reload behavior

- The driver reads `config.toml` at each cycle start. No daemon process; no reload signal needed.
- Disabling a signal (`enabled = false`) takes effect on the next cycle. Disabled signals preserve their state file but skip extraction and filing.
- Renaming a `signal_id` causes the old state file to be orphaned (will be ignored). Recommended: keep old `signal_id` and toggle `enabled = false` rather than renaming.

## Change-control tier

Editing `config.toml` is Tier 3 (logic/workflow). Deploy via the existing repo→office2 deploy script; no pre-flight checklist required.
