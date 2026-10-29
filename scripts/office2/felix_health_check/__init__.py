"""felix-health-check — off-agent twice-daily system health check.

Wraps the version-controlled ``health-check.sh`` bash service checks (in
this package since #1063) with a non-agent Python runner invoked by a
systemd user timer (``scripts/office2/felix-health-check.timer``, 11:00 +
23:00 UTC-office2 local), and adds two coverage checks: the dead-man's
switch on felix-canary and an independent restic-backup check (#1063).
Creates **no** Sonnet ``main`` session (FR-009).

Modules
-------
- ``run`` -- systemd ``ExecStart`` entrypoint: evaluates coverage, runs the
  bash check via ``subprocess.run`` (never ``exec``), combines both with
  failure-wins precedence, stamps the ``last-run.json`` signal file, and
  pushes one alert on any non-healthy outcome.
- ``coverage`` -- the two coverage checks, decided by the canary's own
  evaluator on the service-inventory declarations.

See ``kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/
health-check-runner.contract.md`` for the authoritative behavior contract.
"""
