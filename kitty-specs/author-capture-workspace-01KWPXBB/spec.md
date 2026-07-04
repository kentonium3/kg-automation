# Feature Specification: Author felix-admin-capture Workspace

**Mission**: author-capture-workspace-01KWPXBB
**Type**: software-dev
**Status**: Draft
**Input**: GitHub issue #584 (child of epic #167), plus the pre-spec design locked with Kent on 2026-07-03 (Path 1 — pure refactor).

## Overview

felix-admin-capture is the OpenClaw agent that processes Kent's Obsidian inbox. Its
workspace context files — `SOUL.md`, `USER.md`, `TOOLS.md` — were not intentionally
authored: procedural material has leaked across files, the user context is not scoped
to what the capture role actually needs, and the tool surface is not documented against
what the agent really uses.

This mission re-authors those three files as one coherent, self-contained set against
the file-ownership standard defined in #587, then reconciles and deploys them to office2
with a smoke test. It is a **pure refactor**: the observable behavior of felix-admin-capture
does not change. Every piece of leaked material is relocated to its correct owner file, not
rewritten. All routing-intelligence enhancements (clarify-until-disposed, capability-gap
logging) are explicitly deferred to #651.

## Domain Language

| Term | Canonical meaning | Avoid |
|---|---|---|
| SOUL.md | The agent's **voice** layer — how it writes (tone, stance, word choices). Injected every session. Excludes role, policy, biography. | "personality file" (too broad) |
| USER.md | A **filtered person-view** of Kent scoped to what the capture role needs to interpret inbox items. Not a full profile dump. | "profile", "dossier" |
| TOOLS.md | The agent's **environment/tool surface** — paths, APIs, operating constraints, failure behavior unique to this setup. | "config" |
| AGENTS.md | The agent's **operating rules / role** — authority, workflow, routing logic, enforceable policy. Out of scope to re-author here; receives relocated material only. | — |
| File-ownership standard | The #587 contract that assigns each kind of content to exactly one file, plus the shared invariants every workspace must pass. | — |
| Pure refactor | Content is **relocated or reduced**, never behaviorally changed. Same effective instructions, correctly housed. | "rewrite", "redesign" |

## User Scenarios & Testing

### Primary scenario — operator authors and deploys the workspace

1. **Actor**: Kent (operator), authoring the capture workspace on the Mac.
2. **Trigger**: The three capture files are cross-contaminated and fail the #587
   file-ownership contract.
3. **Happy path**: The operator relocates each leaked block to its correct owner file,
   reduces the SOUL privacy block to a one-line behavioral stance, removes ADD references
   everywhere, and confirms the resulting three-file set is self-contained and passes the
   #587 shared-invariant validation. The files are then reconciled and deployed to office2
   through the manifest pipeline, and a post-deploy smoke test confirms capture still
   processes the inbox exactly as before.
4. **Success outcome**: SOUL/USER/TOOLS each own only their proper content; the deployed
   office2 copies match the repo; capture's behavior is unchanged.

### Exception path — smoke test detects a regression

- After deploy, the smoke test shows capture behaving differently (mis-routes, mis-clarifies,
  or errors). The change is rolled back by reverting the workspace files and re-deploying,
  and the discrepancy is investigated before any retry.

### Rules that must always hold

- **Behavior preservation**: no relocation may change what capture actually does. If a move
  would alter behavior, it is not part of this mission.
- **Single ownership**: after the refactor, no piece of content appears in two files with
  conflicting authority. Exactly one file owns each concern.
- **Privacy boundary integrity**: the enforceable `04-Growth/_private/` never-touch rule
  remains canonically present in its owner file(s); reducing SOUL to a stance must not remove
  the enforceable rule from the workspace as a whole.
- **Deployed == repo**: after rollout, the office2 workspace copies match the repository copies.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Re-author `SOUL.md` so it contains only voice/stance content: keep the "write as Kent" voice section (the keeper); remove the `## Purpose`/role block (already owned by AGENTS.md `## Authority`); reduce the full `## Privacy boundary` block to a single behavioral stance line ("I work only where I'm invited"). | Accepted |
| FR-002 | Remove all ADD references from the workspace files (the SOUL "structured and chunked / Kent has ADD" bullet, and the USER `Notes` "ADD (managed)" fragment), because they bias the agent's responses. | Accepted |
| FR-003 | Re-author `USER.md` as a filtered, capture-relevant person-view of Kent: keep only context needed to interpret inbox captures; retain a neutral line attributing terseness to the capture method ("captures tend to be terse/fragmentary — voice or quick-note"), not to Kent. | Accepted |
| FR-004 | Relocate the `## Date handling` block (timezone resolution, ET offset rule, no-Z-suffix rule) out of `USER.md` and into `TOOLS.md`, where operational/environment mechanics belong. | Accepted |
| FR-005 | Re-author `TOOLS.md` to document capture's actual tool surface (vault paths, Vikunja API, GitHub CLI/skill, privacy path) with operating constraints and failure behavior; add the relocated date-handling mechanics. | Accepted |
| FR-006 | Relocate the `### Available Labels` taxonomy out of `TOOLS.md` and into `AGENTS.md` beside the Step 3 `github_issue` route; leave in `TOOLS.md` only a pointer to the canonical repository label source (no inlined list). | Accepted |
| FR-007 | Keep the canonical enforceable privacy path (`04-Growth/_private/` never-touch) present in `TOOLS.md` and `AGENTS.md` as the mechanically-checked home, so reducing SOUL to a stance does not remove the enforceable rule from the workspace. | Accepted |
| FR-008 | The authored three-file set passes the #587 shared-invariant validation (including the presence of the privacy boundary and the Output Discipline expectation for a user-facing WhatsApp agent). | Accepted |
| FR-009 | Add a `deploys/queued/<name>.yaml` manifest entry that deploys the three authored files to the felix-admin-capture office2 workspace via felix-deployer. | Accepted |
| FR-010 | After rollout, verify the deployed office2 copies of `SOUL.md`, `USER.md`, and `TOOLS.md` match the repository copies. | Accepted |
| FR-011 | Run a post-deploy smoke test confirming felix-admin-capture still processes the inbox with no observable behavior change (correct classification, routing, and clarification behavior). | Accepted |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Behavior preservation | Zero observable behavior changes in the post-deploy smoke test versus pre-deploy behavior (same routing decisions on the same inputs). | Accepted |
| NFR-002 | Content de-duplication | Zero pieces of relocated content remain in their source file after the move; zero conflicting duplicates across files. | Accepted |
| NFR-003 | Repo/deploy parity | 100% byte-for-byte match between repository and deployed office2 copies of the three files after rollout. | Accepted |
| NFR-004 | Validation pass rate | 100% of #587 shared-invariant checks pass on the authored set. | Accepted |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Depends on #587 (the authoring standard + validation). #587 must land first or co-ship; this mission consumes that standard. The plan phase confirms ordering. | Accepted |
| C-002 | `AGENTS.md` is not re-authored here. The only permitted AGENTS.md edits are receiving relocated material (the Available Labels taxonomy beside Step 3) — capture's scope, workflow, and routing logic are unchanged. | Accepted |
| C-003 | Office2 deploy of agent prompt files flows through `deploys/queued/<name>.yaml` and felix-deployer, per deploy discipline. No direct edits on office2. | Accepted |
| C-004 | Risk tier 3 (agent-prompt change): per-agent review before deploy, controlled deploy, post-deploy smoke verification. Rollback = revert workspace files + re-deploy. | Accepted |
| C-005 | Rebaseline obligation (#557): agent prompts are an audited surface, but per the #621 gap `audit.sh` currently hashes only `openclaw.json`, not per-agent SOUL/USER/TOOLS files. The merge records the exact rebaseline outcome ("not required — agent prompt files are not currently hashed by the monitor (#621 gap)") after the plan confirms it. | Accepted |
| C-006 | All routing-intelligence behavior (clarify-until-disposed, capability-gap logging, removal of the 2-round calendar cap) is out of scope and deferred to #651. | Accepted |

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | Each of SOUL/USER/TOOLS owns only its proper concern; a reviewer can point to exactly one file for voice, one for filtered user context, and one for the tool surface, with no cross-contamination. |
| SC-002 | The authored set passes 100% of the #587 shared-invariant validation. |
| SC-003 | The deployed office2 workspace matches the repository copies after rollout. |
| SC-004 | The post-deploy smoke test shows felix-admin-capture processing the inbox with no observable behavior change. |
| SC-005 | A rollback path (revert + re-deploy) is documented and available. |

## Key Entities

- **felix-admin-capture workspace** — the set of context files at
  `scripts/openclaw/agents/felix-admin-capture/` (SOUL.md, USER.md, TOOLS.md are in scope;
  AGENTS.md and IDENTITY.md are context/receivers only).
- **#587 file-ownership standard** — the contract that assigns content to owner files and
  defines the shared invariants validated here.
- **Deploy manifest** — `deploys/queued/<name>.yaml`, consumed by felix-deployer on office2.

## Assumptions

- #587 lands first or co-ships and provides the file-ownership contract + validation this
  mission is authored against (confirmed in plan).
- felix-admin-capture emits user-facing WhatsApp (e.g. calendar clarification messages) and
  therefore carries the Output Discipline invariant, not the "no user-facing WhatsApp"
  annotation.
- The current live files on office2 match the repository copies at mission start (the deploy
  pipeline is the source of truth); the smoke-test baseline is capture's current behavior.

## Out of Scope

- Authoring the other agents' workspaces (#582, #585, #586, `main`).
- Defining the authoring standard itself (#587).
- Changing capture's AGENTS.md scope or routing logic beyond receiving relocated material.
- Any routing-intelligence capability (#651).
