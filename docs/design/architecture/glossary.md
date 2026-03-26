---
title: Glossary
doc_type: reference
status: approved
---

# Glossary

Canonical terms used across kg-automation documentation, code, and agent instructions.

| Term | Definition |
|------|-----------|
| **office2** | Ubuntu 24.04 LTS server (Dell XPS 8700). Always-on hub for all services. Tailscale IP: `100.92.197.90`. |
| **Tailscale** | Mesh VPN providing encrypted connectivity between office2, Mac, and iPhone. All service access is Tailscale-only. |
| **Vikunja** | Open-source task management system. Runs as Docker container on office2. Serves as the task store and web UI. REST API at port 3456. |
| **OpenClaw** | Orchestration and intelligence layer (planned, F002). Calls Anthropic API directly. Runs skills on office2. |
| **Obsidian Sync** | Cloud sync service keeping the Obsidian vault consistent across Mac, iPhone, and office2. Daemon runs on office2 as `obsidian-sync.service`. |
| **second-brain** | Kent's Obsidian vault at `~/second-brain/vault/Notes/`. Separate repo (`kentonium3/second-brain`). Contains constitution docs, growth journals, and private content. |
| **Restic** | Backup tool. Runs at 4AM daily, backs up `/data/services`, `/data/transcripts`, and `/home/*` to `/mnt/backups/restic-repo`. |
| **spec-kitty** | Workflow management system for feature specification, planning, implementation, review, and merge. |
| **func-spec** | Feature specification document in `docs/func-spec/`. Defines requirements before implementation. |
| **FEAT-NNN** | Feature identifier from the v0.3 spec Phase 1 roadmap (e.g., FEAT-001 = Vikunja deploy). |
| **Wispr Flow** | Voice-to-text input device used on Mac and iPhone. Transcribes speech and outputs text into Obsidian notes. Not a pipeline component. |
| **00-Inbox** | Obsidian vault folder where Wispr Flow output and quick captures land. Processed by the inbox-processor skill. |
| **01-Constitution** | Obsidian vault folder containing life/business goals, values, identity docs. Agent context ceiling — the only vault content agents may read. |
| **02-Growth/_private** | Obsidian vault folder that is absolutely off-limits to all agents and scripts. No exceptions. |
| **personal** | Vikunja label for tasks belonging to Kent's personal Google identity. Blue (#2196f3). |
| **intentional** | Vikunja label for tasks belonging to Intentional LLC Google identity. Green (#4caf50). |
| **claude user** | Linux user on office2 for all agent operations. No sudo. SSH alias: `office2-claude`. |
| **kgale user** | Linux user on office2 for human operations. Has sudo. SSH alias: `office2-kgale`. |
