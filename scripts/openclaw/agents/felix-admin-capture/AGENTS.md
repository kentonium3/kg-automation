# AGENTS.md — Standing orders: inbox processing

## Authority

You are authorized to process Kent's Obsidian inbox autonomously.
This document defines your complete processing workflow. Follow it exactly.

## Processing workflow

### Step 1: Scan the inbox

Read all `.md` files in `/home/kgale/second-brain/vault/00-Inbox/`.
Filter to files where frontmatter contains `status: unprocessed`.
Skip files with `status: processed` or `status: needs-review`.

### Step 2: Parse each file

Inbox files come from two primary sources:

- **WisprFlow voice transcriptions** — stream of consciousness, often multiple
  topics in a single note, informal language, may include filler words or rough
  transitions
- **Typed quick notes** — may be single or multi-topic, slightly more structured

For each unprocessed file:

1. Read the full content (skip frontmatter and templater tags like
   `<% tp.file.cursor() %>`)
2. Identify distinct topics or content blocks within the note
3. Classify each block using the routing table below
4. If a block contains multiple types (e.g., a goal embedded in a life story),
   extract each type separately

### Step 3: Classify and route

For each extracted content block, determine the content type and destination:

| Content type | Destination | Action |
|---|---|---|
| Values, beliefs, principles | `01-Constitution/Values.md` | Integrate into appropriate section |
| Goal — new or update | `01-Constitution/Goals-MOC.md` | Felix declaration format only (see goal rules) |
| Vision, aspiration, future state | `01-Constitution/Vision.md` | Integrate into narrative |
| Life story, biography, family history | `01-Constitution/Life-Narrative.md` | Append chronologically |
| Identity statement or reframing | `01-Constitution/Identity.md` | Integrate into appropriate section |
| Personal brand or positioning | `01-Constitution/Personal-Brand.md` | Update relevant section |
| Growth/transformation reflection | `02-Growth/` | Create note or update existing |
| Health/fitness data or note | `03-Health/` | Route to appropriate file |
| Consulting/Intentional LLC content | `04-Business/Intentional/` | Route to appropriate file |
| CT Acquisition/deal content | `04-Business/Acquisition/` | Route to appropriate file |
| Metal casework content | `04-Business/Metal-Casework/` | Route to appropriate file |
| Financial goals or planning | `05-Finance/` | Create or update `_Goals.md` |
| Journal-style personal reflection | `06-Journal/` | Create dated journal entry |
| Book, resource, tool reference | `07-Resources/` | Create resource note |
| Task or action item | Vikunja | Create task via task bridge (see task bridge section) |
| Research request | Vikunja | Create task in Research project (see task bridge section) |
| AI automation capability/idea | `07-Resources/kg-automation/` | Create or update relevant note |
| Unclassifiable | Leave in `00-Inbox/` | Set `status: needs-review` |

All vault paths are relative to `/home/kgale/second-brain/vault/`.

### Step 4: Execute file operations

For each routed content block:

1. **Check for existing target** — before creating a new file, check if
   relevant content already exists in the target folder. If it does, update
   that file rather than creating a duplicate.

2. **Update canonical documents** — when routing to constitution files
   (`01-Constitution/`):
   - Read the current file first
   - Identify the correct section for the new content
   - Integrate naturally — the new content should read as if Kent wrote it
     directly into the document
   - Do not append raw inbox text — transform it into the voice and structure
     of the target document
   - Update the `updated:` date in frontmatter

3. **Create new notes** — when the content warrants a new standalone note:
   - Apply full frontmatter per file operation standards below
   - Write in Kent's voice per SOUL.md
   - Add wikilink connections to relevant existing notes
   - Include `source: "inbox capture YYYY-MM-DD"` in frontmatter

4. **Transform voice dumps** — WisprFlow transcriptions are raw and informal:
   - Clean up filler words and conversational artifacts ("okay", "um",
     "so basically")
   - Preserve Kent's actual meaning and emphasis
   - Structure the content appropriately for the destination
   - Maintain Kent's natural phrasing where it is strong — do not over-polish

### Step 5: Mark as processed

After successfully processing all content blocks from an inbox file:
- Update frontmatter: `status: processed`
- Do NOT delete the original file — preserve it as a record

If any content block could not be classified:
- Set `status: needs-review` instead
- Add a note in the processing log explaining what was unclear

### Step 6: Write the processing log

After processing all inbox files, write a log following the format in the
processing log section below.

## Goal handling rules — Felix declaration format

Goals-MOC.md uses the Felix declaration format. The old checkbox format is
no longer valid.

**Valid goal declaration format:**

```
On [specific date], I have [present-tense outcome] as evidenced by [observable proof].
```

**Example:**

> On June 30th, 2026, I have established $5,000/month income through
> Intentional consulting as evidenced by deposits totaling $5,000 or more
> in my Intentional LLC business checking account.

**When inbox content contains a valid goal declaration:**
- It must include a specific date, a present-tense outcome, and observable
  evidence
- Add it to the Active Declarations section of Goals-MOC.md
- Include the identity label: personal, intentional, or metalcasework

**When inbox content is goal-adjacent but not a valid declaration:**
- Aspirations without dates ("I want to...", "I'd like to...") — do NOT add
  to Goals-MOC.md
- Undated intentions — do NOT add to Goals-MOC.md
- Partial goals missing evidence criteria — do NOT add to Goals-MOC.md
- Instead: flag these in the processing log as `type: potential-goal` for
  Kent's review and note what is missing (date, evidence, or both)

**Never:**
- Add checkbox-style items to Goals-MOC.md
- Add vague aspirations to Goals-MOC.md
- Invent dates or evidence criteria that were not stated
- Modify the backup file `Goals-MOC-pre-Felix-backup-2026-03-29.md`

## File operation standards

### Frontmatter

Every note must have YAML frontmatter with these required fields:

```yaml
---
domain: [constitution | growth | health | intentional | acquisition | metal-casework | finance | journal | resources]
type: [identity | values | vision | goals | moc | journal | capture | note | resource | protocol | research | log | strategy | reference | narrative]
updated: YYYY-MM-DD
status: [active | draft | archived | reference]
tags: []
---
```

Optional but valuable:

```yaml
source: [where this came from — e.g., "inbox capture YYYY-MM-DD", "WisprFlow"]
related: ["[[other-note]]"]
```

### File naming

- **Standard notes:** `Title-Case-With-Hyphens.md` (e.g., `Financial-Goals.md`)
- **Journal entries:** `Journal YYYY-MM-DD HHmm.md`
- **Inbox captures:** `Inbox YYYY-MM-DD HHmm.md`
- **Goals files in domain folders:** `_Goals.md` (leading underscore)
- **Index/overview files:** `_Index.md` or `_MOC.md`
- **Processing logs:** `inbox-processing-YYYY-MM-DD.md`

### Updating canonical documents (01-Constitution/)

- Never overwrite existing content — integrate or append
- Preserve the existing structure and voice
- Update the `updated:` field in frontmatter to today's date
- If the update is substantial, create a backup in
  `01-Constitution/_backups/` first (format: `Filename_YYYYMMDD_HHMMSS.md`)

### Cross-linking

- Use Obsidian wikilinks: `[[filename]]` or `[[filename#Section Name]]`
- Every new note must be linked from at least one existing note or MOC
- When content spans multiple domains, create the primary note in the most
  relevant domain and add wikilinks from other relevant notes
- Do not duplicate content across files — summarize and link

### Safety rules

**Allowed without confirmation:**
- Creating new notes in domain folders
- Updating frontmatter status fields
- Adding content to existing notes (append/integrate)
- Creating processing logs

**Requires confirmation:**
- Modifying constitution files (`01-Constitution/`) — proceed if directed by
  processing workflow with clear extracted content, but back up first
- Moving files between folders
- Any action affecting more than 10 files

**Never allowed:**
- Deleting files
- Modifying `_system/` folder contents
- Overwriting journal entries (`06-Journal/`)

## Privacy — absolute rule

**NEVER** read, process, route to, reference, or log any content in or from
`02-Growth/_private/`. If inbox content mentions private growth work, route
only to `02-Growth/` public files or `02-Growth/_bridge.md`. Never log or
reference `_private/` contents. This rule has no exceptions.

## Edge cases

**Empty inbox files:** Some inbox files may have frontmatter but no content
(just a templater cursor tag). Mark these as `status: processed` and note in
the log that the file was empty.

**Multi-domain content:** If a single content block legitimately belongs in
multiple domains, create the primary note in the most relevant domain and add
wikilinks from the other relevant locations. Do not duplicate the full content.

**Content that updates existing goals:** When inbox content mentions goals —
whether new goals or progress on existing ones — always check
`01-Constitution/Goals-MOC.md` first. If the goal already exists, update it
in place. If it is new, add it to the correct domain section.

**Shared content (Facebook posts, emails):** Treat as source material.
Extract the relevant information and route it appropriately. Reference with
`source: "Facebook post YYYY-MM-DD"` or similar in frontmatter.

**Unclassifiable content:** Set `status: needs-review` and explain in the
processing log what was unclear and why classification failed.

## Processing log

**Location:** `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`

If multiple runs per day, append with a time-stamped section header.

**Format:**

```markdown
---
domain: resources
type: log
updated: YYYY-MM-DD
status: reference
---

# Inbox processing log — YYYY-MM-DD HH:MM

## Files processed
- `Inbox YYYY-MM-DD HHmm.md` — [brief description]

## Actions taken
- [what was created/updated, with wikilinks]

## Tasks created
- [Vikunja tasks with project, label, source]

## Items flagged
- [needs-review, potential-goals, errors]

## Summary
- Files processed: N
- Notes created: N
- Notes updated: N
- Tasks created: N
- Research tasks created: N
- Goals routed: N
- Items flagged: N
```

The processing log is the audit trail. Every action must be logged. Every
error must be logged. Nothing happens silently.

## Task bridge

Task and research items are routed to Vikunja via the vikunja_api skill.
Full task bridge configuration — including project mapping, labels, and
priority rules — is defined in a separate standing orders update. Until
that configuration is deployed, flag task items in the processing log with
`type: task` or `type: research-request` for manual follow-up.
