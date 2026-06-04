"""UC-1..UC-4 classification for divergence candidates (WP03 / T010).

Phase 3 of the 6-phase reconciliation cycle. Pure function from
(DivergenceCandidate, task) to a ClassifiedConflict label + reason codes.

Per research.md § Unknown 3 (Vikunja v0.24.6 returns ``updated_by: null``),
UC-1 (``kent_edit_after_felix_write``) and UC-2 (``operator_authored_field``)
collapse into a single ``uc1_uc2_divergence`` reason code — every divergence
implicitly fires it. UC-3 (downstream-affecting field) and UC-4 (manual
override signal) remain independent. UC-4 INVERTS class to ``auto_resolved``.

Contract: kitty-specs/.../contracts/cycle-pipeline.md § Phase 3.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.sync.diff import DivergenceCandidate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


REASON_CODES: tuple[str, ...] = (
    "uc1_uc2_divergence",
    "uc3_downstream_behavior",
    "uc4_manual_override",
)


# Fields whose value affects downstream Felix behavior. Divergences on these
# fields strengthen the unsafe-class signal. Curated default; downstream WPs
# may surface this via the driver's config without re-deriving the set.
DOWNSTREAM_AFFECTING_FIELDS: frozenset[str] = frozenset({
    "due_date",
    "project_id",
    "done",
    "repeat_after",
    "repeat_mode",
    "title",
})


# UC-4 markers. Either a label-title match OR a task-title prefix match.
MANUAL_OVERRIDE_LABEL: str = "felix:ignore"
MANUAL_OVERRIDE_TITLE_PREFIX: str = "[NO FELIX]"


# Class labels.
CLASS_AUTO_RESOLVED: str = "auto_resolved"
CLASS_UNSAFE: str = "unsafe_to_auto_resolve"


# ---------------------------------------------------------------------------
# ClassifiedConflict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifiedConflict:
    """A divergence with its class label and reason codes."""

    candidate: DivergenceCandidate
    class_: str
    unsafe_reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# UC-4 detection
# ---------------------------------------------------------------------------


def has_override_signal(task: dict) -> bool:
    """Return True iff the task carries an explicit operator-override marker.

    UC-4 fires when:
    - any of the task's labels has ``title == MANUAL_OVERRIDE_LABEL``
    - OR the task's title starts with ``MANUAL_OVERRIDE_TITLE_PREFIX``

    Operator-explicit markers are the only mechanism that REDUCES urgency
    (inverts class to auto_resolved).
    """
    labels = task.get("labels") or []
    if isinstance(labels, list):
        for label in labels:
            if isinstance(label, dict) and label.get("title") == MANUAL_OVERRIDE_LABEL:
                return True
    title = task.get("title")
    if isinstance(title, str) and title.startswith(MANUAL_OVERRIDE_TITLE_PREFIX):
        return True
    return False


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def classify(candidate: DivergenceCandidate, task: dict) -> ClassifiedConflict:
    """Label a DivergenceCandidate with class + reason codes.

    Rules (in order):
    1. UC-1/UC-2 (collapsed): every candidate is by definition a divergence;
       ``uc1_uc2_divergence`` is always present in reasons.
    2. UC-3: if ``candidate.field`` is in ``DOWNSTREAM_AFFECTING_FIELDS``, add
       ``uc3_downstream_behavior``.
    3. UC-4: if ``has_override_signal(task)``, add ``uc4_manual_override``
       AND set class to ``auto_resolved`` (UC-4 inverts).
    4. Otherwise: class is ``unsafe_to_auto_resolve``.

    Pure function. Deterministic on identical inputs.
    """
    reasons: list[str] = ["uc1_uc2_divergence"]

    if candidate.field in DOWNSTREAM_AFFECTING_FIELDS:
        reasons.append("uc3_downstream_behavior")

    override = has_override_signal(task)
    if override:
        reasons.append("uc4_manual_override")
        return ClassifiedConflict(
            candidate=candidate,
            class_=CLASS_AUTO_RESOLVED,
            unsafe_reasons=tuple(reasons),
        )

    return ClassifiedConflict(
        candidate=candidate,
        class_=CLASS_UNSAFE,
        unsafe_reasons=tuple(reasons),
    )
