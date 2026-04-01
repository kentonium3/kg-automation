---
work_package_id: WP02
title: Intelligence Layer
lane: "doing"
dependencies: []
requirement_refs:
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 1166c44659920564f30a4e55274d0bec7aab7cab
created_at: '2026-04-01T22:25:23.920555+00:00'
subtasks: [T005, T006, T007, T008, T009, T010]
shell_pid: "56766"
agent: "claude"
history:
- date: '2026-04-01T22:12:34Z'
  event: created
  agent: claude
priority: P1
---

# WP02: Intelligence Layer

## Implementation Command

```bash
spec-kitty implement WP02 --base WP01
```

Depends on WP01 — needs agent-registry.json schema and constitution to exist.

## Objective

Build the centralized summarization script (`scripts/openclaw/observation/`) that reads standardized agent logs, applies autonomy-level-based filtering, writes Obsidian digests to the vault, and sends WhatsApp critical alerts when warranted.

Test-first per the TEST_FIRST directive.

## Context

- **Spec**: FR-008 through FR-013
- **Plan**: Intelligence Layer Architecture section
- **Data Model**: Structured Activity Log, Surfaced Digest, Log Categories
- **Research**: Decisions 1 (delivery), 2 (cadence), 3 (time window), 4 (retention), 5 (architecture)

**Key design decisions:**
- Centralized script, not per-agent — reads all logs, produces unified digest
- Runs daily at 7:00 PM ET via cron on office2
- Reads `agent-registry.json` for each agent's autonomy level
- Surfacing rules: Assisted/Observed = all activity; Autonomous = exceptions only
- Critical alerts always surfaced at every level
- Obsidian primary (overview.md + per-agent files), WhatsApp for critical alerts only
- Rolling 24-hour window, digest overwritten each cycle

## Subtask T005: Define Standardized Log Format and Create Test Fixtures

**Purpose**: Establish the log format specification that all agents must follow, and create sample log files for testing the intelligence layer.

**Log format specification** (document in a comment block at the top of `summarize.py` or in a separate `LOG_FORMAT.md`):

Based on existing felix-admin-capture log format at `~/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`:

```markdown
---
domain: resources
type: log
updated: YYYY-MM-DD
status: reference
---

# Agent activity log — YYYY-MM-DD HH:MM

**Agent**: felix-admin-capture
**Run time**: YYYY-MM-DD HH:MM ET

## Actions taken
- [routine] Scanned inbox: 2 files found
- [routine] Processed Inbox 2026-04-01 0712.md — classified 3 blocks
- [routine] Updated 03-Health/Conditioning.md (appended 180 words)
- [routine] Created Vikunja task #234 "Schedule car repair" (personal)
- [flagged] Potential goal: "I want to do a triathlon" — missing date and evidence
- [error] Failed to update 04-Finance/Budget.md — file locked

## Summary
- Files processed: 2
- Notes created: 0
- Notes updated: 1
- Tasks created: 1
- Items flagged: 1
- Errors: 1
```

**Key additions to existing format:**
- Category tags on each action: `[routine]`, `[flagged]`, `[error]`, `[security]`
- Agent name in log header
- Summary section with counts

**Create test fixtures** at `scripts/openclaw/observation/tests/fixtures/`:

| Fixture | Content | Tests |
|---------|---------|-------|
| `capture-routine.md` | Normal successful run, all routine actions | Routine filtering, count summarization |
| `capture-flagged.md` | Run with flagged items (potential-goals, needs-review) | Flagged item elevation |
| `capture-error.md` | Run with errors | Critical alert detection |
| `capture-security.md` | Run with security concern | Critical alert detection |
| `habits-routine.md` | Normal habits check-in | Multi-agent consolidation |
| `habits-mixed.md` | Check-in with a flagged pattern | Cross-agent digest |

Each fixture must follow the standardized log format exactly. Use realistic content based on what the actual agents produce.

**Files to create:**
- `scripts/openclaw/observation/tests/fixtures/` (directory)
- 6 fixture files as described above

## Subtask T006: Write test_summarize.py (Test-First)

**Purpose**: Write tests before implementation per the TEST_FIRST directive.

**File**: `scripts/openclaw/observation/tests/test_summarize.py`

**Test cases to implement:**

```python
# Test categories:

# 1. Log parsing
def test_parse_single_log_file():
    """Parse a fixture log and extract agent name, actions, categories, summary."""

def test_parse_log_extracts_categories():
    """Each action line tagged [routine], [flagged], [error], [security] is categorized correctly."""

def test_parse_log_handles_missing_category_tag():
    """Actions without category tags default to [routine]."""

# 2. Autonomy-level filtering
def test_assisted_surfaces_all_categories():
    """At assisted level, routine (as counts), flagged, error, security all appear in digest."""

def test_observed_surfaces_all_categories():
    """At observed level, same as assisted — all categories surfaced."""

def test_autonomous_omits_routine():
    """At autonomous level, routine actions are omitted. Flagged/error/security still surfaced."""

# 3. Digest generation
def test_generate_overview_consolidates_agents():
    """Overview.md contains sections for all agents with activity."""

def test_generate_per_agent_detail():
    """Per-agent file contains that agent's full digest."""

def test_digest_includes_log_reference():
    """Every digest section includes a reference to the full audit log path."""

def test_routine_summarized_as_counts():
    """Routine actions appear as 'N files processed, M tasks created' not individual lines."""

def test_flagged_items_elevated_with_detail():
    """Flagged items appear with full description, not just a count."""

# 4. Critical alerts
def test_error_triggers_critical_alert():
    """Any [error] action sets the critical_alert flag."""

def test_security_triggers_critical_alert():
    """Any [security] action sets the critical_alert flag."""

def test_routine_does_not_trigger_critical_alert():
    """Routine and flagged actions do not trigger critical alerts."""

# 5. Config
def test_load_registry_reads_autonomy_levels():
    """Config loads agent-registry.json and returns autonomy level per agent."""

def test_load_registry_handles_missing_file():
    """Missing registry file raises clear error, not silent failure."""
```

**Testing approach:**
- Use fixture files from T005
- Mock file system paths to point to fixtures directory
- No external dependencies (no SSH, no WhatsApp, no Obsidian)
- Each test is independent and can run in isolation

**File**: `scripts/openclaw/observation/tests/__init__.py` (empty)
**File**: `scripts/openclaw/observation/__init__.py` (empty)

## Subtask T007: Write config.py

**Purpose**: Configuration module that loads agent-registry.json and resolves paths.

**File**: `scripts/openclaw/observation/config.py`

**Responsibilities:**
- Load `agent-registry.json` from a configurable path (default: `docs/constitution/agent-registry.json` relative to repo root, but overridable for office2 deployment where it lives elsewhere)
- Return a dict mapping agent name → autonomy level
- Resolve paths:
  - Log directory: `~/second-brain/agents/logs/` (on office2)
  - Output directory: `~/second-brain/notes/00-System/agent-activity/` (on office2)
  - Registry path: configurable
- Validate registry structure (version, agents dict present)
- Raise clear errors for missing files or malformed JSON — never fail silently

**Example interface:**

```python
class ObservationConfig:
    def __init__(self, registry_path=None, log_dir=None, output_dir=None):
        """Load config with optional path overrides (useful for testing)."""

    @property
    def agents(self) -> dict:
        """Return {agent_name: {"autonomy_level": "assisted", ...}}"""

    @property
    def log_dir(self) -> Path:
        """Resolved log directory path."""

    @property
    def output_dir(self) -> Path:
        """Resolved Obsidian output directory path."""

    def autonomy_level(self, agent_name: str) -> str:
        """Return autonomy level for agent. Raise if agent not in registry."""
```

## Subtask T008: Write summarize.py (Core Intelligence Layer)

**Purpose**: The main script that reads agent logs, applies filtering rules, and produces the Obsidian digest.

**File**: `scripts/openclaw/observation/summarize.py`

**High-level flow:**

```
1. Load config (agent-registry.json, paths)
2. Find today's log files in log_dir (pattern: *-YYYY-MM-DD.md)
3. For each log file:
   a. Parse log: extract agent name, actions with categories, summary counts
   b. Look up agent's autonomy level from registry
   c. Apply filtering rules:
      - Assisted/Observed: include all categories
      - Autonomous: include only flagged, error, security
   d. Format routine actions as counts
   e. Format flagged/error/security with full detail
   f. Track whether any critical alerts exist (error or security items)
4. Generate overview.md — consolidated across all agents
5. Generate per-agent detail files
6. If critical alerts exist: trigger WhatsApp alert (T009)
7. Write all output files to output_dir
```

**Digest output format for overview.md:**

```markdown
# Agent Activity — 2026-04-01

*Generated: 2026-04-01 19:00 ET | Window: last 24 hours*

## felix-admin-capture (Assisted)

**Routine**: 4 notes processed, 6 tasks created, 2 vault updates (3 runs)

**Attention needed:**
- ⚠ Potential goal: "I want to do a triathlon" — missing date and evidence
  *Source: Inbox 2026-04-01 0712.md*

**Full log**: `agents/logs/inbox-processing-2026-04-01.md`

## felix-admin-habits (Assisted)

**Routine**: 7 habits checked, 5 completed, 2 pending

**Full log**: `agents/logs/habits-checkin-2026-04-01.md`

---
*No critical alerts today.*
```

**CLI interface:**

```bash
python summarize.py                    # Normal run (today's logs)
python summarize.py --date 2026-04-01  # Specific date
python summarize.py --dry-run          # Parse and print, don't write files
```

**Error handling:**
- Missing log directory: log warning, produce empty digest with note "No log directory found"
- No log files for today: produce digest with "No agent activity recorded today"
- Malformed log file: skip file, log error, include note in digest
- Missing registry: fail with clear error message
- Never fail silently — every error path produces output

## Subtask T009: Add WhatsApp Critical Alert Path

**Purpose**: When the intelligence layer detects error or security items, send a brief WhatsApp alert pointing to the Obsidian digest for detail.

**Integration point**: Add to `summarize.py` after digest generation.

**Alert format:**

```
🚨 Felix Alert — 2026-04-01

felix-admin-capture: 1 error
  "Failed to update 04-Finance/Budget.md — file locked"

Check Obsidian: 00-System/agent-activity/overview.md
```

**Implementation notes:**
- WhatsApp sending mechanism: use OpenClaw's existing WhatsApp channel via the `exec` tool or a direct Baileys API call. Research the current WhatsApp integration in `scripts/openclaw/` or `docs/handbooks/openclaw-ops.md` for the correct send mechanism.
- **Conditional on DM policy**: Check if WhatsApp DM policy is enabled before attempting to send. If disabled, log that WhatsApp alert was skipped and ensure the critical alert is prominently marked in the Obsidian digest instead.
- Keep messages under 5 lines — WhatsApp is for notification, not detail.
- Include pointer to Obsidian digest for full context.

**Graceful degradation**: If WhatsApp send fails (Baileys error, DM disabled, network issue), log the failure but do NOT fail the overall summarization. The Obsidian digest is the primary channel.

## Subtask T010: Implement Obsidian Digest Output

**Purpose**: Write the consolidated digest and per-agent detail files to the Obsidian vault.

**Output directory**: `~/second-brain/notes/00-System/agent-activity/`

**Files to write:**

| File | Content |
|------|---------|
| `overview.md` | Consolidated digest across all agents (see T008 format) |
| `felix-admin-capture.md` | Detail for capture agent only |
| `felix-admin-habits.md` | Detail for habits agent only |

**Per-agent detail format:**

```markdown
# felix-admin-capture — 2026-04-01

*Autonomy Level: Assisted | Runs today: 3*

## Run 1 — 07:15 ET
**Routine**: 1 note processed, 2 tasks created, 1 vault update
**Flagged**: Potential goal needs attention (see below)

## Run 2 — 12:15 ET
**Routine**: 2 notes processed, 3 tasks created

## Run 3 — 18:15 ET
**Routine**: 1 note processed, 1 task created, 1 vault update

## Flagged Items
- ⚠ "I want to do a triathlon" — missing date and evidence
  *Source: Inbox 2026-04-01 0712.md*

## Full Log
`agents/logs/inbox-processing-2026-04-01.md`
```

**Important**: These are NOT frontmatter files. They are plain Obsidian vault notes (no YAML frontmatter). Keep them clean for Obsidian rendering.

**Overwrite behavior**: Each run overwrites the previous digest. No append. No date-stamped archive files in the vault.

**Directory creation**: If `notes/00-System/agent-activity/` does not exist, create it. This will be handled in WP05 deployment, but the script should handle it gracefully.

## Definition of Done

- [ ] `scripts/openclaw/observation/tests/fixtures/` contains 6 realistic log fixtures
- [ ] `scripts/openclaw/observation/tests/test_summarize.py` contains all test cases and passes
- [ ] `scripts/openclaw/observation/config.py` loads registry and resolves paths
- [ ] `scripts/openclaw/observation/summarize.py` parses logs, applies autonomy-level filtering, generates digest
- [ ] WhatsApp critical alert path implemented with graceful degradation
- [ ] Obsidian digest output writes overview.md and per-agent files
- [ ] `--dry-run` flag works (prints output without writing files)
- [ ] All tests pass: `python -m pytest scripts/openclaw/observation/tests/ -v`
- [ ] No hardcoded paths (all configurable via ObservationConfig)

## Risks

| Risk | Mitigation |
|------|-----------|
| Log format varies between agents | Fixtures cover both agents; parser handles missing fields gracefully |
| WhatsApp DM policy disabled | Graceful degradation — log skip, mark critical alerts prominently in Obsidian |
| Office2 paths differ from local dev | ObservationConfig supports path overrides |

## Reviewer Guidance

- Run `python -m pytest scripts/openclaw/observation/tests/ -v` — all tests must pass
- Verify autonomy-level filtering: at `autonomous`, routine actions should NOT appear in digest
- Verify critical alert detection: any `[error]` or `[security]` line must trigger the alert flag
- Verify digest includes log references (FR-013)
- Verify `--dry-run` does not write files
- Check that no paths are hardcoded — everything goes through ObservationConfig

## Activity Log

- 2026-04-01T22:25:24Z – claude – shell_pid=56766 – lane=doing – Assigned agent via workflow command
