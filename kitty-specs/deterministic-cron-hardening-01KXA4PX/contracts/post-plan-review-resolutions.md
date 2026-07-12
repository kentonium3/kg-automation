# Post-Plan Codex Review — Resolutions (authoritative amendments)

Codex (spec-kitty-review profile) reviewed spec.md + plan.md + research.md + data-model.md + contracts before task generation. 12 findings (3 Critical, 6 High, 3 Medium). This document is the **authoritative amendment layer**: where it conflicts with an earlier artifact, this wins. Tasks/WPs derive tests + acceptance from here.

## Critical

**C1 — Delivery confirmation predicate (RESOLVED empirically).**
`openclaw message send --json` on a real send returns exit 0 with a non-empty top-level `messageId` and `payload.result.messageId` + `payload.result.runId` (`dryRun:false`). **Predicate for FR-006**: delivery is confirmed IFF exit 0 AND `payload.result.messageId` (or top-level `messageId`) is a non-empty string AND `dryRun == false`. Any other shape (missing/null messageId, malformed JSON, non-zero exit, `dryRun:true`) → NOT confirmed → `delivery_confirmed=false`, `status=failure`, non-zero driver exit. Driver tests include fixtures for: confirmed success, dry-run, missing-messageId, malformed JSON, non-zero exit.

**C2 — Deploy verify vs. real delivery conflict (RESOLVED).**
The felix-canary "run the real unit once" gate would send an unscheduled report. Replace it: the driver gains a **`--self-test`** mode that runs generation + the full delivery path with `openclaw message send --dry-run` (no user-facing send) AND **writes a `last-tick.json`** (so the deploy gate can assert a fresh tick without spamming Kent). The deploy `--self-test` asserts: helper ran, message composed, send-path reached dry-run OK, tick written. The first *real* delivery is the first scheduled Monday run (or an explicit operator-approved one-time `systemctl --user start` — labeled — at Kent's discretion). `--dry-run` (no state) is retained for local preview; `--self-test` (writes tick, dry-run send) is the deploy gate.

**C3 — Transactional scheduler cutover (RESOLVED).**
"Exactly one producer" must be guaranteed. Deploy order in `deploy-habits-weekly-driver.py`: (1) install units + daemon-reload; (2) `--self-test` gate passes; (3) **retire** the openclaw cron (`openclaw cron rm habits-weekly-report`) and assert absence via `openclaw cron list --json`; (4) `systemctl --user enable --now felix-habits-weekly.timer` and assert `next elapse` scheduled; (5) **postcheck: assert NOT both** — the openclaw cron is absent AND the timer is enabled. Fail the deploy (and do not leave a half state) if both producers exist or neither does. Report via #701 bus.

## High

**H4 — Freshness must not lie (RESOLVED).**
The canary `tick-signal-file` probe already treats `exit_code != 0` and `status` ∈ {error,failed,fail,failure} as an explicit failure (`scripts/canary/probes.py` `_explicit_error`). The TickSignal schema MUST therefore use `status: "success"|"failure"` and `exit_code` so a fresh *failure* tick reads as failed, not healthy. **Add `delivery_confirmed: bool` and `failure_reason: str|null`** to the tick for evidence. Service-inventory `expected` text documents: healthy = fresh AND `status=success` AND `exit_code=0`.

**H5 — #714 label swap is not truly config-only (SCOPED to #716).**
Correct: `habit_selector` can hold a label form, but the weekly/morning helpers fetch `/projects/{id}/tasks`, and `habit_project_id()` returns `None` for a label. #723 ships the **seam + the `project_id` fetch strategy** only; the **label fetch strategy (`list_habit_tasks(client, selector)` dispatching on kind) is #716's work** (note posted to #716). NFR-004 is amended: *changing the selector VALUE is config-only; introducing the label FETCH strategy is #716-aligned*. Do not claim the label swap is fully config-only in this mission.

**H6 — Escalation exclusion is project-ID-only (SCOPED to #716).**
Same class as H5: if habits become a label, `escalation_excluded_project_ids` won't exclude them. #723 keeps the ID form; #716 re-derives habit exclusion from `habit_selector` (covered in the #716 note). `enumerate_candidates` reads excluded IDs from `vikunja_scope` so the fix is localized.

**H7 — Enumerate output is PRE-candidates, lifecycle gated downstream (RESOLVED).**
`enumerate_candidates` applies only date/priority/project. The agent MUST call `derive_state` per pre-candidate and alert ONLY when `next_eligible_level != null` (snooze/dismiss/level lifecycle). Contract renamed to "pre-candidates"; AGENTS.md Step 2 wording makes the derive_state gate explicit. An end-to-end fixture proves a snoozed/dismissed task is a pre-candidate but produces no alert.

**H8 — Due-date normalization rules (RESOLVED).**
Explicit in `enumerate_candidates.md`: reject null/empty/sentinel/malformed; parse aware datetime; convert to America/New_York; compare local calendar dates; boundary + DST tests.

**H9 — Escalation failure must be health-visible (RESOLVED).**
`enumerate_candidates` exit 1 must cause a monitored failed run: the agent standing orders treat non-zero enumeration exit as a run failure (truthful report AND OpenClaw `status=error`), so `openclaw-cron-state` catches it. The agent must not swallow it into a healthy-looking run.

## Medium

**M10 — Weekly helper pagination (VERIFY, likely non-issue).**
The weekly helper's fetch (`/projects/{id}/tasks`) is unchanged by this mission (only its project id becomes config-sourced). Add a >50-task regression fixture to confirm it paginates correctly; if a pre-existing pagination bug surfaces, file separately (out of scope to fix here).

**M11 — Systemd unit fields contracted (RESOLVED).**
`felix-habits-weekly.service` MUST set, mirroring felix-canary: `Environment=HOME=/home/claude`, `Environment=PYTHONPATH=/home/claude/kg-automation`, `WorkingDirectory=/home/claude/kg-automation`, `ExecStart=/usr/bin/python3 -m scripts.habits.weekly_report_driver`, a `TimeoutStartSec` ≥ 90s, and the state dir created with correct perms. The driver uses the absolute `/usr/bin/openclaw`. Verify via `systemctl --user show` + path checks in the deploy self-test.

**M12 — Service-inventory full cleanup + postcheck (RESOLVED).**
Update ALL `habit-checkin` references to the retired cron — not only `health_check.crons` but `schedules[]`, notes/purpose text, and any config references — plus add the new `felix-habits-weekly` service. Deploy postcheck asserts live OpenClaw config no longer contains `habits-weekly-report`.

## Net effect on scope
- New: driver `--self-test` mode; explicit delivery predicate; transactional cutover + postchecks; due-date parsing rules; failure-propagation contract; contracted systemd unit fields; tick schema `delivery_confirmed`+`failure_reason`.
- Scoped to #716 (not #723): the label fetch strategy + label-form exclusion (note posted).
- No change to the 4-IC decomposition; these tighten IC-02/03/04 contracts.
