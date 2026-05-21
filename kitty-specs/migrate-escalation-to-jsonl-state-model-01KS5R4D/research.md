# Research: Migrate escalation to JSONL state model

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Date**: 2026-05-21

Engineering decisions to lock in before implementation. Format: **Decision → Rationale → Alternatives considered**.

---

## D1. DOMAIN_STATES["escalation"] vocabulary update

**Decision**: Replace the existing `frozenset({"triggered", "level-1", "level-2", "resolved", "dismissed"})` in `scripts/common/state_log_schema.py` with the Q1=A flat enum `frozenset({"level_sent", "snoozed", "dismissed", "done", "rescheduled"})`.

**Rationale**: Spec FR-003 mandates the flat-enum vocabulary. The existing enum (set in place by Phase 2 anticipating Phase 6) reflects the rejected Q1=B composite-string style. Per the spec's amended C-003 (2026-05-21), per-domain `DOMAIN_STATES` updates are NOT a "library modification" — they are the canonical mechanism for each consuming phase to declare its vocabulary. Phase 6 owns the escalation enum.

Zero data migration: no records have ever been written under the old enum (no escalation records exist in any JSONL today). The replacement is a code-only change.

**Alternatives considered**:
- Keep existing enum and bend FR-003 to composite-string states (rejected — undoes Q1=A discovery decision).
- Add new vocabulary alongside old (rejected — clutters the enum with unused tokens; harder for reviewers to enumerate per NFR-005).
- Use a dedicated JSONL store outside the state_log library (rejected — violates spirit of Phase 2 reuse; reinvents append+fsync semantics).

---

## D2. Per-project JSONL file naming

**Decision**: One JSONL file per Vikunja project that hosts escalation-subscribed tasks. Filename: `<project-slug>-escalation-history.jsonl` under `/data/services/openclaw/state/escalation/`.

Project-slug derivation:
1. Fetch project title from Vikunja API (`GET /api/v1/projects/{id}`).
2. Lowercase, replace whitespace with `-`, strip non-alphanumeric except `-`.
3. Collapse repeated hyphens; trim leading/trailing hyphens.
4. Validate result matches `^[a-z0-9][a-z0-9-]{0,63}$`; refuse and hard-fail if not.

Special-case override (config file or hardcoded map) for any project whose slug collides with another.

**Rationale**: Spec NFR-003 requires per-project files. The Vikunja project `id` is immutable (`reference_vikunja_id_vs_identifier.md`), but slugs derived from titles are human-readable in operator log inspection. Combined: filename uses slug; the JSONL record includes both `task_id` and `project_id` for unambiguous routing.

**Alternatives considered**:
- Single shared `escalation-history.jsonl` (rejected — violates NFR-003).
- Filename keyed on project `id` only (e.g., `project-4-escalation-history.jsonl`) — viable but harder to scan in operator workflows. Compromise: keep slug in filename, project_id in records.
- Sub-directories per project (rejected — needless filesystem complexity).

---

## D3. Reconcile detection for "rescheduled then UI-edited"

**Decision**: Reconcile emits a synthetic `rescheduled` record whenever:
- The Vikunja task's current `due_date` differs from the JSONL's last-known `reschedule_to` value (or from the original due_date if no `rescheduled` record exists)
- AND no `done` or `dismissed` record is present
- AND the JSONL has at least one `level_sent` record (i.e., the task is escalation-subscribed)

The synthetic record carries `source: "reconcile"` and `reschedule_to: <new vikunja due_date>`. Subsequent ticks treat it as authoritative.

If reconcile encounters a state it cannot interpret (e.g., Vikunja `done=true` AND JSONL says `dismissed`, AND no clear ordering), it falls through to Q10 hard-fail (D8).

**Rationale**: The simplest rule that handles the spec edge case without inventing new ceremony. UI edits to due_date are the dominant non-Felix mutation path; emitting a `rescheduled` synthetic record keeps the state model consistent with Kent's intent.

**Alternatives considered**:
- Treat any due_date drift as hard-fail (rejected — too aggressive; due_date editing in Vikunja UI is a normal Kent action).
- Emit synthetic record only if the new due_date is in the future (rejected — Kent legitimately moves dates backward sometimes; the JSONL should record reality, not policy).

---

## D4. snooze_until write-time computation

**Decision**: When recording a snooze, compute `snooze_until` at write-time as `today + timedelta(days=snooze_days)` in America/New_York timezone (Kent's local TZ). Persist as ISO-8601 date (`YYYY-MM-DD`).

Reads of `snooze_until` later are pure string comparisons against `date.today().isoformat()` (also in America/New_York). No re-computation.

**Rationale**: Spec FR-004. Write-time is the authoritative clock — if the system clock drifts later or the timezone changes, the persisted value remains the user-intended snooze window. Date arithmetic in local TZ matches Kent's mental model ("snooze 3 days" = three of Kent's calendar days, not three UTC days).

**Alternatives considered**:
- Persist `snooze_days` only; recompute at every read (rejected — FR-004 explicitly forbids this).
- Persist both `snooze_days` AND `snooze_until` (rejected — redundant; if they ever disagree, which is authoritative?).
- Use UTC dates everywhere (rejected — Kent's snooze-window mental model is local-TZ).

---

## D5. Backfill comment vocabulary mapping

**Decision**: The backfill helper reads `[Felix-Escalation]` comments from each escalation-subscribed Vikunja task, parses them per the existing SKILL.md vocabulary, and emits JSONL records using the locked mapping:

| Existing comment shape | New JSONL `event_type` | Structured parameters |
|---|---|---|
| `level-1 \| sent` | `level_sent` | `level: 1`, `source: "backfill"` |
| `level-2 \| sent` | `level_sent` | `level: 2`, `source: "backfill"` |
| `snoozed:Nd \| acknowledged` | `snoozed` | `snooze_days: N`, `snooze_until: <comment-date + N days>`, `source: "backfill"` |
| `dismissed \| acknowledged` | `dismissed` | `source: "backfill"` |
| `done \| acknowledged` | `done` | `source: "backfill"` |
| `rescheduled:YYYY-MM-DD \| acknowledged` | `rescheduled` | `reschedule_to: <YYYY-MM-DD>`, `source: "backfill"` |

Malformed comments (parse fails, unknown vocabulary, missing fields) are NOT replayed. They are collected into a backfill summary report (stdout) with the task ID, comment snippet (first 80 chars), and parse error. Per Phase 4 cycle 2 pattern.

Idempotency: rerunning backfill is safe because `state_log.append` honors the existing dedup mechanism — re-emitted records collide on the existing dedup key and are no-ops.

**Rationale**: Same pattern as Phase 4 (#307) habits backfill. The locked mapping preserves all historical state; malformed-comment surfacing per Phase 4 cycle 2 lesson keeps the operator aware of what didn't replay.

**Alternatives considered**:
- Attempt heuristic recovery on malformed comments (rejected — Q10 philosophy: skip + report, never guess).
- Skip backfill entirely; start fresh JSONL state on cutover (rejected — would lose all prior escalation history; Kent's snooze windows would reset to zero).

---

## D6. Three-write ordering for live escalation events

**Decision**: When the agent sends a Level N alert (or records Kent's response), the order is:

1. **Vikunja side-effect first**: For a level-sent event, that's the WhatsApp send → `[Felix-Escalation]` comment PUT. For Kent's `N done` reply, that's the Vikunja `PATCH /tasks/{id}` with `done=true` → comment PUT. The comment is the v1 surface preserved during soak (per C-001).
2. **state_log.append second**: The JSONL line is written last, after the Vikunja side-effect succeeded.

If the Vikunja step fails, no JSONL line is written; the next tick will re-attempt. If the JSONL step fails after Vikunja succeeded, the helper exits non-zero with a clear stderr — operator manually adds the missing JSONL record. Reconcile will surface the gap on the next tick.

**Rationale**: Mirrors habits Phase 3 D4. Vikunja is the unreliable remote; failing there first surfaces the network problem before any state_log line is written. Vikunja state is authoritative for the existential "did Kent get the message" question — the JSONL is canonical for our derived state walk.

**Alternatives considered**:
- JSONL first, Vikunja second (rejected — if Vikunja then fails, JSONL says "level sent" but WhatsApp wasn't delivered → Kent missed alerts that the state walk thinks happened).
- All three writes wrapped in a Python transaction (rejected — there's no underlying transaction; Vikunja is HTTP, JSONL is fsync. The "three-write atomic contract" is the application-level invariant defined by ordering + Q10 hard-fail).

---

## D7. derive_state pure function shape

**Decision**: `derive_state(records: list[StateLogRecord]) -> EscalationState`

Where `EscalationState` is a frozen dataclass:

```python
@dataclass(frozen=True, slots=True)
class EscalationState:
    current_state: Literal["new", "level_1_sent", "level_2_sent",
                            "snoozed", "dismissed", "done", "rescheduled"]
    last_event: Optional[StateLogRecord]
    snooze_active_until: Optional[date]
    next_eligible_level: Optional[int]  # 1 or 2 or None (terminal/resolved)
    last_event_recorded_at: Optional[datetime]
```

Input: list of records for ONE task, newest-first (caller filters and sorts).
Output: complete picture for the policy walk. All escalation policy semantics (when a snooze expires, when level-2 becomes due after level-1) live here. No HTTP. No file I/O. Pure.

Hard-fail surface: if the records are inconsistent (e.g., `level_sent` with no level parameter; `snoozed` with no snooze_until; `rescheduled` with no reschedule_to), `derive_state` raises `EscalationStateError`. Callers catch this and route to Q10 hard-fail (D8).

**Rationale**: Pure function = trivially unit-testable. Every event_type path + edge case is enumerable in tests. Reviewable per NFR-005. Matches the spec FR-001 intent that JSONL is the SOLE state source.

**Alternatives considered**:
- Method on a stateful escalation-engine class (rejected — pure function is simpler, more testable, no shared mutable state).
- Return a dict rather than a dataclass (rejected — dataclass is documented and slottable; dicts encourage typos).

---

## D8. Q10 hard-fail trigger conditions

**Decision**: The escalation helpers trigger Q10 hard-fail when ANY of:

1. **Malformed JSONL line**: a record fails `validate_record()` from the Phase 2 library (after the D1 vocabulary update). Includes any line that JSON-parses but has missing/typo'd parameter fields per the event_type.
2. **Phantom subscription**: Vikunja task has at least one historical `[Felix-Escalation]` comment (escalation-subscribed) BUT the JSONL has zero records for this task_id. This implies the backfill skipped/missed this task, OR the agent attempted to send a level WITHOUT recording, OR the JSONL was manually deleted. All three cases require operator triage.
3. **derive_state inconsistency**: derive_state raises `EscalationStateError` (see D7).

In all three cases, the helper:
1. Logs the failure (one line to stderr with task_id + reason).
2. Skips the task this tick (NO level sent, NO synthetic record).
3. Files a P2-bug per D9 (with dedup).
4. Continues processing other tasks.

**Rationale**: Spec FR-008. Asymmetric-consequence default: bad outcomes (silent downgrade, spurious re-alert) are structurally impossible. The neutral outcome (skip + alert operator) is what happens.

**Alternatives considered**:
- Synthetic-correction approach (auto-write a "best guess" record to repair the gap) — rejected explicitly by spec FR-008.
- Halt the entire tick on any hard-fail (rejected — one bad task shouldn't stop alerts for other tasks).

---

## D9. Hard-fail dedup query format

**Decision**: Before filing a hard-fail P2-bug, query:

```bash
gh issue list \
  --repo kentonium3/kg-automation \
  --state open \
  --search 'in:title "(task #<vikunja_id>)" "Escalation hard-fail"' \
  --json number,title \
  --limit 5
```

If any result returned, skip filing (dedup hit). If empty, file via `scripts/openclaw/agents/main/felix-file-issue.py`:

```
Title: Escalation hard-fail: <task title> (task #<vikunja_id>) — <reason>
Body: <structured body with task link, JSONL snippet, vikunja state, derive_state output, recommended triage steps>
Labels: P2-bug, area/escalation
```

Verification:
- Task renames after issue is filed: subsequent ticks still hit dedup because the search anchors on `task #<id>`. The TASK TITLE in the issue title may go stale, but the `task #<id>` substring keeps the search valid.
- Task project moves: same — `task #<id>` is project-agnostic.
- Issue manually closed without fixing the record: next tick re-files (dedup query specifies `--state open`).

**Rationale**: Spec FR-009. Vikunja `id` is immutable per memory `reference_vikunja_id_vs_identifier.md`; title-prefix dedup keyed on `task #<id>` survives renames and project moves. Re-fires correctly when issue is closed prematurely.

**Alternatives considered**:
- Dedup keyed on title text (rejected — task renames would orphan the dedup; Vikunja allows free editing of task titles).
- Dedup via local state file ("issues_filed.json") rather than gh search (rejected — local state can drift from GitHub state; the gh query is authoritative).
- Suppress re-filing for 24h after close (rejected — adds complexity; the open-state filter is sufficient).

---

## D10. Per-tick file-locking

**Decision**: Use the existing `state_log.append` locking semantics as-is. The Phase 2 library handles fcntl-style locking on each domain's JSONL file. Per-project escalation files inherit this — each `state_log.append(project_slug, record)` call acquires the lock for that one file.

No new locking surface needed in escalation helpers.

**Rationale**: The cron runs every 24h. Concurrent escalation ticks are essentially impossible. The locking exists as a defense-in-depth against operator-triggered backfill running concurrently with a cron tick — the lib already handles this.

**Alternatives considered**:
- Implement a separate "tick lock" that prevents two escalation ticks from running concurrently (rejected — over-engineering for the 24h cadence).

---

## D11. Comment-write parity during soak (C-001 implementation)

**Decision**: During the 3-day soak window, `record_completion.py` writes BOTH:

1. A `[Felix-Escalation]` comment in the v1 format (existing SKILL.md vocabulary). This preserves the v1 substrate.
2. A JSONL record in the new flat-enum schema.

The agent's state-derivation path (via `derive_state`) reads ONLY the JSONL. The v1 comment write is a write-only mirror for rollback safety per C-001.

After the soak completes and Phase 6 is declared done, a follow-on mission removes the v1 comment-write call. The comments accumulate during soak; if rollback is needed (revert to v1), the comments are the authoritative state and the JSONL is discarded.

**Rationale**: Spec C-001. Rollback to v1 is "a single config flip" because v1 is being kept warm in production throughout the soak. Comments don't need to be re-derived from JSONL on rollback.

**Alternatives considered**:
- Write JSONL only; have rollback path regenerate comments from JSONL if needed (rejected — adds a rollback-time computation step; comment writes during soak are cheap; the asymmetry favors keeping v1 warm).
- Write comments only during soak, JSONL only after (rejected — defeats the purpose of having JSONL as canonical from day 1 of the new flow).

---

## Summary

11 engineering decisions, all locked. No outstanding clarifications. Proceed to Phase 1 design artifacts (data-model.md, contracts/, quickstart.md).
