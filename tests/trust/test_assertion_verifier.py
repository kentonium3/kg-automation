"""Tests for scripts.trust.assertion_verifier (#683, WP03).

All tests mock the Vikunja client — no office2 calls, no LLM.
"""
from __future__ import annotations

import json

import pytest

from scripts.trust import assertion_verifier as av
from scripts.trust import completion_assertion as ca
from scripts.vikunja import create_task as ct


class _FakeVikunjaClient:
    """Minimal fake exposing .get(path) like VikunjaClient, keyed by task id."""

    def __init__(self, *, present_ids=None, error_ids=None):
        self._present = set(present_ids or [])
        self._error_ids = set(error_ids or [])
        self.get_calls: list[str] = []

    def get(self, path, **_kwargs):
        self.get_calls.append(path)
        task_id = path.rsplit("/", 1)[-1]
        if task_id in self._error_ids:
            raise RuntimeError("transient vikunja error")
        if task_id in self._present:
            return {"id": int(task_id)}
        from scripts.common.vikunja_client import VikunjaNotFoundError

        raise VikunjaNotFoundError(path=path, status=404)


def _assertion(**overrides):
    base = {
        "ts": "2026-07-10T12:00:00+00:00",
        "agent": "main",
        "request_summary": None,
        "request_ref": None,
        "artifact_kind": "vikunja_task",
        "artifact_ids": ["91"],
        "claim": "Created Vikunja task #38",
    }
    base.update(overrides)
    return base


# --- artifact_missing ---------------------------------------------------------


def test_verify_assertion_missing_vikunja_task_produces_artifact_missing():
    client = _FakeVikunjaClient(present_ids=set())
    findings = av.verify_assertion(_assertion(artifact_ids=["91"]), client=client)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == "artifact_missing"
    assert finding.artifact_id == "91"
    assert finding.agent == "main"
    assert finding.artifact_kind == "vikunja_task"
    assert finding.claim == "Created Vikunja task #38"


def test_verify_assertion_present_vikunja_task_produces_no_finding():
    client = _FakeVikunjaClient(present_ids={"91"})
    findings = av.verify_assertion(_assertion(artifact_ids=["91"]), client=client)
    assert findings == []


# --- per-id independence ------------------------------------------------------


def test_verify_assertion_mixed_present_and_missing_only_flags_missing():
    client = _FakeVikunjaClient(present_ids={"91", "93", "95"})
    seven_ids = [str(91 + i) for i in range(7)]  # 91..97
    findings = av.verify_assertion(
        _assertion(artifact_ids=seven_ids, claim="Created 7 Vikunja reminder tasks"),
        client=client,
    )
    missing_ids = {f.artifact_id for f in findings}
    assert missing_ids == {"92", "94", "96", "97"}
    assert all(f.kind == "artifact_missing" for f in findings)
    assert len(client.get_calls) == 7


def test_verify_assertion_all_present_seven_ids_no_findings():
    seven_ids = [str(91 + i) for i in range(7)]
    client = _FakeVikunjaClient(present_ids=set(seven_ids))
    findings = av.verify_assertion(_assertion(artifact_ids=seven_ids), client=client)
    assert findings == []


# --- unverifiable_kind ---------------------------------------------------------


@pytest.mark.parametrize("kind", ["other", "calendar_event", "vault_note"])
def test_verify_assertion_unverifiable_kinds_warn_no_client_lookup(kind):
    client = _FakeVikunjaClient()
    findings = av.verify_assertion(
        _assertion(artifact_kind=kind, artifact_ids=["x1", "x2"]), client=client
    )
    assert len(findings) == 2
    assert all(f.kind == "unverifiable_kind" for f in findings)
    assert {f.artifact_id for f in findings} == {"x1", "x2"}
    # No Vikunja lookup at all for a non-vikunja_task kind.
    assert client.get_calls == []


# --- transient errors: no false artifact_missing -----------------------------


def test_verify_assertion_transient_client_error_produces_no_finding():
    client = _FakeVikunjaClient(error_ids={"91"})
    findings = av.verify_assertion(_assertion(artifact_ids=["91"]), client=client)
    # A transient error must not fabricate a false artifact_missing.
    assert findings == []


def test_verify_assertion_transient_error_mixed_with_missing():
    client = _FakeVikunjaClient(present_ids=set(), error_ids={"91"})
    findings = av.verify_assertion(
        _assertion(artifact_ids=["91", "92"]), client=client
    )
    # 91 errors transiently (no finding); 92 is confirmed missing.
    assert len(findings) == 1
    assert findings[0].artifact_id == "92"
    assert findings[0].kind == "artifact_missing"


# --- verify_assertion_detailed: conclusiveness signal (F1) -------------------


def test_verify_detailed_all_present_is_conclusive():
    client = _FakeVikunjaClient(present_ids={"91", "92"})
    res = av.verify_assertion_detailed(_assertion(artifact_ids=["91", "92"]), client=client)
    assert res.findings == []
    assert res.indeterminate is False


def test_verify_detailed_missing_is_conclusive_with_finding():
    client = _FakeVikunjaClient(present_ids=set())
    res = av.verify_assertion_detailed(_assertion(artifact_ids=["91"]), client=client)
    assert len(res.findings) == 1
    assert res.indeterminate is False


def test_verify_detailed_transient_error_marks_indeterminate_no_finding():
    client = _FakeVikunjaClient(error_ids={"91"})
    res = av.verify_assertion_detailed(_assertion(artifact_ids=["91"]), client=client)
    assert res.findings == []  # no false artifact_missing
    assert res.indeterminate is True


def test_verify_detailed_mixed_missing_and_transient():
    client = _FakeVikunjaClient(present_ids=set(), error_ids={"91"})
    res = av.verify_assertion_detailed(_assertion(artifact_ids=["91", "92"]), client=client)
    # 92 conclusively missing -> finding; 91 transient -> indeterminate.
    assert {f.artifact_id for f in res.findings} == {"92"}
    assert res.indeterminate is True


def test_verify_detailed_unverifiable_kind_is_conclusive():
    client = _FakeVikunjaClient()
    res = av.verify_assertion_detailed(
        _assertion(artifact_kind="other", artifact_ids=["x1"]), client=client
    )
    assert len(res.findings) == 1
    assert res.findings[0].kind == "unverifiable_kind"
    assert res.indeterminate is False


# --- verify_vikunja_id_present: F2 re-verify primitive -----------------------


def test_verify_vikunja_id_present_true_false_none():
    present = _FakeVikunjaClient(present_ids={"91"})
    assert av.verify_vikunja_id_present("91", client=present) is True
    missing = _FakeVikunjaClient(present_ids=set())
    assert av.verify_vikunja_id_present("91", client=missing) is False
    transient = _FakeVikunjaClient(error_ids={"91"})
    assert av.verify_vikunja_id_present("91", client=transient) is None


# --- dataclass shape -----------------------------------------------------------


def test_assertion_finding_to_dict_matches_schema_fields():
    client = _FakeVikunjaClient(present_ids=set())
    finding = av.verify_assertion(_assertion(artifact_ids=["1"]), client=client)[0]
    d = finding.to_dict()
    assert set(d.keys()) == {"kind", "agent", "artifact_kind", "artifact_id", "claim"}


# --- reader helpers -------------------------------------------------------------


def test_read_assertions_tolerant_of_blank_and_partial_lines(tmp_path):
    path = tmp_path / "2026-07-10.jsonl"
    good = json.dumps({"agent": "main", "artifact_kind": "vikunja_task", "artifact_ids": ["1"], "claim": "c"})
    path.write_text(f"{good}\n\n   \nnot-json-at-all\n{good}\n")
    records = list(av.read_assertions(path))
    assert len(records) == 2
    assert all(r["artifact_ids"] == ["1"] for r in records)


def test_read_assertions_missing_file_yields_nothing(tmp_path):
    records = list(av.read_assertions(tmp_path / "does-not-exist.jsonl"))
    assert records == []


def test_iter_recent_assertions_reads_across_date_partitions(tmp_path, monkeypatch):
    monkeypatch.setenv(ca.ASSERTIONS_DIR_ENV, str(tmp_path))
    (tmp_path / "2026-07-09.jsonl").write_text(
        json.dumps({"agent": "a", "artifact_kind": "vikunja_task", "artifact_ids": ["1"], "claim": "c1"}) + "\n"
    )
    (tmp_path / "2026-07-10.jsonl").write_text(
        json.dumps({"agent": "a", "artifact_kind": "vikunja_task", "artifact_ids": ["2"], "claim": "c2"}) + "\n"
    )
    records = list(av.iter_recent_assertions())
    assert len(records) == 2
    assert {r["claim"] for r in records} == {"c1", "c2"}


def test_iter_recent_assertions_missing_base_dir_yields_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(ca.ASSERTIONS_DIR_ENV, str(tmp_path / "nope"))
    assert list(av.iter_recent_assertions()) == []


# --- Vikunja hook non-breaking (integration with create_task.main) -----------


class _FakeCreateClient:
    def __init__(self, *, put_result):
        self._put_result = put_result
        self.put_calls: list[tuple[str, dict]] = []

    def get(self, path, **_kwargs):
        raise AssertionError(f"unexpected GET {path}")

    def put(self, path, *, json=None, **_kwargs):  # noqa: A002 - mirror client API
        self.put_calls.append((path, json))
        return self._put_result


def test_create_task_main_succeeds_even_if_record_assertion_raises(monkeypatch, capsys):
    def _boom(**_kwargs):
        raise RuntimeError("ledger exploded")

    monkeypatch.setattr(
        "scripts.trust.completion_assertion.record_assertion", _boom
    )
    client = _FakeCreateClient(put_result={"id": 98, "identifier": "#38", "title": "T"})
    rc = ct.main(["--title", "T", "--project", "1"], client=client)
    assert rc == 0
    out = capsys.readouterr().out
    assert "id=98" in out and "identifier=#38" in out
    assert client.put_calls == [("/projects/1/tasks", {"title": "T"})]


def test_create_task_main_emits_assertion_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scripts.trust.completion_assertion.record_assertion",
        lambda **kwargs: calls.append(kwargs) or True,
    )
    client = _FakeCreateClient(put_result={"id": 42, "identifier": "#7", "title": "T"})
    rc = ct.main(["--title", "T", "--project", "1"], client=client)
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["artifact_kind"] == "vikunja_task"
    assert calls[0]["artifact_ids"] == ["42"]
