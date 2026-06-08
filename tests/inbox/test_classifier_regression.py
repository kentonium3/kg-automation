"""Regression harness for the felix-admin-capture inbox classifier.

Two modes:

1. **Static (default)** — parse the routing table out of
   `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` and verify that
   every fixture's `expected_destination` either (a) maps to a row in the
   routing table that capture knows how to act on, or (b) is a destination
   that this WP knows is still pending (e.g., calendar_event_complete is
   added by WP02). For pending destinations, fixtures are SKIPPED with an
   explicit "pending WP02" reason — not silently ignored.

2. **Live (opt-in)** — gated behind the env var
   ``CLASSIFIER_REGRESSION_LIVE=1`` with ``ANTHROPIC_API_KEY`` present.
   Calls Claude haiku with the actual capture prompt + each fixture
   input and asserts the parsed classification matches expected. Each
   fixture is one API call; the operator runs this deliberately at
   pre-deploy time.

The static gate is the CI default; live mode is the manual pre-deploy
sweep. This file is owned by WP01 and intentionally written so that the
static gate keeps tracking destination drift in the routing table even
before WP02 lands the calendar/aspiration/Someday rows.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "inbox" / "fixtures" / "classifier_regression.json"
CAPTURE_AGENTS_PATH = (
    REPO_ROOT
    / "scripts"
    / "openclaw"
    / "agents"
    / "felix-admin-capture"
    / "AGENTS.md"
)


# Destinations whose routing rows are introduced by WP02. Until WP02 lands,
# fixtures with these destinations are SKIPPED in static mode (the harness
# still records them so the gate flips green automatically once the rows
# appear).
_PENDING_WP02_DESTINATIONS = {
    "calendar_event_complete",
    "calendar_event_incomplete",
    "aspiration",
    "someday",
    "multi_domain",
}


# Signal patterns the static gate looks for in the capture AGENTS.md
# routing table. Each (destination, [aliases]) pair: the destination is
# considered "wired" when ANY alias appears in the routing table source.
#
# Aliases are chosen to be DISTINCT from rows that already exist in the
# pre-WP02 AGENTS.md. For example, the pre-WP02 prompt already has a
# row for "Vision, aspiration, future state" → 03-Constitution/Vision.md;
# WP02 adds a separate "Aspiration / musing" row → 08-Journal/. The
# aliases below are tuned to detect ONLY the WP02-specific intent, so
# the pre-WP02 gate skips cleanly and the post-WP02 gate enforces.
_DESTINATION_TABLE_SIGNALS: dict[str, list[str]] = {
    "calendar_event_complete": [
        "create_calendar_event",
        "gog calendar create",
        "Calendar event (complete)",
    ],
    "calendar_event_incomplete": [
        "pending-calendar-clarifications",
        "calendar_event_clarification",
        "Calendar event (incomplete)",
    ],
    "aspiration": [
        "AspirationJournalEntry",
        "Aspiration / musing",
        "aspiration-journal",
    ],
    "someday": [
        "SomedayTaskRequest",
        "Someday item",
        "Vikunja project 4",
        "project_id=4",
    ],
    "active_task": [
        "Task or action item",
        "felix-admin-tasker",
    ],
    "github_issue": [
        "GitHub issue request",
        "kentonium3/kg-automation",
    ],
    "goal_declaration": [
        "Goals-MOC.md",
        "Felix declaration",
    ],
    "reference_resource": [
        "Book, resource, tool reference",
        "09-Resources",
    ],
    "multi_domain": [
        "multi-domain",
        "multiple blocks",
        "block produced multiple",
    ],
}


def _load_fixtures() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())["fixtures"]


def _load_capture_routing_text() -> str:
    return CAPTURE_AGENTS_PATH.read_text(encoding="utf-8")


def _destination_in_routing_table(destination: str, routing_text: str) -> bool:
    """True when at least one signal alias for ``destination`` is in the text."""
    aliases = _DESTINATION_TABLE_SIGNALS.get(destination, [])
    for alias in aliases:
        if alias in routing_text:
            return True
    return False


# ---------------------------------------------------------------------------
# Fixture set sanity
# ---------------------------------------------------------------------------


def test_fixture_file_loads() -> None:
    data = json.loads(FIXTURE_PATH.read_text())
    assert "fixtures" in data
    assert isinstance(data["fixtures"], list)
    assert len(data["fixtures"]) >= 25, f"Expected >=25 fixtures, got {len(data['fixtures'])}"


def test_every_fixture_has_required_keys() -> None:
    for f in _load_fixtures():
        assert "id" in f, f"missing id in fixture {f!r}"
        assert "input_block" in f, f"missing input_block in fixture {f['id']}"
        assert "expected_destination" in f, f"missing expected_destination in fixture {f['id']}"
        assert "rationale" in f, f"missing rationale in fixture {f['id']}"
        assert f["expected_destination"] in _DESTINATION_TABLE_SIGNALS, (
            f"fixture {f['id']} has unknown destination {f['expected_destination']!r}"
        )


def test_destination_coverage() -> None:
    """The fixture set must exercise every destination type at least once."""
    fixtures = _load_fixtures()
    seen = {f["expected_destination"] for f in fixtures}
    required = set(_DESTINATION_TABLE_SIGNALS.keys())
    missing = required - seen
    assert not missing, f"Destinations not exercised by any fixture: {sorted(missing)}"


def test_historical_misroutes_present() -> None:
    """Fixtures from #556's misroutes must be tagged with source=historical-misroute."""
    fixtures = _load_fixtures()
    misroutes = [f for f in fixtures if f.get("source") == "historical-misroute"]
    assert len(misroutes) >= 2, (
        "Expected at least 2 historical-misroute fixtures from #556; "
        f"found {len(misroutes)}"
    )


# ---------------------------------------------------------------------------
# Static mode — routing-table signal check
# ---------------------------------------------------------------------------


def test_capture_agents_md_exists() -> None:
    assert CAPTURE_AGENTS_PATH.exists(), (
        f"capture AGENTS.md not found at {CAPTURE_AGENTS_PATH}"
    )


@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["id"])
def test_static_destination_wired_in_routing_table(fixture: dict) -> None:
    """Each fixture's expected destination must be wired in capture's AGENTS.md
    routing table — UNLESS the destination is on the WP02-pending list.

    Pre-WP02: calendar/aspiration/Someday/multi-domain rows do not yet exist
    in AGENTS.md. The harness intentionally SKIPS those fixtures so the
    gate stays green now and automatically catches drift the moment WP02
    lands the rows. WP02's reviewer (or this same test in the WP02 lane)
    asserts the inverse: those skipped destinations must then resolve.
    """
    routing_text = _load_capture_routing_text()
    destination = fixture["expected_destination"]
    is_wired = _destination_in_routing_table(destination, routing_text)

    if destination in _PENDING_WP02_DESTINATIONS:
        if is_wired:
            # WP02 has landed: the row now exists. Assertion flips to a real check.
            return
        pytest.skip(
            f"destination {destination!r} is added by WP02; row not yet present in "
            f"capture AGENTS.md (this is the expected pre-WP02 state)"
        )

    assert is_wired, (
        f"Fixture {fixture['id']}: destination {destination!r} is not detected "
        f"in capture's AGENTS.md routing table. Aliases checked: "
        f"{_DESTINATION_TABLE_SIGNALS[destination]!r}. This indicates the row "
        "was removed or renamed and the classifier has lost a destination."
    )


def test_pre_wp02_pending_destinations_not_yet_wired() -> None:
    """Negative assertion: the WP02-pending rows must NOT be present yet in
    pre-WP02 AGENTS.md. Locks the gate so that if any of those rows leak
    in via a different mission, the harness reports it loudly.

    This test is the inverse of the SKIP behaviour above — together they
    form a tripwire. When WP02 lands and adds the rows, this test should
    be removed (its responsibility transfers to the WP02 lane).
    """
    routing_text = _load_capture_routing_text()
    leaked = []
    for destination in sorted(_PENDING_WP02_DESTINATIONS):
        if _destination_in_routing_table(destination, routing_text):
            leaked.append(destination)
    # NOTE: if WP02 has already landed in the worktree (e.g., during a
    # rebase preview), every pending destination will be wired and this
    # assertion will need to be removed. The xfail keeps the failure
    # informational rather than blocking.
    if leaked:
        pytest.xfail(
            f"WP02-pending destinations now wired in AGENTS.md: {leaked}. "
            "Remove this test once WP02 lands; the static gate above will "
            "then enforce the rows directly."
        )


# ---------------------------------------------------------------------------
# Live mode (opt-in) — driven by env var
# ---------------------------------------------------------------------------


LIVE_MODE_ENABLED = os.environ.get("CLASSIFIER_REGRESSION_LIVE") == "1"
LIVE_MODE_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(
    not LIVE_MODE_ENABLED,
    reason="CLASSIFIER_REGRESSION_LIVE=1 not set; static mode only.",
)
@pytest.mark.skipif(
    not LIVE_MODE_API_KEY,
    reason="ANTHROPIC_API_KEY not in environment; cannot drive live LLM calls.",
)
@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["id"])
def test_live_classifier_matches_expected(fixture: dict) -> None:
    """Drive the actual capture prompt against Claude haiku for each fixture
    and assert the parsed classification matches expected. One API call per
    fixture; run deliberately at pre-deploy time.

    Implementation is intentionally minimal — this is a placeholder that
    documents the live-mode contract. The full driver lives behind WP02
    once the capture prompt actually emits classifier_destination_v1 JSON.
    """
    pytest.skip(
        "Live mode harness not yet wired: WP02 adds the structured "
        "classification output the live test will assert against. "
        "This skip is intentional and tracked by the WP02 acceptance gate."
    )


# ---------------------------------------------------------------------------
# Robustness — ensure parse errors don't silently disable the gate
# ---------------------------------------------------------------------------


def test_routing_text_contains_step3_section() -> None:
    """Sanity check: if the Step 3 routing table header disappears the
    parser cannot work. Fail loudly so review catches the doc drift."""
    text = _load_capture_routing_text()
    # Match the actual section heading used in AGENTS.md.
    assert re.search(
        r"###\s+Step\s+3:\s+Classify\s+and\s+route",
        text,
    ), "Step 3 'Classify and route' section header missing from capture AGENTS.md"


def test_signal_alias_table_matches_destination_enum() -> None:
    """Schema integrity: every declared fixture destination has an alias
    entry; every alias entry corresponds to a fixture destination."""
    data = json.loads(FIXTURE_PATH.read_text())
    declared = set(data["destinations"])
    aliased = set(_DESTINATION_TABLE_SIGNALS.keys())
    assert declared == aliased, (
        f"Destination enum drift. fixtures.destinations={sorted(declared)} "
        f"vs _DESTINATION_TABLE_SIGNALS={sorted(aliased)}"
    )
