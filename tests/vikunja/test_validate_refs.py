"""Tests for the ``scripts.vikunja.validate_refs`` CLI (WP02, mission
``vikunja-reference-seam-01KXK68Z``, kentonium3/kg-automation#748/#745).

Locks the CLI contract from ``contracts/vikunja-refs.contract.md``:

- exit ``0`` when the registry is clean;
- exit non-zero (``1``) when any finding is present;
- **unreachable** (the live list raises) → a single ``unreachable`` finding and
  a non-zero exit (``2``) that is *distinct from clean* — never folded into 0;
- ≤2 live list round trips (NFR-002), asserted via a spy client.

All tests inject a fake client (no real network — the global conftest urlopen
guard would fail loudly anyway) and an in-memory registry (WP01's
``set_registry_for_test`` seam).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.common import vikunja_config, vikunja_refs
from scripts.common.vikunja_client import VikunjaError
from scripts.vikunja import validate_refs as vr

# A syntactically valid base URL so ``VikunjaClient`` construction in the
# token-convergence tests never depends on live base-url config resolution.
_FAKE_BASE_URL = "https://host.example/api/v1"


class _SpyClient:
    """Serves canned ``GET /projects`` / ``GET /labels`` and counts calls.

    ``raise_exc`` (when set) is raised on the first ``get`` to simulate an
    unreachable/erroring Vikunja. ``get_calls`` records every requested path so
    tests can assert the ≤2-round-trip budget.
    """

    def __init__(
        self,
        *,
        projects: Any = None,
        labels: Any = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._projects = projects if projects is not None else []
        self._labels = labels if labels is not None else []
        self._raise_exc = raise_exc
        self.get_calls: list[str] = []

    def get(self, path: str, *, params: Any = None) -> Any:
        self.get_calls.append(path)
        if self._raise_exc is not None:
            raise self._raise_exc
        if path == "/projects":
            return self._projects
        if path == "/labels":
            return self._labels
        raise AssertionError(f"unexpected path {path!r}")


_INBOX = {
    "name": "inbox",
    "selector": {"kind": "project_id", "value": 1},
    "title": "Inbox",
    "owner": "kent",
    "provisioned": True,
}
_QSCHEDULE = {
    "name": "q:schedule",
    "selector": {"kind": "label", "value": 23},
    "title": "q:schedule",
    "owner_token": "kent",
}


def _registry(projects: list[dict], labels: list[dict]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_of_truth": "docs/design/vikunja-configuration-design.md",
        "last_verified_utc": "2026-07-15T00:00:00Z",
        "projects": projects,
        "labels": labels,
        "private_projects": [],
    }


@pytest.fixture
def clean_registry():
    """A registry with only provisioned refs (so a matching live set is clean)."""
    vikunja_refs.set_registry_for_test(_registry([_INBOX], [_QSCHEDULE]))
    yield
    vikunja_refs.set_registry_for_test(None)


# ---------------------------------------------------------------------------
# Reachable paths
# ---------------------------------------------------------------------------


def test_clean_registry_exits_zero_and_two_calls(clean_registry, capsys) -> None:
    client = _SpyClient(
        projects=[{"id": 1, "title": "Inbox"}],
        labels=[{"id": 23, "title": "q:schedule"}],
    )
    rc = vr.main([], client=client)
    assert rc == 0
    assert len(client.get_calls) <= 2
    assert client.get_calls == ["/projects", "/labels"]
    assert "registry OK" in capsys.readouterr().out


def test_finding_exits_nonzero(clean_registry, capsys) -> None:
    # Live Inbox id drifted from declared 1 → 42.
    client = _SpyClient(
        projects=[{"id": 42, "title": "Inbox"}],
        labels=[{"id": 23, "title": "q:schedule"}],
    )
    rc = vr.main([], client=client)
    assert rc == 1
    assert len(client.get_calls) <= 2
    assert "id_drift" in capsys.readouterr().out


def test_finding_json_output(clean_registry, capsys) -> None:
    client = _SpyClient(
        projects=[{"id": 42, "title": "Inbox"}],
        labels=[{"id": 23, "title": "q:schedule"}],
    )
    rc = vr.main(["--json"], client=client)
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["unreachable"] is False
    assert [f["kind"] for f in payload["findings"]] == ["id_drift"]


# ---------------------------------------------------------------------------
# Unreachable path — the core guard: distinct from clean
# ---------------------------------------------------------------------------


def test_unreachable_emits_single_finding_and_nonzero(clean_registry, capsys) -> None:
    client = _SpyClient(raise_exc=VikunjaError(path="/projects"))
    rc = vr.main(["--json"], client=client)
    assert rc == 2
    assert rc != 0  # explicit: unreachable is NEVER folded into clean
    out = json.loads(capsys.readouterr().out)
    assert out["unreachable"] is True
    assert [f["kind"] for f in out["findings"]] == ["unreachable"]


def test_unreachable_writes_error_envelope_to_stderr(clean_registry, capsys) -> None:
    client = _SpyClient(raise_exc=VikunjaError(path="/projects"))
    rc = vr.main([], client=client)
    assert rc == 2
    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    assert envelope["error"] == "unreachable"
    assert "detail" in envelope


def test_unreachable_on_generic_exception(clean_registry) -> None:
    client = _SpyClient(raise_exc=ConnectionError("boom"))
    rc = vr.main([], client=client)
    assert rc == 2


# ---------------------------------------------------------------------------
# Token convergence (FR-005) — the validator's default token resolves through
# the SAME single source as the runtime, with no independent literal.
# ---------------------------------------------------------------------------


def test_no_independent_token_literal() -> None:
    """FR-005: the validator no longer carries its own hardcoded token-path
    literal — the single source is get_vikunja_token_path()."""
    assert not hasattr(vr, "DEFAULT_KENT_TOKEN_FILE")


def test_default_token_resolves_via_runtime_single_source(monkeypatch, tmp_path) -> None:
    """With no ``--token-file`` override the validator resolves its token path
    through the runtime single source — the SAME
    ``get_vikunja_token_path`` the Felix runtime / default ``VikunjaClient``
    use — so validator and runtime cannot diverge by construction (FR-005)."""
    token_file = tmp_path / "vikunja-api-kent"
    token_file.write_text("kent-secret-token\n", encoding="utf-8")

    called: dict[str, bool] = {}

    def _fake_get_path() -> Any:
        called["hit"] = True
        return token_file

    monkeypatch.setattr(vikunja_config, "get_vikunja_token_path", _fake_get_path)

    args = vr._build_parser().parse_args(["--base-url", _FAKE_BASE_URL])
    client = vr._build_client(args)

    assert called.get("hit") is True  # resolution went through the single source
    assert client.token == "kent-secret-token"  # and that token was actually used


def test_token_file_override_takes_precedence(monkeypatch, tmp_path) -> None:
    """The explicit ``--token-file`` override is preserved for ops use and wins
    over the runtime single-source default (get_vikunja_token_path is not even
    consulted)."""
    override = tmp_path / "override-token"
    override.write_text("override-token-value\n", encoding="utf-8")

    def _must_not_be_called() -> Any:  # pragma: no cover - asserted via raise
        raise AssertionError(
            "get_vikunja_token_path must not be consulted when --token-file is given"
        )

    monkeypatch.setattr(vikunja_config, "get_vikunja_token_path", _must_not_be_called)

    args = vr._build_parser().parse_args(
        ["--token-file", str(override), "--base-url", _FAKE_BASE_URL]
    )
    client = vr._build_client(args)

    assert client.token == "override-token-value"
