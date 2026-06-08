# tests/calendar/

Unit tests for `scripts/calendar_routing/`. Currently covers
`validate_calendar_event.py` — the deterministic helper that converts an
`ExtractedCalendarBlock` into either a complete `CalendarEventPayload` or
a `missing_fields` report.

## Canonical invocation

The mission-acceptance coverage gate is enforced by this command:

```bash
pytest tests/calendar/ --cov=scripts/calendar --cov-branch --cov-fail-under=90
```

- `--cov=scripts/calendar` — measure the helper module.
- `--cov-branch` — require branch coverage in addition to line coverage.
- `--cov-fail-under=90` — fail the run when combined coverage drops below 90 %.

Coverage targets per WP01's Definition of Done:

| Metric           | Target | Latest (WP01 land) |
|------------------|--------|--------------------|
| Line coverage    | ≥ 90 % | 99 %               |
| Branch coverage  | ≥ 85 % | ≈ 99 %             |

Branches marked with `# pragma: no branch` are defensive guards that
sit downstream of an earlier short-circuit return — i.e., genuinely
unreachable per the calling convention (`re.Match.span()` always
returns in-bounds offsets, etc.). See memory
`reference_pytest_branch_coverage_pragma` for the broader rule.

## Why this gate isn't wired into pyproject.toml / pytest.ini

The kg-automation repo's `pytest.ini` lives outside WP01's `owned_files`
(`scripts/calendar_routing/**`, `tests/calendar/**`, plus two specific files
under `tests/inbox/`). Adding a permanent `--cov` block would require
editing `pytest.ini`, which sits outside the WP's authoritative surface.

Per WP01's reviewer guidance and Felix Constitution Directive 3
(integration boundaries), the coverage gate is enforced by:

1. The canonical command above (documented here; run from a clean
   checkout or CI step).
2. The Definition of Done in the WP01 task file, which requires the
   gate to pass before move-task to `for_review`.

A follow-up mission may wire the gate permanently into `pytest.ini`
or a new `pyproject.toml` `[tool.coverage]` block; that is out of
scope for WP01.

## Fixture catalogue (validator)

The 11 paired `*.input.json` / `*.expected.json` files in
`tests/calendar/fixtures/` exercise:

- `complete_oneoff` — one-shot event with explicit start + end.
- `complete_oneoff_duration` — duration instead of end.
- `complete_weekly` — weekly recurrence (#324 trivia-night case).
- `complete_biweekly` — biweekly with weekday.
- `complete_monthly_by_dayofmonth` — monthly on the 15th.
- `complete_byweekday_of_month` — first Monday of the month.
- `incomplete_no_start` — start phrase unparseable.
- `incomplete_no_end` — neither end nor duration.
- `incomplete_recurrence_unrecognized` — recurrence outside R-007.
- `edge_dst_transition` — event crossing 2026-11-01 DST end.
- `edge_relative_anchor_resolution` — "next Tuesday" against tick_iso.

Each `*.input.json` is the validator's stdin block; each
`*.expected.json` is the canonical stdout shape.

## Classifier regression fixtures

The classifier regression set lives at
`tests/inbox/fixtures/classifier_regression.json` (25 cases) and is
exercised by `tests/inbox/test_classifier_regression.py`. Pre-WP02
calendar / aspiration / Someday / multi-domain cases SKIP cleanly
because their routing rows don't yet exist in capture's `AGENTS.md`.
A negative tripwire (`test_pre_wp02_pending_destinations_not_yet_wired`)
fires loudly the moment WP02 lands those rows.

## Maintenance

- Add fixtures when a new validator branch or recurrence pattern is
  introduced.
- When the classifier prompt at
  `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` changes,
  re-run the classifier regression in both static and live mode and
  update the signal aliases in `test_classifier_regression.py` if the
  destination-row wording changed.
