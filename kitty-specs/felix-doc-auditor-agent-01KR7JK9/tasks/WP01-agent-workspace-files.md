---
work_package_id: WP01
title: Agent workspace files
dependencies: []
requirement_refs:
- FR-005
- FR-009
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-doc-auditor-agent-01KR7JK9
base_commit: 5449fa23604b06f7d0019d1713decd7e174249f0
created_at: '2026-05-10T00:47:13.513838+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
shell_pid: "15377"
agent: "codex:gpt5:reviewer:reviewer"
history:
- at: '2026-05-09T23:54:00Z'
  actor: spec-kitty.tasks
  note: Initial scaffold from /spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-doc-auditor/
execution_mode: code_change
mission_id: 01KR7JK9QTHM5F4PD3YC43KDQW
mission_slug: felix-doc-auditor-agent-01KR7JK9
owned_files:
- scripts/openclaw/agents/felix-doc-auditor/**
tags: []
---

# WP01 — Agent workspace files

## Objective

Create the five OpenClaw agent workspace files for `felix-doc-auditor` per `docs/runbooks/openclaw-agent-setup.md`. The largest of these — `AGENTS.md` — encodes the agent's full standing orders for cron-driven doc-audit processing at Assisted (Level 1).

## Context

- Mission: `felix-doc-auditor-agent-01KR7JK9` (mission_id `01KR7JK9QTHM5F4PD3YC43KDQW`)
- Spec: [../spec.md](../spec.md) — read before starting
- Plan: [../plan.md](../plan.md) — Technical Context describes the agent runtime
- Research: [../research.md](../research.md) — R-002 (workspace files), R-007 (WhatsApp pattern), R-009 (concurrency label)
- Data model: [../data-model.md](../data-model.md) — entities the agent operates on
- Contracts: [../contracts/](../contracts/) — message templates, especially `whatsapp-summary.template.md`, `whatsapp-reply-vocabulary.md`, `audit-summary-comment.template.md`, `commit-message.template.md`
- Pattern reference: `scripts/openclaw/agents/felix-admin-habits/` is the closest existing agent (cron-driven, WhatsApp interactive, Assisted level)

## Branch Strategy

- Planning/base branch: `main`
- Final merge target: `main`
- Execution: a per-WP worktree is allocated by `lanes.json` after `finalize-tasks` runs. Branch from `main`. After implementation, the lane is reviewed and merged back to `main`.

## Subtasks

### T001 — Create IDENTITY.md

**Purpose**: Agent identity card. Read by OpenClaw to display agent identity in `openclaw agents` output. Short — typically ~30-50 lines.

**File**: `scripts/openclaw/agents/felix-doc-auditor/IDENTITY.md` (new)

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/IDENTITY.md` to internalize the format (name, emoji, creature, vibe).
2. Compose the identity card. Suggested fields:
   - **Name**: `felix-doc-auditor`
   - **Emoji**: pick something documentation-flavored (e.g., 🕵️ — investigator/auditor, or 📑 — document review)
   - **Creature**: a short metaphorical character (e.g., "a meticulous library archivist who knows where every misfiled card is")
   - **Vibe**: 1-2 sentences describing how the agent operates (precise, conservative, evidence-driven)
   - **Tagline**: a short one-liner

**Validation**:
- [ ] File exists at the correct path
- [ ] Format mirrors `felix-admin-habits/IDENTITY.md` field-for-field
- [ ] Content is succinct (under ~50 lines)
- [ ] No mention of implementation specifics (this is identity, not behavior)

---

### T002 — Create SOUL.md

**Purpose**: Agent voice, values, and privacy boundaries. Defines how the agent writes communications to Kent (WhatsApp summaries, audit comments) and explicitly enumerates what the agent will not touch. ~80-150 lines.

**File**: `scripts/openclaw/agents/felix-doc-auditor/SOUL.md` (new)

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/SOUL.md` for the format model.
2. Compose SOUL.md with these sections:
   - **Purpose**: One paragraph on why this agent exists (kg-automation's doc accuracy is foundational to safe agent autonomy expansion).
   - **Voice**: Direct, evidence-cited, never editorializes about the docs (just reports what's drifted). Plain text in WhatsApp, structured Markdown in GitHub comments.
   - **Values**: Conservative confidence calls (better to file a debt issue than make a wrong edit). Preserves human attention (no edit proposals for trivial items at Assisted level get reviewed by Kent — only commits do; debt issues happen autonomously).
   - **Privacy boundaries**: Explicit — never reads/references `~/second-brain/notes/04-Growth/_private/`. Never edits Felix Constitution (`docs/constitution/FELIX-CONSTITUTION.md`). Never edits CLAUDE.md (any). Never edits credentials (`.env`, `credentials.json`).
   - **Deference**: When confidence is ambiguous, the agent defers to filing a debt issue. When the audit issue's `area/*` labels indicate a domain not in the domain map, the agent surfaces this as a docs-debt issue (the map needs updating) rather than guessing.

**Validation**:
- [ ] All five sections present
- [ ] Privacy boundaries enumerate the exact paths from spec § Constitutional Compliance / C-002, C-003
- [ ] Voice section gives concrete tone guidance, not generic platitudes

---

### T003 — Create TOOLS.md

**Purpose**: Tool boundary contract. Enumerates what tools the agent uses, what paths/resources it accesses, and what it does NOT use. ~80-120 lines.

**File**: `scripts/openclaw/agents/felix-doc-auditor/TOOLS.md` (new)

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/TOOLS.md` for the format.
2. Compose TOOLS.md with these sections:
   - **Allowed tools**:
     - `gh` CLI (for all GitHub interactions — issues, comments, labels)
     - Standard file I/O (read all docs in scope; write to docs that pass high-confidence threshold)
     - `git` (commit and push edits)
     - OpenClaw send-message (for WhatsApp summaries at Level 1)
   - **Resource references**:
     - Skill: `~/.openclaw/skills/doc-audit/SKILL.md` (loaded at the start of every audit)
     - Domain map: `docs/design/architecture/data/doc-domain-map.json` (read on every audit)
     - System state sources (read-only): `docs/design/architecture/data/service-inventory.json`, `docs/constitution/agent-registry.json`, `docs/design/architecture/data/hardware-inventory.json`, `docs/design/architecture/data/network-topology.json`, `docs/design/architecture/data/credential-manifest.json`, `docs/design/architecture/data/data-flows.json`, `docs/INDEX.md`
     - Issue templates: `.github/ISSUE_TEMPLATE/docs-debt.md`
     - Activity log destination: `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md`
   - **Disallowed tools / paths**:
     - MCP GitHub (use gh CLI per repo convention)
     - Anything under `~/second-brain/notes/04-Growth/_private/`
     - Direct edits to `docs/constitution/FELIX-CONSTITUTION.md`, `CLAUDE.md` (any), `.env`, `credentials.json`
     - Anything under `kitty-specs/` or `.kittify/` (managed by spec-kitty)
   - **GitHub label**: `status:in-progress` — applied when claiming an audit issue, removed when done (R-009 contract)

**Validation**:
- [ ] All four sections present
- [ ] Disallowed list matches the C-002 + C-003 + C-005 constraints from spec
- [ ] Skill path uses `~/.openclaw/skills/doc-audit/SKILL.md` (the deployed location, not the repo path)

---

### T004 — Create USER.md

**Purpose**: Information about Kent for tone calibration in WhatsApp messages. ~30-60 lines. Mostly a small file.

**File**: `scripts/openclaw/agents/felix-doc-auditor/USER.md` (new)

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/USER.md` for the model.
2. Compose USER.md:
   - **Name**: Kent Gale
   - **Timezone**: Eastern (use `TZ=America/New_York` for any date computation; office2 runs UTC)
   - **Communication preferences**: Concise. Plain text in WhatsApp (no emojis, no markdown). Direct asks, not multi-paragraph explanations. Reply parsing matters — Kent uses `approve` / `reject` / `skip` per the vocabulary in `~/.openclaw/skills/doc-audit/SKILL.md` (or this agent's contracts).
   - **Approval expectations**: At Assisted (Level 1), Kent expects to see WhatsApp summary before any commit; 2-hour timeout = default deny. After promotion to Supervised (Level 2), Kent expects no WhatsApp interactions for routine audits — only the GitHub audit summary comments.

**Validation**:
- [ ] Timezone notation explicit
- [ ] WhatsApp tone preferences match what the agent's outbound messages will use

---

### T005 — Create AGENTS.md (standing orders)

**Purpose**: The agent's complete operational instructions. The longest and most important file. Read by the OpenClaw runtime when invoking the agent. ~250-350 lines.

**File**: `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` (new)

**Steps** (write the document section-by-section):

1. **Governance preamble** (top of file, ~10 lines):
   - Reference Felix Constitution and AGENT-REGISTRY (use the same pattern as `felix-admin-habits/AGENTS.md` opening).
   - State current autonomy level: Assisted (Level 1).

2. **Message identity** (~5 lines):
   - Every WhatsApp outbound message starts with: `Sent by felix-doc-auditor:sonnet` followed by a blank line. Mirrors the `felix-admin-habits` convention.

3. **Authority and Scope** (~15 lines):
   - Authority: "You are authorized to process Doc Audit and Weekly Doc Audit issues against the doc-domain-map.json scope."
   - Scope (in): processing audit issues, making high-confidence doc edits, creating docs-debt issues, posting audit summary comments, closing audit issues.
   - Scope (out): editing Felix Constitution, CLAUDE.md, credential files, kitty-specs, second-brain. Filing debt issues outside the domain map. Promoting your own autonomy level.

4. **Trigger and queue management** (~20 lines):
   - Triggered by OpenClaw cron every 60 minutes.
   - On each tick:
     - Query open audit issues lacking the `status:in-progress` label: `gh issue list --label "P2-debt" --state open --search 'Doc audit OR Weekly doc audit' --json number,title,labels`
     - Filter out any with `status:in-progress` already applied
     - Pick the oldest (lowest number) unprocessed
     - If none, exit cleanly (no work this tick)

5. **Lock acquisition** (~10 lines):
   - Apply label: `gh issue edit <#> --add-label "status:in-progress" --repo kentonium3/kg-automation`
   - This claims the issue and prevents other cron ticks from picking it up.
   - On any error path or completion, the label MUST be removed (use a try/finally pattern in your processing logic).

6. **Skill loading** (~5 lines):
   - First action of every audit: load the doc-audit skill: `cat ~/.openclaw/skills/doc-audit/SKILL.md`
   - The skill encodes the audit logic, confidence thresholds, comparison rules, commit format, and error handling.

7. **Audit workflow** (~30 lines):
   - Read the audit issue body (`gh issue view <#> --json body,labels`)
   - Determine in-scope docs: parse `area/*` labels → domain map lookup → list of doc paths. If no `area/*` labels, full-scope.
   - For each in-scope doc:
     - Read the doc
     - Compare against system state sources (per `TOOLS.md`)
     - Build an Edit Proposal (entity E-004 in data-model.md)
     - Classify: high-confidence edit, judgment-required gap, or no change needed
   - Detect missing artifacts (per FR-004 / E-006 in data-model.md): compare deployed agents/services against documented runbooks/inventory entries. Surface gaps as docs-debt issues.

8. **Level 1 approval** (~30 lines):
   - If there are any high-confidence edit proposals, send a WhatsApp summary using the template in `contracts/whatsapp-summary.template.md`.
   - Wait for reply for up to 2 hours (NFR-004).
   - Parse reply per `contracts/whatsapp-reply-vocabulary.md`:
     - `approve` / `yes` / `ok` / `go` / `lgtm` → commit all proposed edits
     - `approve N[,M,...]` → commit only listed; demote rest to debt issues
     - `reject` / `no` / `stop` / `cancel` → demote all to debt issues
     - `skip` → close audit with skip note; no edits, no new debt issues
     - (no reply within 2h) → default-deny; demote all to debt issues
     - Anything else → ask once for clarification; on second ambiguous reply, default-deny
   - Record the WhatsApp message + reply (or timeout) in the audit summary's "Approval log" section

9. **Commit and issue creation** (~30 lines):
   - For approved high-confidence edits:
     - Make the file changes locally
     - `git add` the changed files; `git commit` with the message format in `contracts/commit-message.template.md`
     - `git push origin main`
   - For each judgment-required gap and missing artifact:
     - Create a docs-debt issue using `.github/ISSUE_TEMPLATE/docs-debt.md`
     - Populate all six sections (Artifact, Gap description, Area, Cross-references, Draft outline, Success criteria)
     - The Draft outline MUST be specific enough to act on without further research (FR-003 success criterion)
     - Apply labels: `P2-debt` plus the matching `area/*` label(s) plus `type/debt` (if it exists)
   - Special case for `area/biz-ops` gaps (per C-006): include a flag in the debt issue body asking for human confirmation before action; prefix title with "Docs (biz-ops): ".

10. **Audit summary and closure** (~20 lines):
    - Post the audit summary comment on the originating audit issue using the template in `contracts/audit-summary-comment.template.md`
    - Close the audit issue: `gh issue close <#> --repo kentonium3/kg-automation`
    - At Level 1: the close requires user confirmation per the spec — interpret `approve` reply earlier as authorization for both the commit AND the close

11. **Lock release** (~5 lines):
    - Remove the `status:in-progress` label: `gh issue edit <#> --remove-label "status:in-progress" --repo kentonium3/kg-automation`
    - This MUST happen even on failure paths (use a try/finally pattern).

12. **Activity logging** (~15 lines):
    - Append to `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md`:
      ```
      ## Audit run — <ISO timestamp>
      - Audit issue: #<N>
      - Docs reviewed: <count>
      - Edits committed: <count> (commit: <sha>)
      - Debt issues created: <count> (#<N>, #<M>, ...)
      - Missing artifacts: <count>
      - Failures: <count> (<details>)
      - Reply: <approve|reject|skip|timeout>
      ```
    - Use `TZ=America/New_York date +%FT%T%z` for the timestamp.

13. **Error handling** (~25 lines):
    - **Doc unreadable / locked**: log to summary's "Items requiring human review" section; skip that doc; continue with the rest of the scope. Never abort the whole audit because one doc failed.
    - **Git push fails (rebase needed)**: pull latest main with rebase; re-apply edits; if conflicts arise, abort the commits for that audit; demote all proposals to debt issues; record in summary.
    - **GitHub API rate limit**: exponential backoff; if still hitting, leave the audit at `status:in-progress` and exit cleanly. Next cron tick will retry.
    - **WhatsApp delivery fails**: at Level 1, do NOT proceed without approval. Leave the audit at `status:in-progress` (Kent must manually unlock and Inspector). Log a clear error in the activity log.
    - **Domain map missing**: critical error. Exit with a loud failure (post a comment on the audit issue saying so). Do not delete or mutate anything.

14. **Promotion behavior** (~10 lines):
    - At Level 2 (after governance promotion), skip steps 8 (no WhatsApp) and the Level-1-specific lines in step 10. The agent commits and closes autonomously.
    - The agent never self-promotes; promotion is a governance decision that updates the registry; the agent reads the registry to determine its current level.
    - Read `docs/constitution/agent-registry.json` once per audit run to get the current autonomy level. Cache for the duration of one audit only.

**Validation**:
- [ ] All 14 sections present and substantive
- [ ] Step numbering matches the data-model lifecycle diagram
- [ ] WhatsApp templates match the contracts files exactly
- [ ] Privacy boundaries (C-002, C-003) restated in the Authority/Scope and Error handling sections
- [ ] Level 1 vs Level 2 difference is explicit in step 8 and step 14

## Definition of Done (WP01)

- [ ] All 5 files exist at `scripts/openclaw/agents/felix-doc-auditor/<name>.md`
- [ ] Each file passes its per-subtask validation checklist
- [ ] AGENTS.md is internally consistent (cross-references to TOOLS.md and SOUL.md resolve)
- [ ] Files are added/committed but NOT deployed (deployment is WP05)

## Risks

- **AGENTS.md is verbose** — keep iterating until language is unambiguous to the agent. Read it back as a fresh agent would; if any step is unclear, refine.
- **Cross-file drift** — the four small files (IDENTITY/SOUL/TOOLS/USER) and the big AGENTS.md must stay consistent. After writing all five, do a final pass to ensure no contradictions.
- **Gap between contracts and AGENTS.md** — AGENTS.md describes processes; contracts describe message formats. They must align. After AGENTS.md draft, re-read each contract file and verify references are accurate.

## Reviewer guidance

A reviewer should check:
1. The 5 files compose a complete agent workspace per `docs/runbooks/openclaw-agent-setup.md`
2. AGENTS.md walks step-by-step through the audit lifecycle in data-model.md
3. Constitutional guardrails (no Constitution edits, no CLAUDE.md edits, no second-brain) are enumerated in BOTH SOUL.md (boundaries) and TOOLS.md (disallowed) and AGENTS.md (Authority/Scope)
4. The WhatsApp interaction matches the templates in `contracts/`
5. Error handling section in AGENTS.md is exhaustive (5+ failure modes covered)
6. Step 11 (lock release) is unambiguous about always running

## Implementation command

```bash
spec-kitty agent action implement WP01 --agent <agent-name>
```

## Activity Log

- 2026-05-10T00:47:15Z – claude:sonnet:implementer:implementer – shell_pid=13632 – Assigned agent via action command
- 2026-05-10T00:55:15Z – claude:sonnet:implementer:implementer – shell_pid=13632 – Ready for review: 5 workspace files created per docs/runbooks/openclaw-agent-setup.md, patterned on felix-admin-habits
- 2026-05-10T00:56:00Z – codex:gpt5:reviewer:reviewer – shell_pid=15377 – Started review via action command
