# Issue matrix — felix-admin-cron-path-fix-01KWQTY3

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #658 | Fleet-wide runtime-environment-assumption audit | deferred-with-followup | Filed this mission as the broad follow-on (cwd/HOME/checkout-path class); #656 ships the concrete gateway PYTHONPATH guardrail + inbox fixes, #658 owns the systematic audit + lint. |
| #621 | Rebaseline directives gap (agent-prompt AGENTS.md not baseline-hashed) | deferred-with-followup | WP06 records the determination: gateway drop-in = monitored surface → rebaseline; AGENTS.md changes not hashed (#621) → no rebaseline claimed. The gap itself is tracked in #621. |
| #653 | OpenClaw core ownership relocation (/usr/lib → ~/.local) | deferred-with-followup | Separate in-flight thread; WP01 delivers PYTHONPATH as a systemd drop-in specifically to avoid colliding with #653's ExecStart change. Not modified by #656. |
| #652 | Felix WhatsApp DM-reply break | deferred-with-followup | Unrelated subsystem (WhatsApp DM lifecycle); referenced only as adjacent context. Out of scope for #656; tracked in #652. |
| #659 | Fast-follow: repoint observation-digest logging + complete full /home/claude/second-brain decommission | deferred-with-followup | Filed this session. #656 narrowed FR-008/SC-5 to inbox-only (WP05) to avoid breaking the active observation-digest subsystem; #659 repoints it then completes the full decommission. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
