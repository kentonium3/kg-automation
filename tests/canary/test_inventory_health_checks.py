"""Data guard over the REAL service inventory (#891).

Every prior fix in this class — #720, #721, #327 — repaired instances and the
class came back, because nothing tested the actual inventory. `test_registry.py`
builds its own fixture in `tmp_path`, so a health check that cannot fail is
invisible to CI no matter how many unit tests the probe layer has.

This module loads `docs/design/architecture/data/service-inventory.json` itself
and asserts the architectural rule the probe layer relies on:

    a freshness bound is only meaningful on a method that reads a pointer.

`shell`, `log-tail`, and `journal` decide health from an *executable string* that
lives in the inventory — unversioned, untested, and un-reviewed. When such an
entry also declares `max_age_seconds`, the bound looks enforced but may be
silently inert (the `journal` case: journalctl's default `Aug 27 13:00:43` prefix
does not parse as ISO-8601, so the staleness branch never fires).
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from scripts.canary import registry

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"

#: Methods whose freshness bound is evaluated by `_probe_freshness` against a
#: parsed pointer, i.e. where `max_age_seconds` is genuinely load-bearing.
POINTER_METHODS = frozenset({"tick-signal-file", "signal-file", "state-file"})

#: Components that still declare a freshness bound on a command-scan method.
#: Each entry names the issue that owns its migration. This registry may only
#: SHRINK — `test_exemptions_have_not_gone_stale` fails if an entry no longer
#: needs to be here, so a migrated component cannot leave dead scaffolding
#: behind (the repo's no-vestiges rule).
PENDING_POINTER_MIGRATION: dict[str, str] = {
    # Made fail-closed in #891 (grep + -o short-iso + a rolling 25h window).
    # Its max_age_seconds is still not the binding constraint — the journalctl
    # window is — which is exactly why the pointer migration is still owed.
    "credential-health-check": "#891 follow-up",
    # Fails closed correctly (pipeline ends in grep), but expresses its freshness
    # window twice: `max_age_seconds` in the data and `--since '7 hours ago'` in
    # the endpoint string, and only the string has effect.
    "credential-liveness-probe": "#891 follow-up",
}


@pytest.fixture(scope="module")
def targets():
    inventory = registry.load_inventory(str(INVENTORY))
    loaded, _gaps = registry.load_targets(inventory)
    assert loaded, "inventory produced no canary targets — loader is broken"
    return loaded


def _bounded_non_pointer(targets) -> dict[str, str]:
    out = {}
    for t in targets:
        hc = t.health_check or {}
        if hc.get("max_age_seconds") is not None and hc.get("method") not in POINTER_METHODS:
            out[t.component_id] = hc.get("method")
    return out


def test_freshness_bounds_only_on_pointer_methods(targets):
    """A `max_age_seconds` on a command-scan method may be silently inert."""
    offenders = _bounded_non_pointer(targets)
    unexpected = {k: v for k, v in offenders.items() if k not in PENDING_POINTER_MIGRATION}
    assert not unexpected, (
        "these components declare a freshness bound on a method that decides "
        "health from an executable string, where the bound may never fire:\n"
        + "\n".join(f"  {k} (method={v})" for k, v in sorted(unexpected.items()))
        + "\n\nEither move the component to a pointer method, or add it to "
        "PENDING_POINTER_MIGRATION with the issue that owns its migration."
    )


def test_exemptions_have_not_gone_stale(targets):
    """The exemption registry may only shrink."""
    offenders = _bounded_non_pointer(targets)
    known = {t.component_id for t in targets}
    stale = []
    for component, owner in PENDING_POINTER_MIGRATION.items():
        if component not in known:
            stale.append(f"  {component} — no longer in the inventory ({owner})")
        elif component not in offenders:
            stale.append(f"  {component} — now on a pointer method ({owner})")
    assert not stale, (
        "PENDING_POINTER_MIGRATION has entries that no longer apply; remove "
        "them so the list keeps meaning something:\n" + "\n".join(stale)
    )


def test_pointer_methods_declare_an_absolute_path(targets):
    """A pointer probe with no path is unevaluable — a permanent `unknown`."""
    bad = []
    for t in targets:
        hc = t.health_check or {}
        if hc.get("method") in POINTER_METHODS:
            path = hc.get("state_path") or hc.get("endpoint")
            if not path or not str(path).startswith("/"):
                bad.append(f"  {t.component_id}: {path!r}")
    assert not bad, "pointer health checks without an absolute path:\n" + "\n".join(bad)


def test_declared_success_values_are_non_empty_strings(targets):
    """`success_status_values` inverts `status` to fail-closed — a malformed
    declaration would silently fall back to the fail-open deny-list."""
    bad = []
    for t in targets:
        declared = (t.health_check or {}).get("success_status_values")
        if declared is None:
            continue
        if not isinstance(declared, list) or not declared:
            bad.append(f"  {t.component_id}: {declared!r} (must be a non-empty list)")
        elif not all(isinstance(v, str) and v.strip() for v in declared):
            bad.append(f"  {t.component_id}: {declared!r} (all entries must be non-empty strings)")
    assert not bad, "malformed success_status_values:\n" + "\n".join(bad)


def test_no_alert_eligible_target_probes_a_volatile_path(targets):
    """/tmp is emptied at boot, so a probe target there produces a spurious
    alert on every reboot. #894 drained the last offender
    (obsidian-sync-heartbeat, moved to a state-file pointer under
    /data/services/); this set must stay empty."""
    offenders = sorted(
        t.component_id
        for t in targets
        if "/tmp/" in str((t.health_check or {}).get("endpoint") or (t.health_check or {}).get("state_path") or "")
    )
    assert offenders == [], (
        "a component now probes a path under /tmp, which is emptied at every "
        f"boot and produces a spurious alert per reboot (#894). Found: {offenders}"
    )


#: Command-scan methods decide health from an executable string, and the FINAL
#: pipeline stage owns the exit status. These commands succeed on empty input,
#: so ending a pipeline in one masks any upstream failure. `journalctl` is the
#: subtle member: it prints "-- No entries --" to STDOUT and exits 0 for a unit
#: that does not exist, so a bare journalctl endpoint reports healthy on nothing.
COMMAND_SCAN_METHODS = frozenset({"shell", "log-tail", "journal", "self-check-command", "self-test"})
FAIL_OPEN_FINAL_STAGES = frozenset({
    "journalctl", "ls", "cat", "echo", "printf", "true",
    "head", "tail", "wc", "sort", "uniq", "jq", "tee",
})

#: Separate from PENDING_POINTER_MIGRATION on purpose — an exemption from the
#: pointer rule must not also excuse a fail-open endpoint.
PENDING_FAIL_CLOSED_ENDPOINT: dict[str, str] = {}


def _final_stage(endpoint: str) -> str:
    """Command word of the last top-level pipeline stage.

    Quote-aware: `grep -E 'a|b|c'` is ONE stage, not four. Splitting the raw
    string on "|" gets that wrong and reports the last alternation branch as
    the command.
    """
    if not endpoint:
        return ""
    try:
        tokens = shlex.split(endpoint)
    except ValueError:
        return ""
    last = 0
    for i, tok in enumerate(tokens):
        if tok in ("|", "&&", ";"):
            last = i + 1
    return tokens[last] if last < len(tokens) else ""


def _fail_open_endpoints(targets) -> dict[str, str]:
    out = {}
    for t in targets:
        hc = t.health_check or {}
        if hc.get("method") not in COMMAND_SCAN_METHODS:
            continue
        endpoint = hc.get("endpoint") or ""
        if _final_stage(endpoint) in FAIL_OPEN_FINAL_STAGES:
            out[t.component_id] = endpoint
    return out


def test_command_scan_endpoints_fail_closed(targets):
    """The assertion #891 was filed for.

    `ls -t .../baselines/*.json | head -1` reported healthy on empty stdout
    because the pipeline returned `head`'s status. A bare `journalctl ...`
    reported healthy on a deleted unit for the same reason.
    """
    offenders = _fail_open_endpoints(targets)
    unexpected = {k: v for k, v in offenders.items() if k not in PENDING_FAIL_CLOSED_ENDPOINT}
    assert not unexpected, (
        "these command-scan endpoints do not end in a stage that fails when it "
        "finds nothing, so they can report healthy on no evidence:\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(unexpected.items()))
        + f"\n\nThese final stages succeed on empty input: "
        f"{sorted(FAIL_OPEN_FINAL_STAGES)}. Filter the pipeline through grep/test, "
        "move the component to a pointer method, or record an exemption in "
        "PENDING_FAIL_CLOSED_ENDPOINT with the issue that owns it."
    )


def test_fail_closed_exemptions_have_not_gone_stale(targets):
    offenders = _fail_open_endpoints(targets)
    known = {t.component_id for t in targets}
    stale = []
    for component, owner in PENDING_FAIL_CLOSED_ENDPOINT.items():
        if component not in known:
            stale.append(f"  {component} — no longer in the inventory ({owner})")
        elif component not in offenders:
            stale.append(f"  {component} — endpoint now fails closed ({owner})")
    assert not stale, "PENDING_FAIL_CLOSED_ENDPOINT is stale:\n" + "\n".join(stale)


def test_felix_health_check_still_declares_its_success_allowlist(targets):
    """Deleting the allow-list silently reverts `status` to the fail-open
    deny-list, where UNKNOWN and SCRIPT_MISSING read healthy again (#891).
    Nothing else in the data would show that."""
    hc = next(
        (t.health_check for t in targets if t.component_id == "felix-health-check"),
        None,
    )
    assert hc is not None, "felix-health-check missing from the inventory"
    declared = hc.get("success_status_values")
    assert declared, "felix-health-check must declare success_status_values"
    assert set(declared) == {"ALL_HEALTHY", "FAILURES_DETECTED"}, (
        f"unexpected success set {declared!r} — UNKNOWN and SCRIPT_MISSING are "
        "runner faults and must not be listed as healthy"
    )


def test_no_near_miss_success_allowlist_key(targets):
    """A misspelled key silently falls back to the fail-open deny-list."""
    near_misses = {"success_status_value", "success_statuses", "healthy_status_values",
                   "success_values", "status_success_values"}
    bad = [
        f"  {t.component_id}: {k}"
        for t in targets
        for k in (t.health_check or {})
        if k in near_misses
    ]
    assert not bad, (
        "near-miss key name; the probe only reads 'success_status_values' and "
        "silently fails open otherwise:\n" + "\n".join(bad)
    )


def test_restic_expected_prose_describes_the_prune_rule(inventory_targets=None):
    """Bind the restic `expected` prose to the ledger, not to a substring.

    Analysis finding I1 (pre-pointer-key-ledger-01M189P6): this mission's
    predecessor fixed two unenforced couplings (#906's prose-vs-code header
    stripping, #902's pointer-vs-probe) and would otherwise have created a
    third — the inventory's `expected` text and `_explicit_error`'s behaviour
    agreed only if a reviewer noticed. The original form of this test guarded
    that with a substring check: `expected` must mention `prune_exit_code` and
    `snapshot_timestamp_utc`, and the prune good-set (a `probes.py` module
    constant) must still equal `{0}`.

    pointer-key-ledger-01M189P6/WP02 (#934) made `health_check.key_ledger`
    the single authoritative, machine-validated description of restic-backup's
    adjudication — the exact coupling this test was written to protect against
    — and reduced `expected` to name the ledger as authoritative rather than
    restate its rules in prose. A substring check against prose that no longer
    states the rules would pass trivially and stop meaning anything, which is
    the same defect class this test exists to catch, just moved one level up.
    So the test is now rewritten to bind prose -> ledger -> behaviour: it
    asserts the ledger exists, that its declared `prune_exit_code` good-set is
    exactly `{0}` and `script_finished_at_utc` is declared `diagnostic_only`
    (the two facts the original test's docstring called out by name), and that
    `expected` points at the ledger as authoritative. This is strictly
    stronger than the substring form — it fails if the ledger's declared
    good-set drifts, not merely if a word goes missing from prose — and
    replaces it as a deliberate strengthening, not an erosion.

    Per research.md R3, this deliberately does NOT assert equality against
    `probes.py`'s `_PRUNE_OK_EXIT_CODES` / `_RESTIC_OK_EXIT_CODES` module
    constants: once the ledger is authoritative for a ledger-declaring
    component, those constants no longer govern it, so an equality test would
    make editing a dead constant silently mutate live adjudication.
    """
    import json
    from pathlib import Path

    inv = json.loads(
        (Path(__file__).resolve().parents[2]
         / "docs/design/architecture/data/service-inventory.json").read_text()
    )
    entry = next(s for s in inv["services"] if s.get("name") == "restic-backup")
    hc = entry["health_check"]
    expected = hc["expected"]

    ledger = hc.get("key_ledger")
    assert ledger is not None, (
        "restic-backup no longer declares a health_check.key_ledger — the "
        "expected prose points at it as authoritative and has nothing to "
        "fall back on without it"
    )

    prune_predicate = ledger["adjudicated"]["prune_exit_code"]
    assert prune_predicate["good_values"] == [0], (
        "the ledger's declared prune_exit_code good-set changed from {0} — "
        "this is a deliberately narrower set than restic_exit_code's {0, 3} "
        "(a named prior regression, #902, was merging the two) and any "
        "change here should be a deliberate, reviewed decision"
    )

    diagnostic_only = ledger["diagnostic_only"]
    assert "script_finished_at_utc" in diagnostic_only, (
        "script_finished_at_utc must stay diagnostic_only — it was once a "
        "freshness fallback and a run producing no snapshot read fresh "
        "through it (#902/FR-009); promoting it back to adjudicated risks "
        "reopening that regression"
    )

    assert "key_ledger" in expected or "ledger" in expected.lower(), (
        "the restic-backup `expected` prose must name the ledger as "
        "authoritative, not restate its rules independently — two "
        "authoritative descriptions of the same rules is the exact defect "
        "this mission exists to retire"
    )
