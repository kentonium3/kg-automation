"""``GHIssueSignalSource`` — adapter for GitHub-issue-derived signals.

Realizes the ``SignalSource`` Protocol from
``contracts/signal-source.contract.md`` for the GitHub issue surface.
Three kinds of issue produce signals (in priority order):

- ``pending_approval`` (priority 10) — open ``audit-pending-approval``
  issues that have a decision label (``audit-approve`` /
  ``audit-reject`` / ``audit-skip``) applied. Decision processing
  happens first each tick because it represents work the operator
  already greenlit.
- ``doc_audit`` (priority 20) — open ``Doc audit:`` issues without
  ``status:in-progress``.
- ``weekly_doc_audit`` (priority 30) — open ``Weekly doc audit —``
  issues without ``status:in-progress``.

The adapter is idempotent within a tick via the ``_cached`` list;
the driver instantiates a fresh adapter per tick so the cache resets
automatically. ``commit()`` is a no-op: the GitHub issue's own state
(open/closed + labels) IS the persistent record of outcome, mutated
by the routing layer post-judgment rather than by this adapter.

Stale-lock recovery (re-opening ``status:in-progress`` issues whose
lock owner is gone) is intentionally NOT implemented here. WP06 adds
that atop the simple skip behavior this WP locks in.

Per the contract anti-patterns: credential / connectivity errors are
re-raised. An empty return MUST mean "no work to do," not "couldn't
reach the API."
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

from doc_audit.config import Config
from doc_audit.data_model import Signal
from doc_audit.signals.base import Outcome


# Decision labels that gate pending-approval signal emission.
_DECISION_LABELS = frozenset({"audit-approve", "audit-reject", "audit-skip"})

# Label that suppresses ``Doc audit:`` / ``Weekly doc audit —`` signals
# (stuck-lock recovery is WP06's job, not this adapter's).
_IN_PROGRESS_LABEL = "status:in-progress"


class GHIssueSignalSource:
    """Adapter producing :class:`Signal` instances from GitHub issues.

    Three queries run per :meth:`pending` call (one per signal kind).
    Results are cached on the instance so a second call within the
    same tick returns the same list without re-querying ``gh``.
    """

    name = "gh_issue"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.repo = config.github.repo
        self._cached: Optional[list[Signal]] = None

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def pending(self) -> list[Signal]:
        """Return all GH-derived signals for this tick (cached).

        Order within the returned list is: pending-approvals (P=10),
        then doc-audits (P=20), then weekly audits (P=30). The driver
        re-sorts by (priority, created_utc) so this ordering is for
        readability only.

        Raises:
            subprocess.CalledProcessError: ``gh`` exited non-zero
                (auth / network / repo error). Per the
                signal-source contract, this propagates.
            ValueError: ``gh`` returned non-JSON output.
        """
        if self._cached is not None:
            return self._cached

        signals: list[Signal] = []
        signals.extend(self._fetch_pending_approvals())
        signals.extend(self._fetch_doc_audits(weekly=False))
        signals.extend(self._fetch_doc_audits(weekly=True))

        self._cached = signals
        return signals

    def commit(self, signal: Signal, outcome: Outcome) -> None:
        """No-op: the GH issue state itself records the outcome.

        The routing layer closes audit issues, applies decision-result
        labels to pending-approvals, etc. Nothing for this adapter to
        persist because the source-of-truth lives on GitHub, not in a
        local cursor file.
        """
        # Intentionally empty per signal-source contract: "For source
        # kinds where the GitHub issue itself records the outcome
        # (e.g., closed audits, applied decisions), this method MAY
        # be a no-op."
        return None

    # ------------------------------------------------------------------
    # Internal: per-kind fetchers
    # ------------------------------------------------------------------

    def _fetch_pending_approvals(self) -> list[Signal]:
        """Query open ``audit-pending-approval`` issues with a decision.

        An issue is emitted as a signal ONLY when one of the decision
        labels (``audit-approve`` / ``audit-reject`` / ``audit-skip``)
        is applied. Awaiting-decision issues are filtered out — they
        are not actionable until the operator labels them.
        """
        issues = self._run_gh_issue_list(
            label="audit-pending-approval",
        )
        signals: list[Signal] = []
        for issue in issues:
            labels = _extract_label_names(issue)
            if not (_DECISION_LABELS & set(labels)):
                # No decision label applied yet — operator hasn't
                # acted. Skip until the next tick.
                continue
            signals.append(
                Signal(
                    id=f"gh-issue:{issue['number']}",
                    source=self.name,
                    kind="pending_approval",
                    priority=10,
                    payload={
                        "issue_number": issue["number"],
                        "title": issue.get("title", ""),
                        "body": issue.get("body", ""),
                        "labels": labels,
                        "area_labels": [
                            label for label in labels
                            if label.startswith("area/")
                        ],
                    },
                    created_utc=issue.get("createdAt", ""),
                )
            )
        return signals

    def _fetch_doc_audits(self, weekly: bool) -> list[Signal]:
        """Query open ``Doc audit:`` (or ``Weekly doc audit —``) issues.

        ``status:in-progress`` issues are skipped: a tick that crashed
        mid-audit leaves the label on — recovery is WP06's job. This
        WP's contract is the simple skip.

        Args:
            weekly: When True, emit ``weekly_doc_audit`` signals
                (priority 30); otherwise emit ``doc_audit`` signals
                (priority 20). The two share a label but are
                separated by title prefix.
        """
        title_prefix = "Weekly doc audit —" if weekly else "Doc audit:"
        kind = "weekly_doc_audit" if weekly else "doc_audit"
        priority = 30 if weekly else 20

        issues = self._run_gh_issue_list(label="doc-audit")
        signals: list[Signal] = []
        for issue in issues:
            title = issue.get("title", "")
            if not title.startswith(title_prefix):
                continue
            labels = _extract_label_names(issue)
            if _IN_PROGRESS_LABEL in labels:
                # Skip stuck-lock issues — recovery is WP06.
                continue
            signals.append(
                Signal(
                    id=f"gh-issue:{issue['number']}",
                    source=self.name,
                    kind=kind,
                    priority=priority,
                    payload={
                        "issue_number": issue["number"],
                        "title": title,
                        "body": issue.get("body", ""),
                        "labels": labels,
                        "area_labels": [
                            label for label in labels
                            if label.startswith("area/")
                        ],
                    },
                    created_utc=issue.get("createdAt", ""),
                )
            )
        return signals

    # ------------------------------------------------------------------
    # Internal: gh invocation
    # ------------------------------------------------------------------

    def _run_gh_issue_list(self, *, label: str) -> list[dict]:
        """Invoke ``gh issue list`` and parse the JSON result.

        Errors propagate per the signal-source contract — credential
        or connectivity failures MUST NOT be silently converted to
        an empty list.
        """
        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            self.repo,
            "--label",
            label,
            "--state",
            "open",
            "--json",
            "number,title,labels,body,createdAt",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            parsed = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"gh issue list returned non-JSON output for label "
                f"{label!r}: {exc}"
            ) from exc
        if not isinstance(parsed, list):
            raise ValueError(
                f"gh issue list for label {label!r} returned non-list "
                f"JSON: {type(parsed).__name__}"
            )
        return parsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_label_names(issue: dict) -> list[str]:
    """Flatten ``gh``'s label objects to a list of label name strings.

    ``gh`` returns labels as ``[{"name": "foo"}, ...]``. Tests and
    callers both use the flat string form, so we normalize here.
    """
    return [
        label.get("name", "")
        for label in issue.get("labels", [])
        if isinstance(label, dict)
    ]


__all__ = ["GHIssueSignalSource"]
