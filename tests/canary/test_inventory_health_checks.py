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
    # Its log lines DO lead with an ISO-8601 token (datefmt is explicit), so the
    # bound is live and this entry works today. The rewrite is owned by the
    # substrate move off /tmp.
    "obsidian-sync-heartbeat": "#894",
    # Made fail-closed in #891 (grep + -o short-iso), which also made its bound
    # live for the first time. Migrating it to a pointer needs a writer added to
    # the Python service — tracked separately.
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
    alert on every reboot (#894). Tracked, not yet clean."""
    offenders = sorted(
        t.component_id
        for t in targets
        if "/tmp/" in str((t.health_check or {}).get("endpoint") or (t.health_check or {}).get("state_path") or "")
    )
    assert offenders == ["obsidian-sync-heartbeat"], (
        "the set of components probing a path under /tmp changed; #894 owns "
        f"draining it to empty. Found: {offenders}"
    )
