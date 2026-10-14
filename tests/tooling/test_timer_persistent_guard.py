"""Guard: no tracked systemd timer sets Persistent= without OnCalendar= (#1062).

Persistent= is documented to matter only for OnCalendar= timers, which is why
#925 and #948 called it "inert" on monotonic timers. It is not inert. It makes
systemd keep a stamp file and load ``last_trigger`` from it when the manager
starts. If the claude user manager then starts after the OnBootSec= delay has
already passed (18.7 min on 2026-10-14, while a failing USB disk held up
boot), systemd treats the past boot trigger as already fired and disables it.
The service never runs in that manager lifetime, so OnUnitActiveSec= /
OnUnitInactiveSec= never get a base. The timer stays ``active (elapsed)`` with
no next elapse, permanently and silently. Six timers, felix-canary among them,
were dead for 17 days this way.

The test parses directives, not text. Several timers mention ``OnCalendar`` or
``Persistent`` in comments, and a bare grep misreads them (#948 documents
exactly that mistake).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRUTHY = {"1", "yes", "true", "on"}


def _directives(text: str) -> list[tuple[str, str, str]]:
    """Return (section, key, value) for every directive line in a unit file."""
    out: list[tuple[str, str, str]] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out.append((section, key.strip(), value.strip()))
    return out


def persistent_without_calendar(text: str) -> bool:
    """True when the [Timer] section sets a truthy Persistent= but no OnCalendar=."""
    timer = [(k, v) for s, k, v in _directives(text) if s == "Timer"]
    persistent = any(k == "Persistent" and v.lower() in _TRUTHY for k, v in timer)
    calendar = any(k == "OnCalendar" and v for k, v in timer)
    return persistent and not calendar


def _tracked_timers() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.timer"],
        cwd=_REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode()
    return [_REPO_ROOT / p for p in out.split("\0") if p]


# --- the guard can fail: synthetic cases ------------------------------------

@pytest.mark.parametrize(
    "body, expected",
    [
        # The #1062 shape: monotonic triggers + Persistent -> rejected.
        ("[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\nPersistent=true\n", True),
        # Whitespace around '=' and other truthy spellings are still directives.
        ("[Timer]\nOnBootSec = 2min\nPersistent = yes\n", True),
        ("[Timer]\nOnUnitInactiveSec=300s\nPersistent=1\n", True),
        # A commented-out OnCalendar does not make Persistent legitimate.
        ("[Timer]\n# OnCalendar=hourly\nOnBootSec=5min\nPersistent=true\n", True),
        # Calendar timers are the correct use of Persistent -> accepted.
        ("[Timer]\nOnCalendar=hourly\nPersistent=true\n", False),
        # Monotonic without Persistent -> accepted (felix-deployer shape).
        ("[Timer]\nOnBootSec=5min\nOnUnitActiveSec=5min\n", False),
        # Persistent=false is harmless.
        ("[Timer]\nOnBootSec=5min\nPersistent=false\n", False),
        # A Persistent mention in a comment is not a directive.
        ("[Timer]\n# Why not Persistent=true: #1062\nOnBootSec=5min\n", False),
    ],
)
def test_detector(body: str, expected: bool) -> None:
    assert persistent_without_calendar(body) is expected


def test_repo_has_timers_to_check() -> None:
    # A guard over an empty set passes vacuously; make sure it actually looks.
    assert len(_tracked_timers()) >= 10


# --- the guard over the real tree -------------------------------------------

def test_no_tracked_timer_sets_persistent_without_oncalendar() -> None:
    offenders = [
        str(p.relative_to(_REPO_ROOT))
        for p in _tracked_timers()
        if persistent_without_calendar(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "Persistent= on a timer with no OnCalendar= makes it go permanently "
        "dormant when the user manager starts after OnBootSec= has passed "
        f"(#1062). Remove Persistent= from: {offenders}"
    )
