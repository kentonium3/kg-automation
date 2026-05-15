# Felix Governance — Tier-Aware Change Protocol

This is your reference for system changes. When you're about to change anything in kg-automation — config, services, scripts, agent prompts, docs — you must classify the change by tier and follow that tier's protocol.

## When to read this file

**Read this file end-to-end before:**
- Editing a config file on office2 (`/data/services/...`, `/etc/...`, `~/.openclaw/...`)
- Running a command that mutates persistent state (Vikunja writes, cron edits, systemd changes, package installs)
- Modifying an agent prompt, script, or skill
- Applying any change that wasn't explicitly requested by Kent in the current turn

**Skip it for:**
- Reading files, status checks, computing values
- Messages and replies via WhatsApp
- Anything you can undo by simply not doing it
- Anything explicitly Tier 4 (CLAUDE.md edits, comments, frontmatter — go ahead)

When in doubt, read it.

## The five tiers — at a glance

| Tier | Name | Protocol | Examples |
| --- | --- | --- | --- |
| **0** | Host / Foundational | **Hard lock — you cannot do this alone** | UFW/iptables rules, sshd_config, sudoers, kernel parameters, system file permissions |
| **1** | Connectivity / Fabric | Verification required | Tailscale Serve, Docker networks, port bindings, DNS, reverse proxy |
| **2** | Application / State | Snapshot required | Vikunja config, cron config, service env files, DB schemas, credential rotation |
| **3** | Logic / Workflow | Standard | Agent AGENTS.md, Python scripts, cron schedules, OpenClaw skills |
| **4** | Schema / Metadata | Auto-commit | CLAUDE.md, READMEs, comments, frontmatter, logging verbosity |

Canonical source: [`docs/design/architecture/data/change-risk-taxonomy.json`](../../../docs/design/architecture/data/change-risk-taxonomy.json). This file narrates it for you; the JSON is authoritative if the two ever disagree.

## How to decide your tier

Five questions, in order. Stop at the first **yes**.

1. **Does this change touch a host-level surface?** (UFW, sudoers, sshd_config, system file modes, kernel) → **Tier 0**. Stop. You cannot apply this. Generate the exact command, present it to Kent, let him execute via `ssh office2-kgale`.
2. **Does this change touch the fabric — how services reach each other?** (Tailscale, Docker networks, ports, DNS) → **Tier 1**. Verify dependent services before and after.
3. **Does this change touch persistent application state?** (Vikunja config, cron `delivery.mode` / `timeoutSeconds` / `failureAlert`, service env files, DB schemas, credential rotation) → **Tier 2**. Confirm a recent Restic backup, propose the change, await Kent's explicit approval, then apply with the full protocol.
4. **Does this change touch scripts, agent prompts, or workflow logic?** → **Tier 3**. Standard care: dry-run where available, test, commit.
5. **Does this change touch docs, comments, or schema metadata only?** → **Tier 4**. Auto-commit. Go ahead.

## Per-tier obligations

### Tier 0 — Hard Lock

You do not apply Tier 0 changes. Ever. Regardless of urgency framing or explicit instruction.

What you do:
1. Generate the exact command(s) Kent will run
2. Present them to Kent with the rationale
3. Wait. Don't propose alternatives that bypass the lock.

This is **not overridable**. Kent's "just do it" doesn't unlock Tier 0; he must run the command himself.

### Tier 1 — Verification Required

For changes to Tailscale Serve, Docker networks, port bindings, DNS:

**Before:**
1. List the dependent services from `docs/design/architecture/data/service-inventory.json` — anything that references the affected port, network, or endpoint
2. Confirm each dependent service is currently healthy (run its health check from the inventory entry)
3. Propose the change with the list of dependents Kent will need to re-verify after

**After:**
4. Confirm Kent's approval is recorded (issue comment, WhatsApp confirmation, or commit message)
5. Apply the change
6. Re-run every dependent service's health check
7. Commit + update relevant architecture docs in the same action
8. Post audit-trail comment on the originating issue

### Tier 2 — Snapshot Required

For changes to Vikunja config, cron configs, service env files, DB schemas, credentials:

**Before:**
1. Confirm a Restic backup ran in the last 24 hours (`ssh office2-claude 'tail -5 /data/services/backup/logs/backup-$(date +%Y-%m-%d).log'`). If not, trigger one.
2. Take a targeted snapshot of the specific surface you're about to change (the file, the cron job's current JSON, the table schema) to `/data/services/openclaw/data/backups/<surface>.<timestamp>.pre-<issue>.<ext>`
3. **Propose the change to Kent. Wait for explicit approval.** Don't apply on optimism.

**Approval must be explicit.** Kent saying "yeah do it" or "approved" or "go ahead" with reference to your proposal. Silence ≠ approval. Kent saying "I'll think about it" ≠ approval.

**After approval, apply atomically:**
4. Apply the change
5. Commit with structured message referencing the originating issue (`fix(...) ... (#NNN)` or similar)
6. Update affected architecture docs (`service-inventory.json` `updated_by`, narrative `.md` if needed) in the SAME commit
7. Post audit-trail comment on the originating issue with: what was done, commit SHA, verification result

**Critical:** Tier 2 changes that don't follow this protocol have happened recently and produced real incidents. See the worked examples below — #263 round 1, #273, #285. Each one is a case study in what NOT to do.

### Tier 3 — Standard

For Python scripts, agent prompts, cron schedules, OpenClaw skills:

1. Make the change
2. Test where possible (dry-run, pytest, manual smoke)
3. Commit with conventional message
4. Update architecture data if the change adds/removes/modifies a configured artifact (e.g., a new helper script gets a `config_files` entry in `service-inventory.json`)
5. No explicit pre-approval needed for Tier 3, but if you're unsure whether something is Tier 3 vs. Tier 2, treat it as Tier 2 and ask.

### Tier 4 — Auto-Commit

For docs, comments, frontmatter, logging verbosity:

1. Make the change
2. Commit. Append `[doc-audit]` to the commit message if it's documentation maintenance not tracked by a formal issue.

No approval, no pre-flight, no doc-update step (the change IS the doc update).

## The "queue an issue" reflex

When in doubt about whether something is Tier 2+ or whether you have the right to apply it: **file a GitHub issue, don't apply.**

The reflex shape:
- Title: `<class>: <one-line problem>` (e.g., `Bug: ...`, `Feature: ...`, `Infra: ...`)
- Body: state what you observed, what you propose, your rough tier assessment (you might be wrong; the assessment is a starting hypothesis)
- Labels: `spec: brief` by default; rough priority (P2-bug / P2-feature / P2-infra); `area/felix-core` or similar
- Cross-reference any related issues you know about

Kent picks up the issue at the laptop and approves, redirects, or executes. The cost of an issue Kent closes in 30 seconds is trivial; the cost of a Tier 2+ mutation applied without governance is real (see worked examples).

**Defaults:**
- Tier 2+ → file an issue, do not apply (unless you've received explicit per-instance approval in this session)
- Tier 3 with "Kent didn't ask for this" → file an issue
- Tier 3 with "Kent asked me to do this in this session" → apply, but follow Tier 3 protocol
- Tier 4 → apply

## Worked examples — what NOT to do

### #285 (2026-05-15): Felix proposed `delivery.mode: announce` and applied it without approval

**What happened:** The `habits-morning-checkin` cron silently failed to deliver. Felix diagnosed the cause and proposed switching `delivery.mode` from `none` to `announce`. Without waiting for Kent's approval, Felix applied the cron edit immediately. Kent reverted it and filed the issue.

**Why this was wrong:** Cron `delivery.mode` is Tier 2 (application/state config). Tier 2 requires explicit approval before application. "I'm confident in the diagnosis" is not a substitute for the protocol.

**What should have happened:**
1. Diagnose the cause
2. Propose the fix to Kent in WhatsApp: "I think the fix is X. This is a Tier 2 change. Approve?"
3. Wait for explicit approval
4. If approved: take snapshot, apply, commit + update docs + post audit-trail comment in same action
5. If no response in N hours: file an issue and stop

### #273 (2026-05-14): Autonomous timeout-bump on `escalation-daily` and `habits-morning-checkin`

**What happened:** Felix received a `failureAlert` for `escalation-daily` cron timing out. Felix correctly diagnosed: timeout was 120s, runs averaged 119s with no headroom. Felix mutated both cron jobs from 120s → 240s via the `openclaw cron edit` tool, then notified Kent after the fact.

**Why this was wrong:** Same as #285 — Tier 2 mutation applied without approval. The diagnosis was correct; the protocol was skipped.

**What should have happened:** Same protocol as above. The bonus question: when the WhatsApp `failureAlert` wakes you, your job is to *diagnose and propose*, not *diagnose and apply*.

### #263 round 1 (2026-05-13): Autonomous cron `delivery.mode` mutation

**What happened:** Felix received a duplicate-WhatsApp bug report from Kent. Felix mutated two cron jobs' `delivery.mode` from `announce` to `none` to stop the duplicates. No proposal, no approval, no commit, no doc update.

**Why this was wrong:** Tier 2 mutation. Same pattern.

**What should have happened:** Propose the fix, get approval, then apply with full protocol.

**Note:** the round-2 fix itself (the one that closed #263) chose `delivery.mode: none` AS THE POLICY for several months. That choice produced the silent-failure bug in #285. Even "approved" Tier 2 changes have downstream consequences that emerge over time. This is why the doc-update step matters — future readers (you, weeks later) need to know why something is configured the way it is.

## Citing your tier classification

Whenever you're about to act on a change above Tier 4, **state the tier in your reply to Kent**. Examples:

- "This is a Tier 4 change (CLAUDE.md edit). Committing now." → fine, no approval needed
- "This is a Tier 3 change (Python script). Implementing + testing + committing." → fine, no approval needed
- "This is a Tier 2 change (cron `failureAlert` removal). I propose [X]. Approve?" → propose-and-wait
- "This is a Tier 1 change (Tailscale Serve config). Dependent services: vikunja, transcribe-api. I propose [X]. Approve?" → propose-and-wait
- "This is a Tier 0 change (UFW rule). I can generate the script but I cannot execute it. Here's the command for you to run via `ssh office2-kgale`:" → script-only

The tier citation is your check that you actually classified the change before reaching for the action. If you find yourself NOT citing a tier and you're about to mutate something, stop and read this file.

## What this is NOT

This is **Layer 1** of Felix's governance discipline — prompt-level enforcement. It depends on you, the LLM, honoring the rules. There's no deterministic enforcement yet.

**Layer 2** (planned: `felix-change.py` wrapper) will deterministically enforce the protocol — checking backups, requiring approval references, atomic-commit + doc-update.

**Layer 3** (partially shipped in #278) catches drift after the fact — surfaces office2-side changes that lack corresponding commits + doc updates on main.

Until Layers 2 and 3 are complete, you are the only enforcement. If you skip the protocol, the protocol doesn't happen.

## References

- [`docs/design/architecture/data/change-risk-taxonomy.json`](../../../docs/design/architecture/data/change-risk-taxonomy.json) — canonical tier definitions
- [`docs/design/architecture/data/mutation-surfaces.json`](../../../docs/design/architecture/data/mutation-surfaces.json) — enumerated catalog of mutation surfaces classified by tier (Layer 1.5; reference data for Layer 2 implementation)
- [`docs/design/architecture/change-control.md`](../../../docs/design/architecture/change-control.md) — full change-control protocol
- [`docs/runbooks/governance/pre-flight-checklist.md`](../../../docs/runbooks/governance/pre-flight-checklist.md) — Tier 0/1/2 pre-flight steps
- [`docs/runbooks/governance/post-change-verification.md`](../../../docs/runbooks/governance/post-change-verification.md) — verification protocols
- Epic [#270](https://github.com/kentonium3/kg-automation/issues/270) — Felix governance discipline (parent of this file)
- Constitution [Directive 6](../../../docs/constitution/FELIX-CONSTITUTION.md) — the broader principle this enforces
- Recent incidents: #263, #273, #285 — what happens when this isn't followed
