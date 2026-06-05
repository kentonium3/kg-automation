#!/usr/bin/env python3
"""ADR-0002 Phase 3 habits schedule migration helper.

Reads ``habits-schedule.yaml`` describing per-task schedule changes;
captures a BEFORE-state snapshot to ``/data/services/openclaw/state/
habits-pre-phase3-snapshot.json``; then applies the changes via Vikunja
API calls authenticated as ``felix-bot``.

Tier 2 protocol: operator MUST set ``FELIX_TIER2_PREFLIGHT_OK=yes``
before any destructive HTTP call is issued (or use ``--dry-run`` to
preview safely without the gate).

Vikunja HTTP conventions (per ``docs/design/research/vikunja-task-model-research.md``):
    - Update a task: ``POST /tasks/<id>`` with partial body (NOT PATCH).
      The Vikunja v0.24.6 API uses POST for partial updates.
    - Create a task: ``PUT /projects/<project_id>/tasks`` with full body.
    - Delete a task: ``DELETE /tasks/<id>`` (irreversible).
    - Comment-create endpoint is PUT, not POST (gotcha G4). This helper
      does not write comments — record_completion.py handles that path.

Design references:
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md
        FR-001..FR-005, FR-012, FR-014, NFR-001, NFR-004; C-002, C-003,
        C-004, C-007.
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/{api,cli,config}.md
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/data-model.md
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md
        D1 (urllib), D3 (transaction model), D6 (idempotency),
        D8 (validation), D9 (due-date computation), D10 (gotchas).
    - scripts/vikunja/provision_felix_bot.py (urllib pattern reference).
    - scripts/habits/identify_workout_task.py (companion lookup helper).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover — handled at runtime only
    print(
        "ERROR: PyYAML is required. Install via repo requirements.txt.",
        file=sys.stderr,
    )
    sys.exit(2)

from scripts.common.vikunja_config import get_vikunja_base_url


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_BASE_URL: str = ""

#: Default location of the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"

#: Default snapshot output path. Operator may override via ``--snapshot-out``.
DEFAULT_SNAPSHOT_PATH = (
    "/data/services/openclaw/state/habits-pre-phase3-snapshot.json"
)

#: Environment variable that the operator MUST set (=="yes") before any
#: destructive HTTP call is issued. ``--dry-run`` exempts the gate.
PREFLIGHT_ENV_VAR = "FELIX_TIER2_PREFLIGHT_OK"

#: Valid ``op`` values for entries in ``operations``.
VALID_OPS = {"patch", "retire", "create"}

#: Valid ``repeat_mode`` values per Vikunja v0.24.6.
VALID_REPEAT_MODES = {0, 1, 2}

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS = 30

#: Snapshot schema version. Bumped on breaking changes to the snapshot file.
SNAPSHOT_SCHEMA_VERSION = "1"

#: Regex that pulls a canonical weekday name out of a create-op title
#: (e.g. ``"Strength training — Monday"`` -> ``"Monday"``). Case-sensitive on
#: purpose: titles with lowercase ``monday`` are not the same as a canonical
#: weekday hint.
WEEKDAY_TITLE_RE = re.compile(
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b"
)

#: Map weekday name to Python's ``datetime.weekday()`` (Monday=0).
WEEKDAY_INDEX = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

#: 86400 = daily; 604800 = weekly. Other intervals are passed through.
SECONDS_PER_DAY = 86400
SECONDS_PER_WEEK = 604800


# ---------------------------------------------------------------------------
# T004 — load_schedule + YAML schema validation
# ---------------------------------------------------------------------------


def _validation_error(op_index: int, message: str) -> ValueError:
    """Construct a ``ValueError`` whose message names the operation index."""
    return ValueError(f"Operation {op_index}: {message}")


def _check_repeat_block(op_index: int, block: Any, block_name: str) -> None:
    """Validate a ``{repeat_after, repeat_mode}`` sub-dict for ``patch``/``create`` ops."""
    if not isinstance(block, dict):
        raise _validation_error(
            op_index, f"missing or non-dict '{block_name}' block"
        )
    repeat_after = block.get("repeat_after")
    if not isinstance(repeat_after, int) or isinstance(repeat_after, bool):
        raise _validation_error(
            op_index, f"'{block_name}.repeat_after' must be a positive integer"
        )
    if repeat_after <= 0:
        raise _validation_error(
            op_index,
            f"'{block_name}.repeat_after' must be > 0 (got {repeat_after})",
        )
    repeat_mode = block.get("repeat_mode")
    if not isinstance(repeat_mode, int) or isinstance(repeat_mode, bool):
        raise _validation_error(
            op_index, f"'{block_name}.repeat_mode' must be an integer in {sorted(VALID_REPEAT_MODES)}"
        )
    if repeat_mode not in VALID_REPEAT_MODES:
        raise _validation_error(
            op_index,
            f"'{block_name}.repeat_mode' must be one of {sorted(VALID_REPEAT_MODES)} (got {repeat_mode})",
        )


def _check_positive_task_id(op_index: int, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _validation_error(
            op_index, "'task_id' must be a positive integer"
        )
    if value <= 0:
        raise _validation_error(
            op_index, f"'task_id' must be > 0 (got {value})"
        )


def _check_due_date(op_index: int, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _validation_error(
            op_index, "'due_date' must be a non-empty ISO-8601 string"
        )
    try:
        # Accept ``Z`` suffix by normalizing to +00:00.
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise _validation_error(
            op_index, f"'due_date' is not valid ISO-8601: {value!r} ({e})"
        ) from e
    if parsed.tzinfo is None:
        raise _validation_error(
            op_index,
            f"'due_date' must include a timezone offset (got {value!r})",
        )


def load_schedule(path: Path) -> dict:
    """Load and validate ``habits-schedule.yaml``.

    Args:
        path: Filesystem path to the YAML config file.

    Returns:
        The validated dict (unchanged from ``yaml.safe_load`` output) matching
        the schema in ``contracts/config.md``.

    Raises:
        ValueError: On any schema violation. Error message names the offending
            operation index + field + violation.
        OSError: On file-read error (``FileNotFoundError``, ``PermissionError``).
    """
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Schedule file {path} top-level must be a YAML mapping (got "
            f"{type(data).__name__})"
        )

    mission_id = data.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id.strip():
        raise ValueError(
            f"Schedule file {path} missing required non-empty string "
            "'mission_id'"
        )

    operations = data.get("operations")
    if not isinstance(operations, list):
        raise ValueError(
            f"Schedule file {path} 'operations' must be a list (got "
            f"{type(operations).__name__})"
        )

    seen_task_ids: set[int] = set()
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            raise _validation_error(
                i, f"must be a YAML mapping (got {type(op).__name__})"
            )
        op_name = op.get("op")
        if op_name not in VALID_OPS:
            raise _validation_error(
                i,
                f"unknown op '{op_name}' (expected one of {sorted(VALID_OPS)})",
            )

        if op_name in ("patch", "retire"):
            _check_positive_task_id(i, op.get("task_id"))
            tid = op["task_id"]
            if tid in seen_task_ids:
                raise _validation_error(
                    i, f"duplicate task_id {tid} (already touched by an earlier op)"
                )
            seen_task_ids.add(tid)

        if op_name == "patch":
            _check_repeat_block(i, op.get("target"), "target")

        if op_name == "create":
            _check_repeat_block(i, op.get("schedule"), "schedule")
            attributes = op.get("attributes")
            if not isinstance(attributes, dict):
                raise _validation_error(
                    i, "missing or non-dict 'attributes' block"
                )
            title = attributes.get("title")
            if not isinstance(title, str) or not title.strip():
                raise _validation_error(
                    i, "'attributes.title' must be a non-empty string"
                )
            if "due_date" in attributes:
                _check_due_date(i, attributes["due_date"])
            if "project_id" in attributes:
                pid = attributes["project_id"]
                if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                    raise _validation_error(
                        i,
                        f"'attributes.project_id' must be a positive integer "
                        f"(got {pid!r})",
                    )
            if "labels" in attributes and not isinstance(attributes["labels"], list):
                raise _validation_error(
                    i,
                    f"'attributes.labels' must be a list (got "
                    f"{type(attributes['labels']).__name__})",
                )

    return data


# ---------------------------------------------------------------------------
# T005 — HTTP helpers + capture_snapshot + apply_schedule
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> tuple[int, Any]:
    """Issue an authenticated HTTP request via ``urllib``.

    Args:
        method: ``GET``, ``POST``, ``PUT``, ``DELETE``.
        url: Fully qualified URL.
        token: Vikunja bearer token.
        body: Optional dict — serialized to JSON if present.

    Returns:
        Tuple ``(status_code, parsed_json_or_none)``. ``parsed_json_or_none``
        is None when the response body is empty or non-JSON.

    Raises:
        OSError: On network error or non-2xx HTTP status. The message includes
            the method + URL + (when available) the server's error body so the
            operator can triage quickly.
    """
    data: bytes | None = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover — purely defensive
            err_body = ""
        raise OSError(
            f"{method} {url} failed with HTTP {e.code}: {err_body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"{method} {url} network failure: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"{method} {url} returned HTTP {status}: {raw!r}")

    parsed: Any = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OSError(
                f"{method} {url} returned non-JSON body: {raw!r} ({e})"
            ) from e
    return status, parsed


def _fetch_task(api_base_url: str, token: str, task_id: int) -> dict:
    """GET a Vikunja task and return the fields relevant to Phase 3."""
    url = _join_url(api_base_url, f"tasks/{task_id}")
    _status, payload = _http_request("GET", url, token)
    if not isinstance(payload, dict):
        raise OSError(
            f"GET {url} returned a non-object body (got "
            f"{type(payload).__name__})"
        )
    return {
        "id": payload.get("id", task_id),
        "title": payload.get("title", ""),
        "repeat_after": payload.get("repeat_after", 0),
        "repeat_mode": payload.get("repeat_mode", 0),
        "done": bool(payload.get("done", False)),
        "due_date": payload.get("due_date"),
        "project_id": payload.get("project_id"),
        "labels": payload.get("labels") or [],
        "is_archived": bool(payload.get("is_archived", False)),
        "done_at": payload.get("done_at"),
    }


def _config_sha256(schedule: dict) -> str:
    """Stable SHA-256 of the schedule dict for the snapshot manifest."""
    serialized = json.dumps(
        schedule, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 with offset (e.g. 2026-05-20T12:00:00+00:00)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def capture_snapshot(api_base_url: str, token: str, schedule: dict) -> dict:
    """Capture BEFORE-state of every task touched by ``schedule``.

    Refuses to proceed (raises ``ValueError``) if a ``retire`` op targets a
    task whose ``repeat_after`` is non-zero — Vikunja's auto-advance would
    un-retire the task on next tick.

    Args:
        api_base_url: Vikunja API base URL.
        token: Vikunja bearer token.
        schedule: Validated schedule dict (output of ``load_schedule``).

    Returns:
        Snapshot dict per ``data-model.md`` Entity 3 with empty
        ``applied_changes`` and ``created_tasks`` lists. Caller is responsible
        for persisting via ``_persist_snapshot``.

    Raises:
        OSError: On network/HTTP error during the BEFORE-state fetches.
        ValueError: If a retire op targets a task with ``repeat_after != 0``.
    """
    before_states: list[dict] = []
    seen_ids: set[int] = set()

    for op in schedule["operations"]:
        op_name = op["op"]
        if op_name in ("patch", "retire"):
            task_id = op["task_id"]
            if task_id in seen_ids:
                # load_schedule rejects duplicates; defensive guard only.
                continue
            seen_ids.add(task_id)
            task = _fetch_task(api_base_url, token, task_id)
            if op_name == "retire" and task.get("repeat_after", 0) != 0:
                raise ValueError(
                    f"Cannot retire task {task_id}: BEFORE state has "
                    f"repeat_after={task['repeat_after']} (non-zero). "
                    "Vikunja's auto-advance would un-retire the task on next "
                    "tick. Either patch repeat_after to 0 first, or remove "
                    "the retire op from the schedule."
                )
            before_states.append(
                {
                    "task_id": task_id,
                    "before": {
                        "repeat_after": task.get("repeat_after", 0),
                        "repeat_mode": task.get("repeat_mode", 0),
                        "done": task.get("done", False),
                        "due_date": task.get("due_date"),
                        "is_archived": task.get("is_archived", False),
                        "done_at": task.get("done_at"),
                        "title": task.get("title", ""),
                        "project_id": task.get("project_id"),
                        "labels": task.get("labels") or [],
                    },
                    "intended_op": op_name,
                }
            )

    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "mission_id": schedule["mission_id"],
        "mission_slug": schedule.get("mission_slug"),
        "captured_at": _now_iso(),
        "config_file_sha256": _config_sha256(schedule),
        "before_states": before_states,
        "created_tasks": [],
        "applied_changes": [],
    }
    return snapshot


def _persist_snapshot(snapshot: dict, path: Path) -> None:
    """Write ``snapshot`` to ``path`` atomically.

    Pattern: write to ``<path>.tmp`` -> ``os.fsync(fd)`` -> ``rename``.
    Subsequent updates re-run the same pattern; intermediate states never
    leave a partially written JSON file at ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(serialized)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o644)
    except OSError:  # pragma: no cover — best-effort on non-POSIX FS
        pass


def _find_before_state(snapshot: dict, task_id: int) -> dict | None:
    for entry in snapshot.get("before_states", []):
        if entry.get("task_id") == task_id:
            return entry
    return None


def _default_due_date(title: str, repeat_after: int, *, run_date: datetime | None = None) -> str:
    """Compute the default due_date for a create op (research D9).

    Weekly schedules (``repeat_after == 604800``): next Monday/Tuesday/...
    inferred from the title at 08:00 UTC. If today is already that weekday,
    today at 08:00 UTC.

    Daily schedules (``repeat_after == 86400``): tomorrow at 08:00 UTC.

    Other intervals: ``run_date + repeat_after seconds`` at 08:00 UTC.

    Args:
        title: Create op's ``attributes.title`` (used to extract weekday hint).
        repeat_after: ``schedule.repeat_after`` value (seconds).
        run_date: Optional injected current date for deterministic testing.
            Defaults to ``datetime.now(timezone.utc)``.

    Returns:
        ISO-8601 datetime string with ``+00:00`` offset.
    """
    now = run_date if run_date is not None else datetime.now(timezone.utc)
    base = now.replace(hour=8, minute=0, second=0, microsecond=0)

    if repeat_after == SECONDS_PER_WEEK:
        match = WEEKDAY_TITLE_RE.search(title)
        if match:
            target = WEEKDAY_INDEX[match.group(1)]
            days_ahead = (target - now.weekday()) % 7
            due = base + timedelta(days=days_ahead)
            return due.isoformat(timespec="seconds")
        # No weekday hint — fall through to "next week same day at 08:00 UTC".
        due = base + timedelta(days=7)
        return due.isoformat(timespec="seconds")

    if repeat_after == SECONDS_PER_DAY:
        due = base + timedelta(days=1)
        return due.isoformat(timespec="seconds")

    # Generic: today + repeat_after seconds, but normalized to 08:00 UTC.
    due = base + timedelta(seconds=repeat_after)
    return due.isoformat(timespec="seconds")


def _apply_patch(
    api_base_url: str, token: str, op: dict
) -> dict:
    """POST to update an existing task's schedule (Vikunja uses POST not PATCH)."""
    url = _join_url(api_base_url, f"tasks/{op['task_id']}")
    body = {
        "repeat_after": op["target"]["repeat_after"],
        "repeat_mode": op["target"]["repeat_mode"],
    }
    _status, parsed = _http_request("POST", url, token, body=body)
    if not isinstance(parsed, dict):
        raise OSError(
            f"POST {url} (patch) returned non-object body (got "
            f"{type(parsed).__name__})"
        )
    return parsed


def _apply_retire(
    api_base_url: str, token: str, op: dict
) -> dict:
    """POST to mark an existing task ``done=true`` (Vikunja uses POST for updates)."""
    url = _join_url(api_base_url, f"tasks/{op['task_id']}")
    body = {"done": True}
    _status, parsed = _http_request("POST", url, token, body=body)
    if not isinstance(parsed, dict):
        raise OSError(
            f"POST {url} (retire) returned non-object body (got "
            f"{type(parsed).__name__})"
        )
    return parsed


def _resolve_create_defaults(
    op: dict,
    *,
    inherit_project_id: int | None,
    inherit_labels: list | None,
    run_date: datetime | None = None,
) -> tuple[int, str, list]:
    """Resolve ``project_id``, ``due_date``, and ``labels`` for a create op.

    Returns a tuple ``(project_id, due_date_iso, labels)``.

    Raises ``ValueError`` if ``project_id`` cannot be resolved (no explicit
    attribute and no retire op preceded this create to inherit from).
    """
    attributes = op["attributes"]
    project_id = attributes.get("project_id", inherit_project_id)
    if project_id is None:
        raise ValueError(
            f"Create op for title {attributes['title']!r} has no "
            "'attributes.project_id' and no preceding retire op to inherit "
            "from. Specify 'project_id' explicitly in the schedule."
        )
    labels = attributes.get("labels", inherit_labels or [])
    due_date = attributes.get("due_date") or _default_due_date(
        attributes["title"],
        op["schedule"]["repeat_after"],
        run_date=run_date,
    )
    return project_id, due_date, labels


def _apply_create(
    api_base_url: str,
    token: str,
    op: dict,
    *,
    inherit_project_id: int | None = None,
    inherit_labels: list | None = None,
    run_date: datetime | None = None,
) -> dict:
    """PUT to ``/projects/<id>/tasks`` to create a new task."""
    project_id, due_date, labels = _resolve_create_defaults(
        op,
        inherit_project_id=inherit_project_id,
        inherit_labels=inherit_labels,
        run_date=run_date,
    )
    url = _join_url(api_base_url, f"projects/{project_id}/tasks")
    body = {
        "title": op["attributes"]["title"],
        "due_date": due_date,
        "repeat_after": op["schedule"]["repeat_after"],
        "repeat_mode": op["schedule"]["repeat_mode"],
        "labels": labels,
    }
    _status, parsed = _http_request("PUT", url, token, body=body)
    if not isinstance(parsed, dict):
        raise OSError(
            f"PUT {url} (create) returned non-object body (got "
            f"{type(parsed).__name__})"
        )
    return parsed


def apply_schedule(
    api_base_url: str,
    token: str,
    schedule: dict,
    snapshot_path: Path,
    dry_run: bool = False,
    run_date: datetime | None = None,
) -> dict:
    """Apply the schedule's operations, persisting snapshot incrementally.

    Args:
        api_base_url, token: Vikunja API access.
        schedule: Validated schedule dict (from ``load_schedule``).
        snapshot_path: Where to write the snapshot. Updated after every
            applied change (atomic ``tmp + fsync + rename`` pattern).
        dry_run: If True, prints intended changes but issues no
            mutation calls. BEFORE-state fetches still occur (read-only).
        run_date: Optional injected current date for default due-date
            computation (deterministic testing).

    Returns:
        Final snapshot dict (also written to ``snapshot_path``).

    Raises:
        OSError: On unrecoverable HTTP failure mid-batch. The snapshot on
            disk reflects the partial state and can be used for rollback.
        ValueError: On schedule-level invariants (e.g., retire op against a
            task with ``repeat_after != 0``).
    """
    snapshot = capture_snapshot(api_base_url, token, schedule)
    _persist_snapshot(snapshot, snapshot_path)

    operations = schedule["operations"]
    total = len(operations)

    if dry_run:
        for i, op in enumerate(operations, start=1):
            print(_describe_op(i, total, op, snapshot, dry_run=True, run_date=run_date))
        print(
            f"SUMMARY: dry-run complete; {total} operations planned; "
            f"BEFORE-state captured at {snapshot_path}"
        )
        return snapshot

    # Track the most recent retire op's project_id + labels so subsequent
    # create ops can inherit them. Per data-model.md, Phase 3's MWF tasks
    # inherit the workout task's project + labels.
    inherit_project_id: int | None = None
    inherit_labels: list | None = None

    for i, op in enumerate(operations, start=1):
        op_name = op["op"]
        applied_at = _now_iso()
        try:
            if op_name == "patch":
                # Idempotency: if BEFORE already matches target, skip the POST.
                before = _find_before_state(snapshot, op["task_id"])
                target = op["target"]
                if (
                    before is not None
                    and before["before"]["repeat_after"] == target["repeat_after"]
                    and before["before"]["repeat_mode"] == target["repeat_mode"]
                ):
                    print(
                        f"[{i}/{total}] op=patch task_id={op['task_id']} "
                        f"already matches target (repeat_after="
                        f"{target['repeat_after']}, repeat_mode="
                        f"{target['repeat_mode']}) [SKIPPED]"
                    )
                    snapshot["applied_changes"].append(
                        {
                            "task_id": op["task_id"],
                            "op": "patch",
                            "applied_at": applied_at,
                            "result": "skipped",
                        }
                    )
                    _persist_snapshot(snapshot, snapshot_path)
                    continue

                _apply_patch(api_base_url, token, op)
                print(
                    f"[{i}/{total}] op=patch task_id={op['task_id']}: "
                    f"repeat_after={target['repeat_after']} "
                    f"repeat_mode={target['repeat_mode']} [OK]"
                )
                snapshot["applied_changes"].append(
                    {
                        "task_id": op["task_id"],
                        "op": "patch",
                        "applied_at": applied_at,
                        "result": "success",
                    }
                )
                _persist_snapshot(snapshot, snapshot_path)

            elif op_name == "retire":
                _apply_retire(api_base_url, token, op)
                print(
                    f"[{i}/{total}] op=retire task_id={op['task_id']}: "
                    "done=true [OK]"
                )
                # Capture the retired task's project_id + labels so subsequent
                # create ops in this run can inherit them.
                before = _find_before_state(snapshot, op["task_id"])
                if before is not None:
                    inherit_project_id = before["before"].get("project_id")
                    inherit_labels = before["before"].get("labels") or []
                snapshot["applied_changes"].append(
                    {
                        "task_id": op["task_id"],
                        "op": "retire",
                        "applied_at": applied_at,
                        "result": "success",
                    }
                )
                _persist_snapshot(snapshot, snapshot_path)

            elif op_name == "create":
                response = _apply_create(
                    api_base_url,
                    token,
                    op,
                    inherit_project_id=inherit_project_id,
                    inherit_labels=inherit_labels,
                    run_date=run_date,
                )
                new_id = response.get("id")
                title = op["attributes"]["title"]
                print(
                    f"[{i}/{total}] op=create title={title!r} -> "
                    f"task_id={new_id} [OK]"
                )
                snapshot["created_tasks"].append(
                    {
                        "task_id": new_id,
                        "title": title,
                        "created_at": applied_at,
                    }
                )
                snapshot["applied_changes"].append(
                    {
                        "task_id": new_id,
                        "op": "create",
                        "applied_at": applied_at,
                        "result": "success",
                    }
                )
                _persist_snapshot(snapshot, snapshot_path)

        except OSError as e:
            # Persist the partial snapshot for the rollback path.
            snapshot["applied_changes"].append(
                {
                    "task_id": op.get("task_id"),
                    "op": op_name,
                    "applied_at": applied_at,
                    "result": "error",
                    "error": str(e),
                }
            )
            _persist_snapshot(snapshot, snapshot_path)
            raise

    applied = sum(
        1
        for c in snapshot["applied_changes"]
        if c.get("result") in ("success", "skipped")
    )
    print(
        f"SUMMARY: applied {applied}/{total} operations; snapshot at "
        f"{snapshot_path}"
    )
    return snapshot


def _describe_op(
    i: int,
    total: int,
    op: dict,
    snapshot: dict,
    *,
    dry_run: bool,
    run_date: datetime | None = None,
) -> str:
    """Human-readable per-op status line for dry-run output."""
    op_name = op["op"]
    prefix = f"[{i}/{total}]"
    if op_name == "patch":
        before = _find_before_state(snapshot, op["task_id"])
        before_repeat = (
            before["before"]["repeat_after"] if before else "?"
        )
        target = op["target"]
        return (
            f"{prefix} op=patch task_id={op['task_id']}: "
            f"before(repeat_after={before_repeat}) -> "
            f"after(repeat_after={target['repeat_after']}, "
            f"repeat_mode={target['repeat_mode']}) [DRY-RUN]"
        )
    if op_name == "retire":
        return (
            f"{prefix} op=retire task_id={op['task_id']}: "
            "done=true [DRY-RUN]"
        )
    if op_name == "create":
        attributes = op["attributes"]
        due = attributes.get("due_date") or _default_due_date(
            attributes["title"],
            op["schedule"]["repeat_after"],
            run_date=run_date,
        )
        return (
            f"{prefix} op=create title={attributes['title']!r} "
            f"repeat_after={op['schedule']['repeat_after']} "
            f"due_date={due} [DRY-RUN]"
        )
    return f"{prefix} unknown op {op_name!r}"


# ---------------------------------------------------------------------------
# T006 — rollback + CLI
# ---------------------------------------------------------------------------


def rollback(
    api_base_url: str, token: str, snapshot_path: Path
) -> dict:
    """Reverse every change recorded in the snapshot's ``applied_changes``.

    Iterates in REVERSE order so most-recent changes are undone first:
        - ``patch`` op -> POST back to BEFORE-state values.
        - ``retire`` op -> POST with ``done=false`` (un-retire).
        - ``create`` op -> DELETE the created task.
        - ``skipped`` results are no-ops (nothing to reverse).
        - ``error`` results are no-ops (the mutation never landed).

    Each successful reversal appends a new entry to ``applied_changes`` with
    ``op = "rollback_<orig_op>"`` so the audit trail records both the original
    change and the reversal.

    Args:
        api_base_url, token: Vikunja API access.
        snapshot_path: Path to an existing snapshot.

    Returns:
        Updated snapshot dict (also written to ``snapshot_path``).

    Raises:
        OSError: On HTTP error during rollback. Partial annotation is
            persisted; operator triages.
        ValueError: If the snapshot file is missing, malformed, or has an
            unsupported ``schema_version``.
    """
    if not snapshot_path.exists():
        raise ValueError(f"Snapshot file not found: {snapshot_path}")
    raw = snapshot_path.read_text(encoding="utf-8")
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Snapshot {snapshot_path} is not valid JSON: {e}"
        ) from e
    if not isinstance(snapshot, dict):
        raise ValueError(
            f"Snapshot {snapshot_path} top-level must be a JSON object"
        )
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"Snapshot {snapshot_path} has unsupported schema_version "
            f"{snapshot.get('schema_version')!r} (expected "
            f"{SNAPSHOT_SCHEMA_VERSION!r})"
        )

    applied_changes = snapshot.get("applied_changes", [])
    # Snapshot ordering invariant: changes are appended in apply-order.
    # Take a copy of the original sequence to iterate (we'll mutate the list
    # by appending rollback entries).
    original_changes = [c for c in applied_changes]
    reverse_target = [c for c in original_changes if c.get("result") == "success"]

    total = len(reverse_target)
    reversed_count = 0
    for idx, change in enumerate(reversed(reverse_target), start=1):
        op_name = change["op"]
        task_id = change.get("task_id")
        applied_at = _now_iso()
        try:
            if op_name == "patch":
                before = _find_before_state(snapshot, task_id)
                if before is None:
                    raise ValueError(
                        f"Snapshot missing before_state for task {task_id} "
                        "(cannot reverse patch)"
                    )
                url = _join_url(api_base_url, f"tasks/{task_id}")
                body = {
                    "repeat_after": before["before"]["repeat_after"],
                    "repeat_mode": before["before"]["repeat_mode"],
                }
                _http_request("POST", url, token, body=body)
                print(
                    f"[{idx}/{total}] reverse op=patch task_id={task_id}: "
                    f"repeat_after={body['repeat_after']} "
                    f"repeat_mode={body['repeat_mode']} [OK]"
                )
                snapshot["applied_changes"].append(
                    {
                        "task_id": task_id,
                        "op": "rollback_patch",
                        "applied_at": applied_at,
                        "result": "success",
                    }
                )

            elif op_name == "retire":
                before = _find_before_state(snapshot, task_id)
                if before is None:
                    raise ValueError(
                        f"Snapshot missing before_state for task {task_id} "
                        "(cannot reverse retire)"
                    )
                # Pre-flight check guarantees BEFORE done was False.
                url = _join_url(api_base_url, f"tasks/{task_id}")
                body = {"done": bool(before["before"].get("done", False))}
                _http_request("POST", url, token, body=body)
                print(
                    f"[{idx}/{total}] reverse op=retire task_id={task_id}: "
                    f"done={body['done']} [OK]"
                )
                snapshot["applied_changes"].append(
                    {
                        "task_id": task_id,
                        "op": "rollback_retire",
                        "applied_at": applied_at,
                        "result": "success",
                    }
                )

            elif op_name == "create":
                url = _join_url(api_base_url, f"tasks/{task_id}")
                _http_request("DELETE", url, token)
                print(
                    f"[{idx}/{total}] reverse op=create task_id={task_id}: "
                    "DELETE [OK]"
                )
                snapshot["applied_changes"].append(
                    {
                        "task_id": task_id,
                        "op": "rollback_create",
                        "applied_at": applied_at,
                        "result": "success",
                    }
                )

            else:
                # Skip unknown ops defensively (rollback_* annotations or
                # future op types). Do not raise — partial rollback is
                # operator-triageable.
                continue

            reversed_count += 1
            _persist_snapshot(snapshot, snapshot_path)

        except OSError as e:
            snapshot["applied_changes"].append(
                {
                    "task_id": task_id,
                    "op": f"rollback_{op_name}",
                    "applied_at": applied_at,
                    "result": "error",
                    "error": str(e),
                }
            )
            _persist_snapshot(snapshot, snapshot_path)
            raise

    print(
        f"SUMMARY: rollback complete; {reversed_count} changes reversed"
    )
    return snapshot


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_schedule",
        description=(
            "ADR-0002 Phase 3 habits schedule migration helper. Reads "
            "habits-schedule.yaml; captures BEFORE-state snapshot; applies "
            "schedule changes via Vikunja API. Tier 2 protocol — operator "
            f"must set {PREFLIGHT_ENV_VAR}=yes before any mutation, or use "
            "--dry-run to preview safely."
        ),
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        help=(
            "Path to habits-schedule.yaml. Required unless --rollback."
        ),
    )
    parser.add_argument(
        "--snapshot-out",
        type=Path,
        default=Path(DEFAULT_SNAPSHOT_PATH),
        help=(
            "Path to write the BEFORE-state JSON snapshot "
            f"(default: {DEFAULT_SNAPSHOT_PATH})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Preview the planned operations without issuing any mutation "
            "calls. BEFORE-state snapshot is still written."
        ),
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help=(
            "Reverse-apply changes from a prior run using --snapshot-file."
        ),
    )
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        help="Path to existing snapshot (required for --rollback).",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path(DEFAULT_TOKEN_PATH),
        help=(
            "Path to the Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file).",
    )
    return parser


def _read_token(token_file: Path) -> str:
    try:
        content = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError as e:
        raise OSError(f"Token file not found: {token_file}") from e
    except PermissionError as e:
        raise OSError(
            f"Token file not readable (permission denied): {token_file}"
        ) from e
    except OSError as e:
        raise OSError(f"Could not read token file {token_file}: {e}") from e
    if not content:
        raise OSError(f"Token file is empty: {token_file}")
    return content


def _preflight_message() -> str:
    return (
        f"REFUSED: This is a Tier 2 operation. Before running, confirm a "
        f"recent Restic snapshot exists for /data and set "
        f"{PREFLIGHT_ENV_VAR}=yes in the environment. Use --dry-run to "
        f"preview without the gate. See docs/runbooks/governance/"
        f"pre-flight-checklist.md for details."
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    args.base_url = args.base_url or get_vikunja_base_url()

    if args.rollback:
        if args.snapshot_file is None:
            print(
                "ERROR: --rollback requires --snapshot-file <path>",
                file=sys.stderr,
            )
            return 2
        try:
            token = _read_token(args.token_file)
        except OSError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 3
        try:
            rollback(args.base_url, token, args.snapshot_file)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        except OSError as e:
            print(f"ERROR: rollback aborted mid-batch: {e}", file=sys.stderr)
            print(
                f"Snapshot at {args.snapshot_file} reflects the partial "
                "state. Operator triage required.",
                file=sys.stderr,
            )
            return 1
        return 0

    # Apply path.
    if args.schedule is None:
        print(
            "ERROR: --schedule <path> is required (unless --rollback)",
            file=sys.stderr,
        )
        return 2

    # Tier 2 gate: mutation requires either --dry-run OR FELIX_TIER2_PREFLIGHT_OK=yes.
    if not args.dry_run and os.environ.get(PREFLIGHT_ENV_VAR) != "yes":
        print(_preflight_message(), file=sys.stderr)
        return 3

    try:
        token = _read_token(args.token_file)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    try:
        schedule = load_schedule(args.schedule)
    except ValueError as e:
        print(f"ERROR: schedule validation failed: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: could not read schedule {args.schedule}: {e}", file=sys.stderr)
        return 3

    try:
        apply_schedule(
            args.base_url,
            token,
            schedule,
            args.snapshot_out,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: apply aborted mid-batch: {e}", file=sys.stderr)
        print(
            f"Snapshot at {args.snapshot_out} reflects the partial state. "
            "Use --rollback to reverse the applied changes.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
