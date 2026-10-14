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

import re
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
        # systemd also accepts y/t; an unparseable or empty value is ignored.
        ("[Timer]\nOnBootSec=5min\nPersistent=y\n", True),
        ("[Timer]\nOnBootSec=5min\nPersistent=t\n", True),
        ("[Timer]\nOnBootSec=5min\nPersistent=true\nPersistent=\n", True),
        ("[Timer]\nOnBootSec=5min\nPersistent=true\nPersistent=maybe\n", True),
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


_DOC_PERSISTENT = re.compile(r"Persistent`?\s*=\s*`?(?:true|yes|y|t|1|on)\b", re.I)


def doc_hits(lines: list[str], monotonic_stems: list[str]) -> list[int]:
    """1-based numbers of lines that name a monotonic timer AND set Persistent.

    Matches the unit stem (with or without ``.timer``) and any truthy spelling.
    Lines that name no monotonic timer, such as calendar-timer schedules,
    never match. Schedule strings that omit the unit name entirely are left to
    review.
    """
    return [
        n for n, line in enumerate(lines, 1)
        if _DOC_PERSISTENT.search(line) and any(st in line for st in monotonic_stems)
        and '"updated_by"' not in line  # change history may name the old state
    ]


@pytest.mark.parametrize("line, hit", [
    ("| Felix Canary | `felix-canary.timer` (`OnBootSec=5min`, `Persistent=true`) |", True),
    ("felix-canary runs every 15 min (Persistent = yes)", True),
    ("trigger: felix-canary.timer (OnBootSec=5min, `Persistent`=`true`)", True),
    ("crontab-capture.timer: hourly (OnCalendar=hourly, Persistent=true)", False),
    ("felix-canary.timer: OnBootSec=5min, OnUnitActiveSec=15min", False),
    ("Never add `Persistent=` to felix-canary (#1062)", False),
    ('"updated_by": "#1062 (dropped Persistent=true from felix-canary)"', False),
])
def test_doc_hits_detector(line: str, hit: bool) -> None:
    assert bool(doc_hits([line], ["felix-canary"])) is hit


def test_docs_do_not_describe_persistent_on_monotonic_timers() -> None:
    """The units are not the only place the wrong belief lived (#925, #948)."""
    stems = [
        p.stem for p in _tracked_timers()
        if p.suffix == ".timer"
        and "OnCalendar" not in {k for s, k, v in _directives(p) if s == "Timer"}
    ]
    assert len(stems) >= 6
    docs = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs/*.md", "docs/*.json"],
        cwd=_REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode().split("\0")
    hits = []
    for rel in docs:
        if not rel or rel.startswith("docs/archive/") or "/adr/" in rel:
            continue
        lines = (_REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
        hits += [f"{rel}:{n}" for n in doc_hits(lines, stems)]
    assert not hits, f"Docs describe Persistent on a monotonic timer (#1062): {hits}"


def _directives(path: Path) -> list[tuple[str, str, str]]:
    from scripts.deploy.lib.timer_units import directives
    return directives(path.read_text(encoding="utf-8"))
