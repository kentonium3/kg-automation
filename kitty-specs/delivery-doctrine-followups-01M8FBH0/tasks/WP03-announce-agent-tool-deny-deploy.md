---
work_package_id: WP03
title: Announce-agent tool deny deploy
dependencies: []
requirement_refs:
- FR-006
- FR-007
- C-001
- C-002
- SC-002
- SC-004
planning_base_branch: fix/1146-delivery-doctrine-followups
merge_target_branch: fix/1146-delivery-doctrine-followups
branch_strategy: Planning artifacts for this mission were generated on fix/1146-delivery-doctrine-followups. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/1146-delivery-doctrine-followups unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-delivery-doctrine-followups-01M8FBH0
base_commit: 32009aa5caca89fd640914e85ecdd5539c2e1ef4
created_at: '2026-11-27T21:03:04.400684+00:00'
subtasks:
- T011
- T012
- T013
- T014
- T015
phase: Phase 1 - Capability enforcement
history:
- at: '2026-11-27T20:57:33Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/deploy/
create_intent:
- scripts/deploy/deploy-announce-agent-tool-deny.py
- tests/deploy/test_announce_agent_tool_deny.py
- deploys/queued/announce-agent-tool-deny.yaml
execution_mode: code_change
model: claude-sonnet-5-5
owned_files:
- scripts/deploy/deploy-announce-agent-tool-deny.py
- tests/deploy/test_announce_agent_tool_deny.py
- deploys/queued/announce-agent-tool-deny.yaml
- scripts/openclaw/agents/tests/fixtures/openclaw-sample.json
- scripts/openclaw/agents/tests/test_openclaw_config_schema.py
- scripts/deploy/lib/README.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Announce-agent tool deny deploy

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_ref` field in the event log (via `spec-kitty agent tasks status`).
- **You must address all feedback** before your work is complete. Feedback items are your implementation TODO list.
- **Report progress**: As you address each feedback item, record what you changed with `spec-kitty agent tasks add-history <WPID> --note "..."` (stored in the status event log).

---

## Review Feedback

*[If this WP was returned from review, the reviewer feedback reference appears in the status event log.]*

---

## Markdown Formatting

Wrap HTML/XML tags in backticks: `` `<div>` ``, `` `<script>` ``
Use language identifiers in code blocks: ````python`,````bash`

---

## Objectives & Success Criteria

A Tier 2 deploy, applied by felix-deployer from a queued manifest, that sets the following on office2's live `~/.openclaw/openclaw.json` (as the `claude` user):

```
agents.entries.<id>.tools.deny = ["conversations_*","sessions_*","message","automations"]
```

for exactly `felix-admin-capture`, `felix-admin-escalation` and `felix-admin-habits`. All of the following must hold:

- Every other agent entry, and the top-level `tools`, are unchanged; this is proven by sorted-JSON sha256 before and after.
- It is idempotent: re-applying is a no-op.
- It refuses unexpected shapes.
- It writes a recovery receipt before the first change.
- Reload is confirmed: Gateway acknowledgement, unchanged gateway PID and start time, and `config get` read-back.
- Rollback is scoped and goes through the Gateway.
- **No office2 write happens in this WP.** Development and tests run against fixtures. The deploy happens only when the manifest is merged to `main` and applied by felix-deployer (Kent's go-ahead, 2026-11-27).

## Context & Constraints

- **Read**:
  - `plan.md` (IC-04, and the "Post-plan review" table: R1-1, R1-2, R1-5, R1-6 and R1-7 are binding);
  - `data-model.md` (tool deny entry, manifest fields);
  - `research.md` (Q1 and Q2, in full);
  - `docs/runbooks/deploy/discipline.md` (manifest discipline, the Python entrypoint checklist, `expected_baselines`);
  - `scripts/deploy/lib/README.md`, `apply.py` and `snapshot.py`;
  - a recent entrypoint to copy structure from: `scripts/deploy/deploy-crash-loop-unit-alerting.py` or `deploy-felix-canary.py`;
  - the manifest schema `deploys/schema/manifest-v1.schema.json`, and an example such as `deploys/applied/0043-crash-loop-unit-alerting.yaml`.
- **Facts from research**:
  - The live shape is `agents.entries.<id>`, not `agents.list[]`, and no target agent has a `tools` key today.
  - Deny wins, is case-insensitive and supports `*`; `cron` aliases to `automations`.
  - `openclaw config patch` makes one Gateway-owned validated write: objects merge, arrays replace.
  - Reload mode is `hybrid`, which hot-applies `agents` and `tools`.
  - The bin is `~/.local/bin/openclaw` and is not on the non-login PATH. Use the repo's resolver in `scripts/common/openclaw_bin.py`.
- **Office2 access in this WP**: read-only only, through `ssh office2-claude`. Never read or print secret values; select only the keys you need with `jq`. No `config patch` / `set` / `unset` against live config, and no gateway restart.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T011 – Read-only effective-catalog method

- **Purpose**: R1-1. The canary must prove capability removal, not just a clean run.
- **Steps**:
  1. Read-only on office2, look through the installed OpenClaw CLI and docs (`~/.local/lib/node_modules/openclaw`) for a command that lists an agent's **effective** tools after policy. Try `openclaw tools …`, `openclaw agents … --json` and gateway status/inspect, or a documented RPC.
  2. Record the method in the entrypoint's post-flight as an optional check. If none exists, record that plainly; the canary will then report a weaker check.
  3. Write the finding into your hand-in, with the exact command and its output shape.
- **Notes**: running an agent turn is **not** read-only, because it would post to WhatsApp. Don't do it.

### Subtask T012 – Deploy entrypoint

- **Purpose**: FR-006 and FR-007.
- **File**: `scripts/deploy/deploy-announce-agent-tool-deny.py`: shebang, mode 0755, `sys.path` shim, `--dry-run` / `--apply`, matching the discipline checklist.
- **Behaviour**:
  1. **Resolve** the openclaw bin with the repo resolver. Read the config through `openclaw config get` (JSON) for `agents.entries` and the top-level `tools`.
  2. **Preconditions** (refuse with a clear message and a non-zero exit):
     - any of the three entries is missing;
     - any has `tools.allow` or `tools.alsoAllow`;
     - any has a `tools.deny` that is neither absent nor exactly the target set. If it is exactly the target set, that is the idempotent no-op path.
  3. **Recovery receipt**: before the first change, write a receipt (for example `/data/services/felix-deployer/state/announce-agent-tool-deny.receipt.json`, or a path under the deployer's state dir; follow discipline.md). It records each target's original `tools` value, distinguishing *absent* from `{}` and from empty arrays, plus the sorted-JSON sha256 of every non-target entry and of the top-level `tools`. Never overwrite an existing receipt: retries keep the original.
  4. Also make a timestamped copy of `openclaw.json` next to it, for last-resort recovery only.
  5. **Patch**: one `openclaw config patch` with a JSON object that sets only the three `tools.deny` arrays. Run `--dry-run` first and print it. In `--apply`, run it for real, then `openclaw config validate`.
  6. **Read-back**: assert each target deny equals the target set, and that every non-target hash and the top-level `tools` hash are unchanged. On mismatch, fail loudly and print the rollback command.
  7. **Reload confirmation**:
     - record the gateway PID and start time before and after; they must be unchanged;
     - wait a bounded time (for example 30 s) for the Gateway's reload acknowledgement in its log or journal (find the line read-only in T011);
     - any "restart required" is a failure.
  8. **Optional**: run the T011 effective-catalog check.
  9. **Rollback helper**: `--rollback` applies one `config patch` restoring the original `tools` values from the receipt: unset where the value was absent. It refuses if the receipt is missing. Document in the manifest notes that the manifest must be removed from `deploys/queued/` first if it was never applied.
- **Notes**:
  - Print a recovery block on any failure, as other entrypoints do.
  - Use the `subprocess` argument-list form, never shell strings.
  - No secrets in output.

### Subtask T013 – Tests and fixture migration

- **Steps**:
  1. **R1-5**: migrate `scripts/openclaw/agents/tests/fixtures/openclaw-sample.json` to the live shape (`agents.entries.<id>`, keys only, no secrets), and update its consumer `test_openclaw_config_schema.py` (it currently indexes `agents.list` and requires an embedded `id`) to the new contract. Both stay green.
  2. Create `tests/deploy/test_announce_agent_tool_deny.py`. Stub the openclaw CLI with a fake executable or a subprocess shim over a temporary config. Cover:
     - the happy apply;
     - the idempotent re-apply (no patch issued);
     - each refusal (missing entry, existing allow, different deny);
     - non-target hash protection: a fake patch that also touches `main` must fail read-back;
     - receipt write-once;
     - rollback restoring absent vs empty correctly;
     - PID-change detection as a failure;
     - dry-run writes nothing.
  3. Pair every refusal with a passing control on the same fixture.

### Subtask T014 – Queued manifest

- **File**: `deploys/queued/announce-agent-tool-deny.yaml`. It is unnumbered; the applier assigns the sequence (R1-7).
- **Fields**:
  - `schema_version: v1`, `name: announce-agent-tool-deny`, `issue: kentonium3/kg-automation#1146`, `tier: 2`, `entrypoint: scripts/deploy/deploy-announce-agent-tool-deny.py`;
  - `audited_surface: true`, `expected_baselines: [openclaw-config.txt]`;
  - `verification.pre`: the entrypoint `--dry-run`. The applier's mandatory snapshot gate already enforces Restic ≤ 24 h through the backup-state file (R1-6). Do **not** add a `--backup-confirmed` path;
  - `verification.post`: read-only checks that each target deny equals the set (for example `openclaw config get … | jq -e`), plus the non-target hash check, using the entrypoint's verify mode if you give it one;
  - `created_by`;
  - `notes`: what and why (#1143, #1146, openclaw/openclaw#206884), Tier 2, the rebaseline expectation, and the rollback steps (dequeue if unapplied; else `--rollback` from the receipt; whole-file backup last).
- **Validate**: run the repo's manifest validator or schema test, and run the entrypoint `--dry-run` against a fixture.

### Subtask T015 – Library README note

- In `scripts/deploy/lib/README.md`, add a short section on manifest-driven `openclaw.json` edits: Gateway-owned `config patch`, recovery receipt, non-target hash check, and why direct file writes are wrong. If you extracted a reusable helper into `lib/`, document it; otherwise reference the entrypoint as the pattern.

## Test Strategy

```bash
.venv/bin/python -m pytest tests/deploy/test_announce_agent_tool_deny.py scripts/openclaw/agents/tests/test_openclaw_config_schema.py -q
.venv/bin/python -m pytest tests/deploy -q
```

Also run the manifest schema validation the repo uses for `deploys/queued/` (see `tests/deploy/` or `scripts/deploy/lib/manifest.py`), and the typecheck if CI runs one.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Arrays replace and clobber an existing deny | Refuse unless the deny is absent or exactly the target set |
| Other agents' config touched | Non-target hash check, with a failing test for it |
| A restart instead of a hot reload | PID and start-time check; "restart required" fails |
| A failed apply is re-run and loses the original | Write-once receipt |
| Rollback re-applied by the deployer | Dequeue first (documented in the notes) |
| The CLI is not found under the deployer | Repo bin resolver; covered by a test |

## Review Guidance

- Confirm that nothing in this WP writes to office2.
- Confirm the receipt is write-once and that rollback distinguishes absent from empty.
- Confirm the manifest validates, declares `expected_baselines`, and has no `--backup-confirmed` path.
- Confirm the fixture migration kept `test_openclaw_config_schema.py` meaningful.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`) — never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history <WPID> --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task <WPID> --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
