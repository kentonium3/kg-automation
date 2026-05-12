"""Credential expiry health checker.

Daily, deterministic checker that reads credential-manifest.json, detects
credentials approaching their review-cadence boundary (or with failing
activity signals), and files paired alerts to GitHub + Vikunja.

See kitty-specs/credential-expiry-health-check-01KRCF92/ for the design
and tests/security/ for the unit + contract tests.
"""
