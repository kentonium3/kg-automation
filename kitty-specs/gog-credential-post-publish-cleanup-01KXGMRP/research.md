# Research: gog credential post-publish cleanup

Phase 0 findings that resolve the plan's unknowns. Each entry: Decision / Rationale / Alternatives.

## R-01 — Office2 deploy path for the probe

**Decision**: Deploy is by felix-deployer's `git pull origin/main` into the shared
office2 checkout `/home/claude/kg-automation`. No `deploys/queued` manifest is
required.

**Rationale**: `credential-liveness-probe.service` runs
`/usr/bin/python3 -m scripts.security.credential_health_check` with
`WorkingDirectory=/home/claude/kg-automation` and `PYTHONPATH` = the checkout root,
reading the manifest from that same checkout. The checkout is a git working copy on
`main` (observed at `9829acef`). felix-deployer keeps it at `origin/main` on its ~5min
tick (watermark-based observe range, #685). The change touches only Python/JSON/shell/
docs that live in the checkout and a routine that already runs from it — no systemd
unit, service install, cron, or out-of-checkout file placement. So the new code lands
on the next git pull and the routine uses it on its next 6h tick.

**Alternatives considered**: A `deploys/queued/<name>.yaml` manifest — rejected as
unnecessary; manifests are for deploys needing explicit apply actions (unit installs,
restarts, cron changes, file placement), none of which apply here.

## R-02 — Rebaseline determination

**Decision**: Rebaseline is **not required**. The merge records
`Rebaseline: not required — <reason>`.

**Rationale**: `audited-surfaces.json` enumerates the audited path patterns:
`scripts/openclaw/agents/*/*.md(.tmpl)`, `scripts/openclaw/openclaw*.json`,
`scripts/office2/*.{service,timer,target,path}` + `scripts/office2/deploy/*.sh` +
`scripts/openclaw/*.service.d/*`, `requirements*.txt` / `pyproject.toml`,
docker-compose/Dockerfile, `scripts/security/ssh-keys/*` + `authorized_keys*`, and
`deploys/{queued,applied,failed}/*` + `scripts/deploy/lib/**`. This mission touches
`scripts/security/credential_health_check/*.py`, `scripts/security/gog-reauth.sh`,
`docs/design/architecture/data/credential-manifest.json`, other docs, and
`tests/security/*` — **none** match. (The initial spec C-001 assumed `scripts/security/**`
was audited; only `scripts/security/ssh-keys/*` is. C-001 corrected.)

**Alternatives considered**: Manual rebaseline post-merge — rejected as unnecessary
and would create spurious baseline churn.

## R-03 — Single classification value

**Decision**: Collapse to `dead`. `LivenessClassification = Literal["dead", "probe-error"]`.
Issue title prefix becomes `credential-liveness-dead: <name>`.

**Rationale**: Post-publish there is no "routine" death; every `invalid_grant` is a
genuinely-unexpected failure. `dead` is the clearest single label and reads correctly
in the issue title (`orchestrator` derives the title via `classification.removeprefix('dead-')`,
which yields `dead`). Keeping the old `dead-unexpected` value would preserve a
contrast ("unexpected" vs a "routine" that no longer exists) that is now meaningless.

**Alternatives considered**: (a) keep `dead-unexpected` — rejected (implies a vanished
contrast); (b) gate a `dead-routine-7day` behind a manifest `testing_mode` flag —
rejected by the operator (spec §Scope Decision): no account is in External+Testing, and
re-introducing it later is cheap.

**Migration note (operator, not code)**: pre-existing open liveness issues carry old
titles (`credential-liveness-unexpected: …`, e.g. #629 from 2026-06-24). A future
`dead` alert will not dedup against them. Recommend closing stale liveness issues;
this is an operator note, not a code requirement.

## R-04 — `keyring_file` scope boundary

**Decision**: Keep `keyring_file` in the schema (still required when `enabled`).
Remove only `reauth_marker_glob`.

**Rationale**: `keyring_file` was consumed solely by `_resolve_cycle_baseline()` for
the mtime baseline; post-collapse the probe no longer reads it. But it remains a
legitimate descriptive field (documents where the gog keyring lives) and is referenced
by the manifest and ops docs. Removing it would widen the schema change and risk other
readers, for no cleanup benefit tied to this issue. NFR-004's grep targets
(`reauth_marker_glob`, `CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`, `_resolve_cycle_baseline`,
`routine-7day`, `Testing-app`) intentionally exclude `keyring_file`.

**Alternatives considered**: Drop `keyring_file` too — rejected as out-of-scope schema
creep; a separate hygiene issue could revisit it if desired.

## R-05 — Atomic removal coupling (manifest schema ↔ config)

**Decision**: Remove `reauth_marker_glob` from `manifest.py` (`allowed_keys` set +
`LivenessProbeConfig` field + docstring) **and** from `credential-manifest.json` in the
same work package / commit.

**Rationale**: `manifest.py` raises `ManifestQualityError` on any unknown
`liveness_probe` subkey. If `allowed_keys` drops `reauth_marker_glob` while the JSON
still carries it, the routine raises on that credential every tick. The two edits are
mutually dependent and must be atomic.

**Alternatives considered**: Make the loader silently ignore unknown keys — rejected;
the unknown-key rejection is a useful typo guard and should stay.

## R-06 — Test-rewrite scope

**Decision**: In `tests/security/test_liveness.py`: delete the 5 `reauth_marker_*`
tests and `test_keyring_fallback_message_labels_source`; collapse
`test_dead_routine_7day` / `test_dead_unexpected_too_early` / `_too_late` /
`test_routine_boundary_just_inside` / `_just_outside` / `test_recovery_command_in_dead_result`
into a single `invalid_grant → dead` behavior test (plus a recovery-command-present
assertion on the dead result); change `test_keyring_missing_is_probe_error` to expect
`dead` (keyring no longer stat-ed). Keep `test_alive_returns_none`, the three
probe-error tests, `test_recovery_command_none_in_probe_error`,
`test_raises_if_liveness_probe_disabled`, `test_probed_at_is_utc`. In
`tests/security/test_orchestrator.py`: update any case asserting `dead-routine-7day` /
`dead-unexpected` / `routine-7day` titles to the single `dead` / `credential-liveness-dead`
behavior, and the unconditional investigate block.

**Rationale**: The timing/marker-based cases exist only to exercise the routine/unexpected
split and the baseline machinery, both removed. Coverage is preserved by the retained
paths plus the collapsed dead-path test.

**Alternatives considered**: Keep timing tests as no-ops — rejected (dead tests are
vestiges; NFR-004 spirit).

## R-07 — gog-reauth.sh consent guidance content

**Decision**: Rewrite the browser-consent step to describe the actual consent screen
observed on 2026-07-14: the OAuth scopes expand to ten checkboxes (Drive; "Other
contacts"; Contacts; Docs; Sheets; Calendar; sensitive Gmail settings; Gmail
settings/filters; Gmail read/compose/send; and "See and download your organization's
Google Workspace directory"). Instruct the operator to grant the personal-data scopes
and **leave the "organization's Google Workspace directory" box unchecked** unless
directory access is explicitly wanted. Remove the "six boxes" claim and the
External+Testing 7-day header/closing wording, including the "Next forced re-auth ~<date>"
projection.

**Rationale**: The current script says "check ALL six scope boxes," which both
undercounts and would push the operator to grant the directory scope. Verified that
declining the directory box still yields a working token (`gog contacts list` succeeded
on the resulting token, 2026-07-14). The gog `contacts` service bundles
`directory.readonly` into its request, which is why the box appears despite
`--services` not listing "directory."

**Alternatives considered**: Drop `contacts` from the script's `--services` to remove
the directory box entirely — rejected; that would also drop the wanted personal
Contacts scopes, and the box is optional at consent time anyway.
