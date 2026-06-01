---
tags: [362, 391, 400, 343/, 137, 343, 276]
---

# Dry-run: doc updates to reflect doc-audit suspension

**Date**: 2026-05-31
**Role**: Agent simulating the doc-audit system's intended workflow
**Scope**: Reflect that the doc-audit architecture is *designed, implemented, AND suspended indefinitely as of 2026-05-26*
**Output**: No doc edits. This report only.

---

## Directive used

CLAUDE.md says: *"**Documentation map**: `docs/INDEX.md` — master index of all active documentation, grouped by directory with Divio type annotations. **Start here to discover docs by topic or type.**"* That is the soft directive I followed. (DEVELOPER_PORTAL.md is positioned as the orientation entry; INDEX.md is the discovery entry. For a topic-driven audit, INDEX.md is correct.)

## Meta-observation

The doc-audit system has its **own routing table** at `docs/design/architecture/data/doc-domain-map.json`. A real run of the doc-audit would consume that map to find affected docs from a triggering signal (e.g., commit SHA), not INDEX.md. Using INDEX.md from a human-navigation entry point produces a different — and probably more comprehensive — candidate list than the audit's own map would, because INDEX.md scopes by topic groupings while the domain map scopes by `area/*` label routing. **Gap worth flagging upstream**: a doc-audit run triggered by the suspension commits (`d46a9ead`, `2c399140`) probably wouldn't have reached the constitution, capability roadmap, or LLM spend baseline — those are downstream of the architecture data files the map covers.

---

## Navigation path from INDEX.md

I identified 6 INDEX.md sections plausibly relevant to the doc-audit, then grepped the section's targets for `doc[-_]audit|doc-auditor|drift_interpretation|audit_interpretation|felix-doc-auditor`. Sections traversed:

1. **Constitution & Governance** → `FELIX-CONSTITUTION.md`, `AGENT-REGISTRY.md`, `agent-registry.json`
2. **System Architecture** → `service-inventory.md` + JSON, `data-flows.md` + JSON, `doc-domain-map.json`, `signal-to-doc-map.json`, `mutation-surfaces.json`, `credentials-and-secrets.md`, `credential-manifest.json`, `identity-model.md`, `service-dependencies.view.md`, `architecture/README.md`, `architecture/contracts/drift-ledger-schema.md`, `LLM Spend Baseline` (narrative + JSON)
3. **Baselines** → `baselines/README.md`, `baselines/cutover-log.md`, `baselines/felix-doc-auditor-{pre,post}-rework.json`, `felix-d6-survey.md`
4. **Operational Runbooks** → `doc-auditor-driver-ops.md` (primary), `doc-auditor-ops.md` (legacy/HISTORICAL), `security-baseline-ops.md`, `tasker-ops.md`, `habits-ops.md`, `github-issues-workflow.md`
5. **Design & Standards** → `felix-capability-roadmap.md`, `helper-script-conventions.md`
6. **Onboarding & Navigation** → `DEVELOPER_PORTAL.md`, `INDEX.md` itself

---

## Affected docs and proposed edits

Grouped by edit class. The fact to surface in each: **doc-audit is implemented (post-#343 scripts-first driver, with #362 + #391 + #400 extensions) but suspended indefinitely since 2026-05-26 pending cost-control resolution (#137 family). Suspension is double-layered: systemd timer disabled (office2) AND `[drift_interpretation].enabled = false` + `[audit_interpretation].enabled = false` (since commit `d46a9ead`). GitHub Actions workflows `Doc Audit Trigger` and `Doc Audit Weekly` are also `disabled_manually`.**

### A. Capability status correction (highest priority)

**`docs/design/felix-capability-roadmap.md`** — line 210

Current: `| Doc-auditor agent | 🔄 In progress | #105 | ... |`

Edit: change status to `⏸ Implemented + suspended` (or similar; pick a new emoji per existing legend). Append to the description: *"Implementation complete through #343/#362/#391/#400. Suspended indefinitely 2026-05-26 after the May 2026 API cap exhaustion (see #137 cost-control epic). Unblock signal: cost-control work landing + an explicit re-enable decision."*

### B. Operational runbook frontmatter + status banner

**`docs/runbooks/doc-auditor-driver-ops.md`**

Current frontmatter: `status: draft`, `last_validated: 2026-05-23`. Current top-of-file "Status note" claims the cutover hasn't been executed yet.

Edits:
- Frontmatter: `status: approved`, `last_validated: 2026-05-31`, append `last_updated: '2026-05-31'`, `updated_by: '#400 (initial); suspension reflected 2026-05-31'`.
- Replace the existing "Status note" callout with a **suspension banner** at the very top (above Overview), modeled after the historical banner pattern in `doc-auditor-ops.md`:

  > ⏸ **SUSPENDED INDEFINITELY — 2026-05-26**. The post-#343 driver is implemented and tested. Two-layer suspension is in place: `felix-doc-auditor.timer` is `disabled`, AND `[drift_interpretation].enabled = false` + `[audit_interpretation].enabled = false` in `scripts/doc_audit/config.toml` (commit `d46a9ead`). The cutover playbook has executed; the production service IS the post-#343 driver, just not currently scheduled. Re-enablement requires the cost-control work tracked under #137 to land plus an explicit operator decision.

- Update the body's existing "until that playbook is executed on office2" sentence — the playbook HAS been executed.

### C. Service inventory — narrative + JSON pair

**`docs/design/architecture/service-inventory.md`** + **`docs/design/architecture/data/service-inventory.json`**

Affected entries (narrative):
- Line 39 "Doc Audit Poll | Every 60 minutes" — **factually false**; the timer is disabled. Either move to a "Currently suspended" subsection or annotate inline as `(SUSPENDED 2026-05-26 — see felix-doc-auditor entry)`.
- Lines 358-381 "Felix Doc Auditor (#105…)" — comprehensive but presents the system as operationally active. Add a status field near the top of the entry:

  > **Operational status**: ⏸ **Suspended indefinitely 2026-05-26** (timer `disabled` + interpretation flags `false`; reactivation gated on #137 cost-control epic).

JSON edits: in `service-inventory.json`, the `habits-weekly-report` / `habit-checkin` cron entries are OpenClaw-cron and unaffected. Find the `felix-doc-auditor` service entry and the `Doc Audit Poll` (or equivalent) schedule entry. Set:
- `status` field on the service: change `"active"` → `"suspended"` (or add `"operational_status": "suspended"` alongside `"deploy_status": "deployed"` if the schema supports it)
- Schedule entry: same suspension marker
- Add a `suspension_metadata` block: `{ since: "2026-05-26", reason: "API cap exhaustion (May 2026)", unblock_signal: "#137 cost-control epic", layers: ["systemd timer disabled", "config flags enabled=false"] }`

### D. Data flows — narrative + JSON pair

**`docs/design/architecture/data-flows.md`** + **`docs/design/architecture/data/data-flows.json`**

The "Doc-Auditor Direct Anthropic API" flow (line 125) and the "Doc-Auditor Tick Signal Write" flow (line 148) are the affected sections. The flows remain *architecturally valid* — they describe how the system runs WHEN running — so the edit is annotative rather than structural:

- Add a paragraph at the top of the "Doc-Auditor Direct Anthropic API" section noting current operational status (suspended); reference the runbook banner so a reader hitting this flow doesn't have to chase three docs.
- In the JSON, mark the affected flow entries with `operational_status: "suspended"` matching the service-inventory pattern.

### E. Agent registry — narrative + JSON pair

**`docs/constitution/AGENT-REGISTRY.md`** + **`docs/constitution/agent-registry.json`**

The `felix-doc-auditor` entry in the JSON has `autonomy_level: "assisted"` and `model: "anthropic/claude-sonnet-4-6"`. The runbook says haiku-4-5 (downshifted by #343). **This is a drift, separate from the suspension**, but in scope for this audit since I touched the registry: reconcile the model value. Then add an `operational_status: "suspended"` or `"deployment_status": "deployed_but_suspended"` field.

Narrative AGENT-REGISTRY.md likely has a parallel paragraph; mirror the change.

### F. LLM spend baseline — narrative + JSON

**`docs/design/architecture/llm-spend-baseline.md`** + **`docs/design/architecture/data/llm-spend-baseline.json`**

`llm-spend-baseline.json` last updated 2026-05-15 by #276. The notes for the Anthropic API line reference the *first* credit exhaustion (pre-2026-04-09) but predate the May 2026 cap exhaustion that drove the doc-audit suspension. Update:
- `last_updated`: 2026-05-31
- `updated_by`: "doc-audit suspension reconciliation"
- Anthropic API entry notes: append *"Second credit exhaustion 2026-05-26 (after raising cap from $250 → $500). Doc-auditor identified as primary cost driver; suspended indefinitely while #137 cost-control work designs an attribution model. Spend will drop substantially in June 2026 as a result of suspension."*
- Mention that the $30.11/day extrapolation is now stale.

### G. INDEX.md itself

Line 99: `Doc Auditor Driver Operations` description includes "hourly systemd tick". Either:
- Add a parenthetical `(currently suspended; see runbook banner)`, or
- Leave alone since the description is a "what it does when active" and the runbook banner carries operational state.

I'd choose the parenthetical. INDEX.md is the discovery entry — readers landing here should learn the operational reality before clicking through. Same logic for `LLM Spend Baseline` line 59 description.

### H. Baselines

**`docs/design/architecture/baselines/README.md`** + the two `felix-doc-auditor-{pre,post}-rework.json` files

The pre/post baselines are valid historical measurements unaffected by suspension. Single edit in `baselines/README.md`: in the table describing the felix-doc-auditor row, add a note that the post-rework baseline reflects measured-while-active state and the system has been suspended since 2026-05-26.

### I. Files with passing/cross-reference mentions (no edit needed)

Each of these mentions doc-audit only as a passing reference (a label suffix, a pattern reference, a flow neighbor). The fact of suspension doesn't change the truth of the mention. No edits proposed:

- `docs/DEVELOPER_PORTAL.md` (mentions `[doc-audit]` commit suffix — still a valid pattern even with audit suspended)
- `docs/runbooks/habits-ops.md`, `tasker-ops.md`, `security-baseline-ops.md`, `github-issues-workflow.md` (cross-references and label semantics, not operational claims)
- `docs/design/architecture/credentials-and-secrets.md`, `credential-manifest.json` (the Anthropic key still exists at the documented path)
- `docs/design/architecture/identity-model.md` (kg-felix-bot identity unaffected)
- `docs/design/architecture/contracts/drift-ledger-schema.md` (schema unchanged)
- `docs/design/architecture/data/mutation-surfaces.json` (the surface still exists; just isn't being exercised)
- `docs/design/architecture/data/signal-to-doc-map.json` (mapping unchanged)
- `docs/design/architecture/data/doc-domain-map.json` (the audit's routing table; unchanged)
- `docs/design/architecture/felix-d6-survey.md`, `helper-script-conventions.md` (descriptive references)
- `docs/runbooks/doc-auditor-ops.md` (already marked HISTORICAL with a banner from #391)

---

## Summary of proposed edits

| Class | Files | Action |
|---|---|---|
| A. Capability status | 1 | Roadmap row: "In progress" → "Implemented + suspended" with date + unblock signal |
| B. Runbook banner | 1 | Add prominent suspension banner; update frontmatter |
| C. Service inventory | 2 (md + json) | Mark service & schedule as suspended; add suspension_metadata |
| D. Data flows | 2 (md + json) | Annotative status note on affected flow sections |
| E. Agent registry | 2 (md + json) | Add operational status; reconcile model drift (haiku vs sonnet) |
| F. LLM spend baseline | 2 (md + json) | Update notes to reflect May 2026 cap event + impending spend drop |
| G. INDEX.md | 1 | Parenthetical on the two affected entries |
| H. Baselines README | 1 | Add operational status note next to the felix-doc-auditor row |
| **TOTAL** | **12 file edits** | (no architectural deletions — the system is preserved, only the operational state changes) |

---

## Editorial decisions and reasoning

1. **Preserve architecture; annotate operational state**. The audit's design and implementation are not retracted — only its current operational status. So the bulk of the edits are *additions of status fields and banners*, not deletions or rewrites.
2. **Use a consistent suspension banner pattern across runbooks** (mirroring the existing HISTORICAL banner pattern in `doc-auditor-ops.md`). A new emoji or marker — `⏸ SUSPENDED INDEFINITELY` — gives readers an immediate visual signal distinct from `⚠ HISTORICAL`.
3. **Always mention the unblock signal**. Future-me (and any other operator) needs to find #137 to know when re-enabling is on the table. Every suspension mention should link to the unblock signal.
4. **Treat JSON as authoritative**. Per CLAUDE.md: "machine-readable files (JSON) are the authoritative record." So narrative md changes follow JSON changes, not the other way around. For each pair, I'd edit the JSON first, validate the schema, then write the narrative.
5. **Reconcile the model-drift in AGENT-REGISTRY as a side effect**. It's not strictly in scope for the suspension audit, but it's an out-of-band correctness gap discovered by the same navigation. Better to fix in-flight than leave for a separate ticket.
6. **Do not edit doc-domain-map.json itself**. The audit's routing table doesn't need to know the audit is off; the suspension is enforced upstream (cron + config flags).

---

## Gaps surfaced by this dry-run

1. **No suspension-marker convention exists**. Every doc that needs to declare "this thing is built but currently off" reinvents it. Worth standardizing — either in `doc-standards.md` or as a small Divio-companion convention. Suggested marker: `⏸ Suspended` + `since: <date>` + `unblock_signal: <ref>` triplet in frontmatter, plus a top-of-doc banner template.
2. **The doc-audit's own routing table (`doc-domain-map.json`) likely does not route a commit touching `scripts/doc_audit/config.toml` to the capability roadmap or the LLM spend baseline.** Confirm and patch as part of the eventual #137 work (or sooner if Felix re-enables before #137 lands).
3. **`agent-registry.json` and the runbook disagree about the doc-auditor's model** (sonnet-4-6 vs haiku-4-5). Either is wrong, or both moved at different times. A small reconciliation issue worth filing independently.
4. **No machine-readable manifest of "what is currently suspended"**. If suspensions become a recurring pattern, a `docs/design/architecture/data/suspended-services.json` (or a status field consistently applied across `service-inventory.json` and `agent-registry.json`) would make this kind of audit much cheaper. Currently the suspension state has to be re-derived per audit by reading the runbook banners.

---

## What I did NOT do

- No file edits anywhere outside this report.
- No git operations beyond what's already committed earlier this session.
- No invocation of spec-kitty workflow.
- No remembering anything about "manually update X" as a future agent action — the dry-run is a one-off rehearsal, not a behavior to internalize.
