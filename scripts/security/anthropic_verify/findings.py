"""Finding dataclass + sanitization invariant for anthropic-verify.

The :class:`Finding` dataclass is the structured verdict produced by
``--check`` for each detected condition. Its ``__post_init__`` refuses
construction if any string field carries a key-shaped substring — this is
the C-005 / FR-006 / SC-007 "no key in output" backbone, enforced at the
data-structure boundary so format-time code paths can safely interpolate
the fields without an extra scrub.

Key-shape detection is intentionally permissive: any substring starting
with ``sk-ant-`` followed by at least 82 more non-whitespace characters
(total length >= 90) is treated as key-shaped. Real Anthropic keys are
~108 chars; the 90-char floor leaves headroom against future format
changes while keeping false positives near zero for normal evidence text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal


FindingType = Literal[
    "shadow",
    "drift",
    "anthropic_rejected",
    "network",
    "main_empty",
    "plaintext_missing",
]

# Real Anthropic keys start with ``sk-ant-`` and run ~108 chars (no whitespace).
# We reject any substring matching that shape so a stray field cannot leak a key.
KEY_SHAPE_PREFIX = "sk-ant-"
KEY_SHAPE_MIN_LEN = 90


@dataclass(frozen=True)
class Finding:
    """Structured verdict for one detected condition.

    Attributes
    ----------
    type
        One of the six FindingType literals.
    target
        Sub-agent ID for shadow; path for drift / plaintext_missing;
        ``"main"`` for main_empty; ``"anthropic"`` for *_rejected / network.
    evidence
        Type-specific deterministic fields. NEVER contains key values.
    suggested_action
        Single-line operator hint, copy-pasteable when possible.
    """

    type: FindingType
    target: str
    evidence: Dict[str, Any]
    suggested_action: str

    def __post_init__(self) -> None:
        # Sanitization invariant — refuse instantiation if any field carries a
        # key-shaped substring. This is the linchpin of C-005 (no key in
        # output). It runs on every Finding construction.
        if not self.target:
            raise ValueError("Finding rejected: target must be non-empty")
        if not self.type:
            raise ValueError("Finding rejected: type must be non-empty")
        for source in (str(self.evidence), self.suggested_action, self.target):
            self._refuse_if_key_shaped(source)

    @staticmethod
    def _refuse_if_key_shaped(text: str) -> None:
        idx = text.find(KEY_SHAPE_PREFIX)
        while idx != -1:
            window = text[idx : idx + KEY_SHAPE_MIN_LEN]
            # Key-shape: prefix + enough trailing non-whitespace chars to reach
            # the minimum length. Whitespace breaks the shape (it is not a key).
            if (
                len(window) >= KEY_SHAPE_MIN_LEN
                and " " not in window
                and "\n" not in window
                and "\t" not in window
                and "\r" not in window
            ):
                raise ValueError(
                    "Finding rejected: contains key-shaped substring; "
                    "sanitize before construction"
                )
            idx = text.find(KEY_SHAPE_PREFIX, idx + 1)

    def fmt_line(self) -> str:
        """Return human-readable summary lines per NFR-002 / contracts/cli.md.

        Each finding renders as a ``FIND`` header line plus indented
        evidence + suggested_action lines, joined by newlines so callers
        can ``print`` a single block.
        """
        if self.type == "shadow":
            header = (
                f"FIND  shadow {self.target}: "
                f"auth_profile_store={self.evidence.get('store_rows', 0)} "
                f"auth_profile_state={self.evidence.get('state_rows', 0)} "
                f"last_update_ms={self.evidence.get('last_update_ms', 0)}"
            )
            tail = [
                f"      sqlite_path={self.evidence.get('sqlite_path', '')}",
                f"      suggested_action: {self.suggested_action}",
            ]
        elif self.type == "drift":
            header = "FIND  drift plaintext-file vs main SQLite"
            tail = [
                f"      plaintext_sha8={self.evidence.get('plaintext_sha8', '')}  "
                f"sqlite_sha8={self.evidence.get('sqlite_sha8', '')}",
                f"      plaintext_path={self.evidence.get('plaintext_path', '')}",
                f"      sqlite_path={self.evidence.get('sqlite_path', '')}",
                f"      suggested_action: {self.suggested_action}",
            ]
        elif self.type == "anthropic_rejected":
            header = "FIND  anthropic_rejected"
            tail = [
                f"      http_status={self.evidence.get('http_status', '')}  "
                f"response_summary={self.evidence.get('response_summary', '')}",
                f"      suggested_action: {self.suggested_action}",
            ]
        elif self.type == "network":
            header = "FIND  network"
            tail = [
                f"      error_class={self.evidence.get('error_class', '')}  "
                f"error_message={self.evidence.get('error_message', '')}",
                f"      suggested_action: {self.suggested_action}",
            ]
        elif self.type == "main_empty":
            header = f"FIND  main_empty {self.target}"
            tail = [
                f"      sqlite_path={self.evidence.get('sqlite_path', '')}",
                f"      suggested_action: {self.suggested_action}",
            ]
        elif self.type == "plaintext_missing":
            header = f"FIND  plaintext_missing {self.target}"
            tail = [
                f"      plaintext_path={self.evidence.get('plaintext_path', '')}",
                f"      suggested_action: {self.suggested_action}",
            ]
        else:  # pragma: no cover - exhaustive Literal coverage above
            header = f"FIND  {self.type} {self.target}"
            tail = [f"      suggested_action: {self.suggested_action}"]
        return "\n".join([header, *tail])
