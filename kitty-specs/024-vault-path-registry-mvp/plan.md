# Implementation Plan: Vault Path Registry MVP

**Branch**: `main` | **Date**: 2026-04-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/024-vault-path-registry-mvp/spec.md`
**Source Issue**: #150

## Summary

Build a small set of Python/shell tools that centralize vault path definitions in a JSON registry. The tools use template expansion (`.tmpl` → resolved file) to eliminate hardcoded paths at build time without adding runtime cost to agents. MVP migrates ONE hardcoded inbox path reference as a proof of methodology.

## Technical Context

**Language**: Python 3.13 (standard library only) + POSIX shell (bash/zsh compatible)
**Dependencies**: `jq` (already on both Mac and office2) for the shell resolver
**Deployment targets**: Repo checkout on Mac + office2 agent workspace via SCP
**Change control**: Tier 3 (scripts/logic) on Mac; Tier 3 when pushing resolved files to office2
**Testing strategy**: Manual verification — diff resolved file vs original, trigger inbox agent post-migration

## Research Findings

Resolved through live inspection:

| Question | Answer | Source |
|---|---|---|
| `jq` on Mac? | Yes, `/usr/local/bin/jq` | `which jq` |
| `jq` on office2? | Yes, `/usr/bin/jq` v1.7 | SSH + `which jq` |
| Existing `scripts/` layout | `scripts/<concern>/` pattern (openclaw/, vikunja/, google/, etc.) | `ls scripts/` |
| Existing `.tmpl` files? | None — we're establishing the convention | `find . -name '*.tmpl'` |
| Existing `{{VAULT_` patterns? | None — no collision risk | `grep -r '{{VAULT_'` |
| Inbox path occurrences in target file | 4 total: 1 absolute (line 22), 3 relative filename references | grep of AGENTS.md |
| Python version | 3.13.13 | `python3 --version` |

**Decision: migrate only the absolute path on line 22.** The other three occurrences are relative filename references (`00-Inbox/filename.md`) that describe the folder name, not a path template. They'll be handled in the follow-up feature (#152) when folder renaming is in scope.

**No research.md needed** — all unknowns resolved through live discovery.

## Implementation Approach

### Directory layout

```
scripts/vault/
├── paths.json                    # Registry — source of truth
├── resolver.py                   # Python API: get_vault_path(name)
├── paths.sh                      # Shell API: source → $VAULT_INBOX
├── deploy.py                     # Build script: .tmpl → resolved files
├── README.md                     # Schema + usage documentation
└── targets.json                  # List of .tmpl → target file mappings
```

### paths.json schema (MVP)

```json
{
  "version": 1,
  "paths": {
    "inbox": "/home/kgale/second-brain/notes/00-Inbox"
  }
}
```

`version` enables future schema evolution. `paths` is the lookup table.

### Python resolver (`resolver.py`)

- `get_vault_path(name: str) -> str` — reads paths.json, returns resolved path
- Raises `KeyError` with available names if lookup fails
- Raises `FileNotFoundError` if registry missing
- Module can be imported: `from scripts.vault.resolver import get_vault_path`
- Uses Python standard library only (`json`, `pathlib`)

### Shell resolver (`paths.sh`)

- Sourceable: `source scripts/vault/paths.sh`
- Uses `jq` to parse `paths.json` and export `VAULT_*` env vars
- After sourcing, `$VAULT_INBOX` contains the resolved path
- Silent on success, errors to stderr with non-zero return

### Deploy script (`deploy.py`)

- Reads `paths.json` and `targets.json`
- `targets.json` lists template→output mappings:
  ```json
  {
    "targets": [
      {
        "template": "scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl",
        "output": "scripts/openclaw/agents/felix-admin-capture/AGENTS.md",
        "office2_path": "/data/services/openclaw/inbox-agent/AGENTS.md"
      }
    ]
  }
  ```
- For each target:
  1. Read template
  2. Find all `{{VAULT_<NAME>}}` markers
  3. Verify every marker has a corresponding registry entry (fail with clear error if not)
  4. Replace markers with resolved paths
  5. In dry-run mode: print diff, don't write
  6. In apply mode: write to local output path, then SCP to office2 path if set
- Usage: `python3 scripts/vault/deploy.py` (dry-run default) or `--apply`

### Migration of felix-admin-capture AGENTS.md

1. Copy current `AGENTS.md` to `AGENTS.md.tmpl`
2. In `.tmpl`, replace line 22's `/home/kgale/second-brain/notes/00-Inbox/` with `{{VAULT_INBOX}}/`
3. Add entry to `targets.json`
4. Run deploy in dry-run → verify diff shows only the expected change
5. Run deploy with `--apply` → writes resolved `AGENTS.md` locally + SCP to office2
6. Trigger inbox agent cron run → verify normal operation

## Project Structure

### Files Created

```
scripts/vault/
├── paths.json
├── resolver.py
├── paths.sh
├── deploy.py
├── targets.json
└── README.md

scripts/openclaw/agents/felix-admin-capture/
└── AGENTS.md.tmpl   (new; source of truth for the resolved .md)
```

### Files Modified

```
scripts/openclaw/agents/felix-admin-capture/AGENTS.md
  (will be regenerated by deploy.py from .tmpl; functionally identical to current)

/data/services/openclaw/inbox-agent/AGENTS.md (on office2)
  (SCP'd from repo after deploy)
```

## Risk Mitigation

| Risk | Mitigation | Phase |
|---|---|---|
| Template marker collision | Verified no existing `{{VAULT_` patterns; using distinctive prefix | Research |
| Deploy corrupts target | Dry-run default; atomic write via temp file + rename | Implementation |
| Resolved file drifts from .tmpl | Header comment in resolved files warning "generated from X.tmpl" | Implementation |
| Office2 path differs from repo path | `targets.json` lets us map repo template → different office2 destination | Design |
| Inbox agent regression post-migration | Trigger a run, check session log for errors | Verification |

## Charter Check

Charter references `test-first` paradigm which is not available in this project's doctrine. For this MVP, tests are manual verification (diff + agent trigger) — not automated pytest. This is acceptable for a small scripting MVP where the outputs are directly observable (diff vs original, agent run result).

## Branch Contract

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **true**

---

**PLAN COMPLETE** — Ready for `/spec-kitty.tasks --mission 024-vault-path-registry-mvp`
