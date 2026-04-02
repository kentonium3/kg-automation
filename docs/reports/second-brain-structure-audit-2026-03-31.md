---
title: Second Brain Directory Structure Audit
doc_type: reference
status: approved
---

# Second Brain Directory Structure Audit

**Date:** 2026-04-01
**Scope:** Mac (`/Users/kentgale/second-brain/`) and office2 (`/home/kgale/second-brain/`)
**Purpose:** Inventory what exists, identify stale scaffolding, recommend cleanup

---

## Mac: /Users/kentgale/second-brain/

### Directory Tree

```
second-brain/                        (22 files outside .git/ and vault/)
├── README.md
├── .gitignore
├── .claude/
│   ├── settings.local.json
│   └── skills/
│       ├── inbox-processor/SKILL.md
│       ├── kent-voice/SKILL.md
│       └── vault-writer/SKILL.md
├── agents/
│   ├── logs/                        (10 files, 30K)
│   │   ├── daily-summary-2026-03-24.md
│   │   ├── daily-summary-2026-03-25.md
│   │   ├── daily-summary-2026-03-26.md
│   │   ├── daily-summary-2026-03-27.md
│   │   ├── daily-summary-2026-03-28.md
│   │   ├── inbox-processing-2026-03-24.md
│   │   ├── inbox-processing-2026-03-25.md
│   │   ├── inbox-processing-2026-03-26.md
│   │   ├── inbox-processing-2026-03-27.md
│   │   └── inbox-processing-2026-03-28.md
│   └── outputs/                     (empty)
├── assets/                          (empty — all subdirs empty)
│   ├── audio/
│   ├── pdfs/
│   ├── photos/
│   └── videos/
├── intelligence/                    (empty — all subdirs empty)
│   ├── embeddings/
│   └── vector-db/
├── scripts/                         (empty)
└── vault/                           (8.3M, 159 files)
    └── Notes/
        ├── .obsidian/               (34 files)
        ├── CLAUDE.md
        ├── .gitignore
        ├── 00-Inbox/                (64K, 14 files)
        ├── 01-Constitution/         (116K, 19 files)
        ├── 02-Growth/               (36K, 9 files)
        ├── 03-Health/               (24K, 4 files)
        ├── 04-Business/             (188K, 36 files)
        ├── 05-Finance/              (4K, 1 file)
        ├── 06-Journal/              (44K, 10 files)
        ├── 07-Resources/            (52K, 11 files)
        └── _system/                 (76K, 18 files)
```

### Directory Sizes

| Directory | Size | Files |
|-----------|------|-------|
| `agents/` | 48K | 10 |
| `assets/` | 8K | 0 (only .DS_Store) |
| `intelligence/` | 8K | 0 (only .DS_Store) |
| `scripts/` | 0B | 0 |
| `vault/` | 8.3M | 159 |
| `.claude/` | — | 4 (settings + 3 skills) |

### agents/logs/ Detail

Two log types per day covering Mar 24-28 (5 days). No logs after Mar 28.

| File | Size | Modified |
|------|------|----------|
| `daily-summary-2026-03-24.md` | 2.7K | Mar 24 13:34 |
| `daily-summary-2026-03-25.md` | 2.4K | Mar 25 09:50 |
| `daily-summary-2026-03-26.md` | 2.3K | Mar 26 18:51 |
| `daily-summary-2026-03-27.md` | 1.8K | Mar 27 09:13 |
| `daily-summary-2026-03-28.md` | 3.4K | Mar 28 11:15 |
| `inbox-processing-2026-03-24.md` | 3.9K | Mar 24 13:34 |
| `inbox-processing-2026-03-25.md` | 3.5K | Mar 25 09:49 |
| `inbox-processing-2026-03-26.md` | 3.9K | Mar 26 18:50 |
| `inbox-processing-2026-03-27.md` | 2.9K | Mar 27 09:13 |
| `inbox-processing-2026-03-28.md` | 2.9K | Mar 28 11:15 |

These are **Cowork-era logs** — the Cowork agent was retired around Mar 28 when
the system transitioned to the OpenClaw/office2-based architecture. No new logs
have been written here since.

### agents/outputs/

Empty.

### assets/ Subdirectories

All four subdirectories (`audio/`, `pdfs/`, `photos/`, `videos/`) exist but
contain zero files. Scaffolding only.

### intelligence/ Subdirectories

Both subdirectories (`embeddings/`, `vector-db/`) exist but contain zero files.
Scaffolding only — the intelligence layer was never implemented.

### scripts/

Empty directory.

### .claude/skills/

| File | Purpose |
|------|---------|
| `settings.local.json` | Local Claude Code settings |
| `skills/inbox-processor/SKILL.md` | Inbox processing skill definition |
| `skills/kent-voice/SKILL.md` | Kent's writing voice/style skill |
| `skills/vault-writer/SKILL.md` | Vault note writing skill |

### .gitignore

```
vault/02-Growth/_private/     # Private growth content — never commit
agents/logs/                  # Agent runtime files
agents/outputs/
intelligence/vector-db/       # Intelligence layer — database/cache
intelligence/embeddings/
assets/                       # Binary files handled outside git
vault/.obsidian/workspace.json
vault/.obsidian/workspace
vault/.obsidian/cache
vault/.obsidian/plugins/*/data.json
.DS_Store
**/.DS_Store
tmp/
```

### Git Status

- **Branch:** main, up to date with origin/main
- **Total commits:** 1 (`a4dd9a2 Initial commit: second-brain directory structure and vault`)
- **Modified (unstaged):** 13 files — Obsidian settings + vault content changes
- **Untracked:** 30+ files — `.claude/` directory, new inbox items, new vault notes,
  `_backups/` directory
- **Assessment:** Significantly behind — only the initial commit exists, with weeks
  of accumulated changes uncommitted

---

## office2: /home/kgale/second-brain/

### Directory Tree

```
second-brain/                        (2 files outside vault/)
├── agents/
│   ├── logs/                        (2 files, 12K)
│   │   ├── inbox-processing-2026-03-31.md  (8.5K, written by claude user)
│   │   └── inbox-processing-2026-04-01.md  (3.4K, written by claude user)
│   └── outputs/                     (empty)
├── assets/                          (empty)
├── intelligence/
│   ├── embeddings/                  (empty)
│   └── vector-db/                   (empty)
├── scripts/                         (empty)
└── vault/                           (724K)
    ├── .obsidian/
    ├── CLAUDE.md                    (12K)
    ├── 00-Inbox/                    (68K)
    ├── 01-Constitution/             (116K)
    ├── 02-Growth/                   (44K)
    ├── 03-Health/                   (28K)
    ├── 04-Business/                 (236K)
    ├── 05-Finance/                  (8K)
    ├── 06-Journal/                  (48K)
    ├── 07-Resources/                (60K)
    └── _system/                     (88K)
```

### Directory Sizes

| Directory | Size | Files |
|-----------|------|-------|
| `agents/` | 28K | 2 |
| `assets/` | 4K | 0 |
| `intelligence/` | 12K | 0 |
| `scripts/` | 4K | 0 |
| `vault/` | 724K | — |

### agents/logs/ Detail

| File | Size | Modified | Owner |
|------|------|----------|-------|
| `inbox-processing-2026-03-31.md` | 8.5K | Apr 1 11:02 | claude:claude |
| `inbox-processing-2026-04-01.md` | 3.4K | Apr 1 16:01 | claude:claude |

These are **current production logs** from the OpenClaw inbox processor running
on office2. Only `inbox-processing` type — no `daily-summary` type on office2.

### agents/outputs/

Empty.

### assets/, intelligence/, scripts/

All exist, all empty. Same scaffolding as Mac.

### .claude/ Directory

**Does not exist** on office2. No Claude Code skills defined server-side.

### .gitignore

**Does not exist.** office2's second-brain is not a git repository.

### Git Status

**Not a git repository.** No `.git/` directory exists. The directory was created
manually (or via script) with the folder structure but was never initialized as
a git repo.

### Vault Structure — Key Difference

The vault path structure differs between Mac and office2:

| Machine | Vault notes path |
|---------|-----------------|
| Mac | `vault/Notes/00-Inbox/`, `vault/Notes/01-Constitution/`, etc. |
| office2 | `vault/00-Inbox/`, `vault/01-Constitution/`, etc. |

office2 is **missing the `Notes/` intermediate directory**. The numbered folders
sit directly under `vault/`.

### Vault Sync Status

Recent files on office2 (last 7 days) include inbox items through Mar 31 and
constitution backups through Mar 31. The most recent content modification is
Mar 31. The vault appears to be synced through Obsidian Sync (via the
git-based sync mechanism documented in the F010 feature), though the path
structure mismatch above means the sync target may differ.

### File Ownership

Directories are owned by `kgale:secondbrain`. Agent log files are owned by
`claude:claude`, confirming the claude user writes to `agents/logs/` as
expected by the system design.

---

## Analysis

### 1. Cowork-Era Scaffolding (Mac)

The following Mac directories are Cowork-era scaffolding with no current purpose:

| Directory | Evidence |
|-----------|----------|
| `assets/audio/` | Empty, never populated |
| `assets/pdfs/` | Empty, never populated |
| `assets/photos/` | Empty, never populated |
| `assets/videos/` | Empty, never populated |
| `intelligence/embeddings/` | Empty, intelligence layer never built |
| `intelligence/vector-db/` | Empty, intelligence layer never built |
| `scripts/` | Empty, no scripts ever added |
| `agents/outputs/` | Empty on both machines |

These were part of the original second-brain design but were never populated.
The system evolved toward OpenClaw + Vikunja before these layers were needed.

### 2. Mac agents/logs/ — Cowork Logs

The 10 files in Mac's `agents/logs/` (Mar 24-28) are **stale Cowork-era logs**.
The Cowork agent ran on the Mac and produced both `daily-summary` and
`inbox-processing` logs. This agent was retired around Mar 28.

The current inbox processor runs on **office2** and writes only
`inbox-processing` logs there. The Mac logs are historical artifacts.

### 3. Structural Differences Between Mac and office2

| Aspect | Mac | office2 |
|--------|-----|---------|
| Git repo | Yes (1 commit, dirty) | No |
| `.gitignore` | Yes | No |
| `.claude/` directory | Yes (settings + 3 skills) | No |
| `README.md` | Yes | No |
| `agents/logs/` content | Cowork logs (Mar 24-28) | OpenClaw logs (Mar 31-Apr 1) |
| Vault path | `vault/Notes/XX-Folder/` | `vault/XX-Folder/` |
| Vault size | 8.3M | 724K |

### 4. Vault Path Mismatch

This is the most significant finding. Mac has an extra `Notes/` directory level:

- **Mac:** `second-brain/vault/Notes/00-Inbox/`
- **office2:** `second-brain/vault/00-Inbox/`

This means Obsidian Sync may be targeting different paths, or one side has the
"correct" structure and the other was set up differently. The vault size
difference (8.3M vs 724K) suggests the office2 vault may be incomplete or may
be missing the `.obsidian` plugin data and binary attachments.

### 5. Git Tracking vs. Intent

**What's tracked:** Everything except items listed in `.gitignore` (private
content, agent logs, intelligence DBs, assets, Obsidian cache).

**What's actually committed:** Almost nothing — only the initial commit exists.
13 files are modified and 30+ are untracked. The git repo has not been
maintained since initial setup.

**Assessment:** The `.gitignore` rules match the stated intent (vault content
tracked, private and runtime data excluded), but the repo has not been kept
current. This may be intentional (the repo was scaffolding for Cowork and is
no longer the primary coordination mechanism) or an oversight.

### 6. .claude/skills/ on Mac

Three skills exist (`inbox-processor`, `kent-voice`, `vault-writer`). These
were likely created for Cowork-era Claude Code sessions working directly in the
second-brain repo. Their current relevance depends on whether Claude Code
sessions are still run from `~/second-brain/` or whether all agent work now
goes through kg-automation + office2.

---

## Recommendations

### Directories to Remove

| Directory | Machine | Reason |
|-----------|---------|--------|
| `assets/audio/` | Both | Empty scaffolding, never used |
| `assets/pdfs/` | Both | Empty scaffolding, never used |
| `assets/photos/` | Both | Empty scaffolding, never used |
| `assets/videos/` | Both | Empty scaffolding, never used |
| `intelligence/embeddings/` | Both | Empty scaffolding, layer never built |
| `intelligence/vector-db/` | Both | Empty scaffolding, layer never built |
| `scripts/` | Both | Empty, no scripts ever added |
| `agents/outputs/` | Both | Empty on both machines, no producer exists |

If `assets/` and `intelligence/` are fully emptied, the parent directories can
be removed too.

### Directories to Keep

| Directory | Machine | Reason |
|-----------|---------|--------|
| `agents/logs/` | office2 | Active — OpenClaw inbox processor writes here |
| `agents/logs/` | Mac | Archive or delete — Cowork logs are stale |
| `.claude/skills/` | Mac | Review — may still be useful for local vault work |
| `vault/` | Both | Core content — the entire point of the repo |

### Mac agents/logs/ Decision

Three options for the 10 Cowork-era log files:
1. **Delete** — they served their purpose and the system has moved on
2. **Archive** — move to `agents/logs/archive/cowork/` if historical reference
   is wanted
3. **Leave** — they're gitignored and take 30K of disk; low cost to keep

### Vault Path Mismatch — Must Resolve

The `vault/Notes/` vs `vault/` mismatch needs to be resolved before any sync
improvements. Determine which is canonical:
- If Mac's `vault/Notes/` is correct → office2 needs a `Notes/` directory
- If office2's `vault/` is correct → Mac has an extra nesting level

This likely relates to how Obsidian Sync was configured on each machine and may
have been addressed (or identified) during the F010 feature work.

### Git Repo Status — Decision Needed

The Mac second-brain git repo has been dormant since its initial commit. Options:
1. **Commit and maintain** — bring the repo current, establish a commit cadence
2. **Archive and abandon** — the repo served its Cowork-era purpose; vault
   sync is now handled by Obsidian Sync, and agent coordination is in
   kg-automation
3. **Reinitialize** — if the structure is about to change significantly, it
   may be cleaner to start fresh after cleanup

### Recommended Clean Target Structure

**Mac:**
```
second-brain/
├── .claude/skills/          (if still used for local vault work)
├── agents/logs/             (archive or remove Cowork logs)
├── vault/                   (resolve Notes/ nesting question)
├── .gitignore
└── README.md
```

**office2:**
```
second-brain/
├── agents/logs/             (active — OpenClaw writes here)
├── vault/                   (resolve Notes/ nesting question)
└── .gitignore               (should be added if git is initialized)
```

All empty scaffolding (`assets/`, `intelligence/`, `scripts/`, `agents/outputs/`)
removed from both machines.
