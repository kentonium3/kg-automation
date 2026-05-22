"""Tests for scripts/habits/parse_morning_reply.py (mission #371 / WP02).

Covers ``parse_reply`` (the pure deterministic parser), ``load_morning_list``
(the persistence read path), and the ``main`` CLI entry point.

The most important guarantees this suite enforces (per WP02 reviewer
guidance):

  * SC-002 -- the 2026-05-22 reply ``"Skipped 3,7,8 done"`` must produce
    EXACTLY the intent Kent expressed (positions 3, 7, 8 skipped; rest
    complete). This is the load-bearing acceptance test for #371; the
    fixture is pinned at ``tests/habits/fixtures/morning-checkin-2026-05-22.json``.

  * NFR-001 byte-determinism -- the parser MUST be a pure function. Same
    inputs produce byte-identical JSON output. Verified by running the
    parser twice and comparing ``json.dumps(asdict(...))``.

  * Ambiguous-substring routing -- ``"PT done"`` against multiple PT
    titles MUST emit a ``judgment_required`` item, NEVER silently pick.

  * CLI exit codes per ``contracts/cli.md`` -- 0/1/3/4/5. Including:
    --bogus -> 3 (via the _StructuredArgumentParser pattern from WP01),
    missing morning-list -> 4, corrupt morning-list -> 5.

  * Coverage -- this suite targets >=85% line + branch on
    ``parse_morning_reply``.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.habits import parse_morning_reply as pmr
from scripts.habits.morning_checkin_list import MorningList, MorningListHabit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SC002_FIXTURE = FIXTURES_DIR / "morning-checkin-2026-05-22.json"


def _build_list(*habits: tuple[int, int, str]) -> MorningList:
    """Compact ``MorningList`` builder. Each habit is (position, task_id, title)."""
    return MorningList(
        schema_version=1,
        date="2026-05-22",
        generated_at="2026-05-22T11:05:00Z",
        habits=[
            MorningListHabit(position=p, vikunja_task_id=t, title=title)
            for p, t, title in habits
        ],
    )


@pytest.fixture
def sc002_morning_list() -> MorningList:
    """Load the 2026-05-22 fixture from disk (SC-002 byte-pinned scenario)."""
    return pmr.load_morning_list(date="2026-05-22", state_dir=FIXTURES_DIR)


@pytest.fixture
def small_list() -> MorningList:
    """A 3-habit list for compact tokenization tests."""
    return _build_list(
        (1, 100, "Wake at 5:00 AM"),
        (2, 101, "Meditate"),
        (3, 102, "Read 30 min"),
    )


@pytest.fixture
def pt_ambiguous_list() -> MorningList:
    """A list where the substring 'PT' matches three habits.

    Mirrors the SC-003 scenario in data-model.md and the real 2026-05-22
    morning list (positions 3, 6, 7 are all PT habits).
    """
    return _build_list(
        (1, 14, "Wake at 5:00 AM"),
        (2, 18, "Meditate"),
        (3, 19, "Morning shoulder PT"),
        (4, 20, "Get steps in today"),
        (5, 65, "Read 30 min minimum"),
        (6, 16, "Evening shoulder PT"),
        (7, 17, "Morning hip PT"),
        (8, 15, "Strength training"),
    )


# ---------------------------------------------------------------------------
# Group 1 -- Module shape (dataclasses + constants)
# ---------------------------------------------------------------------------


class TestModuleShape:
    def test_constants(self):
        assert pmr.SCHEMA_VERSION == 1
        assert pmr.DEFAULT_STATE_DIR == Path("/data/services/openclaw/state/habits")
        # LOCAL_TZ should be America/New_York per WP01 + Kent's lived day.
        assert str(pmr.LOCAL_TZ) == "America/New_York"

    def test_dataclasses_are_frozen(self):
        # ParseTuple is frozen + has the expected fields.
        t = pmr.ParseTuple(task_id=1, state="complete", matched_via="position", position=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.task_id = 2  # type: ignore[misc]

        ji = pmr.JudgmentItem(
            token="PT",
            candidate_task_ids=[1, 2],
            candidate_titles=["a", "b"],
            inferred_state="complete",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ji.token = "x"  # type: ignore[misc]

        err = pmr.ParseError(type="unparseable_reply", detail="boom")
        with pytest.raises(dataclasses.FrozenInstanceError):
            err.detail = "other"  # type: ignore[misc]

    def test_parse_result_dataclass(self):
        r = pmr.ParseResult(
            schema_version=1,
            reply_text="x",
            morning_list_path="/p",
            tuples=[],
            judgment_required=[],
            errors=[],
        )
        assert r.schema_version == 1
        assert r.reply_text == "x"


# ---------------------------------------------------------------------------
# Group 2 -- SC-002 (the load-bearing acceptance test from #371)
# ---------------------------------------------------------------------------


class TestSC002:
    """SC-002: the 2026-05-22 reply must produce Kent's exact intent.

    From #371 evidence: ``"Skipped 3,7,8 done"`` means positions 3, 7, 8 are
    skipped and the rest (1, 2, 4, 5, 6) are complete.
    """

    def test_sc002_2026_05_22_reply(self, sc002_morning_list: MorningList):
        result = pmr.parse_reply(
            reply_text="Skipped 3,7,8 done",
            morning_list=sc002_morning_list,
        )

        # No ambiguity, no errors.
        assert result.judgment_required == []
        assert result.errors == []

        # Exactly 8 tuples (one per habit in the morning list).
        assert len(result.tuples) == 8

        # Build the expected output explicitly. Sorted by position.
        expected = [
            (1, 14, "complete"),
            (2, 18, "complete"),
            (3, 19, "skipped"),
            (4, 20, "complete"),
            (5, 65, "complete"),
            (6, 16, "complete"),
            (7, 17, "skipped"),
            (8, 15, "skipped"),
        ]
        actual = [(t.position, t.task_id, t.state) for t in result.tuples]
        assert actual == expected

    def test_sc002_matched_via_position_for_explicit_positions(
        self, sc002_morning_list: MorningList
    ):
        """The explicitly mentioned positions (3, 7, 8) match via 'position';
        the rest-claim positions (1, 2, 4, 5, 6) also match via 'position'
        because that's the only deterministic way to map them.
        """
        result = pmr.parse_reply(
            reply_text="Skipped 3,7,8 done",
            morning_list=sc002_morning_list,
        )
        for t in result.tuples:
            assert t.matched_via == "position"


# ---------------------------------------------------------------------------
# Group 3 -- Special tokens
# ---------------------------------------------------------------------------


class TestSpecialTokens:
    @pytest.mark.parametrize(
        "reply",
        ["all done", "All Done", "all complete", "everything done", "done with everything"],
    )
    def test_all_done_family(self, small_list: MorningList, reply: str):
        result = pmr.parse_reply(reply_text=reply, morning_list=small_list)
        assert result.judgment_required == []
        assert result.errors == []
        assert len(result.tuples) == 3
        for t in result.tuples:
            assert t.state == "complete"
            assert t.matched_via == "special_token"

    def test_nothing_done_maps_to_incomplete(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="nothing done", morning_list=small_list)
        assert result.errors == []
        assert all(t.state == "incomplete" for t in result.tuples)
        assert len(result.tuples) == 3

    def test_skipping_everything_maps_to_skipped(self, small_list: MorningList):
        result = pmr.parse_reply(
            reply_text="skipping everything", morning_list=small_list
        )
        assert result.errors == []
        assert all(t.state == "skipped" for t in result.tuples)
        assert len(result.tuples) == 3

    def test_skipped_all_maps_to_skipped(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="skipped all", morning_list=small_list)
        assert all(t.state == "skipped" for t in result.tuples)


# ---------------------------------------------------------------------------
# Group 4 -- Number references
# ---------------------------------------------------------------------------


class TestNumberReferences:
    def test_single_number_done(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="1 done", morning_list=small_list)
        assert result.errors == []
        assert result.judgment_required == []
        # No rest-claim because the verb consumed the pending id.
        assert len(result.tuples) == 1
        assert result.tuples[0].position == 1
        assert result.tuples[0].task_id == 100
        assert result.tuples[0].state == "complete"
        assert result.tuples[0].matched_via == "position"

    def test_skipped_number(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="skipped 3", morning_list=small_list)
        assert len(result.tuples) == 1
        assert result.tuples[0].position == 3
        assert result.tuples[0].state == "skipped"

    def test_comma_separated_list_verb_last(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="1, 2, 3 done", morning_list=small_list)
        assert result.errors == []
        assert len(result.tuples) == 3
        positions = [t.position for t in result.tuples]
        assert positions == [1, 2, 3]
        assert all(t.state == "complete" for t in result.tuples)

    def test_comma_separated_list_verb_first(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="skipped 1, 2, 3", morning_list=small_list)
        assert result.errors == []
        assert len(result.tuples) == 3
        assert all(t.state == "skipped" for t in result.tuples)

    def test_out_of_range_position_emits_invalid_token(
        self, small_list: MorningList
    ):
        result = pmr.parse_reply(reply_text="99 done", morning_list=small_list)
        assert len(result.tuples) == 0
        assert len(result.errors) == 1
        assert result.errors[0].type == "invalid_token"
        assert "99" in result.errors[0].detail


# ---------------------------------------------------------------------------
# Group 5 -- Title matches (exact + substring + ambiguous)
# ---------------------------------------------------------------------------


class TestTitleMatching:
    def test_exact_title_match(self, small_list: MorningList):
        # "Meditate" is the exact title of position 2.
        result = pmr.parse_reply(reply_text="Meditate done", morning_list=small_list)
        assert result.errors == []
        assert len(result.tuples) == 1
        assert result.tuples[0].task_id == 101
        assert result.tuples[0].matched_via == "exact_title"

    def test_exact_title_match_case_insensitive(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="MEDITATE done", morning_list=small_list)
        assert len(result.tuples) == 1
        assert result.tuples[0].matched_via == "exact_title"

    def test_unique_substring_match(self, pt_ambiguous_list: MorningList):
        # "Wake" is a substring of "Wake at 5:00 AM" and matches only that habit.
        result = pmr.parse_reply(
            reply_text="wake done", morning_list=pt_ambiguous_list
        )
        assert result.errors == []
        assert result.judgment_required == []
        assert len(result.tuples) == 1
        assert result.tuples[0].task_id == 14
        assert result.tuples[0].matched_via == "substring"

    def test_ambiguous_substring_emits_judgment_required(
        self, pt_ambiguous_list: MorningList
    ):
        """SC-003 scenario: 'PT done' against 3 PT habits MUST emit
        judgment_required, NOT silently pick one.
        """
        result = pmr.parse_reply(reply_text="PT done", morning_list=pt_ambiguous_list)
        # No tuples emitted for ambiguous tokens.
        assert all(t.matched_via != "substring" for t in result.tuples) or not result.tuples
        # judgment_required emitted with 3 candidates.
        assert len(result.judgment_required) == 1
        ji = result.judgment_required[0]
        assert ji.token == "PT"
        assert sorted(ji.candidate_task_ids) == sorted([19, 16, 17])
        assert ji.inferred_state == "complete"
        # And no silent guess landed in tuples.
        assert all(t.task_id not in ji.candidate_task_ids for t in result.tuples)

    def test_ambiguous_substring_skipped_inferred_state(
        self, pt_ambiguous_list: MorningList
    ):
        result = pmr.parse_reply(
            reply_text="skipped PT", morning_list=pt_ambiguous_list
        )
        assert len(result.judgment_required) == 1
        assert result.judgment_required[0].inferred_state == "skipped"

    def test_unparseable_token_emits_error(self, small_list: MorningList):
        result = pmr.parse_reply(reply_text="xyzzy done", morning_list=small_list)
        assert len(result.errors) == 1
        assert result.errors[0].type == "unparseable_reply"
        assert "xyzzy" in result.errors[0].detail


# ---------------------------------------------------------------------------
# Group 6 -- Mixed clauses + per-clause state inference
# ---------------------------------------------------------------------------


class TestMixedClauses:
    def test_mixed_numbers_and_titles(self, small_list: MorningList):
        """``"1 done, skipped 3, Meditate done"`` -> three claims:
        (complete, [1]), (skipped, [3]), (complete, [Meditate]).
        """
        result = pmr.parse_reply(
            reply_text="1 done, skipped 3, Meditate done",
            morning_list=small_list,
        )
        assert result.errors == []
        assert result.judgment_required == []
        assert len(result.tuples) == 3

        # Build expected dict: position -> (task_id, state)
        actual = {t.position: (t.task_id, t.state) for t in result.tuples}
        # Position 1 -> 100/complete
        assert actual[1] == (100, "complete")
        # Position 3 -> 102/skipped
        assert actual[3] == (102, "skipped")
        # "Meditate" matched as exact_title (no position attr set)
        # Find it by task_id.
        meditate_tuples = [t for t in result.tuples if t.task_id == 101]
        assert len(meditate_tuples) == 1
        assert meditate_tuples[0].state == "complete"
        assert meditate_tuples[0].matched_via == "exact_title"

    def test_per_clause_state_inference_does_not_misattribute(
        self, small_list: MorningList
    ):
        """The critical anti-pattern: "1 done, skipped 3" must NOT pair "done"
        with "3" or "skipped" with "1".
        """
        result = pmr.parse_reply(
            reply_text="1 done, skipped 3", morning_list=small_list
        )
        assert len(result.tuples) == 2
        by_position = {t.position: t.state for t in result.tuples}
        assert by_position[1] == "complete"
        assert by_position[3] == "skipped"


# ---------------------------------------------------------------------------
# Group 7 -- Byte-determinism (NFR-001)
# ---------------------------------------------------------------------------


class TestDeterminism:
    """NFR-001: same inputs -> byte-identical outputs."""

    def test_determinism_sc002(self, sc002_morning_list: MorningList):
        r1 = pmr.parse_reply(
            reply_text="Skipped 3,7,8 done",
            morning_list=sc002_morning_list,
        )
        r2 = pmr.parse_reply(
            reply_text="Skipped 3,7,8 done",
            morning_list=sc002_morning_list,
        )
        # Dict-level equality first.
        assert dataclasses.asdict(r1) == dataclasses.asdict(r2)
        # Byte-identical JSON serialization.
        s1 = json.dumps(dataclasses.asdict(r1), ensure_ascii=False, sort_keys=True)
        s2 = json.dumps(dataclasses.asdict(r2), ensure_ascii=False, sort_keys=True)
        assert s1 == s2
        # And the standard (non-sort_keys) form -- still deterministic because
        # Python's dict preserves insertion order and dataclasses.asdict
        # walks fields in declaration order.
        s1u = json.dumps(dataclasses.asdict(r1), ensure_ascii=False)
        s2u = json.dumps(dataclasses.asdict(r2), ensure_ascii=False)
        assert s1u == s2u

    def test_determinism_ambiguous_case(self, pt_ambiguous_list: MorningList):
        r1 = pmr.parse_reply(
            reply_text="PT done, meditate done",
            morning_list=pt_ambiguous_list,
        )
        r2 = pmr.parse_reply(
            reply_text="PT done, meditate done",
            morning_list=pt_ambiguous_list,
        )
        assert dataclasses.asdict(r1) == dataclasses.asdict(r2)


# ---------------------------------------------------------------------------
# Group 8 -- load_morning_list
# ---------------------------------------------------------------------------


class TestLoadMorningList:
    def test_load_happy_path(self):
        ml = pmr.load_morning_list(date="2026-05-22", state_dir=FIXTURES_DIR)
        assert ml.schema_version == 1
        assert ml.date == "2026-05-22"
        assert len(ml.habits) == 8
        assert ml.habits[0].position == 1
        assert ml.habits[0].title == "Wake at 5:00 AM"

    def test_load_missing_file_raises_filenotfounderror(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            pmr.load_morning_list(date="1999-01-01", state_dir=tmp_path)

    def test_load_corrupt_json_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)

    def test_load_non_object_top_level_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)

    def test_load_missing_required_field_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text(
            json.dumps({"schema_version": 1, "date": "2026-05-22"}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="habits"):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)

    def test_load_habits_not_list_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text(
            json.dumps(
                {"schema_version": 1, "date": "2026-05-22", "habits": "not a list"}
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="habits"):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)

    def test_load_habit_not_object_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text(
            json.dumps(
                {"schema_version": 1, "date": "2026-05-22", "habits": ["not an object"]}
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)

    def test_load_habit_missing_field_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "date": "2026-05-22",
                    "habits": [{"position": 1, "title": "x"}],  # missing task_id
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="vikunja_task_id"):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)

    def test_load_habit_field_type_error_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "date": "2026-05-22",
                    "habits": [
                        {
                            "position": "not-an-int",
                            "vikunja_task_id": 1,
                            "title": "x",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            pmr.load_morning_list(date="2026-05-22", state_dir=tmp_path)


# ---------------------------------------------------------------------------
# Group 9 -- CLI exit codes (per contracts/cli.md)
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            pmr.main(["--help"])
        assert excinfo.value.code == 0

    def test_cli_bogus_flag_exits_3(self, capsys):
        rc = pmr.main(["--bogus"])
        assert rc == 3
        captured = capsys.readouterr()
        # Structured stderr JSON line.
        msg = json.loads(captured.err.strip())
        assert msg["step"] == "argparse"

    def test_cli_no_reply_exits_3(self, capsys):
        rc = pmr.main([])
        assert rc == 3
        captured = capsys.readouterr()
        msg = json.loads(captured.err.strip())
        assert msg["step"] == "argparse"

    def test_cli_both_reply_flags_exits_3(self, capsys):
        rc = pmr.main(["--reply", "1 done", "--reply-file", "/tmp/x"])
        assert rc == 3

    def test_cli_bad_date_format_exits_3(self, capsys):
        rc = pmr.main(["--reply", "1 done", "--date", "bogus"])
        assert rc == 3
        captured = capsys.readouterr()
        msg = json.loads(captured.err.strip())
        assert "YYYY-MM-DD" in msg["error"]

    def test_cli_impossible_date_exits_3(self, capsys):
        # 2026-13-99 is YYYY-MM-DD shape but not a real date.
        rc = pmr.main(["--reply", "1 done", "--date", "2026-13-99"])
        assert rc == 3

    def test_cli_missing_morning_list_exits_4(self, tmp_path: Path, capsys):
        rc = pmr.main(
            [
                "--reply",
                "1 done",
                "--date",
                "1999-01-01",
                "--state-dir",
                str(tmp_path),
            ]
        )
        assert rc == 4
        captured = capsys.readouterr()
        # Partial ParseResult emitted on stdout per contracts/cli.md.
        result_doc = json.loads(captured.out)
        assert result_doc["errors"]
        assert result_doc["errors"][0]["type"] == "no_morning_list"

    def test_cli_corrupt_morning_list_exits_5(self, tmp_path: Path, capsys):
        path = tmp_path / "morning-checkin-2026-05-22.json"
        path.write_text("{not valid json", encoding="utf-8")
        rc = pmr.main(
            [
                "--reply",
                "1 done",
                "--date",
                "2026-05-22",
                "--state-dir",
                str(tmp_path),
            ]
        )
        assert rc == 5
        captured = capsys.readouterr()
        result_doc = json.loads(captured.out)
        assert result_doc["errors"]

    def test_cli_happy_path_exits_0(self, tmp_path: Path, capsys):
        # Copy SC-002 fixture to tmp_path so the CLI can find it.
        shutil.copy(SC002_FIXTURE, tmp_path / "morning-checkin-2026-05-22.json")
        rc = pmr.main(
            [
                "--reply",
                "Skipped 3,7,8 done",
                "--date",
                "2026-05-22",
                "--state-dir",
                str(tmp_path),
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        doc = json.loads(captured.out)
        assert doc["reply_text"] == "Skipped 3,7,8 done"
        assert len(doc["tuples"]) == 8

    def test_cli_reply_file_happy_path(self, tmp_path: Path, capsys):
        shutil.copy(SC002_FIXTURE, tmp_path / "morning-checkin-2026-05-22.json")
        reply_file = tmp_path / "reply.txt"
        reply_file.write_text("Skipped 3,7,8 done\n", encoding="utf-8")
        rc = pmr.main(
            [
                "--reply-file",
                str(reply_file),
                "--date",
                "2026-05-22",
                "--state-dir",
                str(tmp_path),
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        doc = json.loads(captured.out)
        assert len(doc["tuples"]) == 8

    def test_cli_reply_file_missing_exits_1(self, tmp_path: Path, capsys):
        rc = pmr.main(
            [
                "--reply-file",
                str(tmp_path / "does-not-exist.txt"),
                "--state-dir",
                str(tmp_path),
            ]
        )
        assert rc == 1
        captured = capsys.readouterr()
        msg = json.loads(captured.err.strip())
        assert msg["step"] == "reply_file_read"

    def test_cli_default_date_uses_today_local(self, tmp_path: Path, capsys):
        """Verify ``_today_local()`` is consulted when --date is omitted.

        We monkeypatch ``_today_local`` to a known value, then point
        ``--state-dir`` at tmp_path with no fixture; expect exit 4.
        """
        with patch.object(pmr, "_today_local", return_value="2030-01-01"):
            rc = pmr.main(
                ["--reply", "1 done", "--state-dir", str(tmp_path)]
            )
        assert rc == 4
        captured = capsys.readouterr()
        # The missing-file error should reference the patched date.
        assert "2030-01-01" in captured.err


# ---------------------------------------------------------------------------
# Group 10 -- Tokenizer + verb canonicalization
# ---------------------------------------------------------------------------


class TestTokenization:
    def test_didnt_canonicalized(self, small_list: MorningList):
        result = pmr.parse_reply(
            reply_text="3 didn't", morning_list=small_list
        )
        # Expect position 3 -> incomplete via the didn't -> incomplete map.
        assert len(result.tuples) == 1
        assert result.tuples[0].position == 3
        assert result.tuples[0].state == "incomplete"

    def test_did_not_canonicalized(self, small_list: MorningList):
        result = pmr.parse_reply(
            reply_text="3 did not", morning_list=small_list
        )
        assert len(result.tuples) == 1
        assert result.tuples[0].state == "incomplete"

    def test_not_done_canonicalized(self, small_list: MorningList):
        result = pmr.parse_reply(
            reply_text="3 not done", morning_list=small_list
        )
        assert len(result.tuples) == 1
        assert result.tuples[0].state == "incomplete"

    def test_verb_only_with_no_other_input_is_rest_claim(self, small_list: MorningList):
        # "done" alone -> rest-claim against all positions.
        result = pmr.parse_reply(reply_text="done", morning_list=small_list)
        # All three positions get complete via rest-claim.
        assert len(result.tuples) == 3
        assert all(t.state == "complete" for t in result.tuples)

    def test_multiple_rest_claim_verbs_emit_error(self, small_list: MorningList):
        # "done, skipped" both have no IDs adjacent -> two rest-claim
        # candidates -> the second one becomes an error.
        result = pmr.parse_reply(reply_text="done, skipped", morning_list=small_list)
        # First rest-claim wins for all positions.
        assert len(result.tuples) == 3
        # Second rest-claim should produce an error.
        assert len(result.errors) == 1
        assert result.errors[0].type == "unparseable_reply"
        assert "multiple verbs without identifiers" in result.errors[0].detail.lower() or \
            "rest" in result.errors[0].detail.lower()

    def test_id_with_no_verb_emits_error(self, small_list: MorningList):
        # "1, 2" alone -- no verb claims them.
        result = pmr.parse_reply(reply_text="1, 2", morning_list=small_list)
        # Both should emit unparseable_reply errors.
        assert len(result.errors) >= 1
        assert all(e.type == "unparseable_reply" for e in result.errors)
        assert len(result.tuples) == 0

    def test_and_connective_is_break(self, small_list: MorningList):
        """The word "and" acts as a strong clause-break."""
        result = pmr.parse_reply(
            reply_text="1 done and skipped 3", morning_list=small_list
        )
        # Two distinct claims: (complete, [1]) and (skipped, [3]).
        assert result.errors == []
        assert len(result.tuples) == 2
        by_pos = {t.position: t.state for t in result.tuples}
        assert by_pos[1] == "complete"
        assert by_pos[3] == "skipped"

    def test_short_token_does_not_substring_match(self, small_list: MorningList):
        """A 1-char identifier token should not trigger runaway substring matches.

        "a" is a substring of "Wake at 5:00 AM" but matching on single chars
        produces noise. Defensive: tokens of length <2 yield 0 substring
        candidates -> unparseable error.
        """
        result = pmr.parse_reply(reply_text="a done", morning_list=small_list)
        # Either 0 tuples + 1 error, OR exact-title match (unlikely). Verify
        # we did NOT silently match every habit.
        assert len(result.tuples) <= 1


# ---------------------------------------------------------------------------
# Group 11 -- _today_local helper
# ---------------------------------------------------------------------------


class TestTodayLocal:
    def test_today_local_returns_iso_date(self):
        s = pmr._today_local()
        # Shape only -- the actual value is time-of-day-dependent.
        assert len(s) == 10
        assert s[4] == "-" and s[7] == "-"


# ---------------------------------------------------------------------------
# Group 12 -- Multi-word title parsing (codex cycle 1 fix)
# ---------------------------------------------------------------------------


class TestMultiWordTitleParsing:
    """Whole-phrase title resolution before falling back to per-token.

    Codex review feedback on WP02 cycle 1: the prior implementation tokenized
    identifiers word-by-word and resolved each independently. That broke
    multi-word titles -- ``"meditation done, skipped morning shoulder PT"``
    emitted zero tuples plus four spurious errors / ambiguity records.

    These tests pin the new behavior: each clause's identifier list is
    joined into a phrase and tried against habit titles whole-phrase first;
    only pure-position lists ("3,7,8") or whole-phrase failures with
    mixed numeric content fall back to per-token resolution. Bare
    ambiguous tokens like ``"PT"`` (an entire phrase) still surface as
    ``judgment_required``.
    """

    def test_meditation_done_resolves_to_meditate_uniquely(
        self, sc002_morning_list: MorningList
    ):
        """``"meditation done"`` against the 2026-05-22 fixture: one tuple,
        meditate via substring, zero errors, zero judgment_required.

        "meditation" is a substring superset of "meditate" -- the
        bidirectional substring match (title-in-token direction) resolves
        this to position 2 / task_id 18.
        """
        result = pmr.parse_reply(
            reply_text="meditation done",
            morning_list=sc002_morning_list,
        )
        assert result.errors == []
        assert result.judgment_required == []
        assert len(result.tuples) == 1
        t = result.tuples[0]
        assert t.task_id == 18
        assert t.state == "complete"
        assert t.matched_via == "substring"

    def test_skipped_morning_shoulder_pt_resolves_to_exact_title(
        self, sc002_morning_list: MorningList
    ):
        """``"skipped Morning shoulder PT"`` -> exact title match on
        position 3 (Morning shoulder PT), task_id 19, state=skipped.

        The case-insensitive exact-title match resolves the whole phrase
        in one shot rather than producing an ambiguity record for each
        word individually.
        """
        result = pmr.parse_reply(
            reply_text="skipped Morning shoulder PT",
            morning_list=sc002_morning_list,
        )
        assert result.errors == []
        assert result.judgment_required == []
        assert len(result.tuples) == 1
        t = result.tuples[0]
        assert t.task_id == 19
        assert t.state == "skipped"
        assert t.matched_via == "exact_title"

    def test_mixed_meditation_and_morning_shoulder_pt(
        self, sc002_morning_list: MorningList
    ):
        """The full codex scenario: ``"meditation done, skipped morning shoulder PT"``
        -> two ParseTuples (meditate complete, morning_shoulder_PT skipped),
        zero errors, zero judgment_required.

        This is the load-bearing multi-word title parsing test. The prior
        implementation emitted 0 tuples + 1 unparseable_reply (for
        "meditation") + 3 ambiguity records (for "morning", "shoulder",
        "PT" individually). After the fix both clauses produce exactly
        the expected tuples.
        """
        result = pmr.parse_reply(
            reply_text="meditation done, skipped morning shoulder PT",
            morning_list=sc002_morning_list,
        )
        assert result.errors == []
        assert result.judgment_required == []
        assert len(result.tuples) == 2

        by_task = {t.task_id: t for t in result.tuples}
        assert 18 in by_task  # Meditate
        assert by_task[18].state == "complete"
        assert by_task[18].matched_via == "substring"

        assert 19 in by_task  # Morning shoulder PT
        assert by_task[19].state == "skipped"
        assert by_task[19].matched_via == "exact_title"

    def test_wake_at_5_00_am_done_whole_phrase_resolves(
        self, sc002_morning_list: MorningList
    ):
        """``"Wake at 5:00 AM done"`` -> single tuple via loose exact title match.

        The colon in the title and the word ``"at"`` (which is not a verb)
        previously caused the tokenizer to split this into 5 word-by-word
        fragments. After the fix the punctuation-stripped whole phrase
        ("Wake at 5 00 AM" reconstructed from the tokens) matches the
        title ("Wake at 5:00 AM" loose-normalized) as an exact title.
        """
        result = pmr.parse_reply(
            reply_text="Wake at 5:00 AM done",
            morning_list=sc002_morning_list,
        )
        assert result.errors == []
        assert result.judgment_required == []
        assert len(result.tuples) == 1
        t = result.tuples[0]
        assert t.task_id == 14
        assert t.state == "complete"
        assert t.matched_via == "exact_title"

    def test_bare_pt_token_still_ambiguous(
        self, sc002_morning_list: MorningList
    ):
        """``"PT done"`` against the 2026-05-22 fixture (3 PT habits) MUST
        still route to ``judgment_required``. The whole-phrase fix must
        not silently pick one for bare ambiguous tokens (SC-003).

        The fixture has 3 PT habits: position 3 (Morning shoulder PT, 19),
        position 6 (Evening shoulder PT, 16), position 7 (Morning hip PT, 17).
        """
        result = pmr.parse_reply(
            reply_text="PT done",
            morning_list=sc002_morning_list,
        )
        assert result.errors == []
        assert len(result.tuples) == 0
        assert len(result.judgment_required) == 1
        ji = result.judgment_required[0]
        # Token preserved as the phrase (single-word here, so just "PT").
        assert ji.token.lower() == "pt"
        assert sorted(ji.candidate_task_ids) == sorted([19, 16, 17])
        assert ji.inferred_state == "complete"

    def test_word_only_phrase_with_no_match_emits_single_error(
        self, sc002_morning_list: MorningList
    ):
        """A word-only phrase that matches nothing emits ONE
        unparseable_reply error for the whole phrase, not one per token.

        Anti-regression: prior to the fix, ``"foo bar baz done"`` would
        have emitted three independent errors. After the fix it emits a
        single error citing the joined phrase.
        """
        result = pmr.parse_reply(
            reply_text="foo bar baz done",
            morning_list=sc002_morning_list,
        )
        assert len(result.tuples) == 0
        assert len(result.errors) == 1
        assert result.errors[0].type == "unparseable_reply"
        # The phrase should be present in the error detail (lowercase or
        # original form -- either is fine; we check for "foo").
        assert "foo" in result.errors[0].detail

    def test_sc002_byte_determinism_after_fix(
        self, sc002_morning_list: MorningList
    ):
        """Re-verify byte-determinism on SC-002 specifically (the fix
        introduces new code paths that must remain pure).

        Same input twice -> byte-identical JSON output.
        """
        r1 = pmr.parse_reply(
            reply_text="Skipped 3,7,8 done",
            morning_list=sc002_morning_list,
        )
        r2 = pmr.parse_reply(
            reply_text="Skipped 3,7,8 done",
            morning_list=sc002_morning_list,
        )
        s1 = json.dumps(dataclasses.asdict(r1), ensure_ascii=False, sort_keys=True)
        s2 = json.dumps(dataclasses.asdict(r2), ensure_ascii=False, sort_keys=True)
        assert s1 == s2

    def test_multiword_byte_determinism(
        self, sc002_morning_list: MorningList
    ):
        """Byte-determinism on the new multi-word codepath."""
        r1 = pmr.parse_reply(
            reply_text="meditation done, skipped morning shoulder PT",
            morning_list=sc002_morning_list,
        )
        r2 = pmr.parse_reply(
            reply_text="meditation done, skipped morning shoulder PT",
            morning_list=sc002_morning_list,
        )
        s1 = json.dumps(dataclasses.asdict(r1), ensure_ascii=False, sort_keys=True)
        s2 = json.dumps(dataclasses.asdict(r2), ensure_ascii=False, sort_keys=True)
        assert s1 == s2
