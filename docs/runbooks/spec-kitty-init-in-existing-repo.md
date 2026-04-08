
---
title: Spec-Kitty Installation Guide for Existing Repositories
doc_type: runbook
audience: humans
status: deprecated
---

> **HISTORICAL**: spec-kitty is already installed and configured in this
> repository. This guide documents the steps that were followed during
> initial setup. It is retained for reference in case of reinstallation
> or migration. The current spec-kitty workflow is documented in CLAUDE.md.
>
> Note: Step 5 "Create Project Constitution" uses the old spec-kitty 1.x
> terminology. In spec-kitty 3.x, this is now called a "charter" and is
> managed via `spec-kitty charter interview`. The Felix Constitution at
> `docs/constitution/FELIX-CONSTITUTION.md` is a separate document from
> the spec-kitty charter at `.kittify/charter/charter.md`.

# Spec-Kitty Installation Guide for Existing Repositories

**Purpose:** Initialize Spec-Kitty in an existing git repository to enable spec-driven development with real-time kanban tracking.

**Prerequisites:**
- Spec-Kitty CLI is already installed globally (`uv tool list` should show `spec-kitty-cli`)
- You are in the root directory of the target repository
- Repository has a `.git` directory
- You have Claude Code or another supported AI agent available

**Note:** If Spec-Kitty CLI is not installed, run: `uv tool install spec-kitty-cli --from git+https://github.com/Priivacy-ai/spec-kitty.git`

---

## Step 1: Backup and Pre-Installation Check

**Objective:** Create a safety checkpoint before making any changes.

**Instructions:**
1. Create a backup branch 'pre-spec-kitty-backup' and push it to origin
2. Check if any Spec-Kitty directories already exist (`.kittify`, `kitty-specs`, `.worktrees`, `CLAUDE.md`)
3. If any exist, list them so we can decide how to handle conflicts
4. Show current `.gitignore` contents so we can plan for merge conflicts

**Context:** This is a safety checkpoint. We need to ensure we can rollback if anything goes wrong during installation.

---

## Step 2: Initialize Spec-Kitty

**Objective:** Initialize Spec-Kitty in the current repository.

**Instructions:**
1. Verify the CLI is installed: `spec-kitty check`
2. Initialize Spec-Kitty in the current repo with Claude Code support:
```bash
   spec-kitty init . --force --ai claude
```
3. After installation completes:
   - Show the directory structure of `.kittify/` and its subdirectories
   - List any new files created in the root directory
   - Show what was added to `.gitignore` (if anything)
   - Confirm the dashboard started (check for any port conflict messages)

**Context:** 
- The `--force` flag allows installation in our existing non-empty directory
- The `--ai claude` flag sets up slash commands for Claude Code
- Do not start the dashboard manually - it auto-starts during init

---

## Step 3: Review and Merge .gitignore Changes

**Objective:** Properly integrate Spec-Kitty's gitignore patterns with existing ones.

**Instructions:**
1. Check if Spec-Kitty created a new `.gitignore` or modified the existing one
2. If there's a new `.gitignore` from Spec-Kitty:
   - Show the Spec-Kitty entries (especially `.worktrees/` related patterns)
   - Merge them into our existing `.gitignore` intelligently
   - Ensure `.worktrees/` is ignored but `kitty-specs/` and `.kittify/` are tracked
3. Expected ignore patterns to add:
   - `.worktrees/`
   - `*.pyc`, `__pycache__/` (if not already present)
   - Any temp files from Spec-Kitty scripts
4. After merging, show the final `.gitignore`
5. Stage and commit the Spec-Kitty installation:
```bash
   git add .kittify/ kitty-specs/ .gitignore CLAUDE.md
   git commit -m "feat: Install Spec-Kitty for spec-driven development

   - Add .kittify/ with templates, scripts, and memory structure
   - Add kitty-specs/ for feature specifications
   - Configure worktree-based development workflow
   - Set up Claude Code slash commands"
```

**Important:** Do not commit `.worktrees/` - it should be gitignored.

---

## Step 4: Verify Installation and Available Commands

**Objective:** Confirm Spec-Kitty installation is complete and all commands are available.

**Instructions:**
1. List all available `/spec-kitty.*` slash commands by checking:
   - `.github/copilot-instructions.md` (if it exists)
   - `CLAUDE.md` (should show custom instructions)
   - `.kittify/commands/` directory (if it exists)
2. Confirm these essential commands are available:
   - `/spec-kitty.dashboard`
   - `/spec-kitty.constitution`
   - `/spec-kitty.specify`
   - `/spec-kitty.plan`
   - `/spec-kitty.tasks`
   - `/spec-kitty.implement`
   - `/spec-kitty.review`
   - `/spec-kitty.accept`
   - `/spec-kitty.merge`
3. Check the dashboard status:
   - Is it running? (look for process or port binding messages)
   - If not running, show how to start it manually
4. Show the contents of `.kittify/templates/` to understand what templates are available
5. List any README or documentation files that Spec-Kitty may have created

**Context:** This confirms we're ready to create our first constitution and specification.

---

## Step 5: Create Project Constitution

**Objective:** Establish foundational principles that guide all future specifications, plans, and implementations.

**Instructions:**
Run the `/spec-kitty.constitution` command with guidance appropriate for this project.

**Standard Constitution Template:**
Create a constitution focused on:

1. **Code Quality Standards:**
   - Type safety and static analysis
   - Code review requirements before merging
   - Linting and formatting standards
   - Documentation requirements for public APIs

2. **Testing Standards:**
   - Minimum test coverage requirements (e.g., 80% for new features)
   - Unit tests required for business logic
   - Integration tests for critical paths
   - Test-driven development encouraged where appropriate

3. **Performance Requirements:**
   - Response time budgets for critical operations
   - Resource usage constraints
   - Optimization guidelines

4. **Security Principles:**
   - Input validation requirements
   - Authentication/authorization patterns
   - Secure coding practices
   - Data protection standards

5. **User Experience:**
   - Accessibility standards (if applicable)
   - Error handling and user feedback
   - UI/UX consistency guidelines

6. **Development Workflow:**
   - Feature branches via Spec-Kitty worktrees
   - Specifications required before implementation
   - Code must match approved plan
   - Review checklist completion mandatory

**After completion:**
- Show the contents of `.kittify/memory/constitution.md`
- Commit the constitution to the repository

**Context:** The constitution serves as the "source of truth" for development standards. All future specs and plans will reference these principles.

---

## Step 6: Test Installation with Simple Feature

**Objective:** Validate the Spec-Kitty workflow end-to-end with a minimal test feature.

**Instructions:**
Use `/spec-kitty.specify` to create a specification for a simple test feature appropriate to this project. 

**Example Test Features by Project Type:**
- **API/Backend:** Health check endpoint that returns service status
- **CLI Tool:** Version command that displays version info
- **Library:** Simple utility function with clear inputs/outputs
- **Desktop App:** About dialog showing app information

Let the `/spec-kitty.specify` command run its discovery interview. Answer questions based on:
- This is a new feature, not modifying existing code
- Keep it simple and non-invasive
- Success criteria should be clear and testable

**After specify completes:**
1. Show what branch/worktree was created
2. Show the location of the generated `spec.md`
3. Display a summary of the specification (first 50 lines)
4. Confirm we're now in the feature worktree (show current working directory)

**Important:** Do NOT proceed to `/spec-kitty.plan` yet - we'll do that in the next step.

---

## Step 7: Complete Test Feature Planning

**Objective:** Create a technical plan for the test feature using existing project patterns.

**Instructions:**
1. Verify we're in the feature worktree (should be something like `.worktrees/001-<feature-name>/`)
2. Run `/spec-kitty.plan` with guidance about the existing technology stack

**Planning Guidance Template:**
```
Use our existing technology stack:
- [List actual languages, frameworks, libraries in use]
- Match existing project structure and patterns
- Follow existing conventions and code organization
- Keep dependencies minimal - use built-in libraries where possible
- No new external dependencies unless absolutely necessary

Implementation should:
- Follow existing architectural patterns
- Use established coding conventions
- Integrate with existing modules/components
- Require minimal changes to existing code
```

Let `/spec-kitty.plan` run its planning interview and answer questions about:
- Technical constraints from existing codebase
- Architecture patterns currently used
- Any operational or deployment requirements

**After planning completes:**
1. Show the generated `plan.md` location and first 50 lines
2. Show what files are now in `kitty-specs/001-<feature-name>/` (or similar)
3. List current working directory to confirm we're still in the worktree

**Decision Point:** STOP here. Review the spec and plan. Decide whether to:
- Continue with implementation to fully test the workflow
- Clean up the test feature and begin real development
- Make adjustments to templates or configuration

---

## Step 8: Review Installation and Document Results

**Objective:** Verify successful installation and create reference documentation.

**Instructions:**
1. Summarize what was created during installation:
   - Directory structure (`.kittify/`, `kitty-specs/`)
   - Constitution file and its key principles
   - Test feature specification and plan
   - Git worktree structure

2. Check git status in both locations:
   - Main repo (cd back to root): `git status`
   - Feature worktree (if still active): `git status`

3. Show the current state of:
   - Branches: `git branch -a`
   - Worktrees: `git worktree list`
   - Dashboard accessibility (is it still running? what port?)

4. Provide recommendations:
   - Should we complete the test feature implementation or clean it up?
   - Are there any Spec-Kitty configuration adjustments needed?
   - Any issues or concerns from the installation?

5. Create or update documentation at `docs/spec-kitty-workflow.md` (or appropriate location) that includes:
   - Installation date and configuration
   - Available commands quick reference
   - Workflow overview (specify → plan → tasks → implement → review → merge)
   - Link to constitution
   - Dashboard URL and access instructions
   - Troubleshooting notes (if any issues were encountered)

**Context:** This completes the Spec-Kitty installation. Next steps:
- **Option A:** Continue implementing the test feature to completion
- **Option B:** Clean up the test feature and start with real work
- **Option C:** Make configuration adjustments before proceeding

---

## Post-Installation: Cleaning Up Test Feature (Optional)

If you created a test feature but want to remove it before real development:
```bash
# From the main repo directory
git worktree list  # Note the test feature worktree path
git worktree remove .worktrees/001-<feature-name>
git branch -D 001-<feature-name>
rm -rf kitty-specs/001-<feature-name>/
git add kitty-specs/
git commit -m "chore: Remove Spec-Kitty test feature"
```

---

## Spec-Kitty Workflow Reference

**Standard Feature Development Flow:**

1. **Specify** - Define what to build
```
   /spec-kitty.specify
```
   Creates: `kitty-specs/<feature>/spec.md` and feature worktree

2. **Plan** - Define how to build it
```
   cd .worktrees/<feature>/
   /spec-kitty.plan
```
   Creates: `kitty-specs/<feature>/plan.md`

3. **Tasks** - Break down into work packages
```
   /spec-kitty.tasks
```
   Creates: `kitty-specs/<feature>/tasks.md` and prompt files

4. **Implement** - Build the feature
```
   /spec-kitty.implement
```
   Executes work packages sequentially

5. **Review** - Validate implementation
```
   /spec-kitty.review
```
   Processes completed work packages

6. **Accept** - Final acceptance checks
```
   /spec-kitty.accept
```
   Verifies feature is merge-ready

7. **Merge** - Integrate into main
```
   /spec-kitty.merge --push
```
   Merges feature and cleans up worktree

---

## Troubleshooting

**Dashboard won't start:**
```bash
spec-kitty dashboard --port 3001  # Try different port
spec-kitty dashboard --kill       # Stop existing instance
```

**Worktree conflicts:**
```bash
git worktree list                 # Show all worktrees
git worktree remove <path>        # Remove problematic worktree
```

**Reset to backup:**
```bash
git checkout pre-spec-kitty-backup
git branch -D <spec-kitty-branches>
```

**Update Spec-Kitty CLI:**
```bash
uv tool upgrade spec-kitty-cli
```

---

## Important Notes

- **Constitution First:** Always create the constitution before starting feature work
- **Worktree Workflow:** Features are developed in isolated `.worktrees/<feature>/` directories
- **Dashboard:** Access the real-time kanban at the URL shown during init (typically `http://localhost:3000`)
- **Templates:** Customize templates in `.kittify/templates/` to match project needs
- **Scripts:** Helper scripts are in `.kittify/scripts/` - review these to understand automation
- **Git Hooks:** Optional pre-commit hooks available in `.kittify/scripts/git-hooks/`

---

## Success Criteria

Installation is successful when:
- ✅ All `/spec-kitty.*` commands are available in Claude Code
- ✅ Constitution is created and committed
- ✅ Dashboard is accessible
- ✅ Test feature spec and plan were generated successfully
- ✅ No git conflicts or errors
- ✅ Documentation is updated