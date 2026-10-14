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

from scripts.deploy.lib.timer_units import persistent_without_calendar

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _tracked_timers() -> list[Path]:
    # Drop-ins (``<unit>.timer.d/*.conf``) can add Persistent= too.
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.timer", "*.timer.d/*.conf"],
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
        # Calendar + monotonic: the calendar trigger keeps it alive -> accepted.
        ("[Timer]\nOnCalendar=daily\nOnBootSec=5min\nPersistent=true\n", False),
        # Mixed-case truthy spelling.
        ("[Timer]\nOnBootSec=5min\nPersistent=TRUE\n", True),
        # Calendar timers are the correct use of Persistent -> accepted.
        ("[Timer]\nOnCalendar=hourly\nPersistent=true\n", False),
        # Monotonic without Persistent -> accepted (felix-deployer shape).
        ("[Timer]\nOnBootSec=5min\nOnUnitActiveSec=5min\n", False),
        # Persistent=false is harmless.
        ("[Timer]\nOnBootSec=5min\nPersistent=false\n", False),
        # A Persistent mention in a comment is not a directive.
        ("[Timer]\n# Why not Persistent=true: #1062\nOnBootSec=5min\n", False),
        # An empty expression assignment clears the earlier OnCalendar= (Codex).
        ("[Timer]\nOnCalendar=hourly\nOnCalendar=\nOnBootSec=5min\nPersistent=true\n", True),
        ("[Timer]\nOnCalendar=hourly\nOnBootSec=\nOnBootSec=5min\nPersistent=true\n", True),
        # The last Persistent= wins.
        ("[Timer]\nOnBootSec=5min\nPersistent=true\nPersistent=false\n", False),
        ("[Timer]\nOnBootSec=5min\nPersistent=false\nPersistent=true\n", True),
        # Persistent= outside [Timer] is not a timer setting.
        ("[Unit]\nPersistent=true\n[Timer]\nOnBootSec=5min\n", False),
        # A backslash continuation is one directive.
        ("[Timer]\nOnBootSec=5min\nPersistent=\\\ntrue\n", True),
    ],
)
def test_detector(body: str, expected: bool) -> None:
    assert persistent_without_calendar(body) is expected


def test_drop_in_is_evaluated_with_its_unit() -> None:
    unit = "[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\n"
    assert persistent_without_calendar(unit, "[Timer]\nPersistent=true\n")
    assert not persistent_without_calendar(
        "[Timer]\nOnBootSec=5min\nPersistent=true\n", "[Timer]\nPersistent=no\n"
    )


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


def test_docs_do_not_describe_persistent_on_monotonic_timers() -> None:
    """The units are not the only place the wrong belief lived (#925, #948).

    Any active doc line that names a monotonic-only timer unit together with
    ``Persistent=true`` re-teaches the pattern this guard forbids. The check
    is narrow on purpose: it only fires on lines naming ``<unit>.timer``.
    Schedule strings that omit the unit name are covered by review, not
    here.
    """
    monotonic = [
        p.name for p in _tracked_timers()
        if p.suffix == ".timer"
        and "OnCalendar" not in {k for s, k, v in _directives(p) if s == "Timer"}
    ]
    assert len(monotonic) >= 6
    docs = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs/*.md", "docs/*.json"],
        cwd=_REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode().split("\0")
    hits = []
    for rel in docs:
        if not rel or rel.startswith("docs/archive/") or "/adr/" in rel:
            continue
        for n, line in enumerate((_REPO_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if "Persistent=true" in line and any(t in line for t in monotonic):
                hits.append(f"{rel}:{n}")
    assert not hits, f"Docs describe Persistent=true on a monotonic timer (#1062): {hits}"


def _directives(path: Path) -> list[tuple[str, str, str]]:
    from scripts.deploy.lib.timer_units import directives
    return directives(path.read_text(encoding="utf-8"))
