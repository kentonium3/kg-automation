# Research: F019 Escalation Engine

**Date**: 2026-04-06
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Resolved Unknowns

### Vikunja priority values

**Decision**: Priority filter is `priority >= 2` (medium and above).
**Rationale**: Confirmed from live Vikunja API — priority field is integer:
0=unset, 1=low, 2=medium, 3=high, 4=urgent. Tasks with priority 0 (unset)
or 1 (low) are excluded from escalation to prevent alert fatigue on
non-critical work.
**Source**: Live API query on task schema (2026-04-06).

### Goals project ID

**Decision**: Goals project is ID 11. Habits project is ID 13.
**Rationale**: Confirmed from `GET /api/v1/projects` on live instance.
Note: There are also system virtual projects (negative IDs) including
ID -5 "Goals" — these are saved filters, not real projects. The exclusion
filter should use `project_id NOT IN (11, 13)`.
**Source**: Live API query (2026-04-06).

### Escalation comment format

**Decision**: Use `[Felix-Escalation] YYYY-MM-DD | state | disposition`
format as defined in the spec.
**Rationale**: Follows the established `[Felix]` comment pattern from
the habits agent. The `[Felix-Escalation]` prefix distinguishes these
comments from habit completion comments. Pipe-delimited fields are
simple to parse. Lowercase hyphenated state tokens allow future extension
without breaking existing parsers.
**Alternatives considered**: JSON comments (rejected — harder to read in
Vikunja UI), separate Vikunja project as log (rejected — over-engineered
for the pattern), labels (rejected — labels are shared across tasks and
don't carry per-occurrence state).

### Cron timing

**Decision**: 8:00 AM ET (12:00 UTC) — 55 minutes after habit check-in.
**Rationale**: Gives Kent time to process the habit check-in before
escalation alerts arrive. The habits cron runs at 7:05 AM ET (11:05 UTC).
The escalation cron at 8:00 AM ET provides separation without delaying
too long into the workday.
**Source**: Planning decision based on existing cron schedule review.

### Agent workspace location on office2

**Decision**: `/data/services/openclaw/escalation-agent/`
**Rationale**: Follows the naming pattern of `habits-agent/` — agent
workspaces are at `/data/services/openclaw/<agent-name>/`.
**Source**: Established pattern from F009.

---

**END OF RESEARCH**
