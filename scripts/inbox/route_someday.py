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
3. Attaches the ``q:schedule`` label (resolved by id through the seam:
   ``label_id("q:schedule", "kent")``) via ``PUT /tasks/<id>/labels``. Under the
   single kent identity this attach is **fail-loud** (see below).

Anti-silent-loss + fail-loud attach (#743, #750)
------------------------------------------------
The task is **always created** first — that is the capture's durable landing.
The label attach then runs under the **single kent identity** (the token-seam
cutover, #860 phase 2). The felix-bot **HTTP 403** on the kent-owned
``q:schedule`` label — the #715/#750 two-token symptom that the old fail-soft
branch tolerated — can no longer occur, so that branch is **retired**: a genuine
attach failure now **fails loud** as a :class:`RouteSomedayError` that still
**names the created task id** (the capture is preserved; the failure surfaces at
exit 2 rather than being swallowed into a warning, so a real error — 500,
timeout, network drop — is never masked). The only remaining graceful degrade is
a label **declared but not yet provisioned** in the registry (a dormant registry
state, token-independent): that still logs loudly and the route succeeds
(exit 0), because there is no id to attach yet. The broader ``f:/q:/t:/loe:``
intake taxonomy remains deferred to #749 — this helper never guesses/attaches
labels not declared in the registry.

CLI (mandatory ``-m`` form per ``[[feedback_helper_m_invocation_form]]``)::

    python3 -m scripts.inbox.route_someday \
        --title "<title>" --body "<body>" --note-filename <name> [--project <name>]

Contract: ``task_id=<int>`` to stdout on success (exit 0). A hard failure emits
``{"error": ..., "detail": ...}`` JSON to stderr and exits 2 — this now includes
a genuine label-attach failure (fail-loud), whose error names the created task id
so the capture is not orphaned. The one soft case left — a declared-but-
unprovisioned label — emits a ``{"warning": ...}`` JSON line to stderr but does
**not** change the exit code (the task is safely created; there is no id to
attach yet).

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

    Used for the one remaining soft degrade — a declared-but-unprovisioned
    ``q:schedule`` label: the capture is already safely created, so this never
    changes the exit code — it makes the degraded state visible (never silently
    swallowed) so operators and the #749 loop can see it. A genuine attach
    failure is NOT soft anymore; it fails loud (see :func:`route_someday`).
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
    """Attach the ``q:schedule`` label to ``task_id`` (fail-loud on attach error).

    Returns ``True`` when the label is attached. The single remaining graceful
    degrade is case (1): the ``q:schedule`` label is **declared but not yet
    provisioned** in the registry (:class:`VikunjaRefUnprovisioned` — dormant,
    token-independent) — it warns and returns ``False`` because there is no id to
    attach yet. The felix-bot HTTP 403 fail-soft branch is **retired** (#750): the
    single kent identity cannot receive that 403, so the attach
    ``PUT /tasks/<id>/labels`` no longer swallows Vikunja/network errors — any
    such error **propagates** (fail-loud) and the caller maps it to a hard
    :class:`RouteSomedayError` naming the created task id. A genuine registry
    breakage of the label reference — an undeclared name, wrong-owner token, or
    invalid provisioned id (any *other* :class:`VikunjaRefError`) — likewise
    **propagates**. Attaches via ``PUT /tasks/<id>/labels`` with
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

    # Fail-loud: under the single kent identity a genuine attach failure (incl.
    # the retired felix-bot 403, or a real 500/timeout/network drop) must surface
    # — it propagates to route_someday, which raises RouteSomedayError naming the
    # created task id. No error is swallowed here.
    client.put(f"/tasks/{task_id}/labels", json={"label_id": lbl_id})
    return True


def route_someday(
    title: str,
    body: str,
    note_filename: str,
    project: str = DEFAULT_PROJECT_NAME,
    block_key: str | None = None,
) -> int:
    """Create a ``q:schedule`` + no-due-date task and return its id.

    Resolves the destination ``project`` (default Inbox) through the reference
    seam, creates the task via ``PUT /projects/<id>/tasks`` with **no due
    date**, then best-effort attaches the ``q:schedule`` label. Returns the
    created task id on success. Raises :class:`RouteSomedayError` (wrapping any
    underlying Vikunja / network / registry failure) on any *hard* error path so
    the CLI ``main`` maps it to a single exit code + structured stderr. A soft
    label-attach failure does not raise — the task is already created.

    When ``block_key`` is supplied, a second footer line ``Block: <block_key>``
    is written below ``Source: <note_filename>`` so a caller can look the task up
    by its originating note **and** the specific block within it (the #751
    provenance precheck — makes an in-process create idempotent *before* the side
    effect). The ``Source:`` line is left byte-for-byte intact so the delegated
    provenance-match path (which matches the exact ``Source:`` line) is
    unaffected. ``block_key`` defaults to ``None`` (no ``Block:`` line) so the
    CLI and any legacy caller are unchanged.
    """
    try:
        client = VikunjaClient()
    except ValueError as exc:
        # Token/base-url config errors surface here. Treat as vikunja_error.
        raise RouteSomedayError(f"VikunjaClient construction failed: {exc}") from exc

    project_id = _resolve_destination_project_id(project)

    description = f"{body}\n\nSource: {note_filename}"
    if block_key:
        description = f"{description}\nBlock: {block_key}"
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

    # Anti-silent-loss: the task now exists. Only a declared-but-unprovisioned
    # label degrades gracefully (handled inside _attach_someday_label). Every
    # other failure — a genuine attach error (the retired felix-bot 403, or a
    # real 500/timeout/network drop) OR a registry breakage of the q:schedule
    # reference — must surface loudly (exit 2) while still naming the created
    # task id so the capture is not orphaned.
    try:
        _attach_someday_label(client, task_id)
    except VikunjaRefError as exc:
        raise RouteSomedayError(
            f"Task {task_id} created, but the {SOMEDAY_LABEL_NAME!r} label registry "
            f"reference is broken (not the unprovisioned/attach-degrade case): {exc}"
        ) from exc
    except (VikunjaError, ConnectionError) as exc:
        raise RouteSomedayError(
            f"Task {task_id} created, but attaching the {SOMEDAY_LABEL_NAME!r} label "
            f"failed (fail-loud under the single kent identity): {exc}"
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
    parser.add_argument(
        "--block-key",
        default=None,
        help=(
            "Optional per-block provenance token; when set, a 'Block: <key>' "
            "footer line is added below 'Source:' so the task can be looked up by "
            "its originating block (the #751 idempotency precheck)."
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
            block_key=args.block_key,
        )
    except RouteSomedayError as exc:
        _emit_error(str(exc))
        return 2

    print(f"task_id={task_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
