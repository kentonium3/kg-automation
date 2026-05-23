# Research: Enforce verbatim pass-through

**Mission**: `main-verbatim-passthrough-01KSATRP`

Phase 0 decisions, all locked from pre-specify probe of office2.

## D1 — Session rotation mechanism

**Decision**: filesystem rename `*.jsonl` → `*.jsonl.reset.<ISO timestamp>` in the active session directory.

**Rationale**: pre-specify probe of `/home/claude/.openclaw/agents/main/sessions/` shows the gateway already creates `.jsonl.reset.<timestamp>` files via natural rotation. Mirroring that pattern means:
- We piggyback on existing gateway semantics (no new file type)
- Audit trail preserved (history not deleted, just renamed)
- Idempotent — running twice produces two timestamped reset files for the same session, which is fine
- No new dependencies, no upstream OpenClaw change required

**Alternatives considered**:
- `openclaw session reset` CLI: rejected — `openclaw --help` doesn't expose one
- Deleting session jsonl: rejected — violates C-005 (preserve audit trail)
- File-marker mechanism: rejected — would require gateway-side changes

## D2 — Trim strategy for AGENTS.md

**Decision**: targeted prose reduction in low-information sections; net negative delta despite the new verbatim section.

**Current**: 15,458 chars. **Target**: ≤14,000 chars (NFR-003). **Required delta**: ≥-1,458 net.

**Plan-phase cuts** (locked here so implementer just executes):
- §"Tools" — compress redundant explanatory paragraphs to a single sentence each: ~-500 chars
- §"Error handling" — remove verbose example output (keep one canonical example): ~-300 chars
- §"What this system is" intro — compress 2 paragraphs to 1: ~-400 chars
- §"Message identity" — already concise; no cuts
- New §"Verbatim pass-through (ABSOLUTE)": ~+400 chars (rule + 2 worked examples)
- **Net**: ~-800 chars; comfortable margin under 14K

Implementer may adjust if their reading of the current file suggests different cuts — the goal is the size budget, not the specific cuts.

## D3 — Verbatim-rule placement

**Decision**: new top-level §"Verbatim pass-through (ABSOLUTE)" near the top of AGENTS.md, cross-referenced by each delegation section.

**Rationale**:
- Single source of truth (no duplication across habits/escalation/tasker)
- Top placement = LLM reads it first; rule has primacy in attention
- "ABSOLUTE" framing signals the rule isn't advisory (mirrors the existing "Privacy — absolute rule" pattern in tasker/capture AGENTS.md per memory `reference_felix_output_discipline_pattern.md`)

**Rule content** (locked):
```markdown
## Verbatim pass-through (ABSOLUTE)

When delegating Kent's reply to a sub-agent (`openclaw agent --agent ... --message ...`), forward the message TEXT VERBATIM. Do not paraphrase, rephrase, summarize, restructure, third-person rewrite, add context, or pre-interpret.

### Examples

❌ FORBIDDEN — paraphrasing
Kent: "did 1 and 2, skipping 3"
Wrong delegation: `--message "Kent reports completing tasks 1 and 2 and skipping task 3"`

✅ REQUIRED — verbatim
Kent: "did 1 and 2, skipping 3"
Correct delegation: `--message "did 1 and 2, skipping 3"`

This rule exists because sub-agents have deterministic parsers (`parse_morning_reply`, escalation parser, etc.) that require Kent's exact phrasing. Paraphrased input is silently mis-parsed and the JSONL state-log substrate goes empty.
```

## D4 — Rotation helper scope

**Decision**: rotate ONLY `main` agent sessions. Out of scope: sub-agent session rotation.

**Rationale**:
- The bug is in `main`'s standing orders, not in sub-agent standing orders
- Sub-agents do load updated AGENTS.md when their sessions rotate (which happens naturally daily based on the `.jsonl.reset.*` pattern)
- Scoping to `main` keeps the helper simple + minimizes blast radius

**Helper module**: `scripts/openclaw/helpers/rotate_main_session.py`
**Marker**: `~/.config/openclaw/main-rotation-<ISO timestamp>.done` (one marker per rotation; operator audit trail)
**CLI**: `--dry-run`, `--force`
**Exit codes**: 0 success, 1 filesystem failure, 3 invalid args (via `_StructuredArgumentParser`)
