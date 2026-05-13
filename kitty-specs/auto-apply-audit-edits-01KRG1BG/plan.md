# Implementation Plan: Auto-apply audit edits; gate reserved for future judgment classes

**Branch**: `main` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/auto-apply-audit-edits-01KRG1BG/spec.md`
**Source issue**: [#259](https://github.com/kentonium3/kg-automation/issues/259)

## Summary

Add `scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py` — a single orchestrator that consumes serialized audit state from the agent and does all of partitioning, committing the auto-apply set, filing a pending-approval issue for any gated subset, and posting the audit summary on the originating audit issue. The auditor's AGENTS.md § 7.9 / § 7.10 / § 7.11 collapse to a single CLI invocation. The known-change_type allowlist lives inside the script (C-001). AGENTS.md and AGENTS.md.tmpl get matching prose edits.

Same architectural pattern as the #253 inbox-pipeline mission: deterministic work moves out of the LLM prompt into a script that the agent invokes with serialized state. Inference cost on routine audits drops because the agent no longer reasons through branching logic on every cron tick.

## Technical Context

**Language/Version**: Python 3.10+ (office2 ships 3.12). Standard library + existing agent fixtures. No new pip dependencies.
**Primary Dependencies**: stdlib only. `subprocess` for `git commit` and `gh issue create` (matches the codebase's CLI-as-stable-contract pattern). `json` for serialization.
**Storage**: Reads audit state from `@<path>` JSON tempfile written by the agent. Writes file edits to docs (atomic via `tempfile.mkstemp + os.replace`, preserving original mode per the pattern landed by #254).
**Testing**: `pytest` with `tmp_path` fixtures and `monkeypatch` to stub `subprocess.run` for git/gh calls. New test file `tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py`. Drive the handler via `subprocess.run` for CLI coverage.
**Target Platform**: office2 (Ubuntu 24.04 LTS), Python 3.12. Invoked by felix-doc-auditor agent during its hourly systemd-user timer ticks.
**Project Type**: Single project — Python script under `scripts/openclaw/agents/felix-doc-auditor/`, tests under matching `tests/` path.
**Performance Goals**: NFR-001 — partition + dispatch complete within 100 ms for ≤ 10 proposals (excludes external `git`/`gh` latency).
**Constraints**: NFR-002 stdlib only. NFR-003 ≥ 50% token-budget reduction on a `frontmatter_date`-only audit. C-001 allowlist in script. C-002 AGENTS.md+.tmpl in sync. C-005 no autonomy promotion. C-006 existing pending-approvals preserved as test cases.
**Scale/Scope**: 1 new script (~200–280 lines), 1 new test file, AGENTS.md + AGENTS.md.tmpl edits (collapse 3 prose sections to 1 invocation).

## Charter Check

Charter loaded compact. Same posture as the prior felix-doc-auditor work. Tier 3 (Standard) per `change-risk-taxonomy.json` — Python script logic + agent-prompt edits, no service/credential/topology impact. No pre-flight checklist required.

**Gate**: PASS.

## Project Structure

### Documentation (this feature)

```
kitty-specs/auto-apply-audit-edits-01KRG1BG/
├── plan.md
├── research.md
├── quickstart.md
├── spec.md
├── meta.json
├── checklists/
│   └── requirements.md
└── tasks/                  # populated by /spec-kitty.tasks
```

`data-model.md` and `contracts/` are intentionally omitted — no new data model surface (consume existing E-004 shape) and no API contract.

### Source Code (repository root)

```
scripts/openclaw/agents/felix-doc-auditor/
├── handle_audit_routing.py         # NEW: orchestrator
├── AGENTS.md                       # MODIFY: § 7.5 invariant; § 7.9/§ 7.10/§ 7.11 collapse
├── AGENTS.md.tmpl                  # MODIFY: identical edits
├── IDENTITY.md                     # unchanged
├── SOUL.md                         # unchanged
├── TOOLS.md                        # unchanged
└── USER.md                         # unchanged

tests/openclaw/agents/felix-doc-auditor/
└── test_handle_audit_routing.py    # NEW: 6+ cases
```

Deploy script: reuse the existing felix-doc-auditor deploy pipeline (per `reference_felix_doc_auditor_ops.md` — systemd-user timer on office2 picks up updated scripts and AGENTS.md from the repo on each tick).

**Structure Decision**: helper lives next to the agent it serves (C-004), matching the pattern where inbox helpers live in `scripts/inbox/` (the agent that uses them lives in `scripts/openclaw/agents/felix-admin-capture/`). The doc-auditor scripts cluster is the right home because they're not reusable elsewhere.

## Complexity Tracking

*No Charter Check violations. Section intentionally empty.*

## Phase 0: Research / Alignment

See [research.md](research.md). Five decisions logged:

1. **Allowlist location**: hardcoded constant in `handle_audit_routing.py`. Not a separate config file (C-001 + no operational reason to update without code review).
2. **External-command style**: subprocess for `git commit` and `gh issue create` (matches existing codebase pattern; trying to import a Python `git`/`gh` library would add a dependency for negligible benefit).
3. **Atomic file writes for edit-application**: reuse the `tempfile.mkstemp + os.replace` pattern with mode preservation, identical to the fix that landed in #254. Prevents the perm-orphan bug from reappearing in a new edit-application surface.
4. **Section scope in AGENTS.md**: § 7.9, § 7.10, § 7.11 collapse to a single instruction in the forward path. § 3 (decision-handling for existing pending-approvals) is OUT OF SCOPE for this mission — it keeps its current prose-driven shape, since (a) gated audits are now rare post-mission and (b) collapsing § 3 too would broaden mission scope without a clear ROI.
5. **Test surface**: drive the handler via `subprocess.run` from tests (full CLI coverage) and use `monkeypatch` to stub `subprocess.run` for the *handler's own* `git`/`gh` invocations. This isolates the partition-and-dispatch logic from external state during test runs.

## Phase 1: Design

### `handle_audit_routing.py` interface

```bash
python3 handle_audit_routing.py @/path/to/audit-state.json
```

Where `audit-state.json` has the shape:

```json
{
  "audit_issue_number": 258,
  "commit_sha": "7471fe7",
  "areas": ["area/biz-ops", "area/felix-core"],
  "proposals": [
    {
      "doc_path": "docs/INDEX.md",
      "change_type": "frontmatter_date",
      "current_value": "2026-05-10",
      "proposed_value": "2026-05-13",
      "evidence_source": "commit 7471fe7 (2026-05-13)",
      "confidence": "high"
    }
  ],
  "debt_issues_filed": [],
  "missing_artifact_issues_filed": []
}
```

### Behavior

1. Parse `@<path>` JSON. Validate required keys.
2. Partition `proposals` by `change_type` against the auto-apply allowlist constant:
   ```python
   AUTO_APPLY_CHANGE_TYPES = frozenset({
       "frontmatter_date",
       "version_bump",
       "path_rename",
       "dead_ref_removal",
       "registry_entry_add",
       "registry_autonomy_update",
   })
   ```
3. **For each `auto_apply` proposal**: apply the edit via atomic write (preserving mode per the #254 pattern). Stage the file.
4. **If any auto-apply edits were applied**: build a structured commit message (multi-line, references audit issue, summarizes the edits), run `git commit` via subprocess. On failure: rollback the staging, write structured stderr, exit non-zero.
5. **If `gated` is non-empty**: file an `audit-pending-approval` issue covering ONLY the gated edits, using the existing template at `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/audit-pending-approval-issue.template.md`. Get the new issue number from `gh` output.
6. **Post audit summary** on the originating audit issue (`audit_issue_number`): one comment listing applied edits, gated edits (with link to new pending-approval issue if filed), debt/missing-artifact issue numbers from steps 7.8 already-filed.
7. Exit 0 on full success; non-zero if any leg (apply, commit, file-gate, post-summary) failed, with stderr structured to identify which leg.

### AGENTS.md edits

**§ 7.5** (existing): add invariant statement at end of section:

> **Invariant on Edit Proposals**: Only emit an Edit Proposal when the correct value is deterministically known from a system-state source (commit history, filesystem, registry source, etc.). Cases requiring content judgment — prose drift, missing context, ambiguous remediation — go to § 7.8 as `docs-debt` issues instead. This invariant is the contract that authorizes § 7.9 to invoke the routing helper without a human gate for known change_types.

**§ 7.9** (existing — replace with):

```
### 7.9 Branch on remaining outcome

- **Empty audit** (zero edits, zero debt, zero missing): go to § 8.
- **Debt-only audit** (zero edits; debt and/or missing filed in § 7.8): go to § 8. **No human gate required.**
- **Edit-bearing audit** (one or more proposed edits): serialize the
  proposals + audit state to a tempfile (the shape documented in the
  handler's docstring) and invoke:

  ```bash
  python3 /home/claude/kg-automation/scripts/openclaw/agents/felix-doc-auditor/handle_audit_routing.py @<path>
  ```

  The helper does all partitioning, committing of the auto-apply set,
  filing the pending-approval issue for any gated subset, and posting
  the audit summary on the originating audit issue. It exits non-zero
  if any leg failed; treat that the same as a § 7.11 commit error
  (log to stderr and exit; the next cron tick will retry the audit).
```

**§ 7.10 and § 7.11**: replace bodies with a single one-line cross-reference: "See § 7.9. The routing helper handles this." Preserve section headers for backward-compat with any other docs that link to them.

**`AGENTS.md.tmpl`**: identical edits (C-002).

### Test plan (FR-006)

`tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py`:

| Case | Setup | Action | Assertion |
|---|---|---|---|
| `test_all_auto_apply_no_gate` | 1 frontmatter_date proposal, no gated | run handler | git commit invoked, no gh issue create for gate, summary comment posted, exit 0 |
| `test_all_gated` | 1 fabricated `prose_replacement` (not in allowlist) proposal | run handler | no git commit, gh issue create for gate, summary posted, exit 0 |
| `test_mixed_partition` | 1 frontmatter_date + 1 unknown | run handler | git commit for the known, gh issue create for the unknown, summary names both, exit 0 |
| `test_empty_proposals` | proposals: [] | run handler | no git/gh calls, summary posted (or none — confirm spec), exit 0 |
| `test_invalid_json` | malformed input file | run handler | exit non-zero with structured stderr; no git/gh calls |
| `test_commit_failure_propagates` | mock git commit → non-zero | run handler | exit non-zero; gh gate NOT filed (don't half-do) |
| `test_atomic_write_preserves_mode` | doc at mode 0o644; apply edit | run handler | post-write mode is 0o644 (regression guard against re-introducing #254) |

### Deploy plan

Reuse the existing felix-doc-auditor deploy mechanism. The handler script and updated AGENTS.md ride the same systemd-user timer pickup as today.

### End-to-end verification (SC-001 + SC-003)

Post-merge operator step:
1. Wait for the next natural cron tick (or trigger manually) after merge.
2. Confirm the next `audit-pending-approval` issue is NOT filed for any audit whose proposed edits are all known-change_type. The originating audit issue should show an audit-summary comment and be closed by the auditor's normal closure logic.
3. Apply `audit-approve` to #236 to drain it — the auditor's existing § 3 decision-handling commits the proposed edit and closes both issues.
4. Repeat (3) for #249 and #250.

## Charter Re-check (post-design)

No new gates raised. Plan remains within Tier 3 standard scope. **Gate**: PASS.

## Next Steps

Run `/spec-kitty.tasks` to materialize this plan into work packages.

**Branch contract reminder**: Current branch `main`. Planning/base branch `main`. Merge target `main`. `branch_matches_target=true`.
