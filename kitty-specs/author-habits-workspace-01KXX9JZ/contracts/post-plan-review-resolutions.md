# Post-Plan Codex Review #1 — Findings & Resolutions

Independent Codex (`gpt-5.5`, `spec-kitty-review` profile) design critique of spec + plan +
research + data-model, run 2026-07-19 before task decomposition. All five findings accepted
and folded back (review-AND-fix). Full log: session scratchpad `codex-postplan.log`.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | HIGH | FR-008's de-inline safety proof named the wrong runtime authority — claimed helpers "resolve by name at runtime". Actual: helpers resolve project id via `scripts/common/vikunja_refs.json` (`vikunja_scope`, `HABITS_PROJECT_ID`); active task set from sync-cache + `phase3-schedule.yaml` + morning artifact. Prompt literals consumed by neither helpers nor agent (so de-inline IS safe). | Corrected FR-008, research Decision 3, data-model TOOLS rows, plan IC-01/Testing, and the spec Assumptions bullet to state the real mechanism. De-inline conclusion unchanged (safe); TOOLS now points to `vikunja_refs.json` as canonical id source; name-based `vikunja_api` resolution reserved for the agent's ad-hoc path. |
| 2 | HIGH | NFR-004's before/after morning-list helper diff is not a meaningful prompt-regression gate — a prompt-only edit cannot change deterministic helper output; it only guards scope-creep. | Rewrote NFR-004 as two guards: (a) helper diff = no-helper/config-change scope guard; (b) static-diff of AGENTS tick/reply commands + relay-verbatim + Output Discipline + completion + habit-management rules, PLUS the live smoke as the real prompt-behavior check. Mirrored into data-model invariant 8 and quickstart step 4. |
| 3 | MEDIUM | Content-conservation quickstart greps too coarse to catch silent sub-block drops. | Expanded quickstart step 3 into a row-by-row checklist matching the data-model move-table (per-file, per-block). |
| 4 | MEDIUM | `service-inventory.md:38,452` still describes a weekly OpenClaw cron via `felix-admin-habits`, contradicting `service-inventory.json` (weekly reporting moved to `felix-habits-weekly`, #723). "#409 incorporated repo-wide" was not true. | Narrowed FR-011 to workspace-prompt-files-local; added **FR-012** to fix the `service-inventory.md` weekly-report rows to match the JSON authority (bounded); expanded NFR-002 scope + Success Criterion 7 + plan source tree/IC-01 accordingly. |
| 5 | LOW | quickstart pointed at wrong prompt-sync audit log path; deploy dir unconfirmed. | Corrected path to `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` (`deploy_agent_prompts.py:66`); confirmed habits deploy dir `= /data/services/openclaw/habits-agent/` (per `service-inventory.json`) and folded into FR-010 + quickstart step 7. |

**Codex synthesis verdict**: "The design is directionally sound … The main fix before task
decomposition is to correct the FR-008 proof and replace the current behavior-preservation
gate with checks that actually cover prompt-mediated behavior." — both addressed above.
