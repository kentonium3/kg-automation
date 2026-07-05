# Issue matrix — agent-runtime-env-guardrails-01KWT3GH

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #656 | felix-admin cron ModuleNotFoundError + gateway PYTHONPATH (seed) | verified-already-fixed | Shipped `deploys/applied/0006-gateway-pythonpath-dropin.yaml`; OUT of scope (spec C-005) — this mission builds on the gateway PYTHONPATH it established. |
| #659 | observation-log repoint (seed) | verified-already-fixed | Shipped `deploys/applied/0008-migrate-observation-logs.yaml`; OUT of scope (spec C-005) — a prior concrete fix of the same class. |
| #167 | workspace-authoring standard | verified-already-fixed | Authoring infrastructure exists; this mission extends it (WP06 T023 guardrail reference; WP05 #587 validator fold). Referenced, not fixed. |
| #587 | validate_workspace.py workspace validator | verified-already-fixed | Validator exists at `scripts/openclaw/agents/validate_workspace.py`; WP05 folds the env-assumption check in, reusing its `SUSPENDED_WORKSPACES`/`NON_WORKSPACE_DIRS`. |
| #343 | felix-doc-auditor scripts-first driver refactor | verified-already-fixed | Refactor retired the live doc-auditor agent (in `validate_workspace.SUSPENDED_WORKSPACES`); relied on to disposition doc-auditor as retired (FR-008, WP05 T021). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
