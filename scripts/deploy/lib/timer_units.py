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

# systemd's parse_boolean(); anything else (including empty) is ignored by
# config_parse_bool() and leaves the previous value in place.
TRUTHY = frozenset({"1", "yes", "y", "true", "t", "on"})
FALSY = frozenset({"0", "no", "n", "false", "f", "off"})
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
        # systemd skips comment lines even in the middle of a continuation.
        if pending and stripped.lstrip().startswith(("#", ";")):
            continue
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


def persistent_on_monotonic(*texts: str) -> bool:
    """True when the effective ``[Timer]`` config has a truthy ``Persistent=``
    together with any monotonic trigger (OnActiveSec, OnBootSec, OnStartupSec,
    OnUnitActiveSec, OnUnitInactiveSec).

    Pass the unit file followed by its drop-ins, in load order; they are
    evaluated as one stream. The last parseable ``Persistent=`` wins (systemd
    ignores an empty or invalid boolean and keeps the previous value). An empty
    assignment to any timer expression clears every expression set before it
    (``config_parse_timer()`` → ``timer_free_values()``).

    The rule is "Persistent= only on calendar-only timers". It deliberately
    does not exempt a timer for also having ``OnCalendar=``. systemd ignores an
    invalid calendar expression, so such an exemption could be bought with
    ``OnCalendar=garbage``. And a monotonic trigger next to Persistent= is
    exactly the combination that gets disabled after a slow boot.
    """
    persistent = False
    monotonic = False
    for text in texts:
        for section, key, value in directives(text):
            if section != "Timer":
                continue
            if key == "Persistent":
                v = value.lower()
                if v in TRUTHY:
                    persistent = True
                elif v in FALSY:
                    persistent = False
            elif key in TIMER_EXPRESSIONS:
                if not value:
                    monotonic = False
                elif key != "OnCalendar":
                    monotonic = True
    return persistent and monotonic
