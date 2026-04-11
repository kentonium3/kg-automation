# Phase 0 Research: Inbox Pre-Scan Helper

**Mission**: 027-inbox-pre-scan-helper
**Date**: 2026-04-11

## Purpose

Resolve the deferred-to-plan questions from `spec.md` Assumptions section A-001 through A-009 so that planning can commit to a concrete design.

## Research Items

### R-001: Frontmatter `status` field — observed values

**Decision**: `status: processed` and `status: unprocessed` are the only two values in use. Unknown/missing values are treated as unprocessed per the safety default encoded in FR-003.

**Rationale**: On 2026-04-11, 32 inbox files were sampled on office2 at `/home/kgale/second-brain/notes/01-Inbox/`. All files showed `status: processed`. No unprocessed files were present at the time of sampling (which is consistent with the 4x/day agent run cadence clearing the inbox on every run). Spot-checks of the frontmatter across multiple dates showed a consistent schema:

```yaml
---
date: 2026-03-22
time: 13:55
type: inbox
status: processed
---
```

No alternate `status` values, no multi-line status fields, no quoted values. The schema is stable.

**Alternatives considered**:
- Treat unknown/missing `status` as "error" and fail loudly. Rejected because rejected files would block the cron and leak operator attention on harmless edge cases. The safety default (unknown → unprocessed) means the agent handles it next run with no harm.
- Require a new `processed_at` timestamp field. Rejected as scope creep and would force rewriting every existing file.

### R-002: Age basis for the 7-day archive rule

**Decision**: File mtime (filesystem modification time).

**Rationale**: The frontmatter `date` and `time` fields record the **capture** timestamp (when the user or Wispr Flow created the note), not the **processing** timestamp (when the agent last touched it). Examples in the sampled set show files captured in March that were processed in March and have never been touched since — their mtime reflects the last agent write. Using `date` would mean files captured long ago but processed recently would be prematurely archived. mtime is the correct proxy for "how long since the agent last wrote this file".

**Alternatives considered**:
- Introduce a `processed_at` frontmatter field written by the agent on processing. Rejected as spec-creep; the issue body is clear that this mission should not change the frontmatter schema.
- Use `ctime` (inode change time). Rejected because Linux `ctime` changes on metadata mutations (chmod, chgrp) which happened during mission 026's #161 permission fix — ctime would be skewed across the board.

### R-003: Helper runtime language

**Decision**: Python 3 with PyYAML.

**Rationale**:
- Office2 has Python 3.10+ and PyYAML 6.0.1 confirmed installed (verified 2026-04-11 via `python3 -c "import yaml; print(yaml.__version__)"`)
- kg-automation convention is Python for scripts with any parsing logic; shell for thin wrappers only
- YAML frontmatter edge cases (multi-line, quoting) make shell+grep fragile
- NFR-004 mandates robust YAML parsing; PyYAML is the standard answer
- `json.dumps()` in Python stdlib gives a clean machine-readable stdout contract for the agent

**Alternatives considered**:
- Pure bash + `awk` frontmatter extraction. Rejected per NFR-004.
- Go. Rejected — no Go toolchain on office2, binary distribution would complicate the deploy wrapper.

### R-004: Helper log file location

**Decision**: `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md`

**Rationale**:
- Parallel to the existing `/home/claude/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md` pattern that `felix-admin-capture` already uses
- Markdown format lets Kent read logs in Obsidian if desired (the `agents/logs/` directory is visible in the vault on office2, though not synced to Mac/phone by Obsidian's default-ignore-non-md-except-in-notes rule)
- Daily rotation is idiomatic for kg-automation agent logs
- Path lives under `claude` user's home, which the helper has write access to (no cross-user permission concerns)

**Alternatives considered**:
- `/var/log/felix/inbox-prescan.log` with logrotate. Rejected — too heavyweight, requires sudo to set up, hides logs from the agent's normal "read my logs" workflow.
- Append to the existing `inbox-processing-*.md` file. Rejected — mixes two concerns (helper activity vs agent processing activity) and complicates the helper's error-path logging.

### R-005: Architecture for pre-scan integration

**Decision**: Option B — the `felix-admin-capture` agent runs the helper as its Step 1.

**Rationale**: Kent selected B during the planning interrogation. Summary of the trade-off Kent weighed:
- **Option A (system crontab wrapper + on-demand openclaw agent)**: literal zero agent tokens on empty runs, but loses openclaw cron's built-in failureAlert and isolated-session dashboard features
- **Option B (keep openclaw cron, agent runs helper as Step 1)**: ≤500 tokens per empty run, keeps all openclaw cron features, simpler deploy wrapper (no cron pause/resume dance, no failure-alert replacement)

B trades a small per-empty-run token cost (roughly $0.0002 at Haiku rates) for operational continuity. Over 4 runs/day that's at most ~$0.25/year in empty-run overhead — well worth the operational simplicity.

**Side effect of choosing B**: the mission never disables or re-creates openclaw cron jobs. The deploy wrapper only edits the payload message on existing jobs. This eliminates an entire class of risk (#162-style pause/resume bugs).

**Alternatives considered**:
- Option A (system crontab). Already discussed above.
- Option C (hybrid: system crontab runs helper, helper triggers `openclaw agent` when work exists). Equivalent to A on the failureAlert trade-off; rejected when A was rejected.

### R-006: Deploy wrapper strategy

**Decision**: One-shot `scripts/deploy/deploy-149.sh` following the mission 026 pattern.

**Rationale**: Kent selected A during discovery. #136 (generalized deploy model) is still `spec: brief` and not imminent. Waiting on #136 would stall #149 indefinitely. Building a one-shot is acceptable duplication; when #136 ships, the one-shot can be retroactively migrated to the new primitives.

The deploy wrapper benefits significantly from the R-005 architecture choice: it no longer needs to pause/resume crons, because changing the cron payload message is a safe atomic operation (no half-state exists in the message itself). The worst-case interleaving is "one cron fires mid-deploy using the old message" which is identical to current behavior.

**Alternatives considered**:
- Block on #136. Rejected.
- Deliberately minimal rsync+manual. Rejected because it still needs to call `openclaw cron edit` for each cron and verify the result; a wrapper is the natural place for that.

### R-007: Test approach

**Decision**: pytest unit tests under `tests/scripts/inbox/test_prescan.py` with markdown fixture files under `tests/scripts/inbox/fixtures/`.

**Rationale**: The helper is pure deterministic Python logic (filesystem I/O + YAML parsing + JSON output). Unit tests with fixture files cover every FR and the edge cases in the spec's "Edge Cases" section with zero friction. The helper is small enough that tests give near-complete coverage quickly.

Key test cases to include:
- Happy path: one unprocessed + one stale processed + one recent processed → expected JSON output
- Empty inbox: zero files → `unprocessed_count: 0, archived_count: 0`
- File with no frontmatter → classified as unprocessed
- File with frontmatter but no `status` field → classified as unprocessed
- File with `status: unknown` → classified as unprocessed
- File with `status: processed` and mtime 6 days old → NOT archived
- File with `status: processed` and mtime 8 days old → archived
- File with `status: processed` and mtime exactly 7 days old → boundary case (exclusive-vs-inclusive; document the choice in data-model.md)
- File with `status: unprocessed` and mtime 30 days old → NOT archived
- Malformed YAML → treated as unprocessed with warning
- Missing `{{VAULT_INBOX_PROCESSED}}` directory → helper exits non-zero with clear error
- Idempotence: running twice on the same inbox produces the same output and no duplicate archive moves
- `_private/` under the inbox is never touched (test by constructing a fixture inbox with a `_private/` subdirectory and asserting it is ignored)

**Alternatives considered**:
- Integration tests against a mock office2. Rejected as over-engineered; the helper has no office2-specific logic beyond registry resolution (which is testable via a fake registry file).
- No tests. Rejected; pure-logic Python with unit tests is the lowest-cost-highest-value test surface in the repo.

### R-008: Registry resolution from Python

**Decision**: Read the existing `scripts/vault/paths.json` directly via stdlib `json`. Do NOT invoke a subprocess resolver. Do NOT extend the registry with new markers.

**Rationale**: Mission 026 delivered `scripts/vault/paths.json` with 10 entries including `inbox` and `inbox_processed`. The file is pure JSON, readable by any language's stdlib. The helper needs only two read-only lookups; a shell subprocess would add latency and failure modes for no gain.

Mission 026 also established that the `.tmpl` + substitution flow is for text templates (agent workspace files, etc.), not for Python code. The helper does not consume the `.tmpl` substitution layer — it consumes the `paths.json` data directly.

**Alternatives considered**:
- Subprocess to a shared resolver CLI. Rejected; adds latency and a failure surface for a 6-line stdlib operation.
- Environment variable injection. Rejected; forces the helper to depend on who invokes it, which the agent-as-invoker model makes brittle.
- Extending the registry. Rejected; out of scope per C-004.

## Open Questions

None. All Phase 0 research items are resolved. Phase 1 design proceeds with the decisions above as ground truth.
