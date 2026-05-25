---
id: gemini-instructions
title: Gemini Instructions
doc_type: handbook
level: reference
status: approved
owners:
  - "@kentonium3"
last_updated: '2026-05-25'
revision: v2.0
audience: agents_and_humans
---
# Gemini/Antigravity Instructions — kg-automation

These instructions provide Gemini-specific (including Antigravity CLI) guidance for working in the kg-automation repository.

## Core Responsibilities
- Code generation and review
- Documentation assistance
- System architecture and analysis
- AI handoff processing

## Workflow Rules
1. **Initial Context & Discovery:**
   - On every new session, scan the repository root to discover structural rules (such as `CLAUDE.md`).
   - Read this file (`ai-agents/gemini-instructions.md`) and understand safety constraints.
   - Review relevant directory contents before making changes.

2. **The "Issue-First" Habit (Mandatory):**
   - When the user asks for a bug fix, feature, investigation, or any change that touches deployed services, agent config, or multiple files — ask ***"Want me to create an issue for this first?"*** before starting work.
   - This applies during casual conversation, not just during planned workflow execution.
   - Exemptions: typo fixes, single-line doc edits, `CLAUDE.md` updates, and pure research questions.

3. **Spec-Kitty Workflow Execution:**
   - To advance execution lanes, check what to do next using:
     ```bash
     spec-kitty next --agent antigravity --mission <mission-slug>
     ```
   - Do not execute Claude-specific slash commands; instead, execute the underlying CLI commands directly via shell command tools.
   - **Spec Readiness Gate**: Ensure the GitHub issue has the `spec: ready` label before running `spec-kitty specify`.

4. **Change Control Guardrails & Risk Taxonomy:**
   - Check the tier of any proposed change against `docs/design/architecture/data/change-risk-taxonomy.json`:
     - **Tier 0 (Hard Lock - Foundational: sshd, UFW, sudoers, system files)**: Never execute directly. Generate the script and present it to Kent to run manually.
     - **Tier 1 (Fabric: DNS, Tailscale, Docker networks, port bindings)**: Confirm connectivity of all dependent services before and after changes.
     - **Tier 2 (Application/State: DB, compose, env files)**: Check that a Restic backup has run in the last 24 hours before modifying.
     - **Tier 3 (Logic: Python scripts, prompts, cron)**: Proceed with standard validation/sandbox testing.
     - **Tier 4 (Metadata: Readmes, comments, logging)**: Full autonomy.

5. **Second Brain Boundary:**
   - `~/second-brain/` is a separate repository. We may read files when explicitly required, but do not write to it unless a specific skill requires it.
   - **Absolute Rule**: `~/second-brain/notes/04-Growth/_private/` is never read, written, referenced, or logged under any circumstance.

6. **Architecture & Documentation Sync:**
   - Any implementation that deploys, modifies, or removes a service, credential, port, or data flow **must** update the corresponding JSON file under `docs/design/architecture/data/` (e.g., `service-inventory.json`) and its narrative markdown view in the same commit.

## Safety Guidelines
- No modifications to `.github/workflows/` without explicit instruction.
- Execute local validation/test suite before committing.
- Document all automated operations and use conventional commits (`feat:`, `fix:`, `docs:`, `chore:`).
