"""Single source of truth for the OpenClaw binary path (kentonium3/kg-automation#811).

Resolves "where is the openclaw binary" in ONE place so a future relocation
(a different npm prefix, containerization, a per-host path difference) is a
one-line change here instead of an edit at every subprocess call site.

Resolution order:

1. env ``OPENCLAW_BIN`` (non-blank) — the override for tests, a relocation, or
   a per-host path;
2. :data:`DEFAULT_OPENCLAW_BIN` — the sole install location after the #653
   root-global removal deleted ``/usr/bin/openclaw`` and moved OpenClaw fully
   into claude user space.

**Why absolute-by-default.** Every runtime consumer runs in a PATH-less context
— systemd-user units, cron, and non-login ``sg docker -c`` shells all lack
``~/.local/bin`` on ``PATH`` — so a bare ``openclaw`` raises
``FileNotFoundError`` (or, via ``shutil.which``, resolves to ``None`` and fails
silently). That is the #653 failure class this seam exists to eliminate.

Library-tier per Felix Constitution Directive 6 /
``docs/design/helper-script-conventions.md``: pure, importable, no file I/O and
no network on import or call. Resolution happens at **call time** so an
``OPENCLAW_BIN`` set before the process starts always wins.

Documented exceptions that intentionally do NOT route through this seam (they
are PATH-safe by design or are inert historical artifacts): the felix-deployer
cron primitives (``scripts/deploy/lib/cron.py``,
``scripts/deploy/deploy-deterministic-monitoring-checks.py``) which run only
under felix-deployer's PATH; the two already-applied one-shot cron deploy
scripts; and the canary ``endpoint`` command strings in
``service-inventory.json`` (executed by a shell in a unit with no
``OPENCLAW_BIN``/PATH). See ``docs/runbooks/openclaw-ops.md``.
"""
from __future__ import annotations

import os

__all__ = [
    "DEFAULT_OPENCLAW_BIN",
    "OPENCLAW_BIN_ENV",
    "openclaw_bin",
    "openclaw_argv",
]

#: The sole OpenClaw install location on office2 (claude user space, #653).
DEFAULT_OPENCLAW_BIN = "/home/claude/.local/bin/openclaw"

#: Environment variable that overrides the default (relocation / per-host / tests).
OPENCLAW_BIN_ENV = "OPENCLAW_BIN"


def openclaw_bin() -> str:
    """Return the resolved OpenClaw binary path.

    ``OPENCLAW_BIN`` wins when set to a non-blank value; otherwise the absolute
    :data:`DEFAULT_OPENCLAW_BIN`. A blank/whitespace-only override is ignored
    (an empty string must never be returned as a "path"). Never returns blank.
    """
    override = os.environ.get(OPENCLAW_BIN_ENV)
    if override and override.strip():
        return override
    return DEFAULT_OPENCLAW_BIN


def openclaw_argv(*args: str) -> list[str]:
    """Return ``[openclaw_bin(), *args]`` for ``subprocess.run(..., shell=False)``.

    Convenience for the common case of building an argv list whose first element
    is the resolved binary, e.g. ``openclaw_argv("cron", "list", "--json")``.
    """
    return [openclaw_bin(), *args]
