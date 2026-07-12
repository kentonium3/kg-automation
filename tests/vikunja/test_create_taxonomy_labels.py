"""Tests for scripts.vikunja.create_taxonomy_labels (#715).

All tests inject a fake client mirroring the real ``VikunjaClient`` surface —
``.get/.put/.delete`` with leading-slash paths, list-shaped ``GET /labels``,
empty-dict delete result, typed exceptions for failure modes. No real network
(the global conftest urlopen guard would fail loudly otherwise).
"""
from __future__ import annotations

import json

import pytest

from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaNotFoundError,
    VikunjaServerError,
    VikunjaTimeoutError,
)
from scripts.vikunja import create_taxonomy_labels as ctl

# --- Fidelity reference set (literal — drift here fails loudly) -------------
# INV-1: this MUST match data-model.md / vikunja-configuration-design.md.
EXPECTED_TAXONOMY: dict[str, str] = {
    "f:1-flow": "4caf50",
    "f:2-growth": "fbc02d",
    "f:3-edge": "fb8c00",
    "f:4-overload": "e53935",
    "q:do": "1565c0",
    "q:schedule": "1e88e5",
    "q:delegate": "42a5f5",
    "q:eliminate": "90caf9",
    "t:habit": "8e24aa",
    "loe:s": "bdbdbd",
    "loe:m": "757575",
    "loe:l": "424242",
}
EXPECTED_LEGACY = ("personal", "intentional", "Duplicate")


class _FakeClient:
    """Records get/put/delete calls; serves canned label pages.

    ``pages`` is a list of label-list pages served in order to successive
    ``GET /labels`` calls; when exhausted it yields ``[]``. ``put`` returns a
    fresh dict with an auto-incrementing id. ``get_raises`` / ``delete_raises``
    inject typed exceptions.
    """

    def __init__(
        self,
        *,
        pages=None,
        get_raises=None,
        delete_raises=None,
        next_id=1000,
    ):
        self._pages = list(pages) if pages is not None else [[]]
        self._get_calls = 0
        self._get_raises = get_raises
        self._delete_raises = delete_raises
        self._next_id = next_id
        self.get_calls: list[tuple[str, dict]] = []
        self.put_calls: list[tuple[str, dict]] = []
        self.delete_calls: list[str] = []

    def get(self, path, *, params=None, **_kwargs):
        self.get_calls.append((path, params or {}))
        if self._get_raises is not None:
            raise self._get_raises
        idx = self._get_calls
        self._get_calls += 1
        if idx < len(self._pages):
            return self._pages[idx]
        return []

    def put(self, path, *, json=None, **_kwargs):  # noqa: A002 - mirror client
        self.put_calls.append((path, json))
        assigned = self._next_id
        self._next_id += 1
        return {"id": assigned, "title": json["title"], "hex_color": json["hex_color"]}

    def delete(self, path, *, params=None, **_kwargs):
        self.delete_calls.append(path)
        if self._delete_raises is not None:
            raise self._delete_raises
        return {}


def _label(label_id, title, hex_color):
    return {"id": label_id, "title": title, "hex_color": hex_color}


def _all_taxonomy_present(start_id=1):
    """A single page containing all 12 taxonomy labels with correct colors."""
    return [
        _label(start_id + i, title, color)
        for i, (title, color) in enumerate(EXPECTED_TAXONOMY.items())
    ]


# ---------------------------------------------------------------------------
# T007 — fidelity
# ---------------------------------------------------------------------------


def test_fidelity_declared_titles_match_expected_set():
    declared = {lbl.title: lbl.hex_color for lbl in ctl.TAXONOMY_LABELS}
    assert declared == EXPECTED_TAXONOMY


def test_fidelity_twelve_labels_no_more_no_fewer():
    assert len(ctl.TAXONOMY_LABELS) == 12
    assert len({lbl.title for lbl in ctl.TAXONOMY_LABELS}) == 12


def test_fidelity_colors_are_bare_lower_hex():
    for lbl in ctl.TAXONOMY_LABELS:
        assert lbl.hex_color == lbl.hex_color.lower()
        assert not lbl.hex_color.startswith("#")
        assert len(lbl.hex_color) == 6


def test_fidelity_legacy_titles_case_sensitive():
    assert ctl.LEGACY_TITLES == EXPECTED_LEGACY
    # Duplicate stays capitalized — a lower-cased 'duplicate' would be wrong.
    assert "Duplicate" in ctl.LEGACY_TITLES
    assert "duplicate" not in ctl.LEGACY_TITLES


# ---------------------------------------------------------------------------
# normalize_color
# ---------------------------------------------------------------------------


def test_normalize_color_strips_hash_and_lowercases():
    assert ctl.normalize_color("#4CAF50") == "4caf50"
    assert ctl.normalize_color("4caf50") == "4caf50"
    assert ctl.normalize_color("#FBC02D") == "fbc02d"


# ---------------------------------------------------------------------------
# T007 — create / idempotency
# ---------------------------------------------------------------------------


def test_create_from_empty_issues_twelve_puts():
    client = _FakeClient(pages=[[]])
    outcomes, id_map, failed = ctl.reconcile(client)
    assert not failed
    assert len(client.put_calls) == 12
    # Every put is PUT /labels with the exact declared body.
    for (path, body), lbl in zip(client.put_calls, ctl.TAXONOMY_LABELS):
        assert path == "/labels"
        assert body == {"title": lbl.title, "hex_color": lbl.hex_color}
    created = [o for o in outcomes if o.action == "created"]
    assert len(created) == 12
    assert len(id_map) == 12


def test_create_from_empty_exit_zero_via_main(capsys):
    client = _FakeClient(pages=[[]])
    rc = ctl.main(["--json"], client=client)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["label_id_map"]) == 12
    assert payload["backup_confirmed"] is None
    # All 12 taxonomy titles created; legacy titles absent → already-absent.
    tax_outcomes = [o for o in payload["outcomes"] if o["title"] in EXPECTED_TAXONOMY]
    assert len(tax_outcomes) == 12
    assert all(o["action"] == "created" for o in tax_outcomes)


def test_skip_existing_mixes_created_and_already_present():
    # First two taxonomy labels already present with correct colors.
    present = [
        _label(1, "f:1-flow", "4caf50"),
        _label(2, "f:2-growth", "fbc02d"),
    ]
    client = _FakeClient(pages=[present])
    outcomes, id_map, failed = ctl.reconcile(client)
    assert not failed
    # 12 total - 2 present = 10 puts, none for the present two.
    assert len(client.put_calls) == 10
    put_titles = {body["title"] for _, body in client.put_calls}
    assert "f:1-flow" not in put_titles
    assert "f:2-growth" not in put_titles
    present_outcomes = {o.title: o for o in outcomes if o.action == "already-present"}
    assert set(present_outcomes) == {"f:1-flow", "f:2-growth"}
    assert id_map["f:1-flow"] == 1
    assert id_map["f:2-growth"] == 2


def test_idempotent_rerun_zero_puts():
    client = _FakeClient(pages=[_all_taxonomy_present()])
    outcomes, id_map, failed = ctl.reconcile(client)
    assert not failed
    assert client.put_calls == []
    assert all(o.action == "already-present" for o in outcomes if o.title in EXPECTED_TAXONOMY)
    assert len(id_map) == 12


def test_idempotent_rerun_exit_zero_via_main():
    client = _FakeClient(pages=[_all_taxonomy_present()])
    rc = ctl.main([], client=client)
    assert rc == 0
    assert client.put_calls == []


def test_color_mismatch_non_zero_no_put():
    present = [_label(1, "f:1-flow", "000000")]  # wrong color
    client = _FakeClient(pages=[present])
    outcomes, _id_map, failed = ctl.reconcile(client)
    assert failed
    mismatch = [o for o in outcomes if o.action == "color-mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0].title == "f:1-flow"
    assert mismatch[0].id == 1
    # No put for the mismatched label.
    assert ("/labels", {"title": "f:1-flow", "hex_color": "4caf50"}) not in client.put_calls


def test_color_mismatch_exit_one_via_main(capsys):
    present = [_label(1, "f:1-flow", "000000")]
    client = _FakeClient(pages=[present])
    rc = ctl.main([], client=client)
    assert rc == 1


def test_color_mismatch_tolerates_hash_and_case():
    # Server echoes with a leading '#' and upper-case: still a match.
    present = [_label(1, "f:1-flow", "#4CAF50")]
    client = _FakeClient(pages=[present])
    outcomes, _id_map, failed = ctl.reconcile(client)
    assert not failed
    f1 = next(o for o in outcomes if o.title == "f:1-flow")
    assert f1.action == "already-present"


def test_duplicate_title_non_zero_no_mutation():
    dupes = [
        _label(1, "f:1-flow", "4caf50"),
        _label(2, "f:1-flow", "4caf50"),
    ]
    client = _FakeClient(pages=[dupes])
    outcomes, _id_map, failed = ctl.reconcile(client)
    assert failed
    dup = [o for o in outcomes if o.action == "duplicate-title"]
    assert len(dup) == 1
    assert dup[0].title == "f:1-flow"
    assert set(dup[0].ids) == {1, 2}
    # No put issued for the duplicate title.
    dup_puts = [c for c in client.put_calls if c[1]["title"] == "f:1-flow"]
    assert dup_puts == []


def test_duplicate_title_exit_one_via_main():
    dupes = [_label(1, "f:1-flow", "4caf50"), _label(2, "f:1-flow", "4caf50")]
    client = _FakeClient(pages=[dupes])
    rc = ctl.main([], client=client)
    assert rc == 1


def test_pagination_full_page_then_short_page():
    # 50 non-taxonomy labels on page 1 forces a second GET; short page 2 stops.
    page1 = [_label(100 + i, f"other-{i}", "111111") for i in range(50)]
    page2 = [_label(999, "f:1-flow", "4caf50")]
    client = _FakeClient(pages=[page1, page2])
    outcomes, _id_map, _failed = ctl.reconcile(client)
    # Exactly two label listing GETs (page 1 full, page 2 short → stop).
    label_gets = [c for c in client.get_calls if c[0] == "/labels"]
    assert len(label_gets) == 2
    assert label_gets[0][1] == {"per_page": "50", "page": "1"}
    assert label_gets[1][1] == {"per_page": "50", "page": "2"}
    # f:1-flow found on page 2 → already-present, not re-created.
    f1 = next(o for o in outcomes if o.title == "f:1-flow")
    assert f1.action == "already-present"


def test_pagination_stops_on_empty_after_exact_full_page():
    # Exactly 50 items on page 1 (all taxonomy pad) forces page 2; empty stops.
    page1 = [_label(100 + i, f"other-{i}", "111111") for i in range(50)]
    client = _FakeClient(pages=[page1, []])
    ctl.reconcile(client)
    label_gets = [c for c in client.get_calls if c[0] == "/labels"]
    assert len(label_gets) == 2


# ---------------------------------------------------------------------------
# T008 — delete / failure-modes / dry-run
# ---------------------------------------------------------------------------


def test_delete_refused_without_backup_ref_no_delete_calls(capsys):
    client = _FakeClient(pages=[[_label(5, "personal", "2196f3")]])
    rc = ctl.main(["--delete-legacy"], client=client)
    assert rc == 2
    assert client.delete_calls == []
    assert "requires --backup-confirmed" in capsys.readouterr().err


def test_delete_with_backup_ref_deletes_and_echoes(capsys):
    labels = _all_taxonomy_present() + [_label(500, "personal", "2196f3")]
    client = _FakeClient(pages=[labels])
    rc = ctl.main(
        ["--delete-legacy", "--backup-confirmed", "restic-abc123", "--json"],
        client=client,
    )
    assert rc == 0
    assert client.delete_calls == ["/labels/500"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["backup_confirmed"] == "restic-abc123"
    deleted = [o for o in payload["outcomes"] if o["action"] == "deleted"]
    assert len(deleted) == 1
    assert deleted[0]["title"] == "personal"


def test_delete_all_matches_for_duplicate_legacy():
    labels = [
        _label(10, "Duplicate", "aaaaaa"),
        _label(11, "Duplicate", "bbbbbb"),
    ]
    client = _FakeClient(pages=[labels])
    outcomes, _id_map, failed = ctl.reconcile(
        client, delete_legacy=True, backup_confirmed="ts"
    )
    assert not failed
    assert set(client.delete_calls) == {"/labels/10", "/labels/11"}
    deleted = [o for o in outcomes if o.action == "deleted"]
    assert {o.id for o in deleted} == {10, 11}


def test_delete_404_relist_absent_is_already_absent():
    # First list has the legacy label; delete 404s; re-list shows it gone.
    class _Client(_FakeClient):
        def __init__(self):
            super().__init__(pages=[[_label(7, "intentional", "4caf50")], []])

        def delete(self, path, *, params=None, **_kwargs):
            self.delete_calls.append(path)
            raise VikunjaNotFoundError(path=path, status=404)

    client = _Client()
    outcomes, _id_map, failed = ctl.reconcile(
        client, delete_legacy=True, backup_confirmed="ts"
    )
    assert not failed
    absent = [o for o in outcomes if o.title == "intentional"]
    assert absent and absent[0].action == "already-absent"


def test_delete_404_relist_still_present_fails():
    # Delete 404s but re-list STILL shows the title → inconsistent view, fail.
    class _Client(_FakeClient):
        def __init__(self):
            super().__init__(
                pages=[
                    [_label(7, "intentional", "4caf50")],  # initial list
                    [_label(9, "intentional", "4caf50")],  # re-list still present
                ]
            )

        def delete(self, path, *, params=None, **_kwargs):
            self.delete_calls.append(path)
            raise VikunjaNotFoundError(path=path, status=404)

    client = _Client()
    _outcomes, _id_map, failed = ctl.reconcile(
        client, delete_legacy=True, backup_confirmed="ts"
    )
    assert failed


def test_delete_404_still_present_exit_one_via_main():
    class _Client(_FakeClient):
        def __init__(self):
            super().__init__(
                pages=[
                    _all_taxonomy_present() + [_label(7, "intentional", "4caf50")],
                    [_label(9, "intentional", "4caf50")],
                ]
            )

        def delete(self, path, *, params=None, **_kwargs):
            self.delete_calls.append(path)
            raise VikunjaNotFoundError(path=path, status=404)

    rc = ctl.main(
        ["--delete-legacy", "--backup-confirmed", "ts"], client=_Client()
    )
    assert rc == 1


def test_skipped_no_flag_when_legacy_present_without_flag():
    labels = _all_taxonomy_present() + [_label(500, "personal", "2196f3")]
    client = _FakeClient(pages=[labels])
    outcomes, _id_map, failed = ctl.reconcile(client)
    assert not failed
    assert client.delete_calls == []
    skipped = [o for o in outcomes if o.action == "skipped-no-flag"]
    assert len(skipped) == 1
    assert skipped[0].title == "personal"
    assert skipped[0].id == 500


def test_legacy_absent_reports_already_absent():
    client = _FakeClient(pages=[_all_taxonomy_present()])
    outcomes, _id_map, _failed = ctl.reconcile(
        client, delete_legacy=True, backup_confirmed="ts"
    )
    absent = {o.title for o in outcomes if o.action == "already-absent"}
    assert absent == set(EXPECTED_LEGACY)
    assert client.delete_calls == []


@pytest.mark.parametrize(
    "exc",
    [
        VikunjaTimeoutError(path="/labels"),
        VikunjaAuthError(path="/labels", status=401),
        VikunjaServerError(path="/labels", status=503),
    ],
)
def test_failure_modes_surfaced_non_zero(exc, capsys):
    client = _FakeClient(get_raises=exc)
    rc = ctl.main([], client=client)
    assert rc == 1
    err = capsys.readouterr().err
    assert type(exc).__name__ in err


def test_dry_run_makes_zero_put_delete_calls(capsys):
    labels = [_label(500, "personal", "2196f3")]  # legacy present, no taxonomy
    client = _FakeClient(pages=[labels])
    rc = ctl.main(
        ["--dry-run", "--delete-legacy", "--backup-confirmed", "dry-run"],
        client=client,
    )
    assert rc == 0
    assert client.put_calls == []
    assert client.delete_calls == []


def test_dry_run_plan_lists_would_create_and_would_delete():
    labels = [_label(500, "personal", "2196f3")]
    client = _FakeClient(pages=[labels])
    outcomes, id_map, failed = ctl.reconcile(
        client, delete_legacy=True, backup_confirmed="dry-run", dry_run=True
    )
    assert not failed
    assert client.put_calls == []
    assert client.delete_calls == []
    # would-create for all 12 taxonomy labels (null id in dry-run).
    created = [o for o in outcomes if o.action == "created"]
    assert len(created) == 12
    assert all(o.id is None for o in created)
    # would-delete for the present legacy label.
    deleted = [o for o in outcomes if o.action == "deleted"]
    assert len(deleted) == 1
    assert deleted[0].title == "personal"
    # id_map stays empty in dry-run (no ids assigned).
    assert id_map == {}


def test_main_human_output_renders_table(capsys):
    client = _FakeClient(pages=[[]])
    rc = ctl.main([], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "RECONCILE" in out
    assert "title->id map" in out
    assert "created" in out


def test_main_dry_run_human_output_labels_plan(capsys):
    client = _FakeClient(pages=[[]])
    rc = ctl.main(["--dry-run"], client=client)
    assert rc == 0
    assert "PLAN (dry-run)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# list_labels / helpers
# ---------------------------------------------------------------------------


def test_list_labels_builds_lists_per_title():
    labels = [
        _label(1, "a", "111111"),
        _label(2, "a", "222222"),
        _label(3, "b", "333333"),
    ]
    client = _FakeClient(pages=[labels])
    by_title = ctl.list_labels(client)
    assert set(by_title) == {"a", "b"}
    assert len(by_title["a"]) == 2
    assert len(by_title["b"]) == 1


def test_list_labels_empty_instance_returns_empty_dict():
    client = _FakeClient(pages=[[]])
    assert ctl.list_labels(client) == {}


def test_list_labels_non_list_body_raises():
    class _BadClient(_FakeClient):
        def get(self, path, *, params=None, **_kwargs):
            self.get_calls.append((path, params or {}))
            return {"not": "a list"}

    with pytest.raises(Exception):
        ctl.list_labels(_BadClient())


def test_duplicate_titles_detects_multi():
    by_title = {"a": [{}, {}], "b": [{}]}
    assert ctl.duplicate_titles(by_title) == {"a"}


def test_token_file_read(tmp_path, monkeypatch):
    # --token-file is read and passed to the client constructor.
    token_file = tmp_path / "tok"
    token_file.write_text("secret-token\n", encoding="utf-8")
    captured = {}

    class _FakeVC:
        def __init__(self, *, base_url=None, token=None):
            captured["base_url"] = base_url
            captured["token"] = token

        def get(self, *a, **k):
            return []

        def put(self, *a, **k):
            return {"id": 1}

    import scripts.common.vikunja_client as vc_mod

    monkeypatch.setattr(vc_mod, "VikunjaClient", _FakeVC)
    rc = ctl.main(["--token-file", str(token_file), "--base-url", "https://x/api/v1"])
    assert rc == 0
    assert captured["token"] == "secret-token\n"
    assert captured["base_url"] == "https://x/api/v1"


# ---------------------------------------------------------------------------
# Post-merge Codex fixes — design-doc fidelity, INV-5 unexpected labels,
# backup-ref hardening, non-int-id fail-loud, reconcile-boundary gate.
# ---------------------------------------------------------------------------


def test_fidelity_design_doc_colors_match_constants():
    """INV-1: the design doc's Color column agrees with the code constants.

    Parses the label tables in docs/design/vikunja-configuration-design.md so
    the "single taxonomy authority" claim is actually verified, not asserted in
    a comment (post-merge review LOW-5).
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    doc = (repo_root / "docs/design/vikunja-configuration-design.md").read_text(
        encoding="utf-8"
    )
    lines = doc.splitlines()
    for title, color in EXPECTED_TAXONOMY.items():
        rows = [ln for ln in lines if f"`{title}`" in ln]
        assert rows, f"design doc has no table row for {title!r}"
        assert any(color.lower() in ln.lower() for ln in rows), (
            f"design doc row for {title!r} is missing color {color}"
        )


def test_unexpected_label_reports_and_fails():
    """INV-5/SC-002: a live label outside taxonomy ∪ legacy is surfaced + fails."""
    page = _all_taxonomy_present() + [_label(9999, "stray-label", "000000")]
    client = _FakeClient(pages=[page])
    outcomes, _id_map, failed = ctl.reconcile(client)
    assert failed is True
    actions = {o.title: o.action for o in outcomes}
    assert actions.get("stray-label") == "unexpected-label"


def test_main_unexpected_label_exits_nonzero():
    page = _all_taxonomy_present() + [_label(9999, "stray-label", "abcdef")]
    client = _FakeClient(pages=[page])
    assert ctl.main([], client=client) == 1


def test_delete_legacy_blank_backup_ref_refused(capsys):
    """A whitespace-only --backup-confirmed does not pass the destructive gate."""
    client = _FakeClient(pages=[_all_taxonomy_present()])
    rc = ctl.main(["--delete-legacy", "--backup-confirmed", "   "], client=client)
    assert rc == 2
    assert client.delete_calls == []


def test_delete_legacy_non_int_id_fails_loud():
    """A legacy label lacking an int id fails loud rather than silently skipping."""
    page = _all_taxonomy_present() + [
        {"id": None, "title": "personal", "hex_color": "2196f3"}
    ]
    client = _FakeClient(pages=[page])
    outcomes, _id_map, failed = ctl.reconcile(
        client, delete_legacy=True, backup_confirmed="snap-1"
    )
    assert failed is True
    assert any(
        o.title == "personal" and o.action == "delete-failed" for o in outcomes
    )
    assert client.delete_calls == []  # no resolvable id, nothing deleted


def test_reconcile_delete_legacy_requires_backup_ref():
    """reconcile() enforces the backup gate at the function boundary too."""
    client = _FakeClient(pages=[_all_taxonomy_present()])
    with pytest.raises(ValueError):
        ctl.reconcile(client, delete_legacy=True)
    with pytest.raises(ValueError):
        ctl.reconcile(client, delete_legacy=True, backup_confirmed="   ")
    assert client.delete_calls == []
