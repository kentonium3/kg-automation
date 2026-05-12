# Research — Inbox Capture Dedup and Parser Hardening

**Mission**: `inbox-capture-dedup-and-parser-hardening-01KREZJ8`
**Spec**: [spec.md](./spec.md)
**Date**: 2026-05-12

Plan-phase decisions in Decision / Rationale / Alternatives form.

---

## R-001 — Resolution of spec assumption A-003 (which code path the bug touched)

**Decision**: The bug touched **two code paths**, both of which need attention. Mission 027's fix to `prescan.py` (`690a370`, 2026-04-11) addressed one narrow malformation case but did not prevent the root cause.

**Evidence** (from code inspection during plan):

1. **Read path** — `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` §Step 1 says explicitly: "Do NOT scan `/home/kgale/second-brain/notes/01-Inbox/` yourself — the helper's list is authoritative." So `prescan.py` IS the agent's authoritative source for "is this note unprocessed?" The agent doesn't have a parallel parser.

2. **Write path** — AGENTS.md §Step 5 instructs the agent to write `status: processed` and `processed_at: ...` to the note's frontmatter after routing. This write is performed by the LLM agent at runtime (not by a Python helper). If the frontmatter is malformed in a way the agent's edit tool can't reliably modify, the write may silently fail to actually update the `status` field, leaving the note classified as unprocessed on the next prescan run.

3. **Mission 027's blank-line-skip** (commit `690a370`) catches the case where `lines[0]` is blank but `lines[start]` reaches a valid `---`. That fix is necessary but not sufficient: other malformations (BOM, missing closing `---`, invalid YAML inside the block) still produce `frontmatter = None` or `status = None`, which `prescan.py` treats as "unprocessed" — re-arming the duplicate-issue loop.

**Why this resolves A-003**: the bug-trigger was almost certainly a malformation in the *class* "anything that makes prescan return status=None" — which includes the documented `\n---` case PLUS any other malformation. Mission 027 fixed one narrow shape; the bug's true scope is broader. Our Fix 2 (FR-005) widens the defensive parser; our Fix 1 (FR-001/003) makes dedup orthogonal to frontmatter parseability so even future undiscovered malformations can't trigger duplicates.

**Alternatives considered**:

- *Audit Obsidian/Templater's note-generation pipeline to find the upstream cause.* Worth doing as a follow-up but out of scope here. The root-cause fix (routing log) decouples us from any specific malformation pattern.

---

## R-002 — Routing log helper module

**Decision**: Create `scripts/inbox/routing_log.py` as a small new module exposing `RoutingLogReader.has_filename(name) -> bool` and `RoutingLogWriter.append(entry) -> None`. Both are stdlib-only (no external deps). The module is imported by `prescan.py` for the dedup-classification path (R-003 below) and is invoked directly by helper scripts the agent may shell out to.

**Rationale**:

- Single source-of-truth for log format + path. Future code paths (agent shell-outs, manual `inspect routing log` scripts) consume the same module.
- Easy to unit-test in isolation: pure file I/O + simple data types.
- Matches the kg-automation `scripts/inbox/` neighborhood; fits the existing helper pattern.

**Alternatives considered**:

- *Inline the routing-log logic in `prescan.py`.* Rejected: bundles two responsibilities (classify + dedup state) in one module; harder to test the routing-log code in isolation.
- *Make it a JSON-file driver instead of a Python module (the agent reads/writes the JSONL itself via shell).* Rejected: pushes parse responsibilities to the LLM at runtime, exactly the failure mode this mission is fixing.

---

## R-003 — Where the routing-log dedup check fires

**Decision**: `prescan.py`'s classifier consults the routing log and **filters out already-routed files from `unprocessed_paths`** before returning to the agent. From the agent's perspective, a previously-routed note simply disappears from the unprocessed list — same as if it were marked `status: processed`.

**Rationale**:

- **Single decision surface**: the agent already trusts `prescan.py`'s `unprocessed_paths` (AGENTS.md §Step 1). Filtering inside prescan is invisible to the agent and requires zero changes to the agent's routing logic.
- **Fail-safe by default**: if the routing log is missing or empty, prescan falls back to status-only classification — exactly today's behavior. The new mechanism is purely additive.
- **No agent-runtime dedup logic**: the LLM agent doesn't need to learn a new "before filing, check the log" workflow. It just processes whatever appears in `unprocessed_paths`.

The agent still does its own "write to routing log after filing" step (R-005), but that's a write, not a decision.

**Alternatives considered**:

- *Agent reads routing log directly via shell.* Rejected: adds an LLM-runtime decision that could be skipped or implemented inconsistently across runs.
- *Both prescan AND agent check.* Rejected: redundant and creates coordination cost.

---

## R-004 — Defensive parser scope (FR-005 implementation)

**Decision**: Extend `prescan.py`'s `_extract_frontmatter_block` and surrounding classifier with explicit detection for the four malformation cases. Each case produces a distinct `parse_failure` classification (new third state alongside `unprocessed` / `processed`).

The malformations and their detection:

| Case | Detection |
|---|---|
| **Leading non-newline whitespace before `---`** (already partly handled in mission 027 for blank lines; widen to tabs / spaces / mixed) | After splitlines(), iterate stripping; if first non-empty line is not exactly `---` AND the file's raw first ~10 bytes contain `---`, mark malformed. |
| **UTF-8 BOM at start of file** | Read raw bytes; if file starts with `\xEF\xBB\xBF`, mark malformed. Existing code already does `lstrip("﻿")` in some places — be explicit about it as a malformation that we surface rather than silently strip. |
| **Missing closing `---`** | Existing code returns `None` from `_extract_frontmatter_block` in this case. Add a distinct classification path so the caller sees "malformed: unterminated" rather than "no frontmatter". |
| **Invalid YAML inside the block** | `yaml.safe_load()` raises `yaml.YAMLError`. Existing code catches it and emits warning "malformed YAML frontmatter; treated as unprocessed" — change "treated as unprocessed" to "parse_failure". |

The classifier returns a new top-level field on the JSON output: `parse_failures: [{path, reason}, ...]`. The agent sees these via the helper output and acts on them per FR-004/006/008.

**Rationale**:

- Extends a single tested code surface (`prescan.py`); no new parser implementations.
- The classification taxonomy gets one new state (`parse_failure`) — cleaner than overloading "unprocessed" with a flag.
- BOM stripping is currently silent; making it explicit means notes that arrive with a BOM stay flagged for Kent's attention (the BOM is itself a sign that some upstream tool isn't cooperating with Obsidian).

**Alternatives considered**:

- *Silently strip BOM and other "fixable" whitespace, only flag truly unfixable malformations.* Rejected: silent fixes mask upstream tool problems. Better to surface and let Kent decide.

---

## R-005 — How the agent writes routing log entries

**Decision**: The agent invokes a small helper script `scripts/inbox/append_routing_entry.py <filename> <issue_number> <vikunja_task_id> [excerpt]` after successfully filing the GitHub issue. The script writes one JSONL line to `~/second-brain/agents/state/inbox-routing.jsonl` and exits.

**Rationale**:

- **Agent has no Python state**: each cron tick is a fresh LLM invocation. The routing-log write needs to be a shell-invocable atomic operation, not a Python state mutation across the agent's lifecycle.
- **Idempotent file format**: JSONL append-only. If the agent invokes the script twice for the same filename (shouldn't happen, but defensively), the second invocation appends a second line. Dedup on read (R-003) tolerates duplicate entries.
- **Simple contract**: the agent learns one new shell command in AGENTS.md, not a new Python API.

**Alternatives considered**:

- *Have prescan.py do the writes too.* Rejected: prescan runs at the START of the agent's turn, before any issue is filed. The write must happen AFTER the agent files the issue (so it has the issue number to record).
- *Skip the helper; have the agent emit JSONL with `echo "{...}" >> path`.* Rejected: LLM-generated shell encoding is fragile (quoting, escaping). A typed Python helper is more robust.

---

## R-006 — Callout marker injection logic

**Decision**: Two helper functions on the agent's available surface:

- `scripts/inbox/inject_parse_error_marker.py <filename> <issue_number>` — invoked by the agent at end-of-turn for every file in `parse_failures` after the batched "Inbox quality" issue is filed. The script reads the file, looks for an existing `> [!error] felix-capture:` line at the top of the body, updates-in-place if present or inserts after the closing `---` if frontmatter delimiters are detectable / at the very top otherwise.
- `scripts/inbox/strip_parse_error_marker.py <filename>` — invoked by `prescan.py` when a note that previously had a marker now parses cleanly. (Or invoked by the agent during its Step 5 frontmatter write — TBD in implement phase; lower-friction is for prescan to do it during classification since it already reads the file.)

**Rationale**:

- Same reasoning as R-005 — shell-invokable atomic operations are robust to LLM runtime weirdness.
- Idempotency lives in the helper script's logic, not in the agent's prompt — much less error-prone.

**Alternatives considered**:

- *Have the agent do the injection directly via its Edit tool.* Rejected: same fragility concern as R-005. Each agent turn is a fresh LLM; relying on the LLM to correctly format and insert a callout line is risk we can avoid with a script.

---

## R-007 — Batched "Inbox quality" GitHub issue logic

**Decision**: A helper script `scripts/inbox/file_inbox_quality_issue.py <parse_failures_json>` that:

1. Searches for an existing open issue with title prefix `Inbox quality:` via `gh issue list --search 'in:title "Inbox quality"' --state open --json number,title --limit 50`.
2. If exact-prefix match found (after Python `startswith` post-filter for fuzzy-search resilience, same pattern as credential-health-check), prints the existing issue number and exits 0. Agent uses this number for the callout markers.
3. If no match, files a new issue via `gh issue create --label area/content --title 'Inbox quality: <N> notes with parse errors — YYYY-MM-DD' --body <body>` and prints the new issue number.

The agent invokes this helper at end-of-turn when `parse_failures` is non-empty (FR-006), captures the issue number from stdout, and passes it to `inject_parse_error_marker.py` calls.

**Rationale**:

- **Pattern consistency**: credential-health-check uses the same fuzzy-search + startswith-filter dedup approach (R-005 in that mission). Reusing the pattern keeps cognitive overhead low.
- **Helper, not agent prompt**: same reason as R-005/R-006.

---

## R-008 — Test strategy

**Decision**: Three test layers:

1. **Unit tests** on `prescan.py`'s extended classifier (`tests/inbox/test_prescan_parse_failure.py`) — covers the four malformation cases per FR-005 plus regression tests on existing happy-path classifications. Fixtures: synthetic notes representing each malformation.
2. **Unit tests** on `routing_log.py` (`tests/inbox/test_routing_log.py`) — read/write/dedup against tmp_path-scoped JSONL files.
3. **End-to-end smoke** (canary) — a runbook procedure where Kent deliberately introduces a malformed note into `01-Inbox/` on a test branch / sandbox manifest, watches the next cron tick produce the expected "Inbox quality" issue + marker injection + no duplicate route. Test passes when: (a) zero duplicate GH issues filed, (b) "Inbox quality" issue surfaces the malformed note with correct reason, (c) callout marker injected with correct format, (d) after Kent fixes the frontmatter, next tick auto-strips the marker.

**Rationale**: the deterministic layers (parser + log) have unit-test surfaces; the agent runtime behavior is best tested via canary against the real cron infrastructure. Matches the pattern used for felix-doc-auditor.

---

## R-009 — Architecture documentation updates

**Decision**: Two updates in scope for this mission:

1. **`service-inventory.md` + `service-inventory.json`** — add the routing log state file as a tracked artefact under the `felix-admin-capture` cron entry's notes. Document that the state file is at `~/second-brain/agents/state/inbox-routing.jsonl` and is NOT git-tracked.
2. **`docs/runbooks/inbox-ops.md`** (if it exists; otherwise this is out of scope) — add the new operator workflow: "When you see an Inbox quality issue, ...". Quick read confirms `docs/runbooks/inbox-ops.md` is in the repo; will be updated.

**Out of scope for this mission**: any change to `docs/design/architecture/data/service-inventory.json`'s schema (adding a new "state file" field type). The notes field is sufficient.

---

## Open items deferred to implement phase

| ID | Item | Disposition |
|---|---|---|
| **D-001** | Should `strip_parse_error_marker.py` be invoked by prescan (during classification) or by the agent (during Step 5 frontmatter write)? | Implement-phase decision. Default: prescan, because it already reads every file and can detect "marker present + parses cleanly" in one pass. The agent's Step 5 write happens *after* prescan, so it's already too late for prescan to strip — but prescan can strip on the NEXT cron tick which is acceptable. |
| **D-002** | Exact format of the `parse_failures` field in prescan's JSON output | Implement-phase decision. Likely shape: `parse_failures: [{path: <abs>, reason: <short string>}]` mirroring `unprocessed_paths` style. |
| **D-003** | Should the routing log `note_excerpt` come from the file body (first ~120 chars after frontmatter) or from the GitHub issue title? | Implement-phase decision. Default: body-derived excerpt so the routing log is independently meaningful without GitHub access. |
