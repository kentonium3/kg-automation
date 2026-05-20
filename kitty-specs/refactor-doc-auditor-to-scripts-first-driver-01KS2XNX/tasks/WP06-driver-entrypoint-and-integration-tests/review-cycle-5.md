---
affected_files: []
cycle_number: 5
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-20T21:33:41Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP06
---

### Review Cycle 4 Feedback — WP06

The implementation is high quality, well-documented, and covers all functional requirements. However, there is a critical logic bug in the self-apply guard (FR-008) that will prevent any pending approvals from being applied in production.

#### 1. Critical Bug: Self-apply guard checks Author instead of Label Actor (FR-008)

In `scripts/doc_audit/run.py`, the `_get_decision_actor` function queries the `author` of the issue:

```python
def _get_decision_actor(config: Config, issue_number: int) -> Optional[str]:
    # ...
    cmd = ["gh", "issue", "view", str(issue_number), "--repo", config.github.repo, "--json", "labels,author"]
    # ... returns data.get("author").get("login")
```

**The problem**: Since the bot creates the `audit-pending-approval` issue, it is the `author`. When a human operator approves the issue by adding the `audit-approve` label, the `author` remains the bot. The subsequent check in `_process_pending_approval` then refuses the decision:

```python
is_self_apply = actor_login is not None and actor_login.lower() == config.github.bot_identity.lower()
if is_self_apply:
    # REFUSE
```

This means the driver will **always** refuse approvals on issues it created, even if a human added the label.

**Fix**: `_get_decision_actor` must identify the specific user who **added the decision label**. You can use `gh issue view --json timelineItems` and look for the most recent `LabeledEvent` for the decision label (audit-approve/reject/skip) to find the correct actor login.

#### 2. Integration Tests Masking the Bug

The integration tests (e.g., `test_pending_approval_apply` in `tests/doc_audit/test_integration_tick_outcomes.py`) mask this bug by mocking the `author` as a human (`kentonium3`):

```python
view = {
    7001: {"author": {"login": "kentonium3"}, "labels": pa[0]["labels"]},
}
```

In a real scenario, the author of #7001 would be `kg-felix-bot`. The test should be updated to reflect that the bot is the author, but a human is the labeler, and the guard should correctly distinguish between them.

#### 3. Minor: Stale-lock recovery telemetry

In `_recover_stuck_locks`, you log:
`marker = f"recovered-stale-lock: audit #{number} ..."`
This is good. Ensure this same string pattern is what operators should look for in `last-tick.json`.

---

Please fix the `_get_decision_actor` logic to verify the **labeler** rather than the **author**, and update the tests to prove it works when the bot is the author but a human is the labeler.
