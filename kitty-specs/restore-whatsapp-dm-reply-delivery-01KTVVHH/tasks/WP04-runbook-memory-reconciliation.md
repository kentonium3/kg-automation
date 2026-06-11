---
work_package_id: WP04
title: Runbook + Memory Reconciliation
dependencies: []
requirement_refs:
- FR-011
- FR-012
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T018
- T019
- T020
- T021
agent: claude
history:
- event: created
  timestamp: '2026-06-11T18:30:00Z'
  by: /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/runbooks/openclaw-agent-setup.md
execution_mode: planning_artifact
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
owned_files:
- docs/runbooks/openclaw-agent-setup.md
- docs/INDEX.md
role: curator
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned profile:

```
/ad-hoc-profile-load curator-carla
```

This sets your identity, governance scope, and boundaries for this work package. Adopt the profile fully before proceeding.

---

## Objective

Land **DR-6 through DR-9** per `data-model.md` E4. Two surfaces:

- **In-repo runbook + INDEX** (DR-6, DR-7) — adds a "DM-reply lifecycle troubleshooting" section to the openclaw-agent-setup runbook; conditionally updates INDEX.md
- **Out-of-repo memory** (DR-8, DR-9) — corrects the stale `project_whatsapp_dmpolicy` memory; adds a new `reference_openclaw_dm_reply_lifecycle` memory capturing the lifecycle markers + bug signature + smoke command

The runbook addition lets future operators diagnose this class of bug without re-discovering all of WP01's findings. The memory updates ensure I (or any future Claude session) start with correct facts when this surface comes up again.

You succeed when:
- `docs/runbooks/openclaw-agent-setup.md` has a new "DM-reply lifecycle troubleshooting" section linking the lifecycle and journal contracts
- `docs/INDEX.md` reflects any new top-level section (or is unchanged if DR-6 was a sub-section addition)
- `project_whatsapp_dmpolicy.md` memory says `allowlist` (not `disabled`)
- `reference_openclaw_dm_reply_lifecycle.md` memory exists with the canonical content (see T021)
- `MEMORY.md` index file has been updated to reflect the new + corrected entries

## Context

Read these BEFORE starting:

1. [`research.md`](../research.md) §1.2 (the dm_policy drift) + §3.4 (the lifecycle source-dive) — your factual inputs for DR-8 and DR-9
2. [`contracts/embedded-run-lifecycle.md`](../contracts/embedded-run-lifecycle.md) — DR-6 should cite this
3. [`contracts/journal-event-assertions.md`](../contracts/journal-event-assertions.md) — the awk one-liner for DR-6 + DR-9
4. `docs/runbooks/openclaw-agent-setup.md` (existing) — to find the right insertion point for DR-6
5. `docs/INDEX.md` (existing) — to see if a new index entry is warranted for DR-7
6. `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/MEMORY.md` — current index of memory entries
7. `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/project_whatsapp_dmpolicy.md` — the file you'll correct in DR-8

**Memory editing protocol** (from CLAUDE.md auto-memory section):
- Memory files use a 2-step process: write the file, then update `MEMORY.md` (the index)
- Memory file frontmatter has fields: `name`, `description`, `metadata.type` (one of `user|feedback|project|reference`)
- `MEMORY.md` lines are one per memory: `- [Title](file.md) — one-line hook`
- Link related memories with `[[name]]` (double-bracket Wikilink style)

## Detailed guidance per subtask

### T018 — DR-6: add "DM-reply lifecycle troubleshooting" section to openclaw-agent-setup.md

**File**: `docs/runbooks/openclaw-agent-setup.md`

**Insertion point**: find an existing major section about troubleshooting or operations (e.g., "## Troubleshooting" or "## Verification"). If none exists, add the new section near the end before the "References" or "Cross-references" section.

**Section content** (skeleton — flesh out with full prose):

```markdown
## DM-reply lifecycle troubleshooting

When inbound WhatsApp DMs are received but no reply is delivered, the break is usually in the gateway's `embedded_run` lifecycle. Cron `announce`-mode outbound (morning checkin, IDLE pings, periodic digests) is a separate code path and will keep working even when DM-reply is broken.

### Symptom signature

In `journalctl --user -u openclaw-gateway`, look for:

- `[whatsapp] Inbound message` fires for the DM ✓
- `Sent by <agent>:<model>` appears in the journal (agent's stdout marker per #561) ✓
- `[whatsapp] Sending message` is **MISSING** — channel-send never invoked ✗
- After ~378 seconds: `[diagnostic] stuck session recovery: action=abort_embedded_run` ✗
- Adjacent (downstream symptom): `[ws] ⇄ res ✗ sessions.resolve … errorCode=INVALID_REQUEST errorMessage=No session found: current`

The agent IS executing (its stdout reaches the journal) but the gateway's `embedded_run` completion event (`embedded_run:ended`) is never observed.

### Lifecycle contract reference

The full `embedded_run` lifecycle contract lives at `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/contracts/embedded-run-lifecycle.md` (carries through to its eventual canonical home in `docs/design/architecture/` post-mission). Two state markers (in vendored `openclaw/dist/diagnostic-run-activity-*.js`):

- `embedded_run:started` — fires via `markDiagnosticEmbeddedRunStarted` when `setActiveEmbeddedRun` is called
- `embedded_run:ended` — fires via `markDiagnosticEmbeddedRunEnded` when `clearActiveEmbeddedRun` is called

Healthy runs see both. Broken runs see only `started`.

### Operator smoke command

To verify DM-reply health, send a few DMs from the operator phone, then run:

```bash
TS=<ISO timestamp of smoke start>
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$TS' 2>/dev/null | awk '/\\[whatsapp\\] Inbound message/{i++} /\\[whatsapp\\] Sending message ->/{s++} /\\[whatsapp\\] Sent message /{sent++} /\\[diagnostic\\] stalled session/{stall++} /\\[diagnostic\\] stuck session recovery/{rec++} /sessions\\.resolve.*INVALID_REQUEST.*current/{rf++} END{print \"inbound=\"i\" send=\"s\" sent=\"sent\" stall=\"stall\" recovery=\"rec\" resolve_fail=\"rf}'"
```

Healthy output: `inbound=N send=N sent=N stall=0 recovery=0 resolve_fail=0`.
Broken output: `inbound=N send=0 sent=0 stall=≥1 recovery=≥1 resolve_fail=≥1`.

### Investigation order if broken

Per `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md` §4 + §5 D1, in cost order:

1. **H5** — `openclaw plugins list` — verify `@openclaw/whatsapp` install state
2. **H4** — read `/home/claude/.openclaw/openclaw.json` `channels.whatsapp` + `session` blocks for config drift
3. **H2** — read `/usr/lib/node_modules/openclaw/docs/{channels,gateway}/*.md` for any required field absent from our config
4. **H3** — try a `main/AGENTS.md` rollback to pre-#579 (fast-rollback probe; always restore current state before continuing)

If all in-scope hypotheses fail: the bug is in vendored `openclaw/dist/`; file an internal tracking issue per FR-009 (the spec scope decision Kent made on the 2026-06-11 incident — see issue #588). Do NOT patch vendored code.

### Cross-references

- See memory `reference_openclaw_dm_reply_lifecycle` for the canonical bug signature + smoke command
- See `contracts/journal-event-assertions.md` for the full POSIX-ERE pattern reference
- See `data-flows.json#flows[?name=whatsapp-dm-reply]` for the architectural data flow
```

**Style**: follow the existing runbook voice. Use second-person ("you") for operator instructions. Cite specific files + commands, not vague "check the logs" guidance.

### T019 — DR-7: update INDEX.md (conditional)

**File**: `docs/INDEX.md`

**Decision**:
- If DR-6 added a NEW top-level section (`## DM-reply lifecycle troubleshooting`) that didn't exist as a subsection before: add an index entry under the runbooks group
- If DR-6 was a subsection inside an existing section: no INDEX update needed

**If updating**: find the line currently referencing `openclaw-agent-setup.md` and add a sub-bullet noting the new troubleshooting coverage:

```markdown
- [openclaw-agent-setup](runbooks/openclaw-agent-setup.md) — OpenClaw agent deployment + verification; now includes DM-reply lifecycle troubleshooting (#588)
```

### T020 [P] — DR-8: update memory `project_whatsapp_dmpolicy.md`

**File**: `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/project_whatsapp_dmpolicy.md`

**Current state** (per memory index): "WhatsApp dmPolicy — changed to 'disabled' on 2026-03-31 (was 'pairing', caused unwanted pairing codes)"

**Reality** (per WP01 + WP03 research): the deployed `dmPolicy` is `allowlist` with `allowFrom: ["+16179300916"]`. The 2026-03-31 change moved from `pairing` to `disabled`; somewhere later (date unknown — would need git archeology on the openclaw.json history, which is OUT of scope for WP04) it was changed again to `allowlist`.

**Update**:

Read the existing file first, then rewrite the body to reflect:
- Current value: `allowlist`
- `allowFrom`: `["+16179300916"]`
- Date of correction: 2026-06-11 (this mission)
- Note that the exact date of the `disabled → allowlist` switch is unknown; this memory was found stale during architectural baseline review for #588

Update the frontmatter `description` field accordingly. Do not change `metadata.type` (still `project`).

Add a `[[reference_openclaw_dm_reply_lifecycle]]` link if relevant.

**Update MEMORY.md index**:
- Find the existing line: `- [WhatsApp dmPolicy](project_whatsapp_dmpolicy.md) — changed to "disabled" on 2026-03-31 ...`
- Replace with: `- [WhatsApp dmPolicy](project_whatsapp_dmpolicy.md) — currently "allowlist" with allowFrom +16179300916; transition date unknown; corrected from stale "disabled" 2026-06-11 (#588)`

### T021 [P] — DR-9: add memory `reference_openclaw_dm_reply_lifecycle.md`

**File**: `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/reference_openclaw_dm_reply_lifecycle.md`

**Frontmatter** (per CLAUDE.md memory protocol):

```yaml
---
name: openclaw-dm-reply-lifecycle
description: openclaw embedded_run lifecycle markers + DM-reply break signature + canonical smoke command; reference for future diagnostic work
metadata:
  type: reference
---
```

**Body** (concise — this is reference content, not a long-form report):

```markdown
The openclaw-gateway tracks an `embedded_run` lifecycle per session. Healthy runs visit both markers:

- `embedded_run:started` (fires when `setActiveEmbeddedRun` is called in vendored `runs-DMxJUP3Q.js:419`)
- `embedded_run:ended` (fires when `clearActiveEmbeddedRun` is called in `runs-DMxJUP3Q.js:454` OR `forceClearEmbeddedAgentRun` in `runs-DMxJUP3Q.js:476`)

When a session has `embedded_run:started` but no `embedded_run:ended` for ≥378s, `[diagnostic] stuck session recovery: action=abort_embedded_run` fires and the run is aborted. Channel-send is never invoked. This is the #588 bug signature.

**Bug-signature check**: see [[contracts/journal-event-assertions.md]] (mission `restore-whatsapp-dm-reply-delivery-01KTVVHH`). The canonical awk one-liner is reproduced in `docs/runbooks/openclaw-agent-setup.md` under "DM-reply lifecycle troubleshooting".

**Investigation order if signature detected**: H5 plugin → H4 config → H2 missing-field → H3 AGENTS.md rollback probe → H1 escalation. Vendored runtime (`/usr/lib/node_modules/openclaw/dist/`) is OFF-LIMITS for modification per the #588 mission scope decision.

**Why the agent's `Sent by <agent>:<model>` line appears even when delivery fails**: that's the agent's own workflow output marker (per #561 output-discipline). It's the AGENT'S stdout. The GATEWAY'S completion event is `embedded_run:ended` — distinct, and the actual delivery signal.

Related: [[reference_openclaw_gotchas]], [[reference_openclaw_upgrade_gotchas]], [[project_whatsapp_dmpolicy]].
```

**Update MEMORY.md index**: add a line in the references section:
```markdown
- [openclaw DM-reply lifecycle](reference_openclaw_dm_reply_lifecycle.md) — embedded_run markers + #588 bug signature + canonical smoke command
```

## Branch Strategy

- **Planning base branch**: `main`
- **Execution worktree**: assigned by `lanes.json`
- **Final merge target**: `main` (via spec-kitty merge gate)
- **Commit discipline**: per DIRECTIVE_033, stage ONLY the WP04 owned_files (the in-repo ones). Memory files are OUTSIDE the repo and won't appear in the commit.

**Important — memory edits are out-of-tree**:
- DR-8 + DR-9 mutate files at `/Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/`
- These edits do NOT appear in the git commit
- Reviewer must verify them out-of-band (DoD includes a verification command)

## Definition of Done

- [ ] T018 `docs/runbooks/openclaw-agent-setup.md` has the new "DM-reply lifecycle troubleshooting" section with all the expected content (symptom signature, lifecycle reference, smoke command, investigation order, cross-references)
- [ ] T019 `docs/INDEX.md` updated (or explicitly noted unchanged in commit message)
- [ ] T020 memory `project_whatsapp_dmpolicy.md` updated to reflect `allowlist` reality + cross-link to new lifecycle memory
- [ ] T020 `MEMORY.md` index line updated
- [ ] T021 new memory `reference_openclaw_dm_reply_lifecycle.md` exists with full content
- [ ] T021 `MEMORY.md` index has new line in references section
- [ ] Memory verification command runs clean:
  ```bash
  ls -la /Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/ | grep -E "(project_whatsapp_dmpolicy|reference_openclaw_dm_reply_lifecycle)"
  grep -E "(dmPolicy|dm_reply_lifecycle)" /Users/kentgale/.claude/projects/-Users-kentgale-repos-kg-automation/memory/MEMORY.md
  ```
- [ ] Commit stages ONLY `docs/runbooks/openclaw-agent-setup.md` and (if changed) `docs/INDEX.md`; no spurious files

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Memory edits get lost (not in git) | Medium | DoD includes verification command; commit message documents which memory files were updated |
| Runbook section grows into long-form narrative duplicating research.md | Low | Style guidance: terse, operator-focused, cite-don't-duplicate |
| `MEMORY.md` index gets corrupted by parallel WP04 + future-session edits | Low | Atomic write via tmp + mv if editing programmatically; otherwise edit once, commit once |
| Memory entries forgotten because they're out-of-tree | Medium | DR-8 and DR-9 are tracked in `data-model.md` E4 and surfaced in this WP's DoD |

## Reviewer guidance

Check:

1. **Runbook section completeness**: all 5 subsections present (symptom signature, lifecycle reference, smoke command, investigation order, cross-references)
2. **Smoke command verbatim**: matches `contracts/journal-event-assertions.md` exactly
3. **Memory file content**: open both memory files (out-of-band Read on the absolute paths); verify frontmatter is well-formed YAML with correct `metadata.type`
4. **MEMORY.md index**: confirm new line is present; confirm stale line was updated (not added as duplicate)
5. **Cross-links**: `[[name]]` wikilinks reference real memory entries that exist
6. **DIRECTIVE_033**: only in-repo runbook + INDEX in the commit; no `Untracked` memory paths in `git status`
