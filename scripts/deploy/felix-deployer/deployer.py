"""felix-deployer — pull-based deploy applier entry point.

Runs as systemd --user Type=oneshot service; the companion timer fires
every 5 min. Reads ``deploys/queued/*.yaml``, applies through
:func:`scripts.deploy.lib.apply.dry_run_then_apply_gate`, records the
outcome, dispatches a WhatsApp DM on failure via the openclaw cron.

Invoked by the systemd unit via the file-path ExecStart form::

    /usr/bin/python3 /home/claude/kg-automation/scripts/deploy/felix-deployer/deployer.py

The directory name contains a hyphen (matching the systemd unit name
``felix-deployer`` and the eventual ``deploys/applied/`` entry name),
so it is not importable as a Python module via dotted ``-m`` form.
Path-based invocation sidesteps that — and is the same pattern used
by ``scripts/openclaw/observation/tick.py`` and ``scripts/openclaw/heartbeat_gate/run.py``
(other Type=oneshot deploys in this repo, per ``scripts/office2/*.service``).

This entry point bootstraps two ``sys.path`` entries so the deployer
modules and the deploy library both resolve:

1. The repo root — so ``scripts.deploy.lib`` is importable.
2. The felix-deployer directory itself — so ``_tick`` and ``notify``
   can import each other with plain ``import notify`` style.
"""

from __future__ import annotations

import pathlib
import sys


def _bootstrap_paths() -> None:
    """Put the repo root and the felix-deployer dir on ``sys.path``."""
    here = pathlib.Path(__file__).resolve().parent
    repo_root = here.parents[2]
    for entry in (str(repo_root), str(here)):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def main() -> int:
    _bootstrap_paths()
    # Late import: requires sys.path bootstrap to be in effect.
    import _tick  # type: ignore[import-not-found]

    return int(_tick.run_tick())


if __name__ == "__main__":
    sys.exit(main())
