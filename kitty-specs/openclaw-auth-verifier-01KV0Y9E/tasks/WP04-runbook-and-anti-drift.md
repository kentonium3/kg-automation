---
work_package_id: WP04
title: Runbook addenda + anti-drift test
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- FR-015
- FR-016
- FR-017
tracker_refs:
- kentonium3/kg-automation#597
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
agent: claude
history: []
agent_profile: implementer-ivan
authoritative_surface: docs/runbooks/
execution_mode: code_change
mission_slug: openclaw-auth-verifier-01KV0Y9E
owned_files:
- docs/runbooks/openclaw-ops.md
- docs/runbooks/credential-rotation-ops.md
- tests/security/test_runbook_anchors.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

Land the runbook addenda that make `anthropic-verify` discoverable as the canonical post-`doctor --fix` and post-rotation gate, and add a small test that asserts the runbook section anchors exist so future doc edits don't silently drop the discoverability. The merge commit must record the rebaseline status per `#557`.

## Context

The verifier's existence and usage need to be discoverable from two operator-facing runbooks:

- `docs/runbooks/openclaw-ops.md` — the canonical OpenClaw operations runbook. Already has a "Known upgrade gotchas" section (per `#591`). This WP extends that section with the shadow + drift failure modes and points at `anthropic-verify` as the gate to run post-`doctor --fix`.
- `docs/runbooks/credential-rotation-ops.md` — the canonical credential rotation runbook. Already has an `anthropic` section (per `#591`). This WP extends it to reference `anthropic-verify --check` as part of the rotation's success criteria, and references `anthropic-rotate.sh --rollback <ts>` as the rollback surface.

The anti-drift test (`tests/security/test_runbook_anchors.py`) asserts that specific markdown anchors exist in both runbooks. If a future PR removes those sections, the test catches it.

The merge commit MUST record `Rebaseline: completed at <ts>` per spec FR-017 and the `#557` rebaseline obligation — `scripts/security/` is an audited surface. The operator runs the rebaseline reset on office2 post-merge per `docs/runbooks/security-baseline-ops.md`. This is a MERGE-TIME action by the operator, not a WP-level file change; it's noted here so the reviewer flags any merge commit that doesn't record the status.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Depends on WP01 + WP02 + WP03 — the runbook describes behavior that the prior WPs implement. Spec-kitty's `next` flow handles the dependency chain.

## Subtask guidance

### T014 — `docs/runbooks/openclaw-ops.md` § _Known upgrade gotchas_ addendum

Locate the existing "Known upgrade gotchas" section in `docs/runbooks/openclaw-ops.md`. Append a new subsection:

```markdown
### Per-agent auth-row shadow (post-`doctor --fix`)

**Symptom**: a sub-agent's cron jobs fail with `FailoverError: LLM error authentication_error: invalid x-api-key` while sibling sub-agents continue to work. WhatsApp escalations from `inbox-5pm` / `inbox-10pm` / `inbox-7am` are the canonical signal.

**Cause**: `openclaw doctor --fix` migrates a sub-agent's pre-existing `auth-profiles.json` into the per-agent SQLite store (`~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite`, tables `auth_profile_store` + `auth_profile_state`). The migrated row OVERRIDES the read-through inheritance from `main`. If the imported value is stale, every LLM call routed through that sub-agent fails with `invalid x-api-key`. Healthy state for any sub-agent is **zero rows** in both tables.

**Detection**: run `anthropic-verify --check` (see `scripts/security/anthropic-verify.sh`). Exit 2 = shadow detected; the finding names the affected agent and the specific table.

**Remediation**:
```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --repair
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check
```

The `--repair` mode writes a `.pre-repair.<unix-ts>.bak` sibling before clearing the rows.

**Reference**: `#596` (the post-incident write-up), `#597` (this preventive surface).

### Plaintext / SQLite drift

**Symptom**: `felix-doc-auditor-driver` or `felix-heartbeat-gate` ticks emit `invalid x-api-key` errors while openclaw-gateway-routed agents continue to work.

**Cause**: `/data/services/openclaw/secrets/anthropic` (plaintext file consumed by the non-openclaw Python drivers) has drifted from `main`'s SQLite store. Usually triggered by an Anthropic key rotation that went through `openclaw models auth paste-api-key` directly without going through `anthropic-rotate.sh`.

**Detection**: `anthropic-verify --check` reports `drift` finding with both sha256[:8] fingerprints. Exit code 3.

**Remediation**:
```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --repair
```

The `--repair` mode atomically rewrites the plaintext file from `main`'s SQLite value via tmp-rename, preserving mode 0600. No gateway restart needed — consumers re-read on their next tick.

**Reference**: `#597`.

### Post-`doctor --fix` and post-rotation gate (recommended)

Always run `anthropic-verify --check` after any of:
- `openclaw doctor --fix` (any invocation, including the post-upgrade gate)
- `anthropic-rotate.sh` (already invoked automatically at end-of-rotation)
- Manual edits to any of the three auth substrates (`main` SQLite, plaintext file, any sub-agent SQLite)

Output is fingerprints + verdicts only; no key values printed.
```

The exact wording above is a draft — implementer may refine the phrasing while preserving the structure (Symptom / Cause / Detection / Remediation / Reference per subsection).

### T015 — `docs/runbooks/credential-rotation-ops.md` § _anthropic_ addendum

Locate the existing `anthropic` section. Append to its end:

```markdown
### Post-rotation verification (mandatory)

`anthropic-rotate.sh` invokes `anthropic-verify --check` at the end of every successful rotation as a fail-closed gate (see FR-012 of `kentonium3/kg-automation#597`). If verify reports any finding, the rotation script prints a copy-pasteable rollback command and exits non-zero. The rotation is NOT auto-undone; the operator decides whether to roll back or remediate forward.

To roll back a rotation that landed but verify rejected:

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback <ROTATION_TS>
```

The `<ROTATION_TS>` value is emitted by the rotation script's error output and recorded in `~/.cache/anthropic-rotate/manifest.<ts>.json`. The rollback restores the plaintext file, `openclaw.json`, and the SQLite-side `auth-profiles.json.sqlite-import.<ts>.bak` from the per-step backups, then restarts the openclaw-gateway.

If only specific findings need to be remediated (e.g., a pre-existing shadow row the rotation didn't create), `anthropic-verify --repair` is the targeted surface — see `docs/runbooks/openclaw-ops.md` § _Per-agent auth-row shadow_.
```

### T016 — Anti-drift test for runbook anchors

`tests/security/test_runbook_anchors.py`:

```python
import pathlib
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

ANCHORS = [
    (REPO_ROOT / "docs/runbooks/openclaw-ops.md", "### Per-agent auth-row shadow"),
    (REPO_ROOT / "docs/runbooks/openclaw-ops.md", "### Plaintext / SQLite drift"),
    (REPO_ROOT / "docs/runbooks/openclaw-ops.md", "### Post-`doctor --fix` and post-rotation gate"),
    (REPO_ROOT / "docs/runbooks/credential-rotation-ops.md", "### Post-rotation verification"),
]

@pytest.mark.parametrize("path,anchor", ANCHORS)
def test_runbook_anchor_present(path, anchor):
    assert path.exists(), f"runbook missing: {path}"
    content = path.read_text()
    assert anchor in content, (
        f"Runbook anchor missing in {path.name}: {anchor!r}. "
        f"This section documents the openclaw-auth-verifier remediation flow "
        f"(see kentonium3/kg-automation#597). Do not delete without updating the test."
    )

def test_verifier_referenced_in_both_runbooks():
    """Both runbooks must reference anthropic-verify by name."""
    for runbook in [
        REPO_ROOT / "docs/runbooks/openclaw-ops.md",
        REPO_ROOT / "docs/runbooks/credential-rotation-ops.md",
    ]:
        assert "anthropic-verify" in runbook.read_text(), (
            f"{runbook.name} does not reference anthropic-verify; see #597 for context."
        )
```

The test runs in the standard pytest collection — no special markers. It's fast (< 100 ms total) and acts as a CI-time tripwire against silent doc drift.

### Files touched (final list)

- `docs/runbooks/openclaw-ops.md` (MODIFIED, ~+50 lines: three new subsections under "Known upgrade gotchas")
- `docs/runbooks/credential-rotation-ops.md` (MODIFIED, ~+15 lines: new subsection in `anthropic`)
- `tests/security/test_runbook_anchors.py` (NEW, ~40 lines)

## Test strategy

Test-first per DIRECTIVE_034. Author T016 first; it will fail (anchors not yet present). Then author T014 and T015 to make it pass. The test is structural-only (no behavior coverage); behavioral coverage of the verifier itself lives in WP01-WP03 tests.

## Definition of Done

- All 3 subtasks completed; the anti-drift test passes.
- `grep -F "anthropic-verify"` succeeds against both runbooks.
- The runbook addenda are self-contained — a reader unfamiliar with `#596` understands the failure mode, the detection path, and the remediation flow from the runbook alone.
- The merge commit records `Rebaseline: completed at <ts>` per `#557`. The operator runs the rebaseline reset on office2 post-merge.

## Risks

- **Runbook prose drift**: the suggested wording above is a starting point; future edits may refine. The anti-drift test only guards section anchors and the keyword `anthropic-verify` — it does NOT enforce specific wording. That's intentional; over-asserting locks the doc.
- **Rebaseline forgetting**: the merge commit MUST record the rebaseline status. Reviewer guidance is to flag any merge commit that doesn't, per CLAUDE.md.

## Reviewer guidance

- Verify all four anchors are present in the runbook files.
- Verify the runbook addenda are self-contained — a reader who doesn't know the mission's history can still execute the remediation steps.
- Verify the anti-drift test runs in the standard pytest collection.
- Verify the merge commit records the rebaseline status per `#557`.

## Commands

When `spec-kitty next` directs you here:

```bash
spec-kitty agent action implement WP04 --agent claude
```

When ready for review:

```bash
spec-kitty agent action review WP04 --agent claude
```
