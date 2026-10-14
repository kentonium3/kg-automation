"""systemd timer-unit directive parsing (#1062).

Shared by ``tests/tooling/test_timer_persistent_guard.py`` (repo-wide guard)
and ``scripts/deploy/deploy-monotonic-timer-units.py`` (pre-copy source
validation), so the rule the test enforces and the rule the deploy enforces
cannot drift apart.

Why the rule exists: ``Persistent=`` has its documented effect only with
``OnCalendar=``. On a monotonic timer it makes systemd load a stamp-file
``last_trigger`` at manager start. If the user manager then starts after
``OnBootSec=`` has passed, ``timer_enter_waiting()`` disables the past boot
trigger as already fired. The service never runs, ``OnUnitActiveSec=`` /
``OnUnitInactiveSec=`` never get a base, and the timer stays dormant for the
whole boot. office2's canary was dead this way for 17 days.
"""

from __future__ import annotations

TRUTHY = frozenset({"1", "yes", "true", "on"})
TIMER_EXPRESSIONS = frozenset({
    "OnCalendar", "OnActiveSec", "OnBootSec", "OnStartupSec",
    "OnUnitActiveSec", "OnUnitInactiveSec",
})


def directives(text: str) -> list[tuple[str, str, str]]:
    """Return ``(section, key, value)`` for every directive, in file order.

    Comments (``#``/``;``) are skipped and backslash continuations joined, as
    systemd does. Whitespace around ``=`` is not significant.
    """
    lines: list[str] = []
    pending = ""
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\") and not stripped.lstrip().startswith(("#", ";")):
            pending += stripped[:-1] + " "
            continue
        lines.append(pending + raw)
        pending = ""
    if pending:
        lines.append(pending)

    out: list[tuple[str, str, str]] = []
    section = ""
    for raw in lines:
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


def persistent_without_calendar(*texts: str) -> bool:
    """True when the effective ``[Timer]`` config has a truthy ``Persistent=``
    and no ``OnCalendar=``.

    Pass the unit file followed by its drop-ins, in load order; they are
    evaluated as one stream. The last ``Persistent=`` wins. An empty
    assignment to any timer expression clears every expression set before it
    (``config_parse_timer()`` → ``timer_free_values()``).

    A timer with ``OnCalendar=`` is exempt even if it also has monotonic
    triggers. The exemption is deliberate: the calendar trigger keeps
    re-arming it, so a disabled boot trigger cannot leave it dormant.
    """
    persistent = False
    calendar = False
    for text in texts:
        for section, key, value in directives(text):
            if section != "Timer":
                continue
            if key == "Persistent":
                persistent = value.lower() in TRUTHY
            elif key in TIMER_EXPRESSIONS:
                if not value:
                    calendar = False
                elif key == "OnCalendar":
                    calendar = True
    return persistent and not calendar
