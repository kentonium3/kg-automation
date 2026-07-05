# Data Model: Felix-admin cron path robustness fix

This mission has no schema changes. The "data model" here is the set of
**path-resolved artifacts** the agents produce/consume and the **resolution
rules** that must hold. Recorded so the path contract is explicit and testable.

## Entities

### E1 — Dedup ledger (`inbox-routing.jsonl`)

- **Shape**: append-only JSONL; one `RoutingEntry` per line
  (`filename`, `issue_number`, `vikunja_task_id`, `routed_at` ISO-8601 Z, `note_excerpt`).
- **Producer**: `scripts/inbox/append_routing_entry` (writer) via `routing_log.py`.
- **Consumer**: `RoutingLogReader.routed_filenames()` (dedup check each tick).
- **Location — before**: `/home/claude/second-brain/agents/state/inbox-routing.jsonl` (wrong; `Path.home()` = `/home/claude`).
- **Location — after**: `/data/services/openclaw/state/inbox-routing.jsonl`.
- **Invariant**: relocation must not cause any already-routed filename to be re-routed (SC-3). Reader is fail-safe: missing file → empty set.

### E2 — Calendar clarification state (`pending-calendar-clarifications.json`)

- **Shape**: JSON object keyed by note filename → partial payload + timestamp; swept at 24h.
- **Producer/Consumer**: `scripts/inbox/handle_clarification_state.py` (`add`/`match`/`sweep`).
- **Location — before**: `/home/claude/second-brain/agents/state/pending-calendar-clarifications.json`.
- **Location — after**: `/data/services/openclaw/state/pending-calendar-clarifications.json`.
- **Invariant**: an in-flight clarification pending across the migration must still `match` after the move (no lost clarifications).

### E3 — Forensic log (`inbox-prescan-YYYY-MM-DD.md`)

- **Shape**: human-readable per-run Markdown record of prescan decisions.
- **Producer**: `scripts/inbox/prescan.py` (`DEFAULT_LOG_DIR`).
- **Consumer**: Kent, via Obsidian sync on phone/Mac.
- **Location — before**: `/home/claude/second-brain/agents/logs/` (unsynced).
- **Location — after**: `/home/kgale/second-brain/agents/logs/` (Obsidian-synced).
- **Invariant**: new logs appear under the vault and sync (SC-4); historical logs preserved during migration (FR-008).

### E4 — Import-path environment (the guardrail)

- **Shape**: `PYTHONPATH=/home/claude/kg-automation` exported by `openclaw-gateway.service`.
- **Producer**: systemd (unit `Environment=` line), inherited by all agent subprocesses.
- **Consumer**: every `python3 -m scripts.*` invocation in every agent.
- **Invariant**: `import scripts` succeeds from any cwd (SC-1, NFR-002).

## Path-resolution rules (must hold after this mission)

| Rule | Statement |
|------|-----------|
| PR-1 | No agent-consumed path may resolve through `~` / `HOME` for a location owned by a *different* user. State + logs use absolute anchors. |
| PR-2 | Agent state (machine-readable, not for the vault) lives under `/data/services/openclaw/state/`. |
| PR-3 | Agent forensic output meant for Kent lives under `/home/kgale/second-brain/agents/…` (the synced vault). |
| PR-4 | `scripts` package import must not depend on cwd (satisfied by E4). |
| PR-5 | No writer may target `/home/claude/second-brain/*` after this mission (SC-5). |

## State transition — the migration (one-time)

```
[stray dir live]                       [snapshot verified]
  /home/claude/second-brain/     --->    (restic ≤24h, C-003)
    agents/state/*.{jsonl,json}                 |
    agents/logs/*.md                            v
                                        [copy state → /data/services/openclaw/state/]
                                        [preserve logs → /home/kgale/second-brain/agents/logs/]
                                                |
                                                v
                                        [post: assert new paths present]
                                                |
                                                v
                                        [decommission /home/claude/second-brain]  (SC-5)
```

Cutover safety: reader fail-safe (missing→empty) + note `status: processed`
frontmatter bound the worst case during the window (see research R5 / IC-05).
