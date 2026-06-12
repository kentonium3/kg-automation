---
id: restore-whatsapp-dm-reply-delivery-01KTVVHH-investigation
doc_type: diagnostic-report
title: "WP01 Diagnostic Investigation — WhatsApp DM Reply Delivery (#588)"
status: complete
level: reference
owners: ["kent@intentional.biz"]
last_validated: "2026-06-11"
version: "1.0"
mission_slug: restore-whatsapp-dm-reply-delivery-01KTVVHH
mission_id: 01KTVVHHBJKKG3JPMGRVHSB81P
github_issue: 588
work_package: WP01
agent: debugger-debbie
related_files:
  - kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md
  - kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/spec.md
  - kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/tasks/WP01-diagnostic-investigation.md
---

# WP01 Diagnostic Investigation — WhatsApp DM Reply Delivery (#588)

**Mission**: `restore-whatsapp-dm-reply-delivery-01KTVVHH` (GitHub issue [#588](https://github.com/kentonium3/kg-automation/issues/588))
**Work Package**: WP01 — Diagnostic Investigation
**Agent**: `debugger-debbie` (investigator)
**Investigation date**: 2026-06-11
**Authoritative input**: [`research.md` §9 — H6 (openclaw upgrade) update](../../kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md)
**Companion audit-trail entry**: [`research.md` Discovery Findings (WP01 — 2026-06-11)](../../kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md)

---

## 1. Executive summary

**Verdict**: **`Fix shape: H6 — upgrade openclaw 2026.6.5 (release-notes mapping below)`**

The openclaw 2026.6.5 CHANGELOG explicitly fixes the bug-signature class observed in `research.md` §3 (`classification=stalled_agent_run` / `activeWorkKind=embedded_run` / `recovery=abort_embedded_run`). Multiple independent fixes in the 2026.5.28 → 2026.6.5 delta address (a) the WhatsApp restart-stale-controller path and (b) the Anthropic stream-start lifecycle where `embedded_run:ended` should fire. Desk review is strong enough — per the orchestrator's instruction — to skip the destructive probes (T003 active config swap, T005 H3 AGENTS.md rollback). T002 (H5 plugin probe) and T004 (H2 missing-field discovery) both ran read-only and refuted.

**Next**: WP02 executes the upgrade per the plan in §6.

---

## 2. Scope and method

### 2.1 Hypothesis ramp (post-§9 update)

Per `research.md` §9, hypotheses are ranked:

| # | Hypothesis | Confidence | Cost | Order |
|---|---|---|---|---|
| H6 | openclaw 2026.5.28 → 2026.6.5 upgrade resolves embedded_run completion path | High (~55%) | Low | 1st |
| H5 | `@openclaw/whatsapp` plugin install state | Low | Lowest | 2nd |
| H4 | Config-swap (`dmPolicy` / `dmScope`) | Low | Low | 3rd |
| H2 | Missing config field | Medium | Medium | 4th |
| H3 | AGENTS.md post-#579 hole | Low | Medium (rollback probe) | 5th |
| H1 | Vendored regression with no available fix | Low | High | Escalation only |

### 2.2 Operator constraint applied to ramp

Per the orchestrator's instructions (echoed in the WP01 prompt risk table — "WP01 runs the actual upgrade (out of scope)"), if T001 desk review confirms the Codex mapping is strong, conclude with `Fix shape: H6` and SKIP the destructive probes (T003 active config swap, T005 H3 AGENTS.md rollback). T002 and T004 are read-only and still run as sanity checks.

This investigation followed that constraint. Office2 remains in the same observable state as before WP01 began (gateway running, AGENTS.md unchanged, openclaw.json unchanged, runtime version unchanged at 2026.5.28).

### 2.3 Read-only probes used

All probes invoked via `ssh office2-claude` (the claude user has no sudo; no command in WP01 needs it). Vendored runtime files at `/usr/lib/node_modules/openclaw/dist/` were read but not modified (per C-001).

---

## 3. T001 — H6 openclaw upgrade probe (verdict: validated)

### 3.1 Current installed version

```
$ ssh office2-claude 'openclaw --version'
OpenClaw 2026.5.28 (e932160)

$ ssh office2-claude 'which openclaw && readlink -f $(which openclaw)'
/usr/bin/openclaw
/usr/lib/node_modules/openclaw/openclaw.mjs
```

Confirmed: install is **npm-global** at `/usr/lib/node_modules/openclaw/` (NOT pipx). Upgrade vector is `npm install -g openclaw@2026.6.5` (requires sudo).

### 3.2 Published versions probe

```
$ ssh office2-claude 'npm view openclaw versions --json'
[…, "2026.5.28", "2026.5.30-beta.1", "2026.5.31-beta.1-4", "2026.6.1-beta.1-3",
 "2026.6.1", "2026.6.2-beta.1", "2026.6.5-beta.1-6", "2026.6.5"]

$ ssh office2-claude 'npm view openclaw@2026.6.5 dist-tags'
alpha: 2026.5.19-alpha.1
beta:  2026.6.5-beta.6
latest: 2026.6.5
```

**2026.6.5 is the current `latest` dist-tag** (published 2 days ago by GitHub Actions). Release shasum/integrity captured for reference:
- `.tarball`: `https://registry.npmjs.org/openclaw/-/openclaw-2026.6.5.tgz`
- `.shasum`: `6d935d5642269ede79de4d8c76d4b2c1cedf96a7`
- `.integrity`: `sha512-sRgF0TexfRcJX8Eg0lcL6Jj0YdZbSxUbbp8EbG+qo3v6TtVayE6tKPEs3oCKD7YfYe2C/8Qg26HUxTnycd44ZQ==`

### 3.3 CHANGELOG mapping to bug signature

The 2026.6.5 CHANGELOG was fetched read-only from the npm tarball (`npm pack openclaw@2026.6.5 -> CHANGELOG.md`) on office2 at `/tmp/openclaw-2026.6.5/package/CHANGELOG.md`. The 2026.6.5 entry is the only versioned section (it summarizes all fixes since the previous stable 2026.5.28).

**Direct mapping from CHANGELOG lines to our bug signature**:

| Bug-signature line | Matching CHANGELOG fix | PR refs |
|---|---|---|
| `classification=stalled_agent_run` + `activeWorkKind=embedded_run` (no `embedded_run:ended` fires) | "**Anthropic extended-thinking sessions recover after prompt-cache expiry or Gateway restart because stream start events wait for `message_start`, letting pre-generation signature errors trigger the existing recovery retry.**" + "defer Anthropic stream start events until `message_start`, strip stale compaction thinking signatures before Anthropic replay, detect unsigned thinking-only stalls, refresh prompt fences after compaction writes, **reject empty completion handoffs**" | #90667, #90697, #90163, #90108, #89874, #89505 |
| `recovery=abort_embedded_run` after 350s+ stall | "isolated agent turn payload messages **preserve timeout context**" | #90208 |
| `[ws] ⇄ res ✗ sessions.resolve INVALID_REQUEST errorMessage=No session found: current` | Indirect — addressed by upstream "Anthropic stream start events wait for `message_start`" fix; the `current` lookup fails because the session is stuck in `processing` (per `research.md` §3.5), not because the resolver itself is broken | (cascade fix) |
| `sessionKey=agent:main:whatsapp:direct:+16179300916` (DM session never promoted to `current` after restart) | "**WhatsApp: captured replies after restart now route through the successor controller instead of the stale pre-restart controller.**" | #85823 |
| Recurrence across 4+ gateway restarts (per `research.md` §3.2 — "post-restart 16:44→16:54 UTC, identical pattern") | Same #85823 fix — the stale-controller class is *exactly* the persistence-across-restart signature | #85823 |
| Bounded startup waits | "WhatsApp startup waits are bounded" | #90072, #87951 |

This is a **strong, multi-evidence mapping** — three independent fixes in the 2026.5.28 → 2026.6.5 delta address the bug-signature lines from `research.md` §3.2:

1. **#85823 (WhatsApp restart-stale-controller)** — explains the per-restart persistence
2. **#90667 / #90697 (Anthropic stream-start `message_start`)** — explains why `markDiagnosticEmbeddedRunEnded` never fires (the stream never reaches the `message_start` boundary, so the `clearActiveEmbeddedRun` callback at runs-DMxJUP3Q.js#454 is not invoked — see `research.md` §3.4)
3. **#90208 (timeout context preserved)** — explains the 350s stall before `abort_embedded_run` recovery fires

### 3.4 H6 validation verdict

**H6: VALIDATED by desk review.** The mapping is concrete and unambiguous. The Codex evidence summary cited in `research.md` §9 is corroborated by the CHANGELOG text and the upstream PR references.

---

## 4. T002 — H5 plugin install state probe (verdict: refuted)

### 4.1 Plugin list

```
$ ssh office2-claude 'openclaw plugins list'
Plugins (65/93 enabled)
[…]
│ WhatsApp │ whatsapp │ openclaw │ enabled │ global:whatsapp/dist/index.js │ 2026.5.28 │
```

WhatsApp plugin is `enabled`, sourced from `global:whatsapp/dist/index.js`, version `2026.5.28`.

### 4.2 Plugin install location

```
$ ssh office2-claude 'ls -la /home/claude/.openclaw/extensions/whatsapp/ && cat /home/claude/.openclaw/extensions/whatsapp/package.json'
total 76
drwxr-xr-x  4 claude claude  4096 Jun  2 18:17 .
drwxr-xr-x  3 claude claude  4096 Jun  2 18:17 ..
drwxr-xr-x  2 claude claude  4096 Jun  2 18:17 dist
drwxr-xr-x 72 claude claude  4096 Jun  2 18:17 node_modules
-rw-r--r--  1 claude claude 31440 Jun  2 18:17 npm-shrinkwrap.json
-rw-r--r--  1 claude claude 22773 Jun  2 18:17 openclaw.plugin.json
-rw-------  1 claude claude  1899 Jun  2 18:17 package.json

{
  "name": "@openclaw/whatsapp",
  "version": "2026.5.28",
  "description": "OpenClaw WhatsApp channel plugin for WhatsApp Web chats.",
  […]
  "peerDependencies": { "openclaw": ">=2026.5.28" }
}
```

Plugin is **installed, on-version, and enabled** at the canonical global plugin path. Install date is `2026-06-02 18:17` — matches the `openclaw.json#meta.lastTouchedAt` from §1.1 of research.md.

### 4.3 H5 verdict

**H5: REFUTED.** Plugin install state is healthy. There is no missing or stale plugin to reinstall. The plugin peer-deps openclaw `>=2026.5.28`, so a 2026.6.5 runtime upgrade will be compatible (per `reference_openclaw_upgrade_gotchas` — after upgrade, verify the plugin still loads cleanly via `openclaw plugins list`).

---

## 5. T004 — H2 missing-field discovery (verdict: refuted)

### 5.1 Deployed channel + session config

```
$ ssh office2-claude 'jq ".channels.whatsapp, .session" /home/claude/.openclaw/openclaw.json'
{
  "enabled": true,
  "dmPolicy": "allowlist",
  "selfChatMode": false,
  "allowFrom": ["+16179300916"],
  "groupPolicy": "allowlist",
  "debounceMs": 0,
  "mediaMaxMb": 50,
  "groupAllowFrom": ["+16179300916"]
}
{
  "dmScope": "per-channel-peer"
}
```

### 5.2 Cross-reference against openclaw docs

From `/usr/lib/node_modules/openclaw/docs/channels/whatsapp.md` and `/usr/lib/node_modules/openclaw/docs/gateway/configuration.md`:

| Documented field | Our value | Docs status |
|---|---|---|
| `channels.whatsapp.dmPolicy` (`pairing` \| `allowlist` \| `open` \| `disabled`) | `"allowlist"` | matches doc example exactly |
| `channels.whatsapp.allowFrom` | `["+16179300916"]` | matches recommended `allowFrom` pattern |
| `channels.whatsapp.groupPolicy` / `groupAllowFrom` | `"allowlist"` / `["+16179300916"]` | matches recommended pattern |
| `session.dmScope` (`main` \| `per-peer` \| `per-channel-peer` \| `per-account-channel-peer`) | `"per-channel-peer"` | documented as **"recommended for multi-user"** at `configuration.md:295` |

The deployed config matches the documented "recommended" shape exactly. There is no `channels.whatsapp.reply`, `channels.whatsapp.delivery`, or `agents.<id>.reply` field documented as required for DM-reply dispatch. The DM-reply path is purely runtime behavior; the existing config gates *admission* (which already permits `+16179300916`).

### 5.3 H2 verdict

**H2: REFUTED.** No missing config field is documented as required for DM-reply dispatch on `dmPolicy=allowlist` + `dmScope=per-channel-peer`. The deployed config matches the docs.

---

## 6. T003 — H4 config-swap probe (skipped per orchestrator)

**Status: skipped per orchestrator — H6 desk verdict was clear.**

Read-only review of `dmPolicy`/`dmScope` semantics was already covered in §5 (they match the docs). The active config-swap probe (which would modify openclaw.json on office2 and require a gateway restart) was skipped because:

1. The orchestrator explicitly instructed: "if your H6 desk review (T001) confirms the Codex mapping is strong, conclude WP01 with `Fix shape: H6` and SKIP the destructive probes (T003 active config swap, T005 H3 AGENTS.md rollback)."
2. H6 desk verdict per §3 is unambiguously validated.
3. The risk table in the WP01 task file flags "H4 active probe leaves openclaw.json in non-canonical state if rollback skipped" — skipping eliminates that risk surface.

**H4: not-tested-actively — desk review of deployed config matches docs (§5); active probe deferred per orchestrator constraint.**

---

## 7. T005 — H3 AGENTS.md rollback probe (skipped per orchestrator)

**Status: skipped per orchestrator — H6 desk verdict was clear.**

The destructive probe (replacing `/data/services/openclaw/data/AGENTS.md` with the pre-#579 version, restarting the gateway, sending a test DM, then rolling back) was skipped because:

1. The orchestrator explicitly instructed: "if your H6 desk review (T001) confirms the Codex mapping is strong, SKIP the destructive probes (T005 H3 AGENTS.md rollback)."
2. Per the WP01 task file: "Step 7 rollback is MANDATORY even if H3 validated — the pre-#579 file is over the 12K cap and re-triggers #579 truncation." Skipping the probe eliminates both the rollback risk and the brief window during which #579's truncation would re-occur on the gateway.
3. `research.md` §2 already documents the prior reasoning: "37b3bf56 (#579) is a contributing factor but unlikely to be the root cause given the 2026-06-09 evidence point." The DM-reply break pre-dated #579 by 2 days.
4. The 2026.6.5 CHANGELOG fixes (especially #85823 WhatsApp restart-stale-controller) address the structural cause; even if the pre-#579 AGENTS.md happened to mask the symptom, the underlying runtime bug would remain.

**H3: not-tested-actively — desk-review reasoning in `research.md` §2 + the H6 mapping in §3 above supersede the need for the active probe.**

---

## 8. Upgrade plan (carry-forward to WP02)

This is the upgrade plan WP02 will execute. WP01 produced it but does NOT execute it (C-001 + per-WP scope).

### 8.1 Pre-flight (Tier 2 per C-003)

- Confirm a Restic backup ≤24h exists. If not, trigger one before the upgrade.
- Capture pre-upgrade baselines:
  ```bash
  ssh office2-claude 'openclaw doctor --json > /tmp/openclaw-doctor-pre-upgrade.json'
  ssh office2-claude 'cp /home/claude/.openclaw/openclaw.json /tmp/openclaw.pre-upgrade.$(date +%s).json'
  ssh office2-claude 'cp /data/services/openclaw/data/AGENTS.md /tmp/main-AGENTS.pre-upgrade.$(date +%s).md'
  ```
- Capture pre-upgrade plugins list snapshot for post-flight comparison (especially `@openclaw/whatsapp` version).
- Capture systemd unit metadata: `ssh office2-claude 'systemctl --user show openclaw-gateway.service > /tmp/gateway-unit-pre.txt'`

### 8.2 Upgrade command

```bash
# NOTE: requires sudo; surface to Kent for manual execution via `ssh office2-kgale`
#       (the claude user has no sudo).
ssh office2-kgale 'sudo npm install -g openclaw@2026.6.5'
```

Alternative if WP02 chooses to keep using `npm` global: same command, same sudo requirement. (Confirmed `which openclaw` → `/usr/lib/node_modules/openclaw/openclaw.mjs` in §3.1 — install path is npm-global, not pipx.)

### 8.3 Post-upgrade verification

```bash
# 1. Confirm runtime version
ssh office2-claude 'openclaw --version'                     # expect "OpenClaw 2026.6.5"

# 2. Confirm doctor clean
ssh office2-claude 'openclaw doctor --json'                 # diff against baseline

# 3. Confirm models config still present (per memory `reference_openclaw_upgrade_gotchas`)
ssh office2-claude 'jq ".models.providers" /home/claude/.openclaw/openclaw.json'

# 4. Confirm @openclaw/whatsapp plugin still enabled and current
ssh office2-claude 'openclaw plugins list 2>&1 | grep -i whatsapp'
#    expect 2026.6.5 (auto-upgraded with runtime) — verify; per `reference_openclaw_upgrade_gotchas`
#    plugins should update under runtime upgrade but verify explicitly

# 5. Restart gateway
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
sleep 5
ssh office2-claude 'systemctl --user status openclaw-gateway.service | head -10'

# 6. Post-flight smoke (operator-in-the-loop per Decision D5):
#    - Send 1 test DM to +16179300916
#    - Check journal for [whatsapp] Inbound message → embedded_run:started → embedded_run:ended → [whatsapp] Sending message → [whatsapp] Sent message within ~30 seconds
ssh office2-claude "journalctl --user -u openclaw-gateway --since '5 minutes ago' 2>&1 | grep -E '(Inbound|embedded_run|Sending|Sent|stuck|stalled)'"

# 7. Rebaseline reset (per #557 + memory `architecture-docs first`)
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

### 8.4 Rollback shape (if upgrade fails post-flight)

```bash
# 1. Re-install previous version (also requires sudo)
ssh office2-kgale 'sudo npm install -g openclaw@2026.5.28'

# 2. Restore openclaw.json if it was modified by the upgrade
ssh office2-claude 'cp /tmp/openclaw.pre-upgrade.<ts>.json /home/claude/.openclaw/openclaw.json'

# 3. Restart gateway
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
```

### 8.5 Risk classification

| Item | Risk | Mitigation |
|---|---|---|
| Upgrade itself | Tier 2 (Application/State) per C-003 | Restic ≤24h pre-flight (above); rollback shape documented |
| sudo requirement | Tier 0 boundary surfaces | Surface command to Kent for `ssh office2-kgale` manual run; WP02 must NOT attempt sudo as the claude user |
| WhatsApp pairing loss | Low (npm package replacement preserves `~/.openclaw/`) | If pairing is lost, re-pair via QR per the standard onboarding flow |
| Plugin compatibility | Low (peer-deps are `>=2026.5.28`) | §8.3 step 4 verifies plugin loads; if it doesn't auto-upgrade, re-install with the runtime |
| Audited-surface rebaseline | Required (openclaw runtime is audited per `audited-surfaces.json`) | §8.3 step 7 covers the rebaseline; merge commit must include `Rebaseline: completed at <ts>` trailer |
| Config drift from 2026.6.5 upgrade adding a now-required field | Low (no new required fields named in 2026.6.5 CHANGELOG; existing config matches docs per §5) | §8.3 step 2 (`openclaw doctor --json`) surfaces any new required-field gaps |

---

## 9. Doctrine compliance

| Directive / constraint | How WP01 satisfied it |
|---|---|
| **C-001** (No vendored openclaw runtime modifications) | Vendored runtime read-only via SSH; only the upstream tarball CHANGELOG was inspected via `npm pack` to a temp dir. No vendored files modified. |
| **C-003** (Tier 2 application/state changes) | Upgrade plan §8.1 explicitly calls out Restic ≤24h pre-flight. |
| **DIRECTIVE_001** (Self-documenting) | This report and the research.md append block both link to the WP01 task file and to `research.md` §9 as authoritative input. |
| **DIRECTIVE_010** (Spec fidelity) | The verdict maps to FR-004 (proximate cause is the `current` session lookup failing because the session is stuck — root-caused via #85823 + #90667/#90697) and FR-009 (vendored regression escalation path remains available but is not triggered because 2026.6.5 supersedes). |
| **DIRECTIVE_033** (Commit discipline) | The commit for WP01 stages exactly two files: this investigation report and the research.md append. NEVER `git add .` or `git add -A`. |
| **DIR-008** (Read real service paths) | All probes used `/home/claude/.openclaw/openclaw.json` and `/usr/lib/node_modules/openclaw/` — canonical deployed paths, not repo templates. |
| **DIR-015** (Probe real environment) | Live SSH probes for version, published versions, deployed config, plugin list, plugin install state, and CHANGELOG contents are captured verbatim above. |
| **Operator constraint** ("skip destructive probes if H6 desk verdict is clear") | T003 and T005 explicitly skipped per §6 + §7; H6 desk verdict per §3 was unambiguous. |
| **Office2 state invariant** ("WP01 leaves office2 unchanged") | No openclaw.json edits; no AGENTS.md edits; no gateway restart; no runtime upgrade; only read-only commands + one temp tarball extraction at `/tmp/openclaw-2026.6.5/` (not a service path). |

---

## 10. Decision Record

**Fix shape**: H6 — upgrade openclaw 2026.6.5 (release-notes mapping below)

Concrete evidence:
- **#85823 (WhatsApp)**: "captured replies after restart now route through the successor controller instead of the stale pre-restart controller" — matches the per-gateway-restart persistence of our `sessionKey=agent:main:whatsapp:direct:+16179300916` stall (research.md §3.2).
- **#90667, #90697 (Anthropic stream-start)**: stream start events wait for `message_start`, with stale-compaction stripping and "reject empty completion handoffs" — matches our observation (research.md §3.4) that `markDiagnosticEmbeddedRunEnded` at `runs-DMxJUP3Q.js#454` (called from `clearActiveEmbeddedRun`) is never invoked for DM sessions.
- **#90208 (timeout context preserved)**: explains the 350s stall + `recovery=abort_embedded_run` rather than earlier signaled failure.

Upgrade plan: see §8. Pre-flight Restic ≤24h, baseline capture, sudo-required `npm install -g openclaw@2026.6.5` (surfaced to Kent), post-flight verification (version, doctor, plugin, gateway, smoke DM, rebaseline reset), rollback shape documented.

WP02 owns execution. WP01 outputs the verdict + plan only.

---

## 11. Artifacts and references

- Authoritative input: `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md` §9 (H6 update at tasks phase)
- Bug-signature source: `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/research.md` §3 (live probe) + §3.4 (source dive of vendored runtime)
- WP01 task file: `kitty-specs/restore-whatsapp-dm-reply-delivery-01KTVVHH/tasks/WP01-diagnostic-investigation.md`
- 2026.6.5 CHANGELOG (read-only, fetched to `/tmp/openclaw-2026.6.5/package/CHANGELOG.md` on office2 via `npm pack`)
- Prior-incident checklist for openclaw upgrades: memory `reference_openclaw_upgrade_gotchas`
- Related local issue: [#588](https://github.com/kentonium3/kg-automation/issues/588)
- Related upstream PR refs: openclaw/openclaw#85823, #90667, #90697, #90208, #90163, #90108, #89874, #89505, #87951, #90072
- Companion audit-trail line: `research.md` § "Discovery Findings (WP01 — 2026-06-11T<ts>)" appended in this same commit
