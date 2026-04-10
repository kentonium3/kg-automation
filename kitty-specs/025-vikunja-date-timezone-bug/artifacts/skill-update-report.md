# WP01 — vikunja_api Skill Update Report

**Mission:** 025-vikunja-date-timezone-bug
**Work Package:** WP01 — Fix vikunja_api Skill
**Date:** 2026-04-10
**Target:** `~/.openclaw/skills/vikunja-api/SKILL.md` on office2

## Summary

Updated the canonical `vikunja_api` skill on office2 so its task-creation
example and accompanying description use an explicit ET offset
(`-04:00`) instead of the UTC `Z` suffix. This addresses Bug B from the
mission's `research.md`: agents copying the skill example were creating
tasks with UTC-midnight timestamps, which Vikunja interprets as the
previous day for evening-ET users (off-by-one error).

Only the task-creation section was changed. Query/filter examples later
in the skill (line 331) that reference `2026-04-01T00:00:00Z` are left
intact because they operate against Vikunja's storage layer, which is
genuinely UTC.

## Backup

Pre-edit backup created on office2:

```
/home/claude/.openclaw/skills/vikunja-api/SKILL.md.backup.2026-04-10
```

Verified identical to the original via `diff` before editing. There is
no repo-side copy of this skill (see extension plan in #152), so this
backup is the sole rollback path. To restore:

```bash
ssh office2-claude "cp ~/.openclaw/skills/vikunja-api/SKILL.md.backup.2026-04-10 ~/.openclaw/skills/vikunja-api/SKILL.md"
```

## Changes

### T002 — Creation example (line 159)

**Before:**

```bash
-d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
```

**After:**

```bash
-d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00-04:00", "priority": 1}' \
```

### T003 — Description bullet (line 165)

**Before:**

```
- `due_date` must be ISO 8601 format (e.g., `2026-04-15T00:00:00Z`)
```

**After:**

```
- `due_date` must be ISO 8601 format with an explicit timezone offset
  (e.g., `2026-04-15T00:00:00-04:00` for EDT, `-05:00` for EST).
  Do NOT use the `Z` (UTC) suffix for task creation — it causes
  off-by-one errors for tasks created in the evening ET.
```

### T004 — Dynamic offset resolution note (new content)

Appended immediately after the description bullet:

```
  To determine the current offset dynamically (handles EDT/EST transitions
  automatically):

  ```bash
  TZ=America/New_York date +%:z
  ```

  This returns `-04:00` during EDT and `-05:00` during EST. Use this in
  your due_date computation rather than hardcoding an offset.
```

## Verification (T005)

### Before-state grep

```
$ ssh office2-claude "grep -n '00:00:00Z\|00:00:00-04:00\|TZ=America/New_York date' ~/.openclaw/skills/vikunja-api/SKILL.md"
159:  -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
165:- `due_date` must be ISO 8601 format (e.g., `2026-04-15T00:00:00Z`)
318:- `due_date < 2026-04-01T00:00:00Z` — tasks due before a date
```

### After-state grep

```
$ ssh office2-claude "grep -n '00:00:00-04:00' ~/.openclaw/skills/vikunja-api/SKILL.md"
159:  -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00-04:00", "priority": 1}' \
166:  (e.g., `2026-04-15T00:00:00-04:00` for EDT, `-05:00` for EST).

$ ssh office2-claude "grep -n 'due_date.*00:00:00Z' ~/.openclaw/skills/vikunja-api/SKILL.md"
331:- `due_date < 2026-04-01T00:00:00Z` — tasks due before a date

$ ssh office2-claude "grep -n 'TZ=America/New_York date' ~/.openclaw/skills/vikunja-api/SKILL.md"
174:  TZ=America/New_York date +%:z

$ ssh office2-claude "grep -n '00:00:00Z' ~/.openclaw/skills/vikunja-api/SKILL.md"
331:- `due_date < 2026-04-01T00:00:00Z` — tasks due before a date
```

### Interpretation

- The new ET-offset format appears exactly where expected: once in the
  creation example (line 159) and once in the description bullet
  (line 166).
- The only remaining `00:00:00Z` match is the query filter on line 331,
  which is intentional and correct (query filters operate in UTC).
- The task-creation example and its description no longer contain any
  `Z`-suffixed timestamps.
- The dynamic offset resolution note is present at line 174.

## Definition of Done — Checklist

- [x] Backup of original skill exists on office2
- [x] Skill example uses ET offset (`-04:00`) instead of `Z`
- [x] Skill description explicitly warns against `Z` suffix for creation
- [x] Dynamic offset resolution note added
- [x] Report artifact documents the change with verification output
- [x] No unrelated changes to the skill (filter/query examples untouched)

## Notes for Reviewer

- The edit was performed directly on office2 via a Python script scp'd
  to `/tmp/wp01_edit.py` and executed under the `claude` user.
- Change control tier: Tier 3 (agent skill docs). No pre-flight
  connectivity/snapshot checklist required.
- OpenClaw skill persistence risk (noted in the WP risks section) has
  not materialized — the edit persisted after write. If a future
  OpenClaw sync regenerates the skill from a source template, the
  backup can be used to re-apply the fix, and the skill source should
  be added to a repo-managed location as part of #152's extension plan.
