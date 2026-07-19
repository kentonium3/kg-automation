# Issue matrix — openclaw-skills-sync-01KXW1DQ

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #567 | agent-prompt-sync — the reference mechanism this mission mirrors | verified-already-fixed | Already shipped/closed; WP01 reuses its shared libs (`scripts/deploy/lib/{gitsync,deploylock,health}`) and mirrors its locked-tick discipline — commit 42768eae |
| #714 | Vikunja-config epic — owns the skill CONTENT refresh (out of scope here) | deferred-with-followup | spec.md "Out of Scope" + C-004; the vikunja-api SKILL.md content refresh is #714 itself. This mission ships the deploy/sync MECHANISM only. |
| #557 | Rebaseline obligation for audited surfaces | fixed | WP03 ships `deploys/queued/skills-sync.yaml` (audited_surface: true) + hard-gate deploy; WP04 extended `audited-surfaces.json` globs to cover `scripts/openclaw/deploy/*.{service,timer}` + `scripts/deploy/*.sh` (commit e50f87f1) so the new surfaces are actually monitored. Merge records the rebaseline outcome. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
