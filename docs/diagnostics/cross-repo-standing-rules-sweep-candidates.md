---
title: Cross-Repo Standing Rules Sweep Candidates
doc_type: diagnostic
status: draft
owners: [kgale]
last_updated: '2026-07-06'
---

# Cross-Repo Standing Rules Sweep Candidates

## Summary

WP01 reviewed the primary standing-rules file, the current Spec-Kitty bug-reporting runbook, repo guidance, Felix constitution boundaries, runbooks, and agent rule surfaces using the focused candidate search from the work package prompt.

The only promoted candidate is a stale wording correction to the existing Spec-Kitty issue-reporting rule: the standing-rules file still describes generating a slim external upstream report from an internal issue, while the current runbook says new reports should embed the upstream draft directly in the internal `kentonium3/kg-automation` issue and should not create a separate paste file.

No new broad rule should be added for privacy boundaries or ClawHub community skills during WP02. Those are important, but the evidence shows they are Felix/OpenClaw-specific rather than universal across every repository.

## Promoted Candidates

| Candidate | Classification | Evidence | WP02 guidance |
| --- | --- | --- | --- |
| Align the cross-repo Spec-Kitty issue-reporting summary with the embedded-upstream-draft flow and remove separate paste-file wording. | promote | `.agents/rules/cross-repo-standing-rules.md:26-31` currently says to file an internal issue and "generate the slim EXTERNAL upstream report"; `docs/runbooks/spec-kitty-bug-reporting.md:47-75` says to embed the upstream draft directly in the internal issue and use "No separate paste file"; `docs/runbooks/spec-kitty-bug-reporting.md:106-119` explicitly deprecates transient paste files. | Update the existing "Spec-Kitty (and sibling tooling) issue reporting" bullet. Keep it short and link to the runbook rather than copying the lifecycle. |

## Link-Only Candidates

| Candidate | Classification | Evidence | Rationale |
| --- | --- | --- | --- |
| Keep the full Spec-Kitty bug-reporting lifecycle in the runbook, not the standing-rules file. | link-only | The standing-rules file says longer templates and protocols are linked, not inlined at `.agents/rules/cross-repo-standing-rules.md:3-6`; the runbook lifecycle spans `docs/runbooks/spec-kitty-bug-reporting.md:47-92`. | The lifecycle is procedural and too long for always-on cross-repo context. The global rule should point agents to the runbook and preserve only the short "do not file upstream ad hoc / use embedded draft + approval" reminder. |

## Already Represented Candidates

| Candidate | Classification | Evidence | Rationale |
| --- | --- | --- | --- |
| Public-post copy requires exact wording approval before posting externally. | already-represented | `.agents/rules/cross-repo-standing-rules.md:8-20` already requires exact-copy approval for outward posts and keeps external upstream drafts gated; `docs/runbooks/spec-kitty-bug-reporting.md:76-83` requires approval before filing upstream; `docs/runbooks/spec-kitty-bug-reporting.md:204-211` defines the operator-facing approval prompt. | No new rule needed. Preserve this section in WP02. |
| No `@mentions` in local/internal tracking records. | already-represented | `.agents/rules/cross-repo-standing-rules.md:22-24` already prohibits local `@mentions`. | No new rule needed. Preserve this section in WP02. |
| Use bounded reads and focused searches during codebase navigation. | already-represented | `AGENTS.md:11-17` requires narrow searches and bounded output; `CODEX.md:53-56` requires `rg`/bounded reads and `apply_patch` for edits. | This is already present in repo/Codex guidance and is not a gap in the cross-repo standing-rules file for #649. |

## Local Or Agent-Specific Candidates

| Candidate | Classification | Evidence | Rationale |
| --- | --- | --- | --- |
| Never read, write, reference, or log `~/second-brain/notes/04-Growth/_private/`. | repo-specific | `docs/constitution/FELIX-CONSTITUTION.md:158-167` defines the Felix hard privacy boundary; `CLAUDE.md:408-416` and `CODEX.md:64-74` repeat the same kg-automation/second-brain boundary; agent/runbook copies include `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md:288-296` and `docs/runbooks/inbox-ops.md:216-220`. | This rule is critical for Felix/kg-automation, but the path and substrate are specific to Kent's second-brain/Felix environment. Do not promote it into every repository's universal rules. |
| Community skills from ClawHub require Kent approval and source review before install. | repo-specific | `docs/constitution/FELIX-CONSTITUTION.md:169-171` requires approval and full file review; `docs/runbooks/openclaw-ops.md:277-286` narrows this to OpenClaw/ClawHub installs. | Important for Felix/OpenClaw, but not universal for repositories that do not use OpenClaw or ClawHub. Leave it in constitution/runbooks. |
| Verbatim pass-through when delegating Kent replies to OpenClaw sub-agents. | agent-specific | `scripts/openclaw/agents/main/AGENTS.md:45-59` defines the rule for OpenClaw sub-agent delegation and deterministic parsers. | This is an OpenClaw/Felix operational rule, not a cross-repo agent standing rule. |
| Auto-drive Spec-Kitty missions after Kent says to proceed. | repo-specific | `CLAUDE.md:180-214` defines kg-automation's workflow-driving behavior and stop conditions. | Useful for this repository's Spec-Kitty practice, but too specific for the universal standing-rules library. |

## Unclear Candidates For Operator Judgment

None. The borderline candidates found in this sweep are better classified as repo-specific or agent-specific based on their source surfaces and terminology.
