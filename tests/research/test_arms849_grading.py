"""WP08 T034 — the blinded grading export (contracts/grading-view.md; FR-014, NFR-006).

The exporter is the one place an arm identity could leak to the grader, so the produced view is
grepped here for every forbidden key and value, and every refusal is shown to fire.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from typing import Any

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research import run_849_harness as h
from scripts.research.arms849 import grading
from scripts.research.arms849 import ledger as ledger_mod
from scripts.research.arms849.questions import QUESTIONS
from tests.research.conftest import (
    BLINDING_SEED,
    CORPUS,
    RESEARCH_ENVIRONMENT_SKIP_REASON,
    fake_arms,
    full_run,
    make_runtime,
    open_fake,
)
from tests.research.test_arms849_ledger import (
    SID,
    binding,
    breach_row,
    calibrated,
    fresh,
    ok_row,
    premise,
    rec,
    unreadable_row,
)

pytestmark = pytest.mark.skipif(not (CORPUS / "entities.json").exists(),
                                reason=RESEARCH_ENVIRONMENT_SKIP_REASON)

ID_RE = re.compile(r"q[A-Z0-9]+-[0-9a-f]{6}")
#: Keys that must never appear anywhere in the view (grading-view.md "Forbidden in the view").
FORBIDDEN_KEYS = ("arm", "repeat", "attempt", "seed", "outcome", "plan", "elapsed_s", "prefill_s", "generation_s",
                  "generation_tok_s", "prompt_tokens", "assembled_context_tokens", "output_tokens",
                  "cache_read_tokens", "cache_state", "peak_gtt_gib", "falkordb_rss_peak_mib", "r_g_ratio",
                  "ledger", "path", "error", "context_limit_applied", "k")


@pytest.fixture(scope="module")
def complete(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    path = tmp_path_factory.mktemp("complete") / "primary.jsonl"
    full_run(path)
    return path


@pytest.fixture
def exported(complete: pathlib.Path, tmp_path: pathlib.Path) -> tuple[grading.ExportPaths, Any]:
    with h.open_existing(complete) as ledger:
        paths = grading.export(ledger, BLINDING_SEED, tmp_path / "runs")
        return paths, ledger


def _walk(obj: Any, keys: list[str], values: list[Any]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            _walk(v, keys, values)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, keys, values)
    else:
        values.append(obj)


def test_view_entry_count_equals_the_ok_count(exported):
    paths, ledger = exported
    view = json.loads(paths.view.read_text(encoding="utf-8"))
    n = sum(len(q["entries"]) for q in view["questions"].values())
    assert n == len(ledger.grading_rows()) == 54
    assert len(view["questions"]["C1"]["entries"]) == 9 and len(view["questions"]["B2"]["entries"]) == 6


def test_view_carries_nothing_but_the_allowed_fields(exported, complete):
    paths, _ = exported
    raw = paths.view.read_text(encoding="utf-8")
    view = json.loads(raw)
    assert list(view) == ["questions"] and list(view["questions"]) == [q.id for q in QUESTIONS]
    for qid, q in view["questions"].items():
        assert list(q) == ["question_text", "ask_time", "entries"]
        assert list(q["entries"]) == sorted(q["entries"]), "entries ordered by id"
        for bid, entry in q["entries"].items():
            assert ID_RE.fullmatch(bid) and bid.startswith(f"q{qid}-")
            assert list(entry) == ["text", "truncated"]
    keys: list[str] = []
    values: list[Any] = []
    _walk(view, keys, values)
    for k in FORBIDDEN_KEYS:
        assert k not in keys, f"forbidden key {k!r} in the view"
        assert f'"{k}"' not in raw
    for arm in ("G", "D", "R"):
        assert arm not in values and f'"{arm}"' not in raw, f"arm identifier {arm!r} in the view"
    for leak in (str(BLINDING_SEED), str(complete), complete.name, complete.stem, "exceeds_model_context",
                 "not_implemented", "timeout", "trained", "permitted"):
        assert leak not in raw, f"{leak!r} leaked into the view"
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    assert numbers == [], f"no timing, token count or repeat index may appear: {numbers[:5]}"


def test_the_grep_would_catch_a_leak(exported):
    """Guards the guard: an entry carrying the arm is caught by the same checks."""
    paths, _ = exported
    view = json.loads(paths.view.read_text(encoding="utf-8"))
    first = next(iter(view["questions"]["C1"]["entries"].values()))
    first["arm"] = "G"
    keys: list[str] = []
    values: list[Any] = []
    _walk(view, keys, values)
    assert "arm" in keys and "G" in values


def test_seal_reproduces_the_mapping_from_the_seed(exported):
    paths, ledger = exported
    seal = json.loads(paths.seal.read_text(encoding="utf-8"))
    assert seal["seed"] == BLINDING_SEED
    first_line = ledger.path.read_bytes().split(b"\n", 1)[0]
    assert seal["header_sha256"] == hashlib.sha256(first_line).hexdigest()
    rebuilt = {grading.blinded_id(BLINDING_SEED, r["question"], r["arm"], r["repeat"]):
               {"arm": r["arm"], "question": r["question"], "repeat": r["repeat"]} for r in ledger.grading_rows()}
    assert seal["map"] == rebuilt and len(rebuilt) == 54
    view = json.loads(paths.view.read_text(encoding="utf-8"))
    for bid, cell in seal["map"].items():
        entry = view["questions"][cell["question"]]["entries"][bid]
        row = next(r for r in ledger.grading_rows()
                   if (r["arm"], r["question"], r["repeat"]) == (cell["arm"], cell["question"], cell["repeat"]))
        assert entry == {"text": row["text"], "truncated": row["truncated"]}
    # A different seed draws different ids: the ids come from the seed, not from the cells.
    assert grading.seal_map(ledger, BLINDING_SEED + 1).keys() != seal["map"].keys()


def test_admin_report_holds_the_non_scored_cells_and_lives_apart(exported):
    paths, _ = exported
    admin = json.loads(paths.admin.read_text(encoding="utf-8"))
    cells = admin["non_scored"]
    assert len(cells) == 18 and {c["outcome"] for c in cells} == {"exceeds_model_context"}
    assert all(c["arm"] == "D" and c["prompt_tokens"] > 262_144 for c in cells)
    assert len({paths.view.parent, paths.admin.parent, paths.seal.parent}) == 3
    assert [p.parent.name for p in (paths.view, paths.admin, paths.seal)] == ["views", "admin", "seals"]
    assert paths.view.name == "primary-grading.json"


def test_export_refuses_an_incomplete_ledger(tmp_path):
    path = tmp_path / "partial.jsonl"
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(fake_arms()), limit=30)
        with pytest.raises(grading.ExportRefused, match="incomplete"):
            grading.export(ledger, BLINDING_SEED, tmp_path / "runs")
    assert not (tmp_path / "runs").exists(), "nothing written on a refusal"


def test_export_refuses_not_implemented_cells(tmp_path):
    path = tmp_path / "unbuilt.jsonl"
    arms = fake_arms()
    del arms["R"]
    with open_fake(path) as ledger:
        h.run_session(ledger, make_runtime(arms))
        with pytest.raises(grading.ExportRefused, match="24 not_implemented"):
            grading.export(ledger, BLINDING_SEED, tmp_path / "runs")


def test_export_refuses_a_foreign_seed(complete, tmp_path):
    with h.open_existing(complete) as ledger, pytest.raises(grading.ExportRefused, match="blinding seed"):
        grading.export(ledger, BLINDING_SEED + 1, tmp_path / "runs")


def test_export_refuses_two_outputs_in_one_directory(complete, tmp_path):
    root = tmp_path / "runs"
    (root / "views").mkdir(parents=True)
    (root / "admin").symlink_to(root / "views")
    with h.open_existing(complete) as ledger, pytest.raises(grading.ExportRefused, match="not distinct"):
        grading.export(ledger, BLINDING_SEED, root)
    assert list((root / "views").iterdir()) == []


def test_export_is_idempotent_but_never_overwrites_different_content(complete, tmp_path):
    root = tmp_path / "runs"
    with h.open_existing(complete) as ledger:
        first = grading.export(ledger, BLINDING_SEED, root)
        grading.export(ledger, BLINDING_SEED, root)                    # same bytes: fine
        first.seal.write_text("{}\n", encoding="utf-8")
        with pytest.raises(grading.ExportRefused, match="different content"):
            grading.export(ledger, BLINDING_SEED, root)


def test_blinded_id_format_and_determinism():
    a = grading.blinded_id(11, "C1", "G", 1)
    assert ID_RE.fullmatch(a) and a == grading.blinded_id(11, "C1", "G", 1)
    ids = {grading.blinded_id(11, "C1", arm, r) for arm in ("G", "D", "R") for r in (1, 2, 3)}
    assert len(ids) == 9


def _plain_binding(**gate_shas: str) -> ledger_mod.Binding:
    fields = {"preflight_sha": "a" * 64, "gate_host_sha": "b" * 64, "gate_container_sha": "c" * 64, **gate_shas}
    return ledger_mod.Binding(registration_commit="r", corpus={}, prompt_hash="p", question_manifest_sha="q",
                              serving={}, model_context_tokens=1, limit_applied="none", run_env_commit="e",
                              run_env_manifest_sha="m", code_hashes={}, **fields)


@pytest.mark.parametrize("field", ["preflight_sha", "gate_host_sha", "gate_container_sha"])
def test_binds_skip_gates_is_true_on_any_one_gate_field(field):
    """The single predicate (exporter + harness) covers all three gate fields, each on its own."""
    assert grading.binds_skip_gates(_plain_binding(**{field: grading.SKIP_GATES_SHA})) is True


def test_binds_skip_gates_is_false_on_a_real_binding():
    assert grading.binds_skip_gates(_plain_binding()) is False


def test_harness_and_exporter_share_the_one_predicate():
    """No second copy: the harness has no private skip-gates predicate of its own."""
    assert not hasattr(h, "_binds_skip_gates")
    src = pathlib.Path(h.__file__).read_text(encoding="utf-8") + pathlib.Path(grading.__file__).read_text(encoding="utf-8")
    assert src.count("SKIP_GATES_SHA in (") == 1


# ==========================================================================
# arms-preconditions-01M3FVRY WP01 — completeness and export refusals (ledger-deltas items 1, 5;
# data-model § Smoke ledger identity). NFR-005: no path records a refused, breached, unmeasurable
# or premise-tainted cell as complete.
# ==========================================================================


def _scored(led, key):
    led.begin_attempt(key, SID); rec(led, key, "ok", ok_row(arm=key.arm))


def _complete_but(led, special=None):
    """Score every planned primary cell except ``special`` (key → callable(led, key))."""
    special = special or {}
    calibrated(led)
    for key in ledger_mod.plan_keys():
        if led.terminal(key) is not None:
            continue
        special.get(key, _scored)(led, key)


D_CELL = ledger_mod.RunKey("D", "E1", 3)


def test_a_fully_scored_ledger_is_complete(tmp_path):
    with fresh(tmp_path) as led:
        _complete_but(led)
        assert grading.is_complete(led)[0] is True


def test_a_breached_cell_bars_primary_completeness_and_export(tmp_path):
    def breach(led, key):
        led.begin_attempt(key, SID); rec(led, key, "exceeds_memory_ceiling", breach_row(key.arm))
    with fresh(tmp_path) as led:
        _complete_but(led, {D_CELL: breach})
        assert led.pending_keys(ledger_mod.plan_keys()) == []          # every cell terminal ...
        ok, detail = grading.is_complete(led)
        assert not ok and "exceeds_memory_ceiling" in detail           # ... and still not complete
        with pytest.raises(grading.ExportRefused, match="exceeds_memory_ceiling"):
            grading.export(led, 7, tmp_path / "runs")
        assert not (tmp_path / "runs").exists()


def test_an_unreadable_at_send_cell_bars_primary_completeness_and_export(tmp_path):
    """Cell-terminal (interim, design lead 20260927T034310853223Za953d8513e; a three-way liveness classification is pending Kent's §5 ruling) and never scored: the ledger is never primary-complete while it stands."""
    def unreadable(led, key):
        led.begin_attempt(key, SID); rec(led, key, "sampler_unreadable_at_send", unreadable_row(key.arm))
    with fresh(tmp_path) as led:
        _complete_but(led, {D_CELL: unreadable})
        assert led.pending_keys(ledger_mod.plan_keys()) == []
        assert led.terminal(D_CELL) == "sampler_unreadable_at_send"
        ok, detail = grading.is_complete(led)
        assert not ok and "sampler_unreadable_at_send" in detail
        with pytest.raises(grading.ExportRefused, match="sampler_unreadable_at_send"):
            grading.export(led, 7, tmp_path / "runs")


def test_a_premise_violation_bars_completeness_and_export_even_on_a_scored_ledger(tmp_path):
    """Correction C: the rows are untouched and every cell is scored, but the ledger is unusable."""
    with fresh(tmp_path) as led:
        _complete_but(led)
        led.event("premise_violated", premise())
    with fresh(tmp_path, gated=False) as led:                           # after replay too
        ok, detail = grading.is_complete(led)
        assert not ok and "premise_violated" in detail
        with pytest.raises(grading.ExportRefused, match="premise_violated"):
            grading.export(led, 7, tmp_path / "runs")
        with pytest.raises(h.PrimaryIncomplete, match="premise_violated"):
            h.require_complete_primary(led)


def test_a_smoke_ledger_is_never_complete_primary_or_exportable(tmp_path):
    """Injected defect: a smoke ledger passed to export."""
    with ledger_mod.open_ledger(tmp_path / "smoke.jsonl", binding(), blinding_seed=7,
                                plan=ledger_mod.SMOKE_PLAN) as led:
        ok, detail = grading.is_complete(led)
        assert not ok and "smoke" in detail
        with pytest.raises(grading.ExportRefused, match="smoke"):
            grading.export(led, 7, tmp_path / "runs")
        with pytest.raises(h.PrimaryIncomplete):
            h.require_complete_primary(led)
    assert not (tmp_path / "runs").exists()


def test_seal_map_refuses_a_premise_violated_ledger(tmp_path):
    """Codex WP01 c1: seal_map consumed premise-tainted rows through grading_rows()."""
    with fresh(tmp_path) as led:
        _scored(led, ledger_mod.RunKey("G", "C1", 1))
        led.event("premise_violated", premise())
        with pytest.raises(ledger_mod.LedgerUnusable):
            grading.seal_map(led, 7)
    with fresh(tmp_path, gated=False) as led, pytest.raises(ledger_mod.LedgerUnusable):
        grading.seal_map(led, 7)


def test_the_harness_cannot_reuse_a_calibration_after_a_premise_violation(tmp_path):
    """Codex WP01 c2 (P12): Session.ensure_calibration() and Session._calibration_obj() read the persisted
    calibration; on a premise-violated ledger both refuse, immediately and after replay."""
    with fresh(tmp_path) as led:
        calibrated(led)
        led.event("premise_violated", premise())
        session = h.Session(led, make_runtime(fake_arms()))
        with pytest.raises(ledger_mod.LedgerUnusable):
            session.ensure_calibration()
        with pytest.raises(ledger_mod.LedgerUnusable):
            session._calibration_obj()
    with fresh(tmp_path, gated=False) as led:
        session = h.Session(led, make_runtime(fake_arms()))
        with pytest.raises(ledger_mod.LedgerUnusable):
            session.ensure_calibration()
        with pytest.raises(ledger_mod.LedgerUnusable):
            session._calibration_obj()
