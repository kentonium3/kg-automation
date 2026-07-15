"""Route a captured "someday" block to a ``q:schedule`` + no-due-date task.

Post-#745 routing model
-----------------------
"Someday" is **no longer a Vikunja project**. The post-reset (#714) taxonomy
represents the "important, but not date-committed" state as a task carrying the
``q:schedule`` label **with no due date** (see
``docs/design/vikunja-configuration-design.md``). This helper therefore:

1. Resolves the destination **project** through the reference seam
   (``scripts.common.vikunja_refs``) — the default is **Inbox**
   (``project_id("inbox")``); a caller/classifier may supply a resolved topic
   project via ``--project <logical-name>``. There is **no live ``/projects``
   listing** and **no by-title "Someday" lookup** — the retired
   ``find_someday_project``/``SOMEDAY_PROJECT_TITLE`` path was the direct #743
   cause on this route (it looked up a project that no longer exists).
2. Creates the task via Vikunja's CREATE endpoint ``PUT /projects/<id>/tasks``
   with ``{title, description}`` and **no due date**. Per
   ``[[reference_vikunja_post_partial_replace]]`` we MUST NOT use
   ``POST /tasks/<id>`` (that partial-replaces an existing task and was the root
   cause of #524). The description footer ``Source: <note-filename>`` and the
   caller's routing-log / dedup substrate (FR-013) are preserved.
3. **Best-effort** attaches the ``q:schedule`` label (resolved by id through the
   seam: ``label_id("q:schedule", "kent")``) via ``PUT /tasks/<id>/labels``.

Anti-silent-loss guarantee (#743)
----------------------------------
The task is **always created** first — that is the capture's durable landing.
The label attach is deliberately **fail-soft**: ``route_someday`` runs under the
felix-bot ``VikunjaClient``, and a 2026-07-15 live-probe confirmed felix-bot
receives **HTTP 403** attaching the kent-owned ``q:schedule`` label (the #715
per-token ownership boundary). Rather than block or lose the capture, an attach
failure is **logged loudly** (a structured warning envelope on stderr) and the
route still **succeeds** (exit 0, ``task_id=<int>``). This means the label is
populated automatically the moment felix-bot gains attach capability, with zero
capture loss in the meantime; until then the #749 task-intake loop applies the
label. The broader ``f:/q:/t:/loe:`` intake taxonomy remains deferred to #749 —
this helper never guesses/attaches labels not declared in the registry.

CLI (mandatory ``-m`` form per ``[[feedback_helper_m_invocation_form]]``)::

    python3 -m scripts.inbox.route_someday \
        --title "<title>" --body "<body>" --note-filename <name> [--project <name>]

Contract: ``task_id=<int>`` to stdout on success (exit 0). A hard failure
(cannot create the task) emits ``{"error": ..., "detail": ...}`` JSON to stderr
and exits 2. A soft label-attach failure emits a ``{"warning": ...}`` JSON line
to stderr but does **not** change the exit code (the task is safely created).

Stdlib only. Imports the shared ``VikunjaClient`` and the network-free
``vikunja_refs`` accessor (both stdlib-only).
"""
from __future__ import annotations

import argparse
import json
import sys

from scripts.common import vikunja_refs
from scripts.common.vikunja_client import VikunjaClient, VikunjaError
from scripts.common.vikunja_refs import VikunjaRefError, VikunjaRefUnprovisioned

__all__ = [
    "RouteSomedayError",
    "route_someday",
    "main",
]

#: Default destination project (logical name resolved through the seam). The
#: post-#745 safe-fallback / fall-through bucket is Inbox, never a "Someday"
#: project (FR-010).
DEFAULT_PROJECT_NAME = "inbox"

#: The "someday" task-state label and its owning token (#715 per-token labels).
#: Declared in the WP01 registry (``q:schedule`` -> id 23, kent namespace).
SOMEDAY_LABEL_NAME = "q:schedule"
SOMEDAY_LABEL_TOKEN = "kent"


class RouteSomedayError(Exception):
    """Domain exception for **hard** failures within ``route_someday``.

    Surfaced to the caller via exit 2 + a structured stderr envelope. Wraps
    :class:`VikunjaError`, :class:`ConnectionError`, and registry
    :class:`VikunjaRefError` so the CLI's error contract stays uniform
    regardless of which layer detected the failure. A *soft* label-attach
    failure is NOT a ``RouteSomedayError`` — the task is already created, so it
    is logged and the route succeeds.
    """


def _emit_warning(detail: str, **fields: object) -> None:
    """Write a structured, loud (but non-fatal) warning envelope to stderr.

    Used for the fail-soft label attach: the capture is already safely created,
    so this never changes the exit code — it makes the degraded state visible
    (never silently swallowed) so operators and the #749 loop can see it.
    """
    payload: dict[str, object] = {"warning": "label_attach_failed", "detail": detail}
    payload.update(fields)
    print(json.dumps(payload), file=sys.stderr)


def _resolve_destination_project_id(project_name: str) -> int:
    """Resolve the destination project id through the reference seam.

    Inbox (``DEFAULT_PROJECT_NAME``) is the **default** target for
    unclassifiable captures — the caller passes ``project="inbox"`` for the
    fall-through bucket. It is **not** a fallback for a broken supplied topic
    name: a caller-supplied project that cannot be resolved is a real error,
    because silently landing the capture in Inbox would act on the WRONG target
    (violating FR-003/SC-002, "never acts on a wrong target"). ANY unresolvable
    project name therefore FAILS LOUD as a hard :class:`RouteSomedayError`.
    """
    try:
        return vikunja_refs.project_id(project_name)
    except VikunjaRefError as exc:
        raise RouteSomedayError(
            f"Cannot resolve project {project_name!r} via the reference registry: {exc}"
        ) from exc


def _attach_someday_label(client: VikunjaClient, task_id: int) -> bool:
    """Best-effort attach of the ``q:schedule`` label to ``task_id``.

    Returns ``True`` if the label was attached, ``False`` otherwise. It degrades
    (warns + returns ``False``) for only two cases: (1) the ``q:schedule`` label
    is **declared but not yet provisioned** in the registry
    (:class:`VikunjaRefUnprovisioned` — dormant, graceful), and (2) the attach
    ``PUT /tasks/<id>/labels`` fails with a Vikunja/network error (the felix-bot
    HTTP 403 case). A genuine registry breakage of the label reference — an
    undeclared name, wrong-owner token, or invalid provisioned id (any *other*
    :class:`VikunjaRefError`) — is NOT swallowed: it **propagates** so the caller
    surfaces it loudly. Attaches via ``PUT /tasks/<id>/labels`` with
    ``{"label_id": <id>}`` (the Vikunja task-label endpoint).
    """
    try:
        lbl_id = vikunja_refs.label_id(SOMEDAY_LABEL_NAME, SOMEDAY_LABEL_TOKEN)
    except VikunjaRefUnprovisioned as exc:
        # Label declared but not yet created in Vikunja -> dormant, graceful.
        _emit_warning(
            f"label {SOMEDAY_LABEL_NAME!r} is declared but not yet provisioned "
            f"in the registry: {exc}",
            label=SOMEDAY_LABEL_NAME,
            task_id=task_id,
        )
        return False

    try:
        client.put(f"/tasks/{task_id}/labels", json={"label_id": lbl_id})
    except (VikunjaError, ConnectionError) as exc:
        # Expected today: felix-bot receives HTTP 403 attaching the kent-owned
        # q:schedule label (#715 live-probe 2026-07-15). Log loud, do not lose
        # the task; #749 applies the label later.
        _emit_warning(
            f"could not attach label {SOMEDAY_LABEL_NAME!r} (id {lbl_id}) to "
            f"task {task_id}: {exc}",
            label=SOMEDAY_LABEL_NAME,
            label_id=lbl_id,
            task_id=task_id,
        )
        return False
    return True


def route_someday(
    title: str,
    body: str,
    note_filename: str,
    project: str = DEFAULT_PROJECT_NAME,
) -> int:
    """Create a ``q:schedule`` + no-due-date task and return its id.

    Resolves the destination ``project`` (default Inbox) through the reference
    seam, creates the task via ``PUT /projects/<id>/tasks`` with **no due
    date**, then best-effort attaches the ``q:schedule`` label. Returns the
    created task id on success. Raises :class:`RouteSomedayError` (wrapping any
    underlying Vikunja / network / registry failure) on any *hard* error path so
    the CLI ``main`` maps it to a single exit code + structured stderr. A soft
    label-attach failure does not raise — the task is already created.
    """
    try:
        client = VikunjaClient()
    except ValueError as exc:
        # Token/base-url config errors surface here. Treat as vikunja_error.
        raise RouteSomedayError(f"VikunjaClient construction failed: {exc}") from exc

    project_id = _resolve_destination_project_id(project)

    description = f"{body}\n\nSource: {note_filename}"
    # No due date: the "someday" state is important-but-not-date-committed.
    payload = {
        "title": title,
        "description": description,
    }
    try:
        response = client.put(f"/projects/{project_id}/tasks", json=payload)
    except (VikunjaError, ConnectionError) as exc:
        raise RouteSomedayError(
            f"Failed to create Vikunja task in project {project_id}: {exc}"
        ) from exc

    if not isinstance(response, dict) or "id" not in response:
        raise RouteSomedayError(
            f"Vikunja create-task response missing 'id': {str(response)[:200]}"
        )
    task_id = int(response["id"])

    # Anti-silent-loss: the task now exists. The label attach is fail-soft for
    # the unprovisioned-label and attach-403/network cases, but a genuine
    # registry breakage of the q:schedule reference must surface loudly (exit 2)
    # — while still naming the created task id so the capture is not orphaned.
    try:
        _attach_someday_label(client, task_id)
    except VikunjaRefError as exc:
        raise RouteSomedayError(
            f"Task {task_id} created, but the {SOMEDAY_LABEL_NAME!r} label registry "
            f"reference is broken (not the unprovisioned/attach-degrade case): {exc}"
        ) from exc

    return task_id


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="route_someday",
        description=(
            "Create a Vikunja 'someday' task (q:schedule label, no due date) for "
            "a captured note block. Lands in Inbox by default (or --project) and "
            "uses the CREATE endpoint PUT /projects/<id>/tasks; never "
            "partial-replaces an existing task."
        ),
    )
    parser.add_argument("--title", required=True, help="Task title.")
    parser.add_argument("--body", required=True, help="Task body / description.")
    parser.add_argument(
        "--note-filename",
        required=True,
        help="Source note filename; recorded as 'Source: <name>' footer in description.",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT_NAME,
        help=(
            "Logical project name (resolved via the reference registry) to land "
            f"the task in. Default: {DEFAULT_PROJECT_NAME!r} (the fall-through bucket)."
        ),
    )
    return parser


def _emit_error(detail: str) -> None:
    """Write a structured error envelope to stderr."""
    print(
        json.dumps({"error": "vikunja_error", "detail": detail}),
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        task_id = route_someday(
            title=args.title,
            body=args.body,
            note_filename=args.note_filename,
            project=args.project,
        )
    except RouteSomedayError as exc:
        _emit_error(str(exc))
        return 2

    print(f"task_id={task_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
