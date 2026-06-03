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
