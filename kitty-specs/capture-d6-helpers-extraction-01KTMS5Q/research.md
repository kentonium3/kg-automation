# Research: Capture Directive-6 Helpers Extraction

**Mission**: `capture-d6-helpers-extraction-01KTMS5Q`
**Phase**: 0 (Outline & Research)
**Date**: 2026-06-08

## Decisions Locked at Discovery

### D-001 — Split #566 into two missions

- **Decision**: This mission ships only the 6 new helpers. AGENTS.md rewrite is split into a follow-on mission.
- **Rationale**: Per `[[feedback_speckitty_split_code_and_deploy_missions]]`, if any WP needs the prior WP's code MERGED to main for its runtime correctness, split into two missions. The AGENTS.md rewrite will instruct the agent to `python3 -m scripts.inbox.classify_content ...` — that call fails `ModuleNotFoundError` if the helper isn't on `/home/claude/kg-automation` yet. #567's deploy pipeline syncs the repo→office2 within 5 min of merge. By splitting, we guarantee helpers are live before the prompt depends on them.
- **Alternatives considered**: Single mission with mid-mission operator pause — fragile, requires manual coordination. Within-lane dependency — works in CI tests but doesn't address the office2 deploy lag for the actual prompt change.

### D-002 — Stdlib only, no `python-frontmatter`

- **Decision**: YAML frontmatter parsing in `mark_processed.py` uses a hand-rolled regex parser mirroring `scripts/inbox/handle_marker_cleanup.py`'s pattern. No new third-party dep.
- **Rationale**: Per NFR-002 + kg-automation convention. The frontmatter parser only needs to: split `---\n<yaml>\n---\n<body>`, read+write a flat key→value map (no nested YAML structures expected for inbox notes), preserve unknown keys.
- **Alternatives considered**: `python-frontmatter` (~700KB transitive deps, would require pipx install on office2) — rejected per stdlib-only convention. `PyYAML` — same concern, plus YAML attack surface.

### D-003 — `classify_content` emits structured JSON, not human-readable text

- **Decision**: `classify_content.py` outputs JSON `{note_filename, blocks: [{index, kind, content, confidence, flag?}]}` on stdout.
- **Rationale**: The follow-on AGENTS.md rewrite will parse this output as structured data and route per-block. JSON is the canonical interchange format for stdin/stdout helper handoff (matches existing `scripts/inbox/prescan.py` pattern). Human-readable text would force the agent to parse free-form output via LLM tokens (waste + fragility).
- **Alternatives considered**: JSONL (one block per line) — slightly more grep-friendly but harder to read in WhatsApp digests. Stuck with a single JSON object.

### D-004 — `route_calendar_event` validates only; delegation stays in the prompt

- **Decision**: This helper validates payload schema (via existing `scripts.calendar_routing.validate_calendar_event`) and emits the normalized payload on stdout. Does NOT call gog directly. The agent prompt is responsible for delegating to Felix main for the actual `gog calendar create`.
- **Rationale**: Felix main owns the gog credentials and the delegation contract. Bypassing main would require duplicating credential wiring. Cleaner to keep the delegation surface (main-agent prompt) where it already lives.
- **Alternatives considered**: Move the gog call into the helper — rejected; would expand credential surface.

### D-005 — `handle_clarification_state` is three subcommands of one helper

- **Decision**: One helper file with `argparse` subcommands `add` / `sweep` / `match`. Not three separate files.
- **Rationale**: The three operations share the same state file path, the same JSON schema, and the same atomic-write pattern. Splitting into three would triple boilerplate.
- **Alternatives considered**: Three helpers — rejected for shared-state locality.

### D-006 — 24h sweep is invoked as a separate tick, not auto-fired by other subcommands

- **Decision**: `sweep` runs on its own schedule (cron or manual). `add` and `match` do NOT trigger an aging pass.
- **Rationale**: Single-responsibility per invocation. `sweep` is the explicit aging surface; mixing it into `add`/`match` makes those subcommands slower and less predictable. Aging cadence is operator-tuneable.
- **Alternatives considered**: Auto-sweep-on-write — rejected; complicates the `add` flow's timing.

### D-007 — Test fixtures live under `tests/inbox/fixtures/<helper>/`

- **Decision**: Each helper's tests use a dedicated subdirectory under `tests/inbox/fixtures/` for input notes / payloads / state files. Match the existing `tests/inbox/fixtures/` convention.
- **Rationale**: Aligns with prior precedent. Easier to add new fixtures over time without inflating one large fixture file.
- **Alternatives considered**: Inline `tmp_path.write_text()` — fine for simple cases but harder to maintain for the classifier's regression suite.

## Implementation-Detail Research

### R-001 — Atomic frontmatter write

The existing pattern in `scripts/inbox/inject_parse_error_marker.py`:

```python
import os
from pathlib import Path

def atomic_write(path: Path, content: str) -> None:
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
```

mark_processed mirrors this. The added wrinkle: read existing frontmatter, mutate one field, serialize back, preserve body verbatim.

### R-002 — Vikunja Someday project resolution

Per existing `scripts.common.vikunja_client.VikunjaClient` (from #542):

```python
client = VikunjaClient()
projects = client.list_projects()
someday = next(p for p in projects if p["title"] == "Someday")
task = client.create_task(project_id=someday["id"], title="...", description="...")
```

The client handles auth from `/data/services/openclaw/secrets/vikunja-api`. Tests mock the client's `list_projects` and `create_task` methods.

### R-003 — Block-splitting heuristic for classify_content

Three signals for block boundaries (in order):
1. **Markdown headings** (`^#+\s`) — strongest signal. A heading starts a new block; everything until the next heading is that block's content.
2. **Two-or-more blank lines** — signal block boundary when no headings are present.
3. **Topic shift via leading keyword** (e.g., "TODO:", "Calendar:", "Note to self:") — fallback heuristic.

The heuristic is documented inline per FR-014 so the follow-on AGENTS.md rewrite has a stable reference.

### R-004 — Existing `validate_calendar_event` signature

Probed at design time:

```python
# scripts/calendar_routing/validate_calendar_event.py
def validate_payload(payload: dict) -> tuple[bool, list[str]]:
    """Returns (is_valid, missing_fields)."""
    ...
```

`route_calendar_event` consumes this:

```python
is_valid, missing = validate_payload(payload)
if not is_valid:
    sys.stderr.write(json.dumps({"error": "invalid_payload", "missing": missing}))
    sys.exit(1)
```

### R-005 — Coverage gate strategy

Per NFR-003: ≥90% line, ≥85% branch via `pytest --cov`. Defensive branches that are unreachable in production paths can use `# pragma: no branch` per `[[reference_pytest_branch_coverage_pragma]]` — but sparingly. Each helper aims for >95% coverage on first pass; the gate is a floor, not a target.

## Validation Notes

- Spec FR mapping: every FR (FR-001 through FR-015) is addressed by exactly one IC in plan.md's Implementation Concern Map. Validated by hand.
- Charter directives map to enforcement surfaces in plan.md § Charter Check.
- No [NEEDS CLARIFICATION] markers in plan.md or spec.md.
