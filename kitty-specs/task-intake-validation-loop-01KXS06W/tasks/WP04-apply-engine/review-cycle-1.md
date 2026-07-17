---
affected_files: []
cycle_number: 1
mission_slug: task-intake-validation-loop-01KXS06W
reproduction_command:
reviewed_at: '2026-07-17T23:17:50Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP04
review_artifact_override_at: "2026-07-17T23:22:19Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP04"
review_artifact_override_reason: "reviewer-renata APPROVE (cycle 2): kent-token family-replace, Tier-2 matrix, per-line statuses, closes #750; 128 tests"
---

# WP04 (apply engine) — Review cycle 1

Verdict: **REJECT** (one low-severity correctness finding; single-line fix + one test).

WP04 is otherwise excellent work: 40 new tests, 127 intake tests green, and every
load-bearing / high-stakes invariant is correctly implemented and tested (see the
PASS ledger at the bottom). The reject is for a single precision defect on a
non-blocking advisory note that can present **false information to Kent**. Because
WP05/WP06 consume these `notes`/`applied` fields to build the confirmation
message, it is worth correcting before merge.

---

## Issue 1 (must-fix, low severity) — spurious "no due date" follow-up on a task that already has a due date

**Location:** `scripts/intake/apply_reply.py`, `_plan_line`, lines 644–650.

```python
elif not is_overload and effective_q in _DUE_FOLLOWUP_QUADRANTS:
    # q:do / q:schedule with no due: → non-blocking follow-up (SC-007).
    plan.notes.append(
        f"follow-up: {effective_q} has no due date — reply with due:<date> "
        f"(non-blocking)"
    )
    plan.applied["due_followup"] = True
```

**Problem:** the branch fires whenever the *reply* omits `due:` and the
**effective** quadrant is `q:do`/`q:schedule`. `effective_q = line.quadrant or
live_q` (line 584) falls back to the task's *existing* live quadrant. So for a
task that is already `q:do`/`q:schedule` **and already carries a due date**, a
sparse reply that doesn't restate the due (e.g. `1 personal`, or `1 loe:m`) still
emits `"q:do has no due date — reply with due:<date>"`. That statement is **false**
— the task has a due date — and WP06 will render it to Kent, prompting a redundant
reply. The module already has `_has_due(task)` (line 438) but the follow-up branch
does not consult it.

**Fix:** guard the follow-up on the task genuinely lacking a due date, e.g.

```python
elif not is_overload and effective_q in _DUE_FOLLOWUP_QUADRANTS and not _has_due(task):
```

(`_plan_line` currently receives `task`, so `_has_due(task)` is in scope.)

**Test to add** (there is currently no coverage for this branch condition — grep
confirms no `due_date=` fixture in `test_apply_reply.py`): a `q:do` task created
with an existing `due_date` receiving a sparse no-`due:` reply must **not** set
`result.applied["due_followup"]` and must **not** emit a "has no due date" note;
pair it with the existing `test_q_do_without_due_emits_nonblocking_followup` (task
with no due) so both arms of the guard are pinned.

**Secondary note (no change required unless you prefer to tighten):** FR-010 words
the trigger as "when **the reply's quadrant** is q:do/q:schedule". Using
`effective_q` (live-quadrant fallback) is broader than the literal FR, but it is a
defensible reading and, once the `_has_due` guard is in place, it only nudges when
the nudge is actually true and useful. The `_has_due` guard alone resolves the
false-information defect; no further change is strictly required.

---

## Verification ledger — everything else PASSES

**Extra-scrutiny items (from the review brief):**
1. **kent-token ONLY / #750 (FR-007, SC-008):** PASS. Single client-construction
   path (`_build_client`) reads the kent token via `read_kent_token`, which refuses
   the felix-bot path (line 1007); `main` re-checks the guard *before* building the
   client even when a client is injected (lines 1170–1174). No felix-bot label
   attach exists (the felix-bot import is guard-only). `VikunjaClient` is always
   constructed with an explicit kent token, never `token=None` (which would load the
   felix-bot `DEFAULT_TOKEN_PATH`). `test_cli_refuses_felix_bot_token_and_never_touches_client`
   proves **zero requests** (`client.calls == []`).
2. **Family-replace (FR-013, NFR-003, Codex #2):** PASS. `_plan_family_label` adds
   the new member + removes other same-family members; non-family labels untouched;
   `_verify_labels` readback asserts every preserved non-family label survives AND
   `len(fam) <= 1` for both `q:`/`f:` prefixes. RMW `_post_task_fields` echoes the
   writable-field allowlist so partial-replace never zeros an unstated field.
3. **q:eliminate→done / f:4→overload not scheduled (FR-008/009, SC-004):** PASS.
   `q:eliminate` sets `done=True`, skips project; `f:4` → `overload_flagged`,
   decomposition-pending note, no `due:`, terminal/idempotent (`test_f4_overload_idempotent_stays_overload_flagged`).
4. **Tier-2 matrix (FR-010/017):** PASS. ET-EOD via `_et_eod` (real DST offset,
   `-04:00`/`-05:00`, never `Z` — #733); ignore-with-note on eliminate/f:4; malformed
   `due:`/`loe:` → echo-back; matrix columns (incl. `q:delegate`) match data-model;
   missing Tier-2 never blocks Tier-1. (Only the follow-up sub-case is off — Issue 1.)
5. **Per-line statuses (FR-012, Codex #8):** PASS. Full set incl. `moved_conflict`
   / `not_found` / `already_done` / `access_denied` / `failed`; `noop` only on true
   live match (`plan.has_work()` false) or done/deleted; one failing line never
   blocks others (per-line try/except → `failed`).
6. **Correlation (FR-016, SC-011):** PASS. Line-number-set overlap + title-evidence
   tiebreak + recency; orphan number → `echoed_back`; two-same-day-digest test
   present and correct.
7. **NFR-005 timeouts:** PASS. Every GET/POST/PUT/DELETE passes
   `timeout=_HTTP_TIMEOUT`; fake asserts `timeout is not None`. No LLM anywhere.
8. **Tests:** PASS. `python3 -m pytest tests/intake -q` → **127 passed**; WP02/WP03
   suites unbroken.

**Anti-pattern checklist:** 1 Dead code — PASS (helper's CLI `main` is the
invocation surface; WP05/WP06 wire the cron). 2 Synthetic-fixture — PASS (tests
drive `apply_line`/`apply_reply`/`append_ledger` real paths). 3 Silent empty
return — PASS (each `return []`/`None` documented: missing dir, bad parse, skip
stale record). 4 FR coverage — PASS (every `requirement_refs` FR has real
assertions). 5 Frozen surface — PASS. 6 Locked decision — PASS (no LLM; felix-bot
never writes). 7 Shared-file ownership — PASS (WP04 commit `36a9380b` touches only
`scripts/intake/apply_reply.py` + `tests/intake/test_apply_reply.py`; WP01/02/03
files are inherited base commits). 8 Production fragility — PASS (`ApplyError`
raises are fail-loud on mis-apply/wrong-credential; per-line Vikunja errors become
`failed`, never fatal).

Fix Issue 1 (guard + test) and this is a clean approve.
