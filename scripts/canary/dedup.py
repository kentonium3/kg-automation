"""Canary dedup state — keyed by ``component_id`` with a mandatory transition reset.

State file = a small JSON map ``component_id -> {"last_outcome": str,
"last_emitted_utc": ISO8601}``, written atomically (temp file in the same
directory + ``os.replace``) so a crash mid-write never leaves a partial/corrupt
file. A missing or corrupt state file loads as empty (fail-safe) — never a crash
(mirrors :mod:`scripts.trust.state`).

The dedup decision (:func:`decide`) is keyed by ``component_id`` and remembers
``last_outcome`` (NOT ``(component_id, outcome)``). This is the
``failed → healthy → failed`` guarantee (F7 / INV-F): any *change* in outcome
always emits, so a re-failure after a recovery is never swallowed by a stale
suppression window.

Deterministic: :func:`decide` takes ``now`` as an injected parameter; it never
calls ``datetime.now()`` itself, so tests drive the window boundary exactly.

References: data-model.md (DedupState, INV-F), research.md R5 (dedup),
contracts §4 (severity), WP04 T016.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

__all__ = [
    "DEFAULT_DEDUP_PATH",
    "DEFAULT_WINDOW",
    "load_state",
    "save_state",
    "decide",
]

logger = logging.getLogger(__name__)

# Home for the dedup state file (module constant; injectable via the ``path``
# parameter on load_state/save_state).
DEFAULT_DEDUP_PATH = Path("/data/services/felix-canary/state/dedup.json")

# Default re-remind window for an unchanged-bad outcome (data-model.md: 6 h).
DEFAULT_WINDOW = timedelta(hours=6)

# Outcomes that are "good" — a component in one of these is not paging. Only
# ``healthy`` is a true clean state; ``suppressed`` never reaches decide() (the
# runner never routes a gated component through dedup). Anything not here is
# "bad" and subject to the re-remind window.
_HEALTHY_OUTCOME = "healthy"


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def load_state(path: Path | str = DEFAULT_DEDUP_PATH) -> dict[str, dict[str, str]]:
    """Load the dedup state map; fail-safe (missing/corrupt -> ``{}``).

    A missing file is the expected first-run state. A corrupt/unreadable file is
    logged and treated as empty rather than raised — a state-file problem must
    never break the pass (NFR-001/INV-D); worst case is a spurious re-emit, never
    a crash.
    """
    target = Path(path)
    try:
        raw_text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning(
            "dedup.load_state: unreadable state file %s (%s); loading empty",
            target,
            exc,
        )
        return {}

    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "dedup.load_state: corrupt state file %s (%s); loading empty",
            target,
            exc,
        )
        return {}

    if not isinstance(document, dict):
        logger.warning(
            "dedup.load_state: state file %s is not a JSON object; loading empty",
            target,
        )
        return {}

    cleaned: dict[str, dict[str, str]] = {}
    for component_id, entry in document.items():
        if isinstance(entry, dict) and all(
            isinstance(entry.get(key), str)
            for key in ("last_outcome", "last_emitted_utc")
        ):
            cleaned[component_id] = {
                "last_outcome": entry["last_outcome"],
                "last_emitted_utc": entry["last_emitted_utc"],
            }
    return cleaned


def save_state(
    state: dict[str, dict[str, str]], path: Path | str = DEFAULT_DEDUP_PATH
) -> None:
    """Atomically write *state* to *path* (temp file in the same dir + ``os.replace``).

    Never partially writes: the temp file is written and fsync'd, then atomically
    renamed over the target. Raises on failure (e.g. unwritable directory) — the
    runner catches this and degrades to "state not persisted this tick" rather
    than crashing the pass.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def decide(
    component_id: str,
    outcome: str,
    now: datetime,
    state: dict[str, dict[str, str]],
    *,
    window: timedelta = DEFAULT_WINDOW,
) -> tuple[bool, bool, dict[str, str]]:
    """Decide whether *outcome* should emit for *component_id* this tick.

    Returns ``(should_emit, is_recovery, new_entry)`` where ``new_entry`` is the
    updated ``{"last_outcome", "last_emitted_utc"}`` map the caller stores back
    into the dedup state under ``component_id``.

    Rules (data-model.md DedupState / R5, keyed by ``component_id`` with
    ``last_outcome`` — the F7 mandatory reset):

    - ``last_outcome`` **differs** from *outcome* (any transition, including
      ``→ healthy``) ⇒ **always emit**; when the new outcome is ``healthy`` mark
      ``is_recovery=True`` (the runner renders an INFO "recovered"). The entry's
      ``last_emitted_utc`` advances to ``now``. This is INV-F — a health *change*
      is never swallowed, so ``failed → healthy → failed`` emits all three.
    - unchanged **and** bad **and** ``now - last_emitted_utc < window`` ⇒ suppress
      (``should_emit=False``); the entry is carried forward unchanged (the runner
      still ledgers the tick).
    - unchanged, bad, window elapsed ⇒ re-emit; ``last_emitted_utc`` advances.
    - ``healthy`` unchanged ⇒ no emit, no ``last_emitted_utc`` churn (the entry is
      carried forward so ``last_outcome`` stays recorded).

    ``now`` is injected; this function never calls :func:`datetime.now`.
    """
    now_str = _utc_iso(now)
    prior = state.get(component_id)
    prior_outcome = prior.get("last_outcome") if prior is not None else None
    is_healthy = outcome == _HEALTHY_OUTCOME

    # --- Transition: any change in outcome always emits (F7 / INV-F). ------- #
    # The one exception is a transition *to* healthy with no prior recorded
    # outcome (a first-seen healthy component): there is nothing to recover from
    # and healthy is not actionable, so it does not emit — but the entry is still
    # recorded so a later degradation-then-recovery is caught. A transition to
    # healthy *from a prior bad outcome* is a genuine recovery and emits INFO.
    if prior_outcome != outcome:
        if is_healthy and prior_outcome is None:
            new_entry = {"last_outcome": outcome, "last_emitted_utc": now_str}
            return False, False, new_entry
        is_recovery = is_healthy  # prior_outcome is not None here
        new_entry = {"last_outcome": outcome, "last_emitted_utc": now_str}
        return True, is_recovery, new_entry

    # --- Unchanged outcome. ------------------------------------------------- #
    # A healthy component that stays healthy: no emit, no churn — but keep the
    # entry so last_outcome remains recorded (carry the prior emitted timestamp).
    if is_healthy:
        carried = {
            "last_outcome": outcome,
            "last_emitted_utc": (
                prior.get("last_emitted_utc", now_str)
                if prior is not None
                else now_str
            ),
        }
        return False, False, carried

    # Unchanged and bad: re-remind only once the window has elapsed.
    last_emitted_str = (
        prior.get("last_emitted_utc") if prior is not None else None
    )
    try:
        last_emitted = _parse_iso(last_emitted_str) if last_emitted_str else None
    except ValueError:
        last_emitted = None

    if last_emitted is None:
        # No parseable prior emit time on an unchanged-bad entry — treat as due
        # (conservative: re-remind rather than silently never re-emitting).
        window_elapsed = True
    else:
        window_elapsed = (now - last_emitted) >= window

    if window_elapsed:
        new_entry = {"last_outcome": outcome, "last_emitted_utc": now_str}
        return True, False, new_entry

    # Suppress: carry the prior entry forward unchanged (last_emitted_utc holds).
    carried = {
        "last_outcome": outcome,
        "last_emitted_utc": last_emitted_str or now_str,
    }
    return False, False, carried
