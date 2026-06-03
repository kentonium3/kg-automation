#!/usr/bin/env python3
"""ADR-0002 Phase 6 Q10 hard-fail bug filing + title-prefix dedup helpers.

This module is the **library surface** consumed by the reconcile + record
helpers when an escalation tick observes inconsistent state that requires
operator triage. It implements the two-step Q10 hard-fail flow per spec
FR-008 and FR-009:

1. ``dedup_existing_open(task_id)`` -- query ``gh issue list`` for any open
   P2-bug whose title contains both the ``Escalation hard-fail`` marker and
   the ``(task #<id>)`` substring. The substring is anchored on the
   immutable Vikunja ``id`` per ``reference_vikunja_id_vs_identifier.md``
   so dedup survives task renames and project moves. Re-fires correctly
   when an operator closes the issue without repairing the JSONL record
   (the ``--state open`` filter excludes closed issues).
2. ``render_bug_body(...)`` -- build the data-model Entity 5 template body
   and the title literal. Callers may render before checking dedup if they
   want to log the intended body for diagnostics. Caller-provided strings
   are passed through ``_sanitize_for_body`` so C-006 (no second-brain
   path leakage) is enforced at the render boundary rather than relying
   on caller hygiene.
3. ``file_hard_fail_bug(...)`` -- orchestrate the full flow. Short-circuit
   on a dedup hit; otherwise invoke ``felix-file-issue.py`` as a subprocess.
   Return a structured dict capturing which branch was taken.

felix-file-issue.py interface quirks (verified during T013)
-----------------------------------------------------------

``scripts/openclaw/agents/main/felix-file-issue.py`` is the canonical Felix
issue-filing surface per mission #291. It does **not** accept arbitrary
bodies; instead it requires a fixed ``--type`` flag (one of ``bug``,
``feature``, ``infra``, ``research``) and renders a template-structured
body from ``--problem-statement-file`` + ``--observed-context-file``.

To stay within the canonical issue-filing surface (rather than calling
``gh issue create`` ad-hoc) this helper:

* Writes the data-model Entity 5 body to a tempfile and passes the path
  via ``--problem-statement-file``. The body lands in the Bug template's
  ``Summary`` section.
* Calls felix-file-issue with ``--type bug``, ``--priority P2``,
  ``--area escalation``, ``--tier-hypothesis 3``, ``--spec-ready-eval ready``.
* Accepts the helper's ``Bug:`` title prefix. The resulting issue title is
  ``Bug: Escalation hard-fail: <task title> (task #<id>) — <reason>``.
  The dedup query is substring-anchored on ``"(task #<id>)"`` AND
  ``"Escalation hard-fail"`` so the ``Bug:`` prefix is transparent.
* Adds the ``area/escalation`` label via felix-file-issue's ``--area``
  argument. (The script auto-applies ``P2-bug`` from ``--priority`` +
  ``--type``.) ``area/escalation`` is not in ``KNOWN_AREAS`` so the helper
  emits a WARN to stderr; this is expected and benign.

If felix-file-issue's interface drifts (e.g., gains direct body input),
update ``file_hard_fail_bug`` accordingly. The pure ``render_bug_body``
function does NOT depend on this transport detail.

Design references
-----------------

- kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/spec.md
    FR-008 (Q10 hard-fail behavior), FR-009 (title-prefix dedup keyed on
    Vikunja ``id``), C-006 (no second-brain paths in body templates).
- kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md
    Entity 5 (hard-fail bug body template, reason taxonomy).
- kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/research.md
    D8 (hard-fail trigger conditions), D9 (dedup query format verbatim).
- scripts/openclaw/agents/main/felix-file-issue.py
    Canonical issue-filing surface (mission #291).
- scripts/escalation/derive_state.py
    ``EscalationStateError`` taxonomy fed into ``HardFailReason`` mapping.
"""
from __future__ import annotations

import json
import subprocess
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: GitHub repository where Felix files hard-fail bugs.
REPO = "kentonium3/kg-automation"

#: Labels applied to every hard-fail bug. ``P2-bug`` is auto-added by
#: felix-file-issue.py from ``--type bug --priority P2``; ``area/escalation``
#: is added from ``--area escalation``. The constant exists so consumers and
#: tests can reason about the label set without re-deriving it.
HARD_FAIL_LABELS = ["P2-bug", "area/escalation"]


#: Discriminated literal for the three Q10 hard-fail triggers per spec
#: FR-008 + research D8. The values mirror data-model Entity 5's reason
#: enumeration. ``derive_state_inconsistency`` is the umbrella value when
#: ``derive_state`` raises ``EscalationStateError`` (any reason from its
#: own three-value taxonomy).
HardFailReason = Literal[
    "malformed_jsonl_record",
    "derive_state_inconsistency",
]


#: Mapping from ``HardFailReason`` to the short reason string used in the
#: bug title (per data-model Entity 5). Title shape:
#: ``Escalation hard-fail: <title> (task #<id>) — <short reason>``
#: (the separator is U+2014 EM DASH, not two ASCII hyphens).
_SHORT_REASON: dict[str, str] = {
    "malformed_jsonl_record": "malformed JSONL",
    "derive_state_inconsistency": "derive_state error",
}


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def dedup_existing_open(task_id: int) -> Optional[str]:
    """Return the URL of any open hard-fail bug for ``task_id``, or ``None``.

    Implements the dedup query verbatim per research D9::

        gh issue list --repo kentonium3/kg-automation \\
                      --state open \\
                      --search 'in:title "(task #<id>)" "Escalation hard-fail"' \\
                      --json number,title,url \\
                      --limit 5

    The search is substring-anchored on the immutable Vikunja ``id``
    (``(task #<id>)``) AND the literal marker ``Escalation hard-fail``.
    Returns the first matching issue's ``url`` if any results come back,
    else ``None``. Title renames and project moves are transparent because
    the search ignores everything except those two substrings.

    The ``--state open`` filter is deliberate: when an operator closes a
    hard-fail issue without repairing the underlying JSONL record, the next
    escalation tick re-fires (the dedup query returns empty because closed
    issues are excluded).

    Args:
        task_id: The Vikunja ``id`` of the task with the hard-fail.

    Returns:
        The HTTP URL of the first matching open bug, or ``None`` if no
        open hard-fail bug exists for this ``task_id``.

    Raises:
        subprocess.CalledProcessError: If ``gh`` returns a non-zero exit
            code. Callers decide whether to swallow or surface this; the
            helper never silently coerces a gh failure into ``None``
            (that would mask outages and double-file bugs).
    """
    search_query = f'in:title "(task #{task_id})" "Escalation hard-fail"'
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--repo", REPO,
            "--state", "open",
            "--search", search_query,
            "--json", "number,title,url",
            "--limit", "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    issues = json.loads(result.stdout) if result.stdout.strip() else []
    if not issues:
        return None
    # Return the first match's URL (the search is already limited to 5).
    return issues[0].get("url")


# ---------------------------------------------------------------------------
# Body / title rendering
# ---------------------------------------------------------------------------


#: Forbidden substrings that must never appear in a rendered hard-fail body
#: per spec C-006 (no second-brain path leakage). Order matters: longer
#: prefixes (``~/second-brain``, ``/second-brain``) are matched before the
#: bare ``_private`` suffix so the redaction placeholder is applied to the
#: most specific form first. Match is plain ASCII substring (case-sensitive)
#: -- the second-brain path is canonically lower-case, and an adversarial
#: caller cannot smuggle the path through a casing trick because the
#: filesystem itself is case-sensitive on Linux.
_FORBIDDEN_BODY_SUBSTRINGS: tuple[str, ...] = (
    "~/second-brain",
    "/second-brain",
    "_private",
)

#: Placeholder substituted into the body in place of any forbidden substring.
#: Kept short and self-describing so reviewers reading a redacted bug body
#: can immediately tell what was filtered.
_REDACTION_PLACEHOLDER = "[REDACTED:second-brain-path]"


def _sanitize_for_body(text: str) -> str:
    """Redact second-brain path fragments from a caller-provided string.

    Implements the C-006 invariant at the render boundary: every
    caller-provided string that flows into the hard-fail bug body (title
    OR body) is passed through this function first, so an adversarial or
    accidentally-tainted input cannot leak ``~/second-brain``,
    ``/second-brain``, or ``_private`` substrings into the filed issue.

    The match is plain substring (case-sensitive). Any occurrence of any
    forbidden substring is replaced with ``_REDACTION_PLACEHOLDER``.

    Args:
        text: Caller-provided string. May be empty or ``None``-safe via
            the ``str()`` call in callers (this function assumes ``str``).

    Returns:
        The sanitized string. Identical to the input when no forbidden
        substring is present (the common case for well-behaved callers).
    """
    sanitized = text
    for forbidden in _FORBIDDEN_BODY_SUBSTRINGS:
        if forbidden in sanitized:
            sanitized = sanitized.replace(forbidden, _REDACTION_PLACEHOLDER)
    return sanitized


def render_bug_body(
    *,
    task_id: int,
    project_id: int,
    task_title: str,
    reason: HardFailReason,
    jsonl_path: str,
    detection_snippet: str,
    vikunja_state: dict,
    derive_state_error_message: Optional[str] = None,
    detected_at: Optional[str] = None,
    vikunja_url: Optional[str] = None,
) -> tuple[str, str]:
    """Render the (title, body) pair for a Q10 hard-fail P2-bug.

    Title format (per data-model Entity 5)::

        Escalation hard-fail: <task title> (task #<vikunja_id>) — <short reason>

    The separator between the ``(task #...)`` substring and the short reason
    is U+2014 EM DASH (``—``), not two ASCII hyphens. Felix prefixes the
    final filed title with ``Bug: ``, so the issue title on github reads::

        Bug: Escalation hard-fail: <task title> (task #<id>) — <short reason>

    Body uses the data-model Entity 5 Markdown template verbatim with
    placeholders substituted in. C-006 (no second-brain path leakage) is
    enforced at the render boundary: every caller-provided string is passed
    through ``_sanitize_for_body`` before interpolation. An adversarial
    input containing ``~/second-brain``, ``/second-brain``, or ``_private``
    is replaced with ``[REDACTED:second-brain-path]`` rather than relying
    on caller hygiene.

    Args:
        task_id: Immutable Vikunja ``id`` of the affected task.
        project_id: Vikunja project ``id`` containing the task.
        task_title: Snapshot of the Vikunja task title at detection time.
            Sanitized before interpolation.
        reason: One of the ``HardFailReason`` values.
        jsonl_path: Absolute filesystem path to the project-slug JSONL file.
            Sanitized before interpolation -- a tainted path renders as
            the redaction placeholder, not the raw path.
        detection_snippet: Raw text of the record(s) that triggered the
            hard-fail. Sanitized before interpolation.
        vikunja_state: Dict with at minimum ``done`` (bool) and ``due_date``
            (str|None). Missing keys render as ``"unknown"``. String values
            are sanitized before interpolation.
        derive_state_error_message: The ``str(EscalationStateError)`` text
            when ``reason == "derive_state_inconsistency"``. Pass ``None``
            for the other two reasons; the body emits ``"n/a"`` in that
            case. Sanitized before interpolation.
        detected_at: UTC ISO-8601 timestamp string. Caller-injected for
            testability; if ``None`` the body emits the literal
            ``"unknown"`` placeholder. Sanitized before interpolation --
            an adversarial caller cannot leak second-brain paths through
            this field.
        vikunja_url: Pre-built link to the task in the Vikunja UI. Optional;
            if ``None`` the link reads ``<vikunja URL pending>``. Sanitized
            before interpolation -- real Vikunja URLs contain none of the
            forbidden substrings and pass through unchanged; tainted URLs
            are redacted to the placeholder.

    Returns:
        ``(title, body)`` tuple. Both are non-empty strings.

    Raises:
        ValueError: If ``reason`` is not a known ``HardFailReason`` value.
    """
    if reason not in _SHORT_REASON:
        known = ", ".join(sorted(_SHORT_REASON))
        raise ValueError(
            f"reason '{reason}' not in HardFailReason values {{{known}}}"
        )

    # Sanitize every caller-provided string up front. Anything that flows
    # into the title or body must go through _sanitize_for_body so an
    # adversarial input (e.g., a task title containing "_private", a JSONL
    # path under ~/second-brain, a detection snippet with leaked filesystem
    # context) is redacted before interpolation. C-006 is enforced HERE,
    # not at the caller boundary.
    safe_task_title = _sanitize_for_body(task_title)
    safe_jsonl_path = _sanitize_for_body(jsonl_path)
    safe_detection_snippet = _sanitize_for_body(detection_snippet)
    safe_derive_state_error_message = (
        _sanitize_for_body(derive_state_error_message)
        if derive_state_error_message is not None
        else None
    )

    short = _SHORT_REASON[reason]
    title = (
        f"Escalation hard-fail: {safe_task_title} (task #{task_id}) — {short}"
    )

    # Vikunja state block. Render every key explicitly so reviewers can
    # eyeball the expected shape without running tests. String values are
    # sanitized to enforce C-006 even if a tainted comment or due_date
    # string is passed in.
    done_value = vikunja_state.get("done", "unknown")
    if isinstance(done_value, bool):
        done_repr = "true" if done_value else "false"
    else:
        done_repr = _sanitize_for_body(str(done_value))
    due_date_value = vikunja_state.get("due_date")
    due_date_repr = (
        _sanitize_for_body(str(due_date_value))
        if due_date_value is not None
        else "null"
    )

    # ``vikunja_url`` and ``detected_at`` are caller-provided strings that
    # land in the rendered body, so they MUST flow through
    # ``_sanitize_for_body`` to enforce C-006. Real Vikunja URLs (e.g.,
    # ``https://office2.tail0f5f56.ts.net/tasks/1234``) and ISO-8601
    # timestamps contain none of the forbidden substrings and pass through
    # unchanged; an adversarial caller smuggling ``~/second-brain``,
    # ``/second-brain``, or ``_private`` into either field is redacted to
    # ``[REDACTED:second-brain-path]`` before interpolation.
    safe_vikunja_url = (
        _sanitize_for_body(vikunja_url) if vikunja_url else None
    )
    vikunja_link = (
        f"[{safe_task_title}]({safe_vikunja_url})"
        if safe_vikunja_url
        else f"{safe_task_title} (<vikunja URL pending>)"
    )

    detected_at_repr = (
        _sanitize_for_body(detected_at) if detected_at else "unknown"
    )
    derive_state_repr = (
        safe_derive_state_error_message
        if safe_derive_state_error_message is not None
        else "n/a"
    )

    body = f"""## Hard-fail context

Escalation tick skipped a task due to inconsistent state.

- **Task**: {vikunja_link} (Vikunja `id` {task_id}, project `id` {project_id})
- **Reason**: {reason}
- **Detected at**: {detected_at_repr}
- **JSONL file**: `{safe_jsonl_path}`

## Detection snippet

```
{safe_detection_snippet}
```

## Vikunja state

- `done`: {done_repr}
- `due_date`: {due_date_repr}

## derive_state output (if applicable)

```
{derive_state_repr}
```

## Recommended triage

1. Inspect the JSONL file at the path above. Identify the malformed line.
2. Cross-check against Vikunja state (link above).
3. Either repair the JSONL by hand (if recoverable) OR add a synthetic `{{state: "<best-fit>", source: "operator_repair", note: "manual triage <date>"}}` record.
4. Close this issue. The next escalation tick will reprocess.

## Labels

P2-bug, area/escalation
"""
    return title, body


# ---------------------------------------------------------------------------
# File-bug orchestration
# ---------------------------------------------------------------------------


def file_hard_fail_bug(
    *,
    task_id: int,
    project_id: int,
    task_title: str,
    reason: HardFailReason,
    jsonl_path: str,
    detection_snippet: str,
    vikunja_state: dict,
    derive_state_error_message: Optional[str] = None,
    detected_at: Optional[str] = None,
    vikunja_url: Optional[str] = None,
) -> dict:
    """Orchestrate dedup + render + felix-file-issue invocation.

    Step 1: Call ``dedup_existing_open(task_id)``. On hit, short-circuit and
    return ``{"filed": False, "deduped": True, "existing_url": <url>}``.

    Step 2: Render the title + body via ``render_bug_body``.

    Step 3: Invoke ``felix-file-issue.py`` as a subprocess. The body is
    written to a tempfile and passed via ``--problem-statement-file``; the
    title is passed via ``--title`` (felix-file-issue auto-prefixes with
    ``Bug:``). felix-file-issue's stdout is parsed for the issue URL.

    Returns:
        On success: ``{"filed": True, "deduped": False, "issue_url": <url>}``.
        On dedup hit: ``{"filed": False, "deduped": True, "existing_url": <url>}``.
        On subprocess failure: ``{"filed": False, "deduped": False, "error": <str>}``.
        On dedup query failure: ``{"filed": False, "deduped": False, "error": <str>}``.

    Side effects:
        Writes a temp file (auto-cleaned). Invokes ``gh`` via felix-file-issue.
    """
    # Step 1: dedup check. Catch CalledProcessError so the helper has a
    # well-typed return path on gh outages -- callers can log and continue.
    try:
        existing_url = dedup_existing_open(task_id)
    except subprocess.CalledProcessError as exc:
        return {
            "filed": False,
            "deduped": False,
            "error": (
                f"dedup query failed (gh exit {exc.returncode}): "
                f"{(exc.stderr or '').strip()}"
            ),
        }

    if existing_url is not None:
        return {
            "filed": False,
            "deduped": True,
            "existing_url": existing_url,
        }

    # Step 2: render the title + body.
    try:
        title, body = render_bug_body(
            task_id=task_id,
            project_id=project_id,
            task_title=task_title,
            reason=reason,
            jsonl_path=jsonl_path,
            detection_snippet=detection_snippet,
            vikunja_state=vikunja_state,
            derive_state_error_message=derive_state_error_message,
            detected_at=detected_at,
            vikunja_url=vikunja_url,
        )
    except ValueError as exc:
        return {
            "filed": False,
            "deduped": False,
            "error": f"render_bug_body failed: {exc}",
        }

    # Step 3: invoke felix-file-issue.py. Write the rendered body to a
    # tempfile because felix-file-issue requires ``--problem-statement-file``
    # (a path), not stdin or a literal flag value. The tempfile is
    # auto-cleaned by NamedTemporaryFile's context manager.
    import tempfile  # local import keeps the module's import surface tight

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".md",
        prefix="hard-fail-body-",
        delete=False,
    ) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "python3",
                "scripts/openclaw/agents/main/felix-file-issue.py",
                "--type", "bug",
                "--title", title,
                "--problem-statement-file", tmp_path,
                "--tier-hypothesis", "3",
                "--area", "escalation",
                "--priority", "P2",
                "--spec-ready-eval", "ready",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        return {
            "filed": False,
            "deduped": False,
            "error": (
                f"felix-file-issue.py failed (exit {exc.returncode}): "
                f"{(exc.stderr or '').strip()}"
            ),
        }
    finally:
        # Best-effort cleanup; ignore errors (tempfile cleanup is non-critical).
        try:
            import os
            os.unlink(tmp_path)
        except OSError:
            pass

    # felix-file-issue.py stdout is one line of JSON followed by a SUMMARY:
    # line. Parse the JSON line for the issue URL. Fall back to "" if the
    # output shape drifts.
    issue_url = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        issue_url = payload.get("issue_url") or ""
        break

    return {
        "filed": True,
        "deduped": False,
        "issue_url": issue_url,
    }
