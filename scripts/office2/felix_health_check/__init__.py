"""felix-health-check — off-agent twice-daily system health check.

Wraps the existing ``/home/claude/helper-scripts/health-check.sh`` bash
check with a non-agent Python runner invoked by a systemd user timer
(``scripts/office2/felix-health-check.timer``, 11:00 + 23:00 UTC-office2
local). Creates **no** Sonnet ``main`` session (FR-009).

Modules
-------
- ``run`` -- systemd ``ExecStart`` entrypoint: runs the bash check via
  ``subprocess.run`` (never ``exec``), classifies its output with
  failure-wins precedence, stamps the ``last-run.json`` signal file, and
  pushes an ntfy alert on any non-healthy outcome.

See ``kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/
health-check-runner.contract.md`` for the authoritative behavior contract.
"""
