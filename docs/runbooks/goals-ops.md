---
title: Goals Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Goals Operations Runbook

This runbook covers the goal declaration system established by F006. Goals are
outcome declarations — distinct from tasks — that anchor all downstream
prioritization, escalation, and briefing features.

## Goal Declaration Format

Every goal declaration must follow this exact structure:

> On [specific date], I have [present-tense outcome statement]
> as evidenced by [observable, concrete proof].

**Rules for a valid declaration:**

- **Date is specific** — a concrete calendar date (e.g., "June 30th, 2026"),
  not a range, quarter, or vague timeframe
- **Outcome is present-tense** — written as if already achieved ("I have"),
  not "I will" or "I want to"
- **Evidence is observable** — something that can be verified without
  interpretation (bank deposits, a completed document, a signed contract,
  a measurable metric)
- **One outcome per declaration** — compound goals must be split into
  separate declarations

### Valid Examples

> On June 30th, 2026, I have established a consulting income of $2,500/month
> through Intentional LLC as evidenced by deposits totaling an average of
> $2,500 or more in my Intentional LLC business checking account for the
> months of April, May, and June 2026.

> On June 27th, 2026, I have completed the Against the Tide 5K race in
> Brewster as evidenced by crossing the finish line and receiving a finisher
> confirmation.

### Invalid Examples

- "I want to grow my consulting business" — future tense, no date, no evidence
- "By Q2, I will have revenue" — range not a date, future tense, vague evidence
- "On June 30th, I have grown as a person" — not observable or verifiable
- "On June 30th, I have a successful business and am healthier" — compound goal, must be split

## Identity Labels

Every goal must have exactly one identity label:

| Label | Color | Domain |
| --- | --- | --- |
| personal | Blue (#2196f3) | Personal life goals |
| intentional | Green (#4caf50) | Intentional LLC business goals |
| metalcasework | Orange (#ff9800) | Metal Casework project goals |

A goal without an identity label is invalid. Assign the label when creating
the goal.

## Where Goals Live

Goals are stored in two places that must stay in sync:

| System | Role | Source of Truth For |
| --- | --- | --- |
| **Vikunja** (Goals project) | Machine-readable store | State (active/achieved/retired), target date |
| **Obsidian** (Goals-MOC.md) | Human-readable reference | Narrative context, full declaration text |

Until automated sync is built (future feature), both must be updated manually
whenever a goal is added, closed, or retired.

## Adding a New Goal

### Step 1 — Vikunja

1. Open Vikunja web UI: `http://100.92.197.90:3456` (requires Tailscale)
2. Navigate to the **Goals** project
3. Create a new task:
   - **Title**: Short summary (e.g., "Intentional: $5K/month consulting income")
   - **Description**: Full declaration in canonical format, followed by evidence
     criteria as a separate paragraph:
     ```
     On [date], I have [outcome] as evidenced by [proof].

     **Evidence criteria:** [detailed description of what counts as proof]
     ```
   - **Due date**: Target date from the declaration
   - **Label**: Identity label (personal, intentional, or metalcasework)

### Step 2 — Obsidian

1. Open `03-Constitution/Goals-MOC.md` in Obsidian
2. Add the declaration as a blockquote under the appropriate identity section
   (Personal, Intentional, or Metal Casework):
   ```markdown
   > On [date], I have [outcome] as evidenced by [proof].
   ```
3. Update the `*Last updated:*` date at the bottom of the file

## Closing an Achieved Goal

When a goal's target date has been reached and the evidence criteria are met:

### Step 1 — Vikunja

1. Open the goal task in the Goals project
2. Mark it as **done** (check the completion box)

### Step 2 — Obsidian

1. Open `03-Constitution/Goals-MOC.md`
2. Move the declaration from its active section to **Archive > Achieved**
3. Add the date achieved:
   ```markdown
   > On June 27th, 2026, I have completed the Against the Tide 5K race...
   >
   > *Achieved: 2026-06-27*
   ```
4. Update the `*Last updated:*` date

## Retiring an Abandoned Goal

When a goal is no longer being pursued (changed priorities, no longer relevant):

### Step 1 — Vikunja

1. Open the goal task in the Goals project
2. Mark it as **done**
3. Add a note in the description explaining why it was retired:
   ```
   **Retired: 2026-07-15** — Priorities shifted to business acquisition;
   consulting income target deferred.
   ```

### Step 2 — Obsidian

1. Open `03-Constitution/Goals-MOC.md`
2. Move the declaration from its active section to **Archive > Retired**
3. Add the date and reason:
   ```markdown
   > On September 30th, 2026, I have established a consulting income of...
   >
   > *Retired: 2026-07-15 — Priorities shifted to business acquisition*
   ```
4. Update the `*Last updated:*` date

## Viewing Active Goals

- **Vikunja**: Use the **Goals** saved filter — shows all active (incomplete)
  goal declarations sorted by target date (nearest first)
- **Obsidian**: Open `03-Constitution/Goals-MOC.md` — active declarations are
  listed under their identity sections
- **Mobile**: Open Vikunja at `http://100.92.197.90:3456` on iPhone (requires
  Tailscale) or view Goals-MOC.md in the Obsidian mobile app

## Setup Script

The Vikunja goal infrastructure was created by `scripts/vikunja/setup_goals.py`.
This script is idempotent and can be re-run safely to verify or repair the
setup:

```bash
# Verify current setup:
python3 scripts/vikunja/setup_goals.py --verify-only

# Re-run full setup (creates only missing entities):
python3 scripts/vikunja/setup_goals.py

# Dry run (shows what would be created):
python3 scripts/vikunja/setup_goals.py --dry-run
```

---

*Last updated: 2026-03-30 (F006)*
