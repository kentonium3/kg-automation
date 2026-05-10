# TOOLS.md — felix-doc-auditor

## Allowed tools

- **`gh` CLI** — all GitHub interactions: issue list, view, create, comment,
  edit (label add/remove), close. Per repo convention `gh` is used because
  MCP GitHub auth is unreliable. The `gh` CLI is installed and authenticated
  on office2 with `issues: write` scope (A-002 in spec).
- **Standard file I/O** — read all docs in scope (E-002 / E-003 sources);
  write to docs that pass the high-confidence threshold defined in the
  doc-audit skill.
- **`git`** — local commit and push for approved high-confidence edits.
  Pattern: `git add <files>` → `git commit -m <message>` (per
  `contracts/commit-message.template.md`) → `git pull --rebase origin main`
  → `git push origin main`.
- **OpenClaw send-message** — outbound WhatsApp messages for Level 1
  approval requests. Pattern matches felix-admin-habits.
- **`TZ=America/New_York date`** — all date/timestamp computation. office2
  runs UTC; without the TZ prefix dates after 8 PM ET resolve to the wrong
  calendar day.

## Resource references

### Skill (loaded at the start of every audit)

- `~/.openclaw/skills/doc-audit/SKILL.md` — encodes the audit logic,
  confidence thresholds, comparison rules, commit message format, and
  per-doc error handling. Self-contained: a full audit can be run using only
  this skill plus the domain map.

### Domain map (the scope contract)

- `docs/design/architecture/data/doc-domain-map.json` — read on every audit.
  Maps `area/*` label name → array of doc paths. The audit issue's `area/*`
  labels select which domains apply. If the audit issue has no `area/*`
  labels (typical for weekly audits), use the full domain map (full-scope).
  Per C-005, the domain map is the authority on what's in scope.

### System state sources (read-only)

These are the "current state" against which docs are compared. Never
mutated by this agent.

| Source | Path | Used to verify |
|---|---|---|
| Service inventory | `docs/design/architecture/data/service-inventory.json` | Service entries, versions, dependencies, status |
| Agent registry | `docs/constitution/agent-registry.json` | Agent autonomy levels, transition history |
| Hardware inventory | `docs/design/architecture/data/hardware-inventory.json` | Host hardware, OS, GPU, kernel |
| Network topology | `docs/design/architecture/data/network-topology.json` | Network bindings, ports |
| Credential manifest | `docs/design/architecture/data/credential-manifest.json` | Credentials inventory |
| Data flows | `docs/design/architecture/data/data-flows.json` | Data flow definitions |
| Doc index | `docs/INDEX.md` | Master doc index (used for missing-artifact detection) |
| Git log | local | Recent commits — prioritization and dead-reference detection |

When the JSON source and a narrative markdown view conflict, the JSON
source is authoritative per CLAUDE.md / Felix Constitution Directive 5
(Documentation Standards). Surface the narrative drift as a debt issue.

### Issue templates

- `.github/ISSUE_TEMPLATE/docs-debt.md` — template used for every
  `docs-debt` issue this agent creates. All six sections (Artifact, Gap
  description, Area, Cross-references, Draft outline, Success criteria)
  must be populated. The Draft outline must be specific enough to act on
  without further research (FR-003 success criterion).

### Activity log destination

- `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` —
  append one section per audit run. Format defined in AGENTS.md § 12.
  Consumed by `felix-core-digest` for cross-agent activity summaries
  (NFR-008).

## GitHub label (concurrency control per R-009)

- **`status:in-progress`** — applied when claiming an audit issue, removed
  on completion (success, failure, or skip). Cron query filters out issues
  already carrying this label so concurrent cron ticks don't double-process.
- Stale-lock recovery (>30 min): manual cleanup via
  `gh issue edit <#> --remove-label "status:in-progress"`. Documented in
  `docs/runbooks/doc-auditor-ops.md`.

## Disallowed tools and paths

These are absolute. The agent must refuse to read, write, reference, or log
any of the following regardless of trigger source.

### Tools

- **MCP GitHub** — use `gh` CLI per repo convention (C-007). MCP GitHub
  auth is unreliable in this environment.
- **`sudo` / privilege escalation** — the claude user has no sudo. If a
  step appears to require sudo, halt and surface the requirement in the
  audit summary's "Items requiring human review" section.
- **`rm -rf` or any destructive non-reversible operation** — per C-004,
  all operations must be reversible. File edits go through git
  (revertible); issue mutations are reversible via `gh`.

### Paths

- **`~/second-brain/notes/04-Growth/_private/`** — never read, write,
  reference, or log. Privacy boundary C-003.
- **`docs/constitution/FELIX-CONSTITUTION.md`** — never edited (C-002).
  If an audit's scope appears to require a Constitution edit, file a debt
  issue and surface the conflict.
- **`CLAUDE.md` (any path)** — never edited (C-002). CLAUDE.md is an
  agent-instruction document; only Kent edits these.
- **`.env`, `credentials.json`, anything under a path that looks like a
  secret store** — never read or written (C-002).
- **`kitty-specs/` and `.kittify/`** — owned by spec-kitty. Never written.
  Reading for context is permitted (the mission spec, contracts, etc. are
  here) but no edits, moves, or deletions.
- **Any doc not in `doc-domain-map.json`** — out of scope per C-005. Even
  if the doc obviously needs an edit, the agent does not touch it. File a
  debt issue against the domain map if a domain is missing.
