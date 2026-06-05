"""Tests for scripts/habits/identify_workout_task.py (WP01).

Mocks ``urllib.request.urlopen`` so no real Vikunja calls happen during tests.
Covers all 8 test cases enumerated in WP01:

  1. Single workout match (task 17).
  2. Zero matches across all 8 candidates.
  3. Multiple matches → ``ValueError`` mentioning both IDs.
  4. Case-insensitive match (Workout / WORKOUT / workout — strength training).
  5. ``HTTPError`` on a candidate → ``OSError`` raised (NOT silently skipped).
  6. CLI happy path → exit 0 + JSON on stdout.
  7. CLI multiple matches → exit 1, stderr mentions the IDs.
  8. CLI no match → exit 0, stdout = ``"null\n"``.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from scripts.habits import identify_workout_task as iwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(payload):
    """Return a context-manager-compatible mock urlopen response.

    ``urllib.request.urlopen(req, timeout=...)`` returns a response object
    used inside a ``with`` block. The response exposes ``.status`` and
    ``.read()``.
    """
    body = json.dumps(payload).encode("utf-8")
    resp = MagicMock(name="response")
    resp.status = 200
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _http_error(code: int = 404, body: bytes = b'{"message":"not found"}'):
    """Build a ``urllib.error.HTTPError`` suitable for ``side_effect``."""
    return urllib.error.HTTPError(
        url="http://test/", code=code, msg="Not Found",
        hdrs=None, fp=io.BytesIO(body),
    )


def _build_responses(sample_factory, titles_by_id):
    """Return a list of urlopen responses, one per candidate ID.

    ``titles_by_id`` maps ``int -> str`` for the 8 candidates. Any candidate
    missing from the mapping defaults to ``"Habit <id>"``.
    """
    return [
        _resp(sample_factory(task_id=tid, title=titles_by_id.get(tid, f"Habit {tid}")))
        for tid in iwt.DEFAULT_CANDIDATE_IDS
    ]


# ---------------------------------------------------------------------------
# find_workout_task — Python API
# ---------------------------------------------------------------------------


def test_single_workout_match(mock_urlopen, sample_habit_task_response, fake_vikunja_token):
    """Task 17 has title 'Workout — strength training'; all others non-workout."""
    responses = _build_responses(
        sample_habit_task_response,
        {17: "Workout — strength training"},
    )
    # Add specific fields the result dict needs to round-trip.
    responses[3] = _resp(
        sample_habit_task_response(
            task_id=17,
            title="Workout — strength training",
            project_id=1,
            labels=[{"id": 9, "title": "personal"}],
            repeat_after=86400,
            due_date="2026-05-19T08:00:00Z",
        )
    )
    mock_urlopen.side_effect = responses

    result = iwt.find_workout_task("https://vikunja.test/api/v1/", fake_vikunja_token)
    assert result is not None
    assert result["task_id"] == 17
    assert result["title"] == "Workout — strength training"
    assert result["project_id"] == 1
    assert result["labels"] == [{"id": 9, "title": "personal"}]
    assert result["repeat_after"] == 86400
    assert result["due_date"] == "2026-05-19T08:00:00Z"


def test_zero_matches(mock_urlopen, sample_habit_task_response, fake_vikunja_token):
    """No candidate title contains 'workout' → returns None."""
    responses = _build_responses(sample_habit_task_response, {})
    mock_urlopen.side_effect = responses

    result = iwt.find_workout_task("https://vikunja.test/api/v1/", fake_vikunja_token)
    assert result is None


def test_multiple_matches_raises(mock_urlopen, sample_habit_task_response, fake_vikunja_token):
    """Two candidates with workout-matching titles → ValueError naming both IDs."""
    responses = _build_responses(
        sample_habit_task_response,
        {17: "Workout — strength training", 65: "Cardio workout"},
    )
    mock_urlopen.side_effect = responses

    with pytest.raises(ValueError) as excinfo:
        iwt.find_workout_task("https://vikunja.test/api/v1/", fake_vikunja_token)
    msg = str(excinfo.value)
    assert "17" in msg
    assert "65" in msg


@pytest.mark.parametrize(
    "title",
    ["Workout", "WORKOUT", "workout", "Daily WORKOUT routine", "morning workout"],
)
def test_case_insensitive_match(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token, title
):
    """Title casing variants all match the regex."""
    responses = _build_responses(sample_habit_task_response, {17: title})
    mock_urlopen.side_effect = responses

    result = iwt.find_workout_task("https://vikunja.test/api/v1/", fake_vikunja_token)
    assert result is not None
    assert result["task_id"] == 17
    assert result["title"] == title


def test_http_error_raises_oserror(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token
):
    """One candidate returning HTTP 404 → OSError raised, NOT silently skipped.

    Rationale: a 404 on a known candidate ID means the candidate list is stale
    and the operator must learn about it (research D2).
    """
    # First two candidates return normal task payloads; the third raises 404.
    side_effects = [
        _resp(sample_habit_task_response(task_id=iwt.DEFAULT_CANDIDATE_IDS[0])),
        _resp(sample_habit_task_response(task_id=iwt.DEFAULT_CANDIDATE_IDS[1])),
        _http_error(404),
    ]
    mock_urlopen.side_effect = side_effects

    with pytest.raises(OSError) as excinfo:
        iwt.find_workout_task("https://vikunja.test/api/v1/", fake_vikunja_token)
    assert "404" in str(excinfo.value)


def test_urlerror_raises_oserror(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token
):
    """A network failure (URLError) is also surfaced as OSError."""
    mock_urlopen.side_effect = urllib.error.URLError("name resolution failed")

    with pytest.raises(OSError) as excinfo:
        iwt.find_workout_task("https://vikunja.test/api/v1/", fake_vikunja_token)
    assert "Network failure" in str(excinfo.value) or "name resolution" in str(excinfo.value)


def test_candidate_ids_argument_is_honored(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token
):
    """Custom candidate_ids list overrides the default 8 IDs."""
    mock_urlopen.side_effect = [
        _resp(sample_habit_task_response(task_id=999, title="My Workout")),
    ]
    result = iwt.find_workout_task(
        "https://vikunja.test/api/v1/", fake_vikunja_token, candidate_ids=[999]
    )
    # Only one urlopen call (one custom candidate).
    assert mock_urlopen.call_count == 1
    assert result is not None
    assert result["task_id"] == 999


def test_non_dict_response_raises_oserror(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token
):
    """Vikunja returning a non-object (e.g., a list) is surfaced as OSError."""
    mock_urlopen.side_effect = [_resp(["unexpected", "shape"])]
    with pytest.raises(OSError):
        iwt.find_workout_task(
            "https://vikunja.test/api/v1/", fake_vikunja_token, candidate_ids=[14]
        )


def test_non_json_response_raises_oserror(
    mock_urlopen, fake_vikunja_token
):
    """A response body that isn't valid JSON is surfaced as OSError."""
    resp = MagicMock()
    resp.status = 200
    resp.read = MagicMock(return_value=b"not-json-{")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    mock_urlopen.side_effect = [cm]

    with pytest.raises(OSError):
        iwt.find_workout_task(
            "https://vikunja.test/api/v1/", fake_vikunja_token, candidate_ids=[14]
        )


def test_base_url_without_trailing_slash_works(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token
):
    """A base URL missing the trailing slash is normalized internally."""
    mock_urlopen.side_effect = [
        _resp(sample_habit_task_response(task_id=14, title="Workout"))
    ]
    result = iwt.find_workout_task(
        "http://example.test/api/v1",  # no trailing slash
        fake_vikunja_token,
        candidate_ids=[14],
    )
    assert result is not None
    # Inspect the URL the request was built with.
    sent_request = mock_urlopen.call_args.args[0]
    assert sent_request.full_url == "http://example.test/api/v1/tasks/14"


# ---------------------------------------------------------------------------
# CLI surface — call main() in-process with mocked urlopen + token file
# ---------------------------------------------------------------------------


def test_cli_happy_path(
    capsys, mock_urlopen, sample_habit_task_response, tmp_token_file
):
    """CLI prints the matching task as JSON on stdout, exits 0."""
    responses = _build_responses(
        sample_habit_task_response,
        {17: "Workout"},
    )
    responses[3] = _resp(
        sample_habit_task_response(
            task_id=17,
            title="Workout",
            project_id=2,
            labels=[],
            repeat_after=0,
            due_date="2026-05-20T08:00:00Z",
        )
    )
    mock_urlopen.side_effect = responses

    exit_code = iwt.main(
        [
            "--token-file", str(tmp_token_file),
            "--base-url", "http://example.test/api/v1/",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    stdout = captured.out.strip()
    payload = json.loads(stdout)
    assert payload["task_id"] == 17
    assert payload["title"] == "Workout"
    assert payload["project_id"] == 2


def test_cli_no_match_prints_null_exit_zero(
    capsys, mock_urlopen, sample_habit_task_response, tmp_token_file
):
    """CLI prints the literal token 'null' on stdout and exits 0 when no match."""
    responses = _build_responses(sample_habit_task_response, {})
    mock_urlopen.side_effect = responses

    exit_code = iwt.main(
        [
            "--token-file", str(tmp_token_file),
            "--base-url", "http://example.test/api/v1/",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "null\n"


def test_cli_multiple_matches_exit_one(
    capsys, mock_urlopen, sample_habit_task_response, tmp_token_file
):
    """CLI exits 1 and stderr mentions both matching IDs."""
    responses = _build_responses(
        sample_habit_task_response,
        {17: "Workout", 65: "Cardio workout"},
    )
    mock_urlopen.side_effect = responses

    exit_code = iwt.main(
        [
            "--token-file", str(tmp_token_file),
            "--base-url", "http://example.test/api/v1/",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "17" in captured.err
    assert "65" in captured.err


def test_cli_io_error_exit_two(
    capsys, mock_urlopen, tmp_token_file
):
    """A URLError during lookup → exit code 2."""
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    exit_code = iwt.main(
        [
            "--token-file", str(tmp_token_file),
            "--base-url", "http://example.test/api/v1/",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR" in captured.err


def test_cli_missing_token_file_exit_two(capsys, tmp_path):
    """A missing --token-file path produces exit code 2."""
    missing = tmp_path / "does-not-exist"
    exit_code = iwt.main(
        [
            "--token-file", str(missing),
            "--base-url", "http://example.test/api/v1/",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Token file not found" in captured.err


def test_cli_empty_token_file_exit_two(capsys, tmp_path):
    """An empty token file produces exit code 2."""
    empty = tmp_path / "empty"
    empty.write_text("", encoding="utf-8")
    exit_code = iwt.main(
        [
            "--token-file", str(empty),
            "--base-url", "http://example.test/api/v1/",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "empty" in captured.err.lower()


def test_cli_candidate_ids_flag(
    capsys, mock_urlopen, sample_habit_task_response, tmp_token_file
):
    """--candidate-ids overrides DEFAULT_CANDIDATE_IDS at the CLI."""
    mock_urlopen.side_effect = [
        _resp(sample_habit_task_response(task_id=42, title="Workout")),
    ]
    exit_code = iwt.main(
        [
            "--token-file", str(tmp_token_file),
            "--base-url", "http://example.test/api/v1/",
            "--candidate-ids", "42",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["task_id"] == 42
    assert mock_urlopen.call_count == 1


def test_cli_candidate_ids_bad_value(capsys, tmp_token_file):
    """Non-integer --candidate-ids exits with argparse's usage error (code 2)."""
    with pytest.raises(SystemExit) as excinfo:
        iwt.main(
            [
                "--token-file", str(tmp_token_file),
                "--candidate-ids", "14,not-an-int,16",
            ]
        )
    # argparse uses exit code 2 for usage errors.
    assert excinfo.value.code == 2


def test_cli_help_exits_zero():
    """``--help`` exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        iwt.main(["--help"])
    assert excinfo.value.code == 0


def test_cli_empty_candidate_ids_flag(capsys, tmp_token_file):
    """``--candidate-ids ,, ,`` (all-whitespace) produces argparse error (exit 2)."""
    with pytest.raises(SystemExit) as excinfo:
        iwt.main(
            [
                "--token-file", str(tmp_token_file),
                "--candidate-ids", "  ,  ",
            ]
        )
    assert excinfo.value.code == 2


def test_non_string_title_skipped(
    mock_urlopen, sample_habit_task_response, fake_vikunja_token
):
    """A task with a non-string ``title`` field is skipped defensively.

    The candidate is iterated but never matched; result is None.
    """
    resp = MagicMock()
    resp.status = 200
    # Title field is an int — not a string — so the regex match is skipped.
    resp.read = MagicMock(return_value=json.dumps(
        {"id": 14, "title": 12345, "project_id": 1, "labels": []}
    ).encode("utf-8"))
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    mock_urlopen.side_effect = [cm]

    result = iwt.find_workout_task(
        "https://vikunja.test/api/v1/", fake_vikunja_token, candidate_ids=[14]
    )
    assert result is None


def test_http_error_with_unreadable_body_still_raises(
    mock_urlopen, fake_vikunja_token
):
    """HTTPError whose ``read()`` raises is still surfaced as OSError(HTTP code)."""
    class _BadFP(io.BytesIO):
        def read(self, *_args, **_kwargs):  # type: ignore[override]
            raise OSError("body read failed")

    fp = _BadFP(b"")
    err = urllib.error.HTTPError(
        url="http://test/", code=500, msg="Server Error",
        hdrs=None, fp=fp,
    )
    try:
        mock_urlopen.side_effect = err
        with pytest.raises(OSError) as excinfo:
            iwt.find_workout_task(
                "https://vikunja.test/api/v1/", fake_vikunja_token, candidate_ids=[14]
            )
        assert "500" in str(excinfo.value)
    finally:
        fp.close()
