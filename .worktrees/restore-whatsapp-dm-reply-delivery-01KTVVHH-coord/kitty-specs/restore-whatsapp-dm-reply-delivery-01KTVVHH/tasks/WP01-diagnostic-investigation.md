---
work_package_id: WP01
title: Diagnostic Investigation
dependencies: []
requirement_refs:
- FR-007
- FR-011
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "46240"
history:
- event: created
  timestamp: '2026-06-11T18:30:00Z'
  by: /spec-kitty.tasks
- event: h6-added
  timestamp: '2026-06-11T18:50:00Z'
  by: /spec-kitty.tasks (operator update — Codex 2026.6.5 release notes)
agent_profile: debugger-debbie
authoritative_surface: docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md
execution_mode: planning_artifact
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
owned_files:
- docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md
role: investigator
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned profile:

```
/ad-hoc-profile-load debugger-debbie
```

This sets your identity, governance scope, and boundaries for this work package. Adopt the profile fully before proceeding.

---

## Objective

Validate hypotheses **H6 → H5 → H4 → H2 → H3 → H1-escalation** in priority order per `research.md` §9 and emit a **Decision Record** naming the verdict. H6 (openclaw 2026.5.28 → 2026.6.5 upgrade) is the highest-confidence candidate per Codex's release-notes review.

You succeed when `research.md` contains a new `## Discovery Findings (WP01 — <ISO timestamp>)` append block with a final line of the form:
- `Fix shape: H6 — upgrade openclaw 2026.6.5 (release notes mapping below)`, OR
- `Fix shape: <H5|H4|H2|H3> — <specific change>`, OR
- `Escalation: H1 (vendored runtime with no available upstream fix); evidence summary attached`

And when `spec-kitty agent decision open/resolve` has recorded the chosen verdict in the spec-kitty decision ledger.

## Context

Read these files in this order before starting:

1. [`spec.md`](../spec.md) — FRs, NFRs, Cs, SCs (acceptance criteria)
2. [`research.md`](../research.md) — §3 live diagnostic, §4 original hypothesis ranking, §5 decisions D1–D6, **§9 H6 update + A3 relaxation (your authoritative input)**
3. [`contracts/embedded-run-lifecycle.md`](../contracts/embedded-run-lifecycle.md) — what `embedded_run:started` / `:ended` mean and why their start/end pairing is the bug signature
4. [`quickstart.md`](../quickstart.md) §3 — canonical diagnostic ramp (note: written before H6 was added; treat as reference for command shapes but follow the H6-first order)
5. Memory `reference_openclaw_upgrade_gotchas` — the prior-incident checklist for openclaw upgrades

You are operating against **office2** via `ssh office2-claude` (NEVER `ssh office2-kgale`). The `claude` user has no sudo; if a command needs sudo, surface to Kent for manual execution. T001 (H6 probe) is read-and-plan only; T005 (H3 AGENTS.md probe) is the only destructive-but-reversible subtask.

## Detailed guidance per subtask

### T001 — H6 openclaw upgrade probe + plan (FIRST in ramp)

**Purpose**: Confirm that openclaw 2026.6.5 is available + the release notes credibly address our bug signature, then draft an upgrade plan. **Do NOT execute the upgrade in WP01** — WP02 owns the execution. Your output is a desk-research verdict + an upgrade plan.

**Steps**:

```bash
# 1. Confirm current installed version
ssh office2-claude 'openclaw --version'
# Expected: OpenClaw 2026.5.28 (e932160)

# 2. Probe for newer published version
ssh office2-claude 'npm view openclaw versions --json 2>&1 | head -60'
# Look for 2026.6.5 (or newer); note the exact release identifier

# 3. Read the openclaw 2026.6.5 release notes / CHANGELOG
ssh office2-claude 'find /usr/lib/node_modules/openclaw -name "CHANGELOG*" -o -name "RELEASE*" 2>/dev/null | grep -v node_modules/.bin | head -5'
ssh office2-claude 'cat /usr/lib/node_modules/openclaw/CHANGELOG.md 2>/dev/null | head -200' || \
ssh office2-claude 'npm view openclaw README 2>&1 | head -80'
# Cross-reference against the Codex summary in research.md §9
```

**Map release-notes fixes to our bug signature** — explicitly note which release-note lines map to:
- `classification=stalled_agent_run`
- `activeWorkKind=embedded_run`
- `recovery=abort_embedded_run`
- `sessions.resolve INVALID_REQUEST current`

If the mapping is strong (the Codex summary indicates it is), proceed to draft the upgrade plan.

**Draft the upgrade plan** (write into your WP01 notes; will be incorporated into the Decision Record at T006):
- Pre-flight: Restic ≤24h (Tier 2 per C-003), `openclaw doctor --json` baseline capture
- Upgrade command: `ssh office2-claude 'sudo npm install -g openclaw@2026.6.5'` — **NOTE: requires sudo; surface to Kent for manual execution per CLAUDE.md (claude user has no sudo)**
  - Alternative: pipx-install path if applicable; verify via `which openclaw` whether it's npm-global or pipx
- Post-upgrade verification:
  - `openclaw --version` reports `2026.6.5`
  - `openclaw doctor --json` returns clean
  - `models.providers.<x>.models[]` still present (per `reference_openclaw_upgrade_gotchas`)
  - `@openclaw/whatsapp` plugin auto-installs if previously bundled (verify via `openclaw plugins list`)
  - Restart gateway: `systemctl --user restart openclaw-gateway.service`
  - Post-flight smoke: send 1 test DM, check journal for `embedded_run:ended`
- Rollback shape: re-install previous version `npm install -g openclaw@2026.5.28`; restore openclaw.json from pre-upgrade backup; restart gateway

**Validation captured to notes**: `H6: <validated|deferred|refuted-by-desk-review> — <release-note-to-bug-signature mapping summary>`. "Validated" means desk review is strong enough that you recommend WP02 execute the upgrade; "deferred" means you want to test H5–H3 first because of risk concerns; "refuted-by-desk-review" means the release notes do NOT credibly address our bug signature (unlikely given the Codex summary).

**What this subtask does NOT do**:
- Does NOT execute the upgrade
- Does NOT install or modify any package on office2 (except read-only commands)
- Does NOT restart the gateway

### T002 [P] — H5 plugin install state + version check (read-only)

**Purpose**: Verify the `@openclaw/whatsapp` external plugin is installed and on a current version. Lower priority than H6 — but quick to check and might surface a separate issue.

```bash
# List installed plugins
ssh office2-claude 'openclaw plugins list 2>&1'

# Get version info for the whatsapp plugin (if installed)
ssh office2-claude 'openclaw plugins info @openclaw/whatsapp 2>&1' || \
ssh office2-claude 'openclaw plugins info whatsapp 2>&1'

# Actual install location
ssh office2-claude 'ls -la /home/claude/.openclaw/plugins/ 2>&1; find / -path "*node_modules/@openclaw/whatsapp*" -type d 2>/dev/null | head -5'
```

**Validation**: `H5: <validated|refuted> — <evidence>`. Validated = plugin missing or older than 2026-06-01.

### T003 [P] — H4 config-swap probe matrix (read-only first)

**Purpose**: Examine `dmPolicy` (`allowlist`) and `session.dmScope` (`per-channel-peer`); optionally try ONE temporary config swap with full rollback.

```bash
# Read deployed config (authoritative per DIR-008)
ssh office2-claude 'jq ".channels.whatsapp, .session" /home/claude/.openclaw/openclaw.json'
```

**Active probe** (only if H6 + H5 don't validate by desk review and read-only analysis is inconclusive):
- Save backup: `ssh office2-claude 'cp /home/claude/.openclaw/openclaw.json /tmp/openclaw.pre-probe.$(date +%s).json'`
- Apply ONE change at a time; restart gateway; send 1 DM; observe journal
- **ALWAYS** rollback regardless of outcome

**Validation**: `H4: <validated|refuted|not-tested-actively> — <evidence>`.

### T004 [P] — H2 missing-field discovery via openclaw docs

**Purpose**: Discover whether the deployed `openclaw.json` is missing a config key the 2026.5.28 runtime expects for DM-reply dispatch. (Becomes near-irrelevant if H6 validates, but check in case the upgrade requires accompanying config that we're missing.)

```bash
# Read openclaw docs (read-only)
ssh office2-claude 'cat /usr/lib/node_modules/openclaw/docs/channels/whatsapp.md' | head -200
ssh office2-claude 'cat /usr/lib/node_modules/openclaw/docs/gateway/configuration.md 2>/dev/null' | head -200
ssh office2-claude 'grep -rln "reply\|delivery\|dmScope\|dm-reply" /usr/lib/node_modules/openclaw/docs/ 2>/dev/null | head -20'
```

**Validation**: `H2: <validated|refuted> — <which field is missing and where it's documented>`.

### T005 — H3 AGENTS.md rollback probe (mutates + restores; never persists rollback state)

**Purpose**: Test whether post-#579 `main/AGENTS.md` changes left a behavioral gap. Quick rollback probe to pre-#579 version. **Run AFTER H6/H5/H4/H2 desk research** to minimize unnecessary disruption to office2 if H6 already explains the bug.

```bash
# 1. SAVE current AGENTS.md
ssh office2-claude 'cp /data/services/openclaw/data/AGENTS.md /tmp/main-AGENTS.current.$(date +%s).md'

# 2. Get pre-#579 version
git show 37b3bf56^:scripts/openclaw/agents/main/AGENTS.md > /tmp/main-AGENTS.pre579.md

# 3. Deploy pre-#579 version
scp /tmp/main-AGENTS.pre579.md office2-claude:/data/services/openclaw/data/AGENTS.md

# 4. Restart gateway
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
sleep 5

# 5. Operator-coordinated DM probe
TS=$(date -u +"%Y-%m-%d %H:%M:%S"); echo "Send 1 DM now. Baseline: $TS"

# 6. Check journal for embedded_run:ended after 60 seconds
ssh office2-claude "journalctl --user -u openclaw-gateway --since '$TS' 2>/dev/null | grep -E '(embedded_run|stuck session|Sending message|Sent message)'"

# 7. ALWAYS rollback (regardless of outcome)
ssh office2-claude 'cp /tmp/main-AGENTS.current.*.md /data/services/openclaw/data/AGENTS.md && systemctl --user restart openclaw-gateway.service'

# 8. Confirm rollback landed
ssh office2-claude 'wc -l /data/services/openclaw/data/AGENTS.md'
```

**Validation**: `H3: <validated|refuted> — <which behavior was restored, if any>`. Step 7 rollback is MANDATORY even if H3 validated — the pre-#579 file is over the 12K cap and re-triggers #579 truncation.

### T006 — Synthesize Decision Record into research.md append block

**Steps**:
1. Open `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md` and navigate to the end.
2. Append a new heading: `## Discovery Findings (WP01 — <ISO 8601 UTC timestamp>)`.
3. Under that heading:
   - One subsection per hypothesis with `<verdict> — <evidence summary in 1-3 sentences>`
   - A `### Decision Record` subsection with the final verdict in one of three forms:
     - `**Fix shape**: H6 — upgrade to openclaw <version>. Upgrade plan: <plan from T001>.`
     - `**Fix shape**: <H5|H4|H2|H3> — <exact change>` (with "Next steps for WP02" block enumerating files to edit + precise edits)
     - `**Escalation**: H1 — vendored runtime regression with no available upstream fix (even 2026.6.5 doesn't address). Evidence: <2-3 sentences>. Tracking issue to be filed by WP02 per FR-009.`
4. Commit the change. DIRECTIVE_033: stage ONLY `research.md`.

### T007 — Open + resolve spec-kitty decision

```bash
DECISION_ID=$(spec-kitty agent decision open \
  --mission restore-whatsapp-dm-reply-delivery-01KTVVHH \
  --flow tasks \
  --slot-key tasks.wp01.root-cause-verdict \
  --input-key root_cause_verdict \
  --question "Which hypothesis is the validated root cause for #588?" \
  --options '["H6","H5","H4","H2","H3","H1-escalation"]' \
  | jq -r '.decision_id')

spec-kitty agent decision resolve "$DECISION_ID" \
  --mission restore-whatsapp-dm-reply-delivery-01KTVVHH \
  --final-answer "<H6|H5|H4|H2|H3|H1-escalation>"

spec-kitty agent decision verify --mission restore-whatsapp-dm-reply-delivery-01KTVVHH
```

The decision artifact lands at `kitty-specs/.../decisions/DM-<DECISION_ID>.md`. Do NOT hand-edit.

## Branch Strategy

- **Planning base branch**: `main` (planning artifacts at HEAD per the #1784 FF workaround applied at plan→tasks transition)
- **Execution worktree**: assigned by `lanes.json` via `spec-kitty agent action implement WP01 --agent claude`
- **Final merge target**: `main` (via spec-kitty merge gate at mission-end)
- **Commit discipline**: per DIRECTIVE_033, stage ONLY `research.md`. NEVER `git add .` or `git add -A`.

## Definition of Done

- [ ] T001 H6 desk-review + upgrade plan captured in WP01 notes with explicit release-note-to-bug-signature mapping
- [ ] T002 H5 verdict captured with evidence
- [ ] T003 H4 verdict captured with evidence (note if active probe was used + rollback confirmed)
- [ ] T004 H2 verdict captured with evidence
- [ ] T005 H3 verdict captured with evidence; AGENTS.md ROLLED BACK on office2 (step 7 + step 8 verified)
- [ ] T006 `research.md` has new `## Discovery Findings (WP01 — <ISO TS>)` append block with full verdict + Decision Record
- [ ] T007 spec-kitty decision opened + resolved; `decision verify` returns `status: clean`
- [ ] No vendored openclaw runtime files modified (C-001 — note: the upgrade ITSELF is not a "modification" per C-001; it's a package replacement)
- [ ] Office2 in same observable state as before WP01 (gateway running; AGENTS.md unchanged; openclaw.json unchanged unless H4 active probe → rolled back; openclaw runtime version unchanged unless H6 execution moved into WP02)

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| H6 desk review concludes upgrade isn't relevant after all | Low (~15% — Codex review was strong) | T002-T005 still run; fallback to H5/H4/H2/H3 |
| H5 plugin install state probe destabilizes gateway | Low | All H5 commands are read-only |
| H3 probe leaves wrong AGENTS.md if rollback skipped | High | T005 step 7 explicitly always runs; step 8 verifies |
| WP01 runs the actual upgrade (out of scope) | High | T001 prompt explicitly says "WP02 owns execution"; T001 ends with a plan + verdict only |
| Sensitive `openclaw.json#gateway.auth.token` accidentally logged | High | Always use `jq` to extract only the keys you need |
| All hypotheses (including H6) refuted | Medium | FR-009 covers: escalate to H1 via WP02 internal tracking issue |

## Reviewer guidance

When reviewing WP01, check:

1. **H6 decision quality**: T001 explicitly maps release-note items to bug-signature lines; upgrade plan includes pre-flight + post-flight verification + rollback shape
2. **Hypothesis order respected**: T001 always considered first; T005 (H3 mutating probe) only after T001-T004 desk reviews
3. **Rollback completeness**: any active probe (T003 or T005) has rollback evidence in the WP01 notes
4. **Decision Record clarity**: the final line in research.md is one of three unambiguous forms (Fix shape H6, Fix shape H2-H5, or Escalation)
5. **No vendored runtime mods**: search the commit for any vendored-path reference; upgrade plan is in T001 as a plan (not an executed upgrade)
6. **Decision ledger consistency**: `decision verify` clean; chosen verdict matches research.md exactly
7. **Office2 state**: gateway running; runtime version unchanged (T001 is planning-only); AGENTS.md size unchanged

If any check fails, reject with structured feedback naming the failing item.

## Activity Log

- 2026-06-11T18:59:24Z – claude:opus:debugger-debbie:investigator – shell_pid=42734 – Started implementation via action command
- 2026-06-11T19:09:43Z – claude:opus:debugger-debbie:investigator – shell_pid=42734 – H6 desk review complete; destructive probes (T003 config-swap, T005 AGENTS.md rollback) skipped per orchestrator instruction; Decision Record: Fix shape: H6 — upgrade openclaw 2026.6.5 (release-notes mapping in docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation.md §3.3 + Decision Record §10); decision ledger clean (DM-01KTW1CJVX0YPJZR27XZFRG95M)
- 2026-06-11T19:10:46Z – claude:opus:reviewer-renata:reviewer – shell_pid=46240 – Started review via action command
- 2026-06-11T19:15:01Z – user – shell_pid=46240 – Review passed: H6 verdict well-evidenced (3 CHANGELOG mappings); office2 untouched; staging clean; WP02 has clear upgrade plan
