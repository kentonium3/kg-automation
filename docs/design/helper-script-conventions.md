---
title: "Helper script conventions"
doc_type: standard
status: draft
audience: agents_and_humans
owners: [kgale]
last_validated: 2026-05-15
---

# Helper script conventions

Operational conventions for the helper scripts that implement [Constitution Directive 6](../constitution/FELIX-CONSTITUTION.md) (deterministic detection, AI interpretation). This document is the **Phase 3 deliverable** of [#281](https://github.com/kentonium3/kg-automation/issues/281) and is referenced from Directive 6 as the source of truth for how helpers are built, tested, and deployed.

These conventions are grounded in patterns established across missions [#253](https://github.com/kentonium3/kg-automation/issues/253), [#259](https://github.com/kentonium3/kg-automation/issues/259), [#277](https://github.com/kentonium3/kg-automation/issues/277), and [#278](https://github.com/kentonium3/kg-automation/issues/278). They formalize what worked; they don't impose new structure for its own sake.

> **Status**: DRAFT — awaiting Kent's review before being referenced from Directive 6. Once approved, this document becomes the convention; deviations from it should be deliberate and documented.

---

## 1. Storage location

The helper's caller and reach determines its home.

| Pattern | Location | When to use |
|---|---|---|
| **Agent-co-located** | `scripts/openclaw/agents/<agent>/<helper>.py` | The helper is called by exactly one agent and is tightly coupled to that agent's standing orders. Examples: `handle_audit_routing.py`, `handle_drift_events.py`. |
| **Domain-co-located** | `scripts/<domain>/<helper>.py` | The helper is called by one agent but is part of a logical domain that may grow over time. Examples: `scripts/inbox/prescan.py`, `scripts/inbox/handle_parse_failures.py`. |
| **Skill (project-specific)** | `~/.openclaw/skills/<skill>/SKILL.md` + helper files | The helper is called by **≥2 agents** OR encodes cross-agent reusable capability. See § 9 for promotion criteria. |
| **System pipeline** | `scripts/office2/<script>` or `scripts/<domain>/<pipeline>` | The script runs as a background job (cron / systemd timer) without an agent invoker. Examples: `audit.sh`, `sync-heartbeat.py`. |

**Default decision**: start at domain-co-located unless the helper is so agent-specific it would never be called by another caller. Domain placement makes later promotion to skill (§ 9) frictionless.

**Don't mix**: a helper should never sit in an agent's directory if any other agent could conceivably need it. That's the friction point that prevented `scripts/openclaw/agents/felix-admin-capture/` helpers from being shared with `felix-admin-tasker` even though both create Vikunja tasks.

---

## 2. CLI interface contract

Every helper presents a stable, testable interface.

### Required

- **argparse-based CLI.** No `sys.argv[1:]` hand-parsing. argparse gives `--help` for free; agents and humans both benefit.
- **Long-form flags** (`--cursor`, `--mapping`, `--repo`). Short flags only if a flag is invoked >5× in tests or by agent prompts; otherwise long-form is more readable in AGENTS.md.
- **Meaningful exit codes**:
  - `0` — success, no errors
  - `1` — operational error (file unreadable, external command failed, etc.)
  - `2` — usage error (invalid arguments, missing required config)
  - Other codes only if the helper has documented semantics for them
- **Stable input format.** If a helper accepts structured input (e.g., JSON), the schema is documented in the module docstring with a worked example.

### Strongly recommended

- **`--dry-run` flag** for any helper that mutates state. Dry-run prints what would happen without performing the mutation; cursor / state files are NOT advanced.
- **`--limit` flag** for any helper that processes a queue / loop. Bounds work per invocation, prevents runaway on first deploy with many backlogged events.
- **`--repo` or equivalent override** for helpers that talk to GitHub. Lets tests run against a fixture repo without changing defaults.

### Reference implementations

- [`scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py`](../../scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py) — argparse, `--dry-run`, `--limit`, structured input via `@file` syntax
- [`scripts/inbox/prescan.py`](../../scripts/inbox/prescan.py) — argparse, JSON output to stdout for agent consumption
- [`scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py`](../../scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py) — file-based structured input, multi-leg execution, exit-code semantics

---

## 3. Stdout convention

Helpers output structured information that both humans (reading logs) and agents (consuming output) can parse predictably.

### Required for every helper

- **Final line is a `SUMMARY: ...` line** that summarizes the invocation. Format: `SUMMARY: key1=value1 key2=value2 ...`. Example: `SUMMARY: processed=3 matched_filed=1 unmapped=2 errors=0 cursor=12→15`.
- **Operational info lines** start with `INFO: ` for normal events, `WARN: ` for noteworthy non-fatal issues.
- **Errors** go to `stderr` (not stdout) prefixed with `ERROR: `. Stdout stays clean for consumers.

### Reference implementation

`handle_drift_events.py` lines ~190-220 — the `SUMMARY:` line pattern emerged from this helper and should be the model.

### Why this matters

A consistent stdout shape lets a calling agent:

- Parse just the `SUMMARY:` line to see outcome counts
- Quote the full output to Kent for diagnostic visibility
- Detect partial-progress (e.g., `errors > 0` AND `processed > 0`) and route accordingly

Without a convention, every helper invents its own output shape and agent prompts have to remember each one.

---

## 4. Atomic state mutation

Helpers that write to state files (cursors, baselines, indexes, mapping tables) MUST use the atomic-write pattern. Partial writes corrupt state; a crash mid-write strands the system.

### Canonical pattern (Python)

```python
def write_atomic(path: Path, value: str) -> None:
    """Write to `path` atomically via tempfile + os.replace."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
        # Preserve original file mode if it exists
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except FileNotFoundError:
            mode = 0o644
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
```

### Canonical pattern (bash)

```bash
write_atomic() {
    local target="$1" content="$2"
    local tmp="${target}.tmp.$$"
    printf '%s' "$content" > "$tmp"
    mv "$tmp" "$target"  # POSIX rename is atomic on the same filesystem
}
```

### Reference implementations

- [`scripts/inbox/inject_parse_error_marker.py`](../../scripts/inbox/inject_parse_error_marker.py) `_atomic_write()` — preserves file mode (mission #33/#254 — the perm-orphaning bug that motivated this convention)
- [`scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py`](../../scripts/openclaw/agents/felix-doc-auditor/handle_drift_events.py) `write_cursor_atomic()`

### Why this matters

Mission #254 was specifically about a cron job whose state file got orphaned (wrong owner) by a non-atomic write. The atomic pattern preserves mode AND ensures all-or-nothing semantics.

---

## 5. Idempotency

Helpers that can be called multiple times (cron, agent retry, manual debug) MUST be idempotent on their own state. The agent invoking them must not have to "remember whether it ran already."

### Idempotency primitives

- **Cursor files**: track progress through a queue; processing past the cursor is the new operation, past events are NOT reprocessed (`handle_drift_events.py` pattern).
- **Content-hash comparison**: check whether the new value differs from the current value before writing (`audit.sh`'s `check_baseline` pattern).
- **Existence check before create**: query for an existing target before creating a new one (Vikunja `find before create` pattern used in `felix-admin-tasker` Step 6).
- **Conditional state transition**: only act if the current state is the expected source state for the transition (escalation level state machine).

### When idempotency is NOT achievable

Some operations are intrinsically non-idempotent (sending a notification, posting a WhatsApp message). For these:

- **Deduplicate at the source**: agent doesn't call the helper twice unless intended
- **Cooldown / rate-limit at the helper**: `audit.sh`'s `failureAlert.cooldownMs` pattern
- **Mark as sent**: write a state record BEFORE the side-effect, check before next call

### Reference implementations

- `handle_drift_events.py`'s cursor mechanism — perfect idempotency on queue consumption
- `audit.sh`'s `check_baseline` function — content-hash comparison
- `felix-admin-tasker`'s "Check for duplicates: `GET /projects/{id}/tasks?s={title}`" — existence check

---

## 6. Failure-mode handling (helper + calling agent)

A helper that exits non-zero must produce actionable output, and the calling agent must have a deterministic response.

### Helper side

- **Exit non-zero on any error the agent should know about.** Don't silently degrade.
- **Print to stderr WHAT failed.** "Couldn't load mapping file" is useful; "Error" is not.
- **DO NOT advance cursors / state on partial failure.** Failed events should re-attempt next invocation, not be silently dropped.
- **For queue processors, retry failed items first.** Stop processing on first failure; cursor stays at the failed item.

### Agent side (in AGENTS.md)

Every agent's standing orders that invoke a helper MUST include a failure-handling clause that specifies:

1. How to detect the failure (exit code or stderr content)
2. What to log
3. Whether to file a `[doc-audit]` issue (Tier 4-class failures) or escalate to Kent (Tier 2+-class failures)
4. Whether to continue the rest of the agent's tick or halt

### Canonical agent-side failure handler (template)

```markdown
### Failure handling

If the helper exits non-zero:
- Read stderr from the OpenClaw session output
- File a `[doc-audit]` issue titled "<agent>: <helper> failed" with the error output and the inputs that caused the failure
- Continue to the next step — don't block the rest of the tick on this
```

### Reference implementation

`felix-doc-auditor` AGENTS.md § 2.3 — drift-handler failure handling. This is the model.

---

## 7. Observability

Helpers emit signals that downstream pipelines can consume. This connects helpers to the signal-driven doc-audit architecture (#278).

### Conventions

- **Structured events on state changes**: if the helper detects or causes a state change worth recording, append a JSONL line to a known event stream (e.g., `drift-events.jsonl`). Use base64 encoding for any multi-line content (diffs, logs) to avoid JSON-escaping issues.
- **Cursor files** are read-only state for resumability, not for human consumption. Keep them simple (just an integer or hash; not human-formatted).
- **Activity logs** go to a separate path from event streams. Activity logs are for humans; event streams are for pipelines.

### When to emit

| Helper operation | Event emit? |
|---|---|
| Detects state drift (baseline diff, etc.) | YES — append to drift-events.jsonl |
| Auto-applies a Tier 4 mechanical edit | YES — append to applied-edits.jsonl (or similar) |
| Files an issue / posts a comment | NO — the issue itself is the record |
| Reads state without mutation | NO |
| Detects a recoverable error | NO (stderr is enough) |
| Detects an unrecoverable error | YES — append to errors.jsonl with helper name, args, error message |

### Reference implementation

`audit.sh`'s `emit_drift_event` function + `handle_drift_events.py`'s cursor-driven consumption.

---

## 8. Testing discipline

When does a helper require tests, and what should those tests cover?

### Tests REQUIRED when

- The helper mutates state outside its own process (writes files, makes network calls, modifies databases)
- The helper has multiple code paths (>2 distinct execution branches based on input)
- The helper is invoked by ≥2 agents (reuse amplifies any bug)
- The helper handles money, dates with timezone math, security-sensitive values, or anything that satisfies Directive 6 § 4 criticality

### Tests STRONGLY RECOMMENDED when

- The helper has any logic that's not "call API, pass result through"
- The helper is part of the daily critical path (runs daily or more often)

### Tests OPTIONAL when

- The helper is genuinely one-shot (run once during a setup, never again)
- The helper is a thin wrapper over a well-tested external tool

### What to test

- **Happy path**: typical input → expected output
- **Edge cases**: empty input, malformed input, large input
- **Failure modes**: external command fails, file not found, network error
- **Idempotency**: calling twice produces the same final state
- **State preservation**: file modes / ownership preserved if relevant

### Test location

- `tests/<domain>/test_<helper>.py` for domain-co-located helpers
- `tests/openclaw/agents/<agent>/test_<helper>.py` for agent-co-located helpers
- pytest is the standard; no other framework should be introduced

### Reference

The inbox helpers (`scripts/inbox/`) have test coverage; recent additions (handle_drift_events.py, audit.sh extensions) do NOT yet have tests. The gap is a known debt; Phase 4 refactors should backfill tests where the criticality threshold demands them.

---

## 9. Helper vs skill — promotion criteria

A helper is a script invoked by an agent. A skill is an OpenClaw construct that wraps capability with a `SKILL.md` description, auto-discoverable by agents.

### When to keep as helper

- Used by exactly one agent
- Tight coupling to a specific agent's standing orders
- Project-specific in a way that doesn't generalize

### When to promote to skill

A helper qualifies for promotion to skill when ANY of these are true:

1. **Called by ≥2 agents.** Currently the strongest signal — by definition cross-agent.
2. **Has a clear capability name** that future agents could reasonably want. Example: "create a Vikunja task with full enrichment" is skill-shape; "extract today's habit list from this specific Vikunja project structure" is helper-shape.
3. **Has stabilized over multiple revisions** without changing its interface. Stability is a precondition; an unstable interface as a skill creates breakage across agents.

### Skill structure (project-specific)

A project-specific skill lives at `~/.openclaw/skills/<skill-name>/` and contains:

- `SKILL.md` — the agent-facing description: what the skill does, when to use it, input/output contract, examples
- One or more helper scripts that implement the skill
- Optional: a small README for human reference

Project-specific skills are NOT installed via ClawHub. They're maintained in this repo and deployed to office2 alongside agent workspaces.

### Pilot candidate (per #281 survey)

`scripts/vikunja/create_task.py` — used by both `felix-admin-capture` (fallback path) and `felix-admin-tasker` (primary path). First likely promotion to skill once Phase 4 refactor work begins.

---

## 10. Deploy story

Helpers run on office2 and must reach there reliably.

### Current state

Manual `scp` per file. Works at current scale; brittle as helper count grows.

### Convention (until automation lands)

- Helpers live in the repo at their canonical path (per § 1)
- Manual deploy: `scp scripts/<domain>/<helper>.py office2-claude:/home/claude/kg-automation/scripts/<domain>/<helper>.py`
- For helpers tied to an agent workspace, ALSO scp to the workspace path: `scp ... office2-claude:/data/services/openclaw/<workspace>/<helper>.py`
- After deploy, verify with a smoke-test invocation (`--dry-run` or `--help`)

### Future automation (out of scope for Phase 3, captured for Phase 4 mission design)

When helper count exceeds ~15 across the project (a heuristic threshold), build a `scripts/deploy/deploy_felix_helpers.py` that:

- Reads a manifest of (source path, office2 paths) for each helper
- scps each, verifies file size matches, runs a `--help` smoke test
- Updates a deploy-log on office2 with timestamp + commit SHA

Until then, manual deploy is fine. Don't build infrastructure ahead of need.

---

## 11. Documentation per helper

Every helper has:

- **Module docstring** (Python) or **header comment** (bash) explaining:
  - What it does in one sentence
  - When the agent invokes it
  - Input contract (CLI args, structured input shape)
  - Output contract (stdout, exit codes)
  - Side effects (which files it writes, which external systems it touches)
  - Idempotency posture (is calling twice safe? what's the rollback story?)
- **Reference from the calling AGENTS.md** that explains the invocation in operational context

### Index

When helper count grows beyond ~10, a `docs/design/architecture/helper-index.md` becomes worth maintaining. Below that, each helper's docstring + AGENTS.md reference is sufficient discovery.

---

## 12. Migration discipline

When existing prompt-heavy logic gets refactored to a helper, the change must be behavior-preserving.

### Required for every refactor

1. **Document the golden-path scenarios** the existing agent handles. Capture inputs + expected outputs.
2. **Build the helper to satisfy those scenarios** (unit-tested where § 8 says required).
3. **Replace the AGENTS.md block** with the helper invocation + the surrounding interpretation prompt.
4. **Smoke-test the refactored agent end-to-end** before declaring done — at least one full happy-path run with a real input.
5. **Behavior-diff** observable outputs (agent message to Kent, Vikunja state, file changes) — should match the pre-refactor case for the golden-path scenarios.

### Rollback story

- Helpers are versioned by git like any other code
- Reverting the AGENTS.md change + the helper restores prior behavior
- For helpers that hold state files (cursors, baselines), document explicitly whether reverting requires resetting those files

---

## Cross-references

- [Felix Constitution Directive 6](../constitution/FELIX-CONSTITUTION.md) — The principle this document operationalizes
- [#281](https://github.com/kentonium3/kg-automation/issues/281) — Parent epic
- [`felix-d6-survey.md`](./architecture/felix-d6-survey.md) — Phase 1 survey informing the conventions
- [`feedback_scripts_vs_llm.md`](../../../.claude/projects/-Users-kentgale-repos-kg-automation/memory/feedback_scripts_vs_llm.md) — Memory note grounding the principle
- Reference helpers cited throughout:
  - `scripts/inbox/prescan.py`, `handle_parse_failures.py`, `handle_marker_cleanup.py`, `inject_parse_error_marker.py`
  - `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py`, `handle_drift_events.py`
  - `scripts/office2/security-monitor/audit.sh`

---

*Draft prepared overnight 2026-05-15. Awaiting Kent's review. When approved, Directive 6 in the Constitution will be amended to reference this document as the operational source of truth.*
