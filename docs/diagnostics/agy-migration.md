---
id: agy-migration-audit
doc_type: diagnostic
title: agy (Antigravity) migration audit
status: open
last_updated: '2026-05-21'
updated_by: 'post-#309 cycle'
version: '1.0.0'
---

# agy (Antigravity) migration audit

**Triggered by**: Kent's 2026-05-21 mid-#309 message announcing migration from `gemini-cli` to Google Antigravity (`agy`) ahead of gemini-cli's reported 2026-06-18 deprecation. He bound his paid business API key in `~/.zshrc` and asked for a post-cycle audit + automation update.

**Scope**: read-only inventory of every `gemini` reference across dispatch surfaces, validation of agy's actual CLI behavior, and a split-by-owner action plan. No automation changes applied in this audit — recommendations below.

---

## 1. System state findings (verified on Kent's Mac)

| Item | Finding |
|---|---|
| `which agy` | `/usr/local/bin/agy` (v1.0.1) |
| `which gemini` | `/usr/local/bin/gemini` (v0.42.0) **still present** — Kent reported he had uninstalled it; the binary is still on PATH |
| `~/.zshrc` API-key binding | `export GEMINI_API_KEY="..."` set by the Antigravity CLI installer comment block |
| Auth path used at runtime | Env-var API key → project `gen-lang-client-0552426899` (a Google AI Studio key project, NOT a Workspace-OAuth project) |
| Required Google Cloud API | `aiplatform.googleapis.com` — was NOT enabled at audit time; Kent enabled mid-session and agy unblocked within ~10 minutes |
| Stray broken config | `~/.gemini/config/mcp_config.json` — "unexpected end of JSON input" per agy startup logs. Non-blocking but noise. |
| Antigravity local marker | `kg-automation/.antigravitycli/` directory exists; contains a symlink `<project-uuid>.json → /Users/kentgale/.gemini/config/projects/<uuid>.json` |

### Earlier OAuth misread (corrected here)

Initial probe interpretation suggested agy was using gcp keyring OAuth (kent@intentional.biz), not the env-var API key. That was wrong. The `ChainedAuth: authenticated via keyring (effective: gcp)` and `email=kent@intentional.biz` log lines are fallback-path probes that run during init before the env-var key path is tried. Evidence the env var is the active credential: the 403 PERMISSION_DENIED resolved when `aiplatform.googleapis.com` was enabled on `gen-lang-client-0552426899` specifically — a Workspace-OAuth route would have hit a different project. Google's `google-cloud-go` credential resolution prioritizes explicit env vars over keychain OAuth.

**Conclusion**: paid plan is being charged correctly. No auth fix needed.

---

## 2. Working agy dispatch syntax (verified during #309)

The legacy gemini-cli Tier-1 dispatch pattern was:

```bash
gemini -p "$PROMPT_CONTENT" --yolo --output-format json -C "$WORKSPACE"
```

The verified-working agy equivalent (used for WP05/WP06/WP07/WP09 reviews this mission):

```bash
agy -p "$PROMPT" \
    --add-dir "$WORKTREE" \
    --add-dir "$MAIN_REPO" \
    --dangerously-skip-permissions \
    --log-file /tmp/<slug>.log \
    --print-timeout 15m > /tmp/<slug>-out.txt 2>&1
```

Key differences from gemini-cli:

| gemini-cli flag | agy equivalent | Notes |
|---|---|---|
| `--yolo` | `--dangerously-skip-permissions` | Same intent (auto-approve), different name |
| `--output-format json` | _(no equivalent)_ | agy emits text only; structured response is interleaved with internal gRPC logs in `--log-file` |
| `-C <dir>` | `--add-dir <dir>` (repeatable) | Multiple `--add-dir` allowed; no equivalent of cd-to-workspace semantics |
| _(default behavior)_ | `--print-timeout 15m` | Default is 5m; long reviews need explicit timeout |
| `gemini -p` | `agy -p` or `agy --print` | Alias preserved |

### Performance note

agy reviews complete noticeably faster than codex reviews per Kent's observation in mission #309 and confirmed by direct comparison: WP05/WP06 cycle-2 agy reviews finished in single-digit minutes; codex reviews on earlier WPs took longer.

---

## 3. Files with legacy `gemini` references

All locations grepped for `gemini` across Kent's Mac home directory, the kg-automation repo, and the spec-kitty install location.

### A. Spec-kitty bundled skill files (upstream-owned)

Three locations on disk; all three are byte-identical copies (same size 26807, same mtime):
- `~/.agents/skills/spec-kitty-implement-review/SKILL.md`
- `~/.claude/skills/spec-kitty-implement-review/SKILL.md`
- `/Users/kentgale/repos/kg-automation/.agents/skills/spec-kitty-implement-review/SKILL.md`

Lines referencing `gemini` (same in all three copies):

```
65:  | Google Gemini | `gemini` | `gemini -p "prompt" --yolo --output-format json` | Yes | 1 |
223: gemini -p "$PROMPT_CONTENT" --yolo --output-format json -C "$WORKSPACE"
347: # Example for gemini:
348: gemini -p "$(cat /tmp/review-prompt-WP##.md)" --yolo --output-format json -C "$WORKTREE"
```

These are the **load-bearing** references — the implement-review skill is the orchestrator's source of truth for how to dispatch a fallback reviewer when codex hits its quota. With gemini-cli being deprecated, this path needs an agy alternative or it will silently fail in future missions.

### B. Other spec-kitty bundled references (upstream-owned)

| File | Line | Reference |
|---|---|---|
| `~/.claude/skills/spec-kitty-implement-review/references/agent-dispatch-matrix.md` | 14 | Agent matrix row for "Google Gemini" |
| `~/.claude/skills/spec-kitty-orchestrator-api-operator/SKILL.md` | 99 | `agent_family` enum lists `gemini` |
| `~/.claude/skills/spec-kitty-orchestrator-api-operator/references/orchestrator-api-contract.md` | 155 | Same enum docs |
| `~/.claude/skills/spec-kitty-setup-doctor/references/agent-path-matrix.md` | 16 | Tool path matrix row for "Gemini CLI" |

### C. Spec-kitty commands (upstream-owned)

| File | Line | Reference |
|---|---|---|
| `~/.claude/commands/spec-kitty.charter.md` | 113 | Lists `.gemini/` among agent wrapper directories — minor; needs `.antigravitycli/` (or equivalent) added |

### D. kg-automation repo (project-owned, safe to patch)

| File | Line | Reference |
|---|---|---|
| `.kittify/config.yaml` | `agents.available:` | Lists `gemini` (not `agy`) |
| `scripts/install-gemini-cli.sh` | All | Helper script installing gemini-cli. Reasonable candidates: delete (gemini is being deprecated) OR rename to `scripts/install-agy.sh` + rewrite. Not blocking. |

---

## 4. Spec-kitty upstream status

| Check | Result |
|---|---|
| `spec-kitty --version` | 3.1.8 (active CLI) |
| `pip show spec-kitty-cli` | Version 3.1.1 reported by pip (mismatch — spec-kitty probably self-updates internally) |
| Latest on PyPI | 3.1.9, released 2026-05-21 13:27 UTC (~5 hours before this audit) |
| PyPI 3.1.9 description grep | No `agy`/`antigravity`/`AGY` references |
| `spec-kitty changelog` command | Does not exist |

**Conclusion**: spec-kitty 3.1.8 (and the just-released 3.1.9) do NOT yet support agy. The implement-review skill's dispatch matrix has no agy row.

---

## 5. Recommendations (split by ownership)

### Upstream — file with spec-kitty maintainer

The spec-kitty bundled files in §3A + §3B + §3C must be patched upstream because:
1. They are reinstalled on every `spec-kitty` upgrade — local patches would be overwritten.
2. Per Kent's standing rule (memory `feedback_no_workarounds_for_expediency.md`): "default to canonical/package-managed install paths; manual binaries and 'remember to update later' scripts create invisible debt."

Proposed upstream contribution:
- Add `agy` row to the agent dispatch matrix (Tier 1) with the verified syntax in §2 above
- Add `agy` entry to the orchestrator-api-operator `agent_family` enum
- Add `agy` entry to setup-doctor's tool path matrix (paths: `~/.agents/skills/` + `.agy/skills/` if applicable)
- Add `.antigravitycli/` to the agent wrapper directories list in `spec-kitty.charter.md`
- Optionally: rename "Google Gemini → `gemini`" rows to "Google Gemini (legacy)" + add a deprecation note

The upstream repository is not obvious from PyPI metadata; need to identify the right contribution surface (GitHub repo, issue tracker, or maintainer contact). Kent: where should I file this?

### Project-local — can patch immediately

- **`.kittify/config.yaml`**: add `agy` to `agents.available`. No mission state depends on this; safe one-line change.
- **`scripts/install-gemini-cli.sh`**: defer. Either delete after gemini deprecation lands (2026-06-18 per Kent's reported timeline) or rewrite as `install-agy.sh`. Not blocking.

### Environment cleanup

- **`/usr/local/bin/gemini`**: still installed. Kent intended to uninstall. Confirm whether to remove now or leave until 2026-06-18 deprecation.
- **`~/.gemini/config/mcp_config.json`**: broken JSON, repair or remove.
- **`~/.zshrc` API-key cleanup**: the env-var binding works; no action needed for billing correctness (per §1's corrected understanding).

---

## 6. Open questions

1. **Where to file the upstream spec-kitty contribution?** PyPI metadata doesn't list a repo URL. Need Kent to point me at the right place (GitHub repo, issue tracker, Discord, etc.) OR I can probe further via `pip show` URL fields.
2. **Should I patch the spec-kitty skill files locally as a stopgap** while waiting on upstream? Pro: future missions get an agy fallback path now. Con: local patches will be silently overwritten on next `spec-kitty upgrade` (memory `feedback_no_workarounds_for_expediency.md`: invisible debt).
3. **Should `scripts/install-gemini-cli.sh` be deleted or renamed?** Tied to whether gemini-cli stays installed past 2026-06-18.
4. **`.agy/skills/` directory** — agy may install its own skills root analogous to `~/.agents/skills/`. Not present yet. Worth checking the agy docs for the canonical location.

---

## Cross-references

- Memory: [`project_gemini_cli_paid_tier_misconfig.md`](../../~/.claude/projects/-Users-kentgale-repos-kg-automation/memory/project_gemini_cli_paid_tier_misconfig.md) — running notes from the in-mission probe
- Mission #309: this migration was deferred to post-cycle per Kent's instruction
- Spec-kitty implement-review skill: `~/.claude/skills/spec-kitty-implement-review/SKILL.md`
- The `agy --help` output (full verified surface) is captured in the working dispatch syntax in §2.
