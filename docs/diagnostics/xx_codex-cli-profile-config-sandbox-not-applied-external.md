# Bug: codex CLI `-p <profile>` reads the profile file but silently drops the `sandbox` setting

## Summary

When codex CLI 0.135.0+ is invoked with `-p <name>`, the dedicated profile file at `$CODEX_HOME/<name>.config.toml` is loaded — `model`, for example, is applied correctly — but the `sandbox` setting in that same file is silently filtered out of the effective config. The session header reports `sandbox: workspace-write` (the codex default) even though the profile file declares `sandbox = "danger-full-access"`. Adding `-s danger-full-access` to the same invocation applies the override correctly, confirming the regression is specific to how the profile-file merge handles the `sandbox` field. The CLI help for `-p, --profile` describes it as `Layer $CODEX_HOME/<name>.config.toml on top of the base user config`, so users reasonably expect every top-level key — including `sandbox` — to participate in that layer.

## Reproduction

### Prerequisites

- codex CLI v0.136.0 (also reproduces on v0.135.0)
- `$CODEX_HOME` unset (defaults to `~/.codex`)
- No `[profiles.<name>]` block in `~/.codex/config.toml`

### Steps

```bash
# 1. Confirm the profile file is read at all (model field is honored)
cat > ~/.codex/probe-model.config.toml <<'EOF'
model = "gpt-5.1"
EOF
codex -p probe-model exec "echo test" < /dev/null 2>&1 | head -12

# 2. Now set sandbox in the same shape and observe it is NOT honored
cat > ~/.codex/probe-sandbox.config.toml <<'EOF'
sandbox = "danger-full-access"
EOF
codex -p probe-sandbox exec "echo test" < /dev/null 2>&1 | head -12

# 3. Confirm the value works when set via the CLI flag
codex -p probe-sandbox -s danger-full-access exec "echo test" < /dev/null 2>&1 | head -12
```

### Expected Behavior

Step 2's session header should show:

```text
sandbox: danger-full-access
```

…matching the profile file's declared value, the same way Step 1's `model: gpt-5.1` correctly reflects the profile-file `model` field.

### Actual Behavior

Step 1 (model field via profile file) — works as expected:

```text
OpenAI Codex v0.136.0
--------
workdir: /Users/kentgale/repos/kg-automation
model: gpt-5.1            ← profile applied
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR]
```

Step 2 (sandbox field via profile file) — **profile loaded, sandbox dropped**:

```text
OpenAI Codex v0.136.0
--------
workdir: /Users/kentgale/repos/kg-automation
model: gpt-5.5
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR]   ← profile file declared danger-full-access; ignored
```

Step 3 (explicit `-s` flag) — works:

```text
sandbox: danger-full-access   ← correct only when set via the CLI flag
```

### Root Cause

Not source-confirmed locally, but the observable behavior shows:

1. `$CODEX_HOME/<name>.config.toml` *is* loaded by `-p <name>` (the `model` key is honored).
2. The `sandbox` key from that file is silently dropped before `derive_sandbox_policy()` is called — there is no warning, error, or visible signal that the declared sandbox was ignored.

Likely an oversight in whatever transforms the layered profile config into the structure consumed by the sandbox-policy resolver. The migration from inline `[profiles.<name>]` tables to dedicated `<name>.config.toml` files (introduced in 0.135.0) may have routed only a subset of fields through the new merge path.

Other field-form variants we tested:

- `[profile]\nsandbox = "..."` (table wrapper) — rejected at parse time: `invalid type: map, expected a string in 'profile'`.
- `[profiles.<name>]\nsandbox = "..."` (legacy form inside the dedicated file) — silently ignored; no error, but sandbox stays at default.

So the bare top-level `sandbox = "..."` is the only syntactically valid shape, and that is the shape being dropped.

## Workaround Applied

Add explicit `-s <sandbox-mode>` flag alongside `-p <profile>` on every invocation. Acceptable but defeats the purpose of profile files — the whole point of the profile is to centralize per-use-case config (including sandbox policy) in one place that callers don't need to re-specify.

```bash
codex -p example-profile -s danger-full-access exec "<prompt>"
```

## Impact

Any user who migrated from `[profiles.<name>]` table syntax (deprecated in 0.135.0) to the new `<name>.config.toml` file form *and* relies on a non-default `sandbox` policy in that profile will see the policy silently revert to `workspace-write`. The session looks like the profile applied — workspace writes succeed — so the regression is invisible until an out-of-workspace write fails. This particularly affects tool integrations that need to write to user-state directories (`~/.<tool>/`) or to `.git/` (where some tools place lock files). In our case (spec-kitty workflow), every codex-dispatched review fails its terminal cleanup step, forcing the orchestrator to replay the action from outside the sandbox.

Suggested mitigation, in priority order:

1. **Fix the merge**: ensure `sandbox` from the profile file participates in `derive_sandbox_policy()` the same way `model` participates in the model resolver.
2. **Warn on drop**: if certain fields are intentionally excluded from the profile-file layer, emit a startup warning naming the dropped fields so users aren't surprised.
3. **Document the exclusion in `codex exec --help`** under the `-p, --profile` entry so the layering semantics are explicit.

## Environment

- OS: macOS Darwin 25.5.0 (x86_64)
- codex CLI: 0.136.0 (Homebrew install: `brew install --cask codex`; `/usr/local/bin/codex`)
- Also reproduces on: 0.135.0
- `CODEX_HOME`: unset (defaults to `~/.codex`)
- Terminal: VS Code 1.114.0 (also reproduces in standalone terminals)
- Auth mode: ChatGPT (auth.json file storage)
- Subscription: ChatGPT Plus
- Model: `gpt-5.5` (codex session default; no `model` pin in base config.toml or in the failing profile file)

## `codex doctor --json`

<details>
<summary>Full output (codex 0.136.0, macOS)</summary>

```json
{
  "schemaVersion": 1,
  "generatedAt": "1780505583s since unix epoch",
  "overallStatus": "ok",
  "codexVersion": "0.136.0",
  "checks": {
    "app_server.status": {
      "id": "app_server.status",
      "category": "app-server",
      "status": "ok",
      "summary": "background server is not running",
      "details": {
        "control socket": "~/.codex/app-server-control/app-server-control.sock",
        "daemon state dir": "~/.codex/app-server-daemon",
        "mode": "ephemeral",
        "pid file": "~/.codex/app-server-daemon/app-server.pid (missing)",
        "settings": "~/.codex/app-server-daemon/settings.json (missing)",
        "status": "not running",
        "update-loop pid file": "~/.codex/app-server-daemon/app-server-updater.pid (missing)"
      },
      "remediation": null,
      "durationMs": 0
    },
    "auth.credentials": {
      "id": "auth.credentials",
      "category": "auth",
      "status": "ok",
      "summary": "auth is configured",
      "details": {
        "auth file": "~/.codex/auth.json",
        "auth storage mode": "File",
        "stored API key": "false",
        "stored ChatGPT tokens": "true",
        "stored agent identity": "false",
        "stored auth mode": "chatgpt"
      },
      "remediation": null,
      "durationMs": 0
    },
    "config.load": {
      "id": "config.load",
      "category": "config",
      "status": "ok",
      "summary": "config loaded",
      "details": {
        "CODEX_HOME": "~/.codex",
        "config.toml": "~/.codex/config.toml",
        "config.toml parse": "ok",
        "cwd": "~/repos/<project>",
        "enabled feature flags": "shell_tool, unified_exec, shell_snapshot, terminal_resize_reflow, sqlite, hooks, enable_request_compression, multi_agent, apps, tool_suggest, plugins, in_app_browser, browser_use, browser_use_external, computer_use, plugin_sharing, image_generation, skill_mcp_dependency_install, steer, guardian_approval, goals, collaboration_modes, tool_call_mcp_elicitation, personality, fast_mode, tui_app_server, workspace_dependencies",
        "feature flag overrides": "none",
        "feature flags enabled": "27",
        "log dir": "~/.codex/log",
        "mcp servers": "0",
        "model": "<default>",
        "model provider": "openai",
        "sqlite home": "~/.codex"
      },
      "remediation": null,
      "durationMs": 0
    },
    "git.environment": {
      "id": "git.environment",
      "category": "git",
      "status": "ok",
      "summary": "git version 2.54.0",
      "details": {
        ".git entry": "directory",
        "PATH git #1": "/usr/local/bin/git",
        "PATH git #2": "/usr/bin/git",
        "PATH git entries": "2",
        "git branch": "main",
        "git build options": "git version 2.54.0; cpu: x86_64; no commit associated with this build; sizeof-long: 8; sizeof-size_t: 8; shell-path: /bin/sh; rust: disabled; feature: fsmonitor--daemon; gettext: enabled; libcurl: 8.6.0; zlib: 1.2.12; SHA-1: SHA1_DC; SHA-256: SHA256_BLK; default-ref-format: files; default-hash: sha1",
        "git exec path": "/usr/local/opt/git/libexec/git-core",
        "git version": "git version 2.54.0",
        "repo detected": "true",
        "repo root": "~/repos/<project>",
        "selected git": "/usr/local/bin/git"
      },
      "remediation": null,
      "durationMs": 19
    },
    "installation": {
      "id": "installation",
      "category": "install",
      "status": "ok",
      "summary": "installation looks consistent",
      "details": {
        "PATH codex #1": "/usr/local/bin/codex",
        "current executable": "/usr/local/bin/codex",
        "install context": "brew",
        "managed by bun": "false",
        "managed by npm": "false",
        "managed package root": "not set"
      },
      "remediation": null,
      "durationMs": 4
    },
    "mcp.config": {
      "id": "mcp.config",
      "category": "mcp",
      "status": "ok",
      "summary": "no MCP servers configured",
      "details": {},
      "remediation": null,
      "durationMs": 0
    },
    "network.env": {
      "id": "network.env",
      "category": "network",
      "status": "ok",
      "summary": "network-related environment looks readable",
      "details": {
        "proxy env vars": "none"
      },
      "remediation": null,
      "durationMs": 0
    },
    "network.provider_reachability": {
      "id": "network.provider_reachability",
      "category": "reachability",
      "status": "ok",
      "summary": "active provider endpoints are reachable over HTTP",
      "details": {
        "ChatGPT base URL": "https://chatgpt.com/backend-api/ reachable (HTTP 403)",
        "reachability mode": "ChatGPT auth"
      },
      "remediation": null,
      "durationMs": 429
    },
    "network.websocket_reachability": {
      "id": "network.websocket_reachability",
      "category": "websocket",
      "status": "ok",
      "summary": "Responses WebSocket handshake succeeded",
      "details": {
        "DNS": "2 IPv4, 2 IPv6, first IPv4",
        "auth mode": "chatgpt",
        "connect timeout": "15000 ms",
        "endpoint": "wss://chatgpt.com/backend-api/<redacted>",
        "handshake result": "HTTP 101 Switching Protocols",
        "model provider": "openai",
        "models etag present": "true",
        "provider name": "OpenAI",
        "proxy env vars": "none",
        "reasoning header": "false",
        "server model present": "false",
        "supports websockets": "true",
        "wire API": "responses"
      },
      "remediation": null,
      "durationMs": 945
    },
    "runtime.provenance": {
      "id": "runtime.provenance",
      "category": "runtime",
      "status": "ok",
      "summary": "running brew on macos-x86_64",
      "details": {
        "commit": "unknown",
        "current executable": "/usr/local/bin/codex",
        "install method": "brew",
        "platform": "macos-x86_64",
        "version": "0.136.0"
      },
      "remediation": null,
      "durationMs": 0
    },
    "runtime.search": {
      "id": "runtime.search",
      "category": "search",
      "status": "ok",
      "summary": "search is OK (system)",
      "details": {
        "search command": "rg",
        "search command readiness": "ripgrep 15.1.0",
        "search provider": "system"
      },
      "remediation": null,
      "durationMs": 23
    },
    "sandbox.helpers": {
      "id": "sandbox.helpers",
      "category": "sandbox",
      "status": "ok",
      "summary": "sandbox configuration is readable",
      "details": {
        "approval policy": "OnRequest",
        "codex-linux-sandbox helper": "none",
        "execve wrapper helper": "~/.codex/tmp/arg0/codex-arg07KTqwj/codex-execve-wrapper",
        "filesystem sandbox": "restricted",
        "network sandbox": "restricted"
      },
      "remediation": null,
      "durationMs": 0
    },
    "state.paths": {
      "id": "state.paths",
      "category": "state",
      "status": "ok",
      "summary": "state paths and databases are inspectable",
      "details": {
        "CODEX_HOME": "~/.codex (dir)",
        "active rollout files": "209 files, 66525841 total bytes, 318305 average bytes",
        "archived rollout files": "0 files, 0 total bytes, 0 average bytes",
        "goals DB": "~/.codex/goals_1.sqlite (file)",
        "goals DB integrity": "ok",
        "log DB": "~/.codex/logs_2.sqlite (file)",
        "log DB integrity": "ok",
        "log dir": "~/.codex/log (dir)",
        "memories DB": "~/.codex/memories_1.sqlite (file)",
        "memories DB integrity": "ok",
        "sqlite home": "~/.codex (dir)",
        "state DB": "~/.codex/state_5.sqlite (file)",
        "state DB integrity": "ok"
      },
      "remediation": null,
      "durationMs": 445
    },
    "state.rollout_db_parity": {
      "id": "state.rollout_db_parity",
      "category": "threads",
      "status": "ok",
      "summary": "rollout files and state DB thread inventory agree",
      "details": {
        "default model provider": "openai",
        "rollout DB active files": "209",
        "rollout DB active rows": "209",
        "rollout DB archive mismatches": "0",
        "rollout DB archived files": "0",
        "rollout DB archived rows": "0",
        "rollout DB duplicate DB paths": "0",
        "rollout DB duplicate rollout thread ids": "0",
        "rollout DB malformed file names": "0",
        "rollout DB missing active rows": "0",
        "rollout DB missing archived rows": "0",
        "rollout DB model providers": "openai=209",
        "rollout DB rows": "209",
        "rollout DB scan cap reached": "false",
        "rollout DB scan errors": "0",
        "rollout DB sources": "exec=184, subagent:review=16, cli=9",
        "rollout DB stale rows": "0"
      },
      "remediation": null,
      "durationMs": 1157
    },
    "system.environment": {
      "id": "system.environment",
      "category": "system",
      "status": "ok",
      "summary": "OS language en-US",
      "details": {
        "LANG": "C.UTF-8",
        "os": "Mac OS 26.5.0 [64-bit]",
        "os language": "en-US",
        "os type": "Mac OS",
        "os version": "26.5.0"
      },
      "remediation": null,
      "durationMs": 6
    },
    "terminal.env": {
      "id": "terminal.env",
      "category": "terminal",
      "status": "ok",
      "summary": "terminal metadata was detected",
      "details": {
        "COLORTERM": "truecolor",
        "TERM_PROGRAM": "vscode",
        "VSCODE_INJECTION": "present",
        "color output": "disabled (stdout is not a terminal)",
        "effective locale": "C.UTF-8",
        "stderr is terminal": "false",
        "stdin is terminal": "false",
        "stdout is terminal": "false",
        "terminal": "VS Code",
        "terminal size": "80x24",
        "terminal version": "1.114.0"
      },
      "remediation": null,
      "durationMs": 10
    },
    "terminal.title": {
      "id": "terminal.title",
      "category": "title",
      "status": "ok",
      "summary": "terminal title default",
      "details": {
        "terminal title activity": "true",
        "terminal title items": "activity, project-name",
        "terminal title project source": "git repo root",
        "terminal title project value": "<project>",
        "terminal title source": "default"
      },
      "remediation": null,
      "durationMs": 0
    },
    "updates.status": {
      "id": "updates.status",
      "category": "updates",
      "status": "ok",
      "summary": "update configuration is locally consistent",
      "details": {
        "cached latest version": "0.130.0",
        "check for update on startup": "true",
        "last checked at": "2026-05-15T17:17:23.289526Z",
        "latest version": "0.136.0",
        "latest version status": "current version is not older",
        "update action": "brew upgrade --cask codex",
        "version cache": "/Users/kentgale/.codex/version.json"
      },
      "remediation": null,
      "durationMs": 61
    }
  }
}
```

</details>

Note: home-directory paths (`/Users/<user>/...`) were replaced with `~/` and the project name was redacted to `<project>` for the upstream paste. All other values are verbatim from the run.

## Related (not duplicates)

I searched open + closed issues and PRs in this repo for terms covering "profile sandbox", "config_profile_v2", "danger-full-access ignored", "<name>.config.toml", and adjacent variants. Nothing matches the exact gap (`codex exec -p <name>` silently drops the profile file's `sandbox` field while honoring other fields like `model`), but several items are in the same neighborhood:

- #14515 (closed 2026-03-12) — same pattern, different field: `model_instructions_file` silently dropped via `codex exec --profile`. Was fixed; the current report looks like the same class re-emerging for `sandbox` after the profile-v2 migration.
- #25440 (open 2026-05-31) — adjacent migration friction: legacy `[profiles.<name>]` config startup breakage after upgrade. Different failure mode but same profile-v1 → profile-v2 migration window.
- #25526 (open 2026-06-01) — `codex-config` loader README is stale relative to the implementation comments. Same area of churn; arguably evidence that the layered-config behavior has shifted recently without docs catching up.
- PR #25943 (merged 2026-06-02) — "config: remove dead profile sandbox fallback." Removed `profile_sandbox_mode` from `ConfigToml::derive_permission_profile` on the theory that "production now always derives permissions without that value, and legacy profile contents are ignored." That assumption appears to be the inverse of what users invoking `codex exec -p <name>` actually need from the profile file — the gap this report describes.
- PR #24110 (merged 2026-05-22) — added `--profile` support to the `codex sandbox` *subcommand* specifically. The bug here is in the `codex exec -p <name>` path, which is separate.
- PR #23886 (merged 2026-05-21) — removed legacy profile-v1 plumbing. Likely when the gap was introduced; the `<name>.config.toml` form may have replaced the v1 path without threading `sandbox` through.
