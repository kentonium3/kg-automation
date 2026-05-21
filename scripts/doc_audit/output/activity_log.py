"""Activity-log appender.

Per spec C-005, the driver preserves the format of the activity log
produced by the previous openclaw-agent path so operator workflows
(Kent reads these manually in the Obsidian vault) do not break.

The canonical-format fixture captured from office2 on 2026-05-20
lives at ``tests/doc_audit/output/fixtures/activity_log_sample.txt``
and is byte-for-byte authoritative — the writer is tested against
it. Any format change MUST update both the writer and the fixture.

Format details (mission #343 capture, 2026-05-20)::

    ## Audit run — 2026-05-20T15:15:33-0400
    - Audit issue: #347
    - Title: Doc audit: cf0e0b9 (area/biz-ops)
    - In-scope docs: 3
    - Docs reviewed: 3
    - High-confidence edits proposed: 0
    - Pending-approval issue filed: none
    - Edits committed: 0
    - Debt issues created: 0
    - Missing artifacts flagged: 0
    - Items requiring human review: 0
    - Decision applied this tick: none
    - Errors: 0

Key shape invariants:

- Header: ``## Audit run — <local-tz ISO-8601>`` with the em-dash
  surrounded by single spaces. The timestamp is **local-tz with
  numeric offset** (``-0400``, NOT ``-04:00`` and NOT UTC ``Z``).
- Bulleted ``- <Field>: <value>`` lines, one per field, in the
  fixed order above.
- One entry per AUDIT (not per tick): if a tick processes 3 audits,
  the writer is called 3 times.
- Each entry ends with a trailing blank line so consecutive
  appended entries are separated by exactly one blank line — the
  operator-visible multi-entry format Kent reads in the vault.
  The single-entry fixture (captured as an end-of-file snapshot)
  does NOT include this trailing blank line; tests account for
  the extra ``\\n`` when comparing single-write output to it.
- File has NO YAML frontmatter; the entries are appended directly
  to the file. The first call of the day creates an empty file
  before appending.
- File name uses the **local-tz** date (``doc-auditor-YYYY-MM-DD.md``)
  to match the existing convention.

Time zone: ``America/New_York`` (the offset captured in the
canonical sample). If the host TZ ever needs to change, lift this
to ``Config`` — for now it's a module constant.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from doc_audit.config import Config
from doc_audit.data_model import AuditIssue, TickResult

__all__ = ["LOCAL_TZ", "append_audit_entry"]


# Per the captured fixture (`-0400`), the activity log is timestamped
# in America/New_York. Promote to a config knob if the host TZ ever
# changes.
LOCAL_TZ = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_local() -> datetime:
    """Return the current ``LOCAL_TZ`` datetime.

    Wrapped so tests can monkeypatch wall-clock without touching
    ``datetime.now`` globally.
    """
    return datetime.now(LOCAL_TZ)


def _format_timestamp(dt: datetime) -> str:
    """Format the entry header timestamp.

    Matches the captured fixture: ``%Y-%m-%dT%H:%M:%S%z`` produces
    e.g. ``2026-05-20T15:15:33-0400`` (no colon in the TZ offset).
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def _format_audit_entry(
    audit: AuditIssue,
    outcome: dict[str, Any],
    now: datetime,
) -> str:
    """Format one ``## Audit run`` entry.

    Each entry ends with TWO newlines (``\\n\\n``) so that when a
    second entry is appended to the same daily log file, the two
    ``## Audit run`` blocks are separated by a single blank line.
    The WP05 validation checklist (and the canonical multi-entry
    operator format Kent reads in the Obsidian vault) requires one
    blank line between subsequent entries; without the trailing
    blank line, consecutive entries would butt up against each
    other with no visual separator.

    Cycle 1 of WP05 review (Codex finding) flagged this: a single
    trailing ``\\n`` made two consecutive entries render with no
    blank line between them. The single-entry fixture at
    ``tests/doc_audit/output/fixtures/activity_log_sample.txt`` is
    a single entry captured from office2 and does NOT include this
    inter-entry blank line; tests that compare a single write to
    the fixture account for the extra trailing ``\\n``.
    """
    ts = _format_timestamp(now)
    issue_number = audit.issue_number
    title = audit.title

    # Read counts with safe defaults so partial-result paths (e.g.,
    # mid-tick failure) still produce a syntactically-valid entry.
    in_scope = outcome.get("in_scope_docs", len(audit.in_scope_docs))
    docs_reviewed = outcome.get("docs_reviewed", 0)
    hc_edits = outcome.get("hc_edits_proposed", 0)
    pending_approval = outcome.get("pending_approval_issue", "none")
    edits_committed = outcome.get("edits_committed", 0)
    debt_count = outcome.get("debt_issues_created", 0)
    debt_refs = outcome.get("debt_issue_refs", "")
    missing = outcome.get("missing_artifacts", 0)
    human_review = outcome.get("human_review_items", 0)
    decision_applied = outcome.get("decision_applied", "none")
    error_count = outcome.get("error_count", 0)

    debt_line = f"- Debt issues created: {debt_count}"
    if debt_refs:
        debt_line = f"{debt_line} {debt_refs}"

    lines = [
        f"## Audit run — {ts}",
        f"- Audit issue: #{issue_number}",
        f"- Title: {title}",
        f"- In-scope docs: {in_scope}",
        f"- Docs reviewed: {docs_reviewed}",
        f"- High-confidence edits proposed: {hc_edits}",
        f"- Pending-approval issue filed: {pending_approval}",
        f"- Edits committed: {edits_committed}",
        debt_line,
        f"- Missing artifacts flagged: {missing}",
        f"- Items requiring human review: {human_review}",
        f"- Decision applied this tick: {decision_applied}",
        f"- Errors: {error_count}",
        "",  # trailing empty line → ``"\n".join`` yields ``\n`` after
             # the last bullet; the explicit ``+ "\n"`` below makes a
             # second ``\n``, producing the inter-entry blank line.
    ]
    # Each entry ends with ``\n\n``: the empty-string element above
    # plus the explicit ``+ "\n"`` below. When two entries are
    # appended in sequence, the second entry's ``## Audit run``
    # header is preceded by exactly one blank line, matching the
    # operator-visible multi-entry format.
    return "\n".join(lines) + "\n"


def _init_log_file(path: Path) -> None:
    """Create a new daily log file. NO frontmatter — existing convention.

    The file starts empty; entries are appended below.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_audit_entry(
    config: Config,
    result: TickResult,
    audit: AuditIssue,
    outcome: dict[str, Any],
) -> Path:
    """Append one ``## Audit run`` entry to today's activity log.

    Args:
        config: Driver :class:`Config`. The log directory is
            ``config.paths.activity_log_dir``; the file name is
            ``doc-auditor-<local-tz-date>.md``.
        result: The accumulated :class:`TickResult`. Currently
            unused by the entry formatter (per-audit counts come
            from the ``outcome`` dict the driver populates as it
            processes each audit) but accepted on the signature
            so future per-tick summary entries can lift fields
            from it.
        audit: The originating :class:`AuditIssue` (E-002). The
            entry pulls ``issue_number`` and ``title`` from this
            instance, plus a fallback for ``in_scope_docs`` count.
        outcome: Per-audit outcome dict populated by the driver's
            audit-processing loop. Recognized keys (all optional;
            unset keys fall back to safe defaults):

            - ``in_scope_docs`` (int) — defaults to
              ``len(audit.in_scope_docs)``
            - ``docs_reviewed`` (int) — defaults to 0
            - ``hc_edits_proposed`` (int) — defaults to 0
            - ``pending_approval_issue`` (str) — defaults to ``"none"``
            - ``edits_committed`` (int) — defaults to 0
            - ``debt_issues_created`` (int) — defaults to 0
            - ``debt_issue_refs`` (str) — appended after the count
              (e.g., ``"#341, #342"``); empty string omits the
              tail. Defaults to empty.
            - ``missing_artifacts`` (int) — defaults to 0
            - ``human_review_items`` (int) — defaults to 0
            - ``decision_applied`` (str) — defaults to ``"none"``
            - ``error_count`` (int) — defaults to 0

    Returns:
        The :class:`Path` of the daily activity log file.
    """
    # Unused today; accepted on the signature for forward-compat.
    # The driver may eventually want a per-tick summary entry placed
    # above the per-audit ones; that lift consumes ``result``.
    del result

    now = _now_local()
    today_local = now.date().isoformat()
    log_path = Path(config.paths.activity_log_dir) / f"doc-auditor-{today_local}.md"

    if not log_path.exists():
        _init_log_file(log_path)

    entry_text = _format_audit_entry(audit, outcome, now)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry_text)
    return log_path
