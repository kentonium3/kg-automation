---
work_package_id: WP01
title: scripts/common/deadman.py — bounded, secret-safe dead-man ping and channel check
dependencies: []
requirement_refs:
- FR-005
- FR-006
- FR-007
- NFR-001
- NFR-003
- NFR-004
- NFR-005
- C-001
- C-002
- SC-003
planning_base_branch: feat/offhost-deadman-pings
merge_target_branch: feat/offhost-deadman-pings
branch_strategy: Planning artifacts for this mission were generated on feat/offhost-deadman-pings. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/offhost-deadman-pings unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-offhost-deadman-pings-01M50990
base_commit: cd84582ded5af3b95ca5c9265f061001a68a9ef1
created_at: '2026-10-15T17:40:22.239531+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
history:
- at: '2026-10-15T18:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (after 4 post-plan Codex rounds)
agent_profile: python-pedro
authoritative_surface: scripts/common/
create_intent:
- scripts/common/deadman.py
- scripts/common/deadman.env.sample
- tests/common/test_deadman.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/common/deadman.py
- scripts/common/deadman.env.sample
- tests/common/test_deadman.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – `scripts/common/deadman.py`

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `feat/offhost-deadman-pings` · **Merge target branch**: `feat/offhost-deadman-pings`. Worktrees come from `lanes.json`.

## Context

- **Authority:** the four "Post-plan … dispositions" sections in `plan.md`. **Round 3 (stateless) and round 4 (probe transport) win over anything earlier.** Also `data-model.md` (env file, `ping`, URL invariants, the superseded-section note).
- **Transport precedent:** `scripts/common/alert_bus/delivery.py` runs curl through subprocess with `--max-time 10` and a subprocess timeout of 15. `_base_url()` reads `FELIX_ALERT_NTFY_BASE_URL`, defaulting to `https://ntfy.sh`.

## Subtasks

### T001 – Env-file loader and URL canonicalisation

- **Path:** `ENV_FILE = Path("/home/claude/.config/felix/deadman/env")`, a fixed path that is never derived from `$HOME` (engineering principle 15). Test override: `FELIX_DEADMAN_ENV_FILE`, which holds a path only.
- **`_load(path) -> dict[str,str]`**
  - Read only `KEY=value` lines. Skip blanks and `#` lines. Strip one matching pair of surrounding quotes. Ignore anything malformed.
  - Never raise. A missing or unreadable file returns `{}`.
  - Read **only** `FELIX_DEADMAN_CANARY_URL` and `FELIX_DEADMAN_HEALTHCHECK_URL`.
  - Never write to `os.environ`.
- **`_canonical(url) -> tuple[str,str] | None`**, returning `(success_url, fail_url)`.
  - Parse with `urlsplit`. Require scheme `https` and a host.
  - Reject any of: a query, a fragment, userinfo, whitespace, a control character, `"`, `\`, or a length over 512.
  - Reject a final path segment of `fail`, `start` or `log`, or one that is all digits.
  - Strip one trailing `/`. Build fail with `urlunsplit` and `path + "/fail"`.
- **Labels:** `{"canary": "FELIX_DEADMAN_CANARY_URL", "healthcheck": "FELIX_DEADMAN_HEALTHCHECK_URL"}`.

### T002 – Ping transport and `ping()`

- **`ping(label, outcome, *, env_file=None, run=subprocess.run, sleep=time.sleep) -> PingResult(sent: bool, reason: str)`**
- **Reasons:** `ok`, `unconfigured`, `invalid`, `timeout`, `unreachable`, `http_error`, `curl_missing`, `error:<Class>`.
- **Argv**, exactly: `["curl", "-q", "--silent", "--show-error", "--fail", "--globoff", "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "0", "--max-time", "5", "--retry", "0", "--output", "/dev/null", "-K", "-"]`. `-q` must be first.
- **URL handling:**
  - Pass the URL on stdin as the curl config line `url = "<url>"`. Validation already rejected `"` and `\`.
  - The URL must never appear in argv.
  - Use the explicit minimal env `{"PATH": "/usr/bin:/bin", "LANG": "C"}`, with no HOME and no proxy variables.
  - Run with `capture_output=True`; **discard** curl's stdout and stderr.
  - Subprocess timeout 8.
- **Exit-code mapping:**
  - curl exit 22 means `http_error`.
  - curl exit 28 means `timeout`.
  - curl exits 6 and 7 mean `unreachable`.
  - `TimeoutExpired` means `timeout`.
  - `FileNotFoundError` means `curl_missing`.
  - Anything else means `error:<Class>`.
- **Attempts:** at most 2. The second comes after `sleep(2)`, and only when the first did not succeed.
- **Logging:** exactly one line per call to stderr: `deadman <label> <outcome>: <reason>`. Never include the URL.
- **Totality:** `ping` never raises. Wrap the whole body.

### T003 – `channel_ok(env, delivered_ok, *, run=subprocess.run, sleep=time.sleep) -> tuple[bool, str]`

Return `(False, reason)` on the first failing check, else `(True, "ok")`:
1. `env.get("FELIX_ALERT_NTFY_TOPIC","").strip()` is empty: return `topic_missing`. This check sends nothing.
2. The probe, `GET <base>/v1/health`, where base is `env.get("FELIX_ALERT_NTFY_BASE_URL","").strip() or "https://ntfy.sh"` with any trailing `/` stripped.
   - **Use the same transport context as `alert_bus/delivery.py`** (plan round 4): inherit `env` (pass `env=dict(env)`), and **no `-q`**.
   - `curl --silent --show-error --max-time 5 <url>`, where the URL in argv is fine because the probe carries no secret. Up to 2 attempts. Subprocess timeout 8.
   - The response must parse as JSON with `healthy is True`. Otherwise return `ntfy_unhealthy` or `probe_error`.
3. `delivered_ok` is False: return `undelivered`.

Never raises.

### T004 – Operator CLI and template

- **CLI:** `python3 -m scripts.common.deadman --label {canary,healthcheck} --outcome {success,fail}` calls `ping` and prints only `sent=<bool> reason=<reason>`. Exit 0 if sent, else 1.
- **`scripts/common/deadman.env.sample`:** placeholders `https://hc-ping.com/<uuid>` plus a comment covering the 0600 mode and the provisioning one-liner from `quickstart.md`.

### T005 – Tests (`tests/common/test_deadman.py`)

Inject `run` and `sleep` fakes; there is no network.
- **Unconfigured:** a missing file, or an empty file, gives `unconfigured` and `run` is never called.
- **Valid URL:**
  - Argv equals the exact list.
  - The URL is not in argv, and stdin carries `url = "<url>"`.
  - The env passed contains no URL and has only `PATH` and `LANG`.
  - `fail` hits `<url>/fail`.
  - A trailing slash is normalised.
- **Rejections**, each never calling `run`: `http://`, `?q=1`, `#f`, `user@host`, embedded whitespace or `"` or `\`, a final segment of `fail`, `start`, `log` or `0`, and length over 512.
- **Exit-code mapping:** 22, 28, 7, `TimeoutExpired` and `FileNotFoundError` each map to their reason. Retry happens once with `sleep(2)`, and never after success.
- **Totality:** `run` raising arbitrary exceptions gives `error:<Class>`.
- **Secrecy:** a sentinel URL never appears in captured stderr or stdout (capsys) in any branch, including errors.
- **Hostile curl config:** run the real `curl -q -K -` path once against `https://127.0.0.1:9/` with `HOME` and `CURL_HOME` pointing to a tmp dir whose `.curlrc` sets `trace-ascii` to a file. Assert no trace file appears. Skip if `curl` is absent.
- **`channel_ok`:**
  - topic missing gives `topic_missing` without calling `run`;
  - a probe returning `{"healthy":true}` gives ok;
  - false JSON or non-JSON gives `ntfy_unhealthy` or `probe_error`;
  - the probe's env equals the env passed in, with proxy variables preserved (the round-4 transport match);
  - `-q` is not in the probe argv;
  - `delivered_ok=False` gives `undelivered`.
- **CLI:** output never contains the URL.

## Definition of Done

`TMPDIR=/dev/shm .venv/bin/python3 -m pytest tests/common/test_deadman.py -q` passes, and the module imports cleanly.

## Risks

- The `-K` config quoting. Validation already forbids `"` and `\`; keep it that way.
- Never raise. Never log the URL.

## Reviewer guidance

- Grep the diff for any path where the URL could reach argv, the env, logs or an exception message.
- Run the hostile-curlrc test.
