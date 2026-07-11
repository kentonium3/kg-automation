"""Felix component-health canary package.

The runner reads ``service-inventory.json`` and evaluates the declared
health of every service-type component, emitting alerts via the #701
alert bus. This ``registry`` module is the pure, offline first stage:
it turns the inventory into the runner's work list (:class:`CanaryTarget`)
plus a coverage-gap set (:class:`CoverageGap`). Probing is WP03; the
orchestration/emission loop is WP04.
"""
