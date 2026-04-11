# WP01 Migration Target Audit

**Mission:** 026-vault-path-registry-and-folder-renumber
**Work Package:** WP01 — Registry Extension and Deploy Wrapper
**Subtask:** T001 (+ T005 charter audit)
**Date:** 2026-04-11
**Author:** claude:opus-4-6 implementer (lane-a worktree)

## Methodology

Ran a repo-wide grep for the nine vault folder literals that mission 026 cares
about:

```bash
grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|\
05-Finance\|06-Journal\|07-Resources\|00-System" \
  scripts/ ai-agents/ CLAUDE.md \
  --include="*.md" --include="*.json" --include="*.py" --include="*.sh"
```

Per the WP01 prompt, excluded from the migration list:

- `.claude/worktrees/` — ephemeral agent worktrees
- `kitty-specs/` — mission history, workflow-managed
- `docs/archive/`, `docs/func-spec/` — historical archive
- `scripts/vault/paths.json` — registry data file (contains literal by design)
- `scripts/vault/README.md` — documentation examples
- `CLAUDE.md`'s single `_private/` boundary line (constitutional, stays
  hardcoded per C-001)
- Any `_private/` boundary-only hit in any file (constitutional carve-out)

Cross-referenced the file list against the four known OpenClaw agents in
`docs/constitution/AGENT-REGISTRY.md`: `felix-admin-capture`,
`felix-admin-escalation`, `felix-admin-habits`, `felix-admin-tasker` — all four
are represented in the audit, plus the `main/` and `main-patches/` support
directories.

Office2 agent directory naming was confirmed via `ssh office2-claude 'ls
/data/services/openclaw/'`:

```
data
escalation-agent
habits-agent
inbox-agent
secrets
tasker-agent
```

So the office2 deploy targets are:

| Repo agent dir | Office2 dir |
|---|---|
| `felix-admin-capture` | `/data/services/openclaw/inbox-agent/` |
| `felix-admin-tasker` | `/data/services/openclaw/tasker-agent/` |
| `felix-admin-escalation` | `/data/services/openclaw/escalation-agent/` |
| `felix-admin-habits` | `/data/services/openclaw/habits-agent/` |

---

## Category A — OpenClaw agent workspace files (WP02 will templatize)

These files contain non-`_private/` vault folder literals and are deployed to
office2 under `/data/services/openclaw/<agent-dir>/`. Each becomes a
`.tmpl` source file in WP02 and gets a `targets.json` entry with an
`office2_path`.

### felix-admin-capture

| File | Literals present | Notes |
|---|---|---|
| `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` | `00-Inbox`, `01-Constitution`, `02-Growth`, `03-Health`, `04-Business`, `05-Finance`, `06-Journal`, `07-Resources` | `.tmpl` already exists from mission 024. WP02 must extend the existing `.tmpl` to cover every folder literal now in the `.md` file (mission 024 shipped with just `inbox`). |
| `scripts/openclaw/agents/felix-admin-capture/USER.md` | `00-Inbox` (line 12) | New `.tmpl` in WP02. |
| `scripts/openclaw/agents/felix-admin-capture/SOUL.md` | `02-Growth/_private/` (line 57) ONLY | **Boundary-only hit — EXCLUDED.** No migration. Stays hardcoded. |
| `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` | `00-Inbox` (line 6), `02-Growth/_private/` (line 17) | Non-boundary hit present → WP02 creates a `.tmpl`. The `_private/` line stays hardcoded in the `.tmpl`. |

### felix-admin-tasker

| File | Literals present | Notes |
|---|---|---|
| `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` | `00-Inbox` (line 164), `02-Growth/_private/` (line 73) | New `.tmpl` in WP02. |
| `scripts/openclaw/agents/felix-admin-tasker/USER.md` | `02-Growth/_private/` (line 34) ONLY | **Boundary-only hit — EXCLUDED.** No migration. |
| `scripts/openclaw/agents/felix-admin-tasker/SOUL.md` | `02-Growth/_private/` (line 66) ONLY | **Boundary-only hit — EXCLUDED.** |
| `scripts/openclaw/agents/felix-admin-tasker/TOOLS.md` | `02-Growth/_private/` (line 39) ONLY | **Boundary-only hit — EXCLUDED.** |

### felix-admin-escalation

| File | Literals present | Notes |
|---|---|---|
| `scripts/openclaw/agents/felix-admin-escalation/SOUL.md` | `02-Growth/_private/` (line 55) ONLY | **Boundary-only — EXCLUDED.** |
| `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` | `02-Growth/_private/` (line 228) ONLY | **Boundary-only — EXCLUDED.** |
| `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md` | `02-Growth/_private/` (line 86) ONLY | **Boundary-only — EXCLUDED.** |

**Result for felix-admin-escalation: no migration targets.** Every vault-folder
hit in this agent is the `_private/` boundary, which stays hardcoded.

### felix-admin-habits

| File | Literals present | Notes |
|---|---|---|
| `scripts/openclaw/agents/felix-admin-habits/SOUL.md` | `02-Growth/_private/` (line 57) ONLY | **Boundary-only — EXCLUDED.** |
| `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` | `02-Growth/_private/` (line 440) ONLY | **Boundary-only — EXCLUDED.** |
| `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` | `02-Growth/_private/` (line 19) ONLY | **Boundary-only — EXCLUDED.** |

**Result for felix-admin-habits: no migration targets.** Same as escalation.

### main (base agent)

| File | Literals present | Notes |
|---|---|---|
| `scripts/openclaw/agents/main/USER.md` | `02-Growth/_private/` (line 17) ONLY | **Boundary-only — EXCLUDED.** |
| `scripts/openclaw/agents/main/SOUL.md` | `02-Growth/_private/` (line 147) ONLY | **Boundary-only — EXCLUDED.** |

`main/` is not deployed to office2 and has no non-boundary hits → no migration.

### main-patches

| File | Literals present | Notes |
|---|---|---|
| `scripts/openclaw/agents/main-patches/inbox-delegation.md` | `00-Inbox/` (line 16) | Non-boundary hit. This file is a delegation instruction patch text, not deployed to office2 directly but consumed by other agents at compose time. WP02 converts to `.tmpl` (repo-only, no `office2_path`). |

---

## Category B — Claude instruction files under `ai-agents/`

These files are consumed by Claude Code on the operator's Mac. They are
repo-only — no `office2_path`.

| File | Literals present | Notes |
|---|---|---|
| `ai-agents/claude-instructions.md` | `00-Inbox` (line 42), `01-Constitution/` (line 45), `02-Growth/_private/` (line 46) | Two non-boundary hits → WP02 creates `.tmpl`. Boundary line stays hardcoded. |
| `ai-agents/claude-code-instructions.md` | `00-Inbox/` (line 105), `02-Growth/_private/` (line 108) | One non-boundary hit → WP02 creates `.tmpl`. Boundary line stays hardcoded. |

---

## Category C — Top-level project config (`CLAUDE.md`)

| File | Literals present | Notes |
|---|---|---|
| `CLAUDE.md` | `02-Growth/_private/` (line 288) ONLY | **Boundary-only hit — EXCLUDED.** CLAUDE.md does not need a `.tmpl`. The `_private/` reference will be updated via a direct hardcoded rewrite in WP05 (from `02-Growth` to `04-Growth`), not via a template marker. |

**Result: CLAUDE.md has zero non-boundary hits — NO migration target entry.**
This matches the WP01 prompt's guidance that the `_private/` boundary line
stays hardcoded per C-001.

---

## Category D — Scripts referencing vault paths

Per the targets-schema contract § Category D, prefer the resolver refactor for
code. Neither file gets a `targets.json` entry — they are refactored to call
`get_vault_path(...)` at runtime in WP02.

| File | Literals present | Resolution strategy |
|---|---|---|
| `scripts/office2/validate-obsidian-sync.sh:43` | `00-Inbox` | WP02: refactor to `source scripts/vault/paths.sh` and use `$VAULT_INBOX`. |
| `scripts/openclaw/observation/config.py:22,30` | `00-System` (in docstring and default-path construction) | WP02: refactor to `from scripts.vault.resolver import get_vault_path` and use `get_vault_path("system")`. The docstring update is cosmetic. |

---

## Charter files (T005 audit)

Per the WP01 prompt, `.kittify/charter/` files are workflow-managed — **do not
edit directly**. Audit only:

```bash
grep -n "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|\
05-Finance\|06-Journal\|07-Resources\|00-System" \
  .kittify/charter/charter.md \
  .kittify/charter/directives.yaml \
  .kittify/charter/library/user-project-profile.md
```

### Findings

| File | Line | Literal | Category |
|---|---|---|---|
| `.kittify/charter/charter.md` | 47 | `02-Growth/_private/` | Boundary (excluded) |
| `.kittify/charter/charter.md` | 78 | `02-Growth/_private/` | Boundary (excluded) |
| `.kittify/charter/directives.yaml` | 11–12 | `02-Growth/_private/` | Boundary (excluded) |
| `.kittify/charter/library/user-project-profile.md` | 16 | `02-Growth/_private/` | Boundary (excluded) |

**Result: Every charter-file hit is the `_private/` boundary reference.**
There are no non-boundary vault folder literals in `.kittify/charter/`.

**Operator action required: NONE for WP01 or WP02.** The `_private/` references
in charter files will be updated in WP05 as part of the hardcoded-path rewrite
(from `02-Growth/_private/` to `04-Growth/_private/`), which requires the
operator to edit via `spec-kitty charter sync` (not a direct agent edit). The
WP05 runbook will include this step.

WP01 report statement:

> Charter files require no migration beyond the WP05 hardcoded-path update
> (`02-Growth/_private/` → `04-Growth/_private/`), which must be performed by
> the operator via `spec-kitty charter sync` rather than by any agent
> modifying `.kittify/` directly.

---

## Summary: WP02 migration target list

The files below need `.tmpl` sources in WP02 and `targets.json` entries in
WP01:

1. `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — **extend existing
   `.tmpl` from mission 024** (entry already in `targets.json`; WP02 extends
   markers)
2. `scripts/openclaw/agents/felix-admin-capture/USER.md` — new
3. `scripts/openclaw/agents/felix-admin-capture/TOOLS.md` — new
4. `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` — new
5. `scripts/openclaw/agents/main-patches/inbox-delegation.md` — new, repo-only
6. `ai-agents/claude-instructions.md` — new, repo-only
7. `ai-agents/claude-code-instructions.md` — new, repo-only

Plus the two Category D script refactors (no target entries):

8. `scripts/office2/validate-obsidian-sync.sh` — shell refactor (WP02)
9. `scripts/openclaw/observation/config.py` — python refactor (WP02)

**Total target entries in `targets.json` after WP01:** 7 (1 preserved from
mission 024 + 6 new entries for files 2–7 above).

**Total non-entry migrations in WP02:** 2 (script refactors).

---

## T006 verification results (run at WP01 completion)

Populated after the registry/targets/wrapper are in place. See the WP01
completion report in the implementer's status update for the full verification
transcript.

- [x] `python3 -m json.tool scripts/vault/paths.json` succeeds
- [x] `python3 -m json.tool scripts/vault/targets.json` succeeds
- [x] `python3 scripts/vault/resolver.py <each of 10 logical names>` returns a
      path
- [x] `python3 scripts/vault/resolver.py _private` exits non-zero with
      `UnknownPathError`
- [x] `source scripts/vault/paths.sh && echo "$VAULT_INBOX_PROCESSED"` prints
      the target path
- [x] `scripts/deploy/deploy-f026.sh --help` exits 0
- [x] `scripts/deploy/deploy-f026.sh` (no flags) defaults to dry-run and exits 0
- [x] `scripts/deploy/deploy-f026.sh --apply` (no mode) exits non-zero with
      clear error
- [x] `scripts/deploy/deploy-f026.sh --apply --mode invalid` exits non-zero

Note on `python3 scripts/vault/deploy.py` dry-run: because the new `.tmpl`
source files do not yet exist (WP02 will create them), invoking `deploy.py`
against the extended `targets.json` will report missing templates. This is the
expected, documented state at the WP01/WP02 boundary — see WP01 prompt step
T003.6 and verification-contract § WP01 smoke note.
