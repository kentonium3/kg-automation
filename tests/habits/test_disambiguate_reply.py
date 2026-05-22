"""Tests for scripts/habits/judgment/disambiguate_reply.py (mission #371 / WP03).

Covers the ``disambiguate`` function, the ``main`` CLI entry point, the
cache-aware prompt loading, and the strict response validation that
defends the habits check-in pipeline from LLM drift.

The MOST IMPORTANT guarantee this suite enforces (per WP03 reviewer
guidance) is the **out-of-set chosen_task_id rejection** -- if the LLM
returns a ``chosen_task_id`` that is not in the input's
``candidate_task_ids`` list, ``DisambiguatorError`` MUST be raised. That
is the load-bearing safety check that prevents a hallucinated task_id
from being routed to ``record_completion.py`` downstream (which would
silently complete the wrong habit).

Other guarantees:

  * Cache-control marker present on the system block.
  * Strict JSON validation: malformed JSON, missing fields, wrong types,
    and invalid ``result`` values all surface as ``DisambiguatorError``.
  * Shape A vs Shape B (chosen vs clarify) is enforced -- ``clarify``
    without ``suggested_question`` is a hard-fail.
  * ``suggested_question`` ≤200 chars (WhatsApp budget).
  * CLI exit codes 0/1/3/5 per ``contracts/cli.md``.

No live Anthropic API calls in any test. ``anthropic.Anthropic`` is
monkeypatched at module scope.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.habits.judgment import disambiguate_reply as dr
from scripts.habits.judgment.disambiguate_reply import (
    DisambiguationResult,
    DisambiguatorError,
    disambiguate,
)
from scripts.habits.parse_morning_reply import JudgmentItem


# ---------------------------------------------------------------------------
# Fake Anthropic SDK -- minimal shape compatible with disambiguate()
# ---------------------------------------------------------------------------


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    """Minimal response shape: ``response.content[0].text``."""

    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    """Records the calls + returns canned text per invocation."""

    def __init__(self, text: str = '{"result": "chosen"}') -> None:
        self.calls: list[dict[str, Any]] = []
        self._text = text
        self._raise: BaseException | None = None

    def set_text(self, text: str) -> None:
        self._text = text

    def set_raise(self, exc: BaseException) -> None:
        self._raise = exc

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


@pytest.fixture
def fake_client(monkeypatch) -> _FakeClient:
    """Return a fake Anthropic client + patch ``anthropic.Anthropic``.

    Any code path that does ``anthropic.Anthropic(api_key=...)`` inside
    the module under test will transparently receive the fake client.
    No network I/O is possible.
    """
    client = _FakeClient()
    monkeypatch.setattr(
        dr.anthropic,
        "Anthropic",
        lambda *args, **kwargs: client,
    )
    return client


@pytest.fixture
def api_key_file(tmp_path: Path) -> Path:
    """Write a deterministic fake API key file (mode 0600) and return its path."""
    path = tmp_path / "anthropic.key"
    path.write_text("test-api-key-not-real\n", encoding="utf-8")
    return path


@pytest.fixture
def pt_ambiguity() -> JudgmentItem:
    """The canonical PT ambiguity from the SC-003 scenario.

    Mirrors the data-model.md Entity 3 example: three PT habits matched
    by the bare token ``"PT"``.
    """
    return JudgmentItem(
        token="PT",
        candidate_task_ids=[19, 16, 17],
        candidate_titles=[
            "Morning shoulder PT",
            "Evening shoulder PT",
            "Morning hip PT",
        ],
        inferred_state="complete",
    )


# ---------------------------------------------------------------------------
# Group 1 -- Module shape (constants + dataclasses + prompt file)
# ---------------------------------------------------------------------------


class TestModuleShape:
    def test_module_constants_present(self):
        assert dr.DEFAULT_API_KEY_PATH == Path(
            "/data/services/openclaw/secrets/anthropic"
        )
        assert dr.DEFAULT_MODEL == "claude-haiku-4-5"
        assert dr.DEFAULT_TIMEOUT_SECONDS == 30
        assert dr.DEFAULT_MAX_TOKENS == 256
        assert dr.SCHEMA_VERSION == 1
        assert dr.SUGGESTED_QUESTION_MAX_CHARS == 200

    def test_prompt_template_exists(self):
        assert dr.PROMPT_PATH.is_file()
        body = dr.PROMPT_PATH.read_text(encoding="utf-8")
        assert "[CACHE_PREFIX_START]" in body
        assert "[CACHE_PREFIX_END]" in body

    def test_prompt_template_has_system_and_user_sections(self):
        cached, user_template = dr._load_prompt_template()
        # System block must contain the rules + examples.
        assert "STRICT JSON" in cached.upper() or "Strict JSON" in cached
        assert "chosen" in cached
        assert "clarify" in cached
        # User template must contain the placeholders.
        assert "{reply_text}" in user_template
        assert "{token}" in user_template
        assert "{candidates}" in user_template
        assert "{inferred_state}" in user_template

    def test_disambiguation_result_dataclass_is_frozen(self):
        result = DisambiguationResult(
            schema_version=1,
            result="chosen",
            chosen_task_id=19,
            reason="r",
            suggested_question=None,
        )
        with pytest.raises(Exception):
            result.chosen_task_id = 99  # type: ignore[misc]

    def test_disambiguator_error_is_exception(self):
        assert issubclass(DisambiguatorError, Exception)


# ---------------------------------------------------------------------------
# Group 2 -- disambiguate() happy paths
# ---------------------------------------------------------------------------


class TestDisambiguateChosenHappyPath:
    def test_chosen_in_candidates_returns_result(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 19,
                    "reason": "morning PT context",
                }
            )
        )
        result = disambiguate(
            reply_text="morning PT done",
            ambiguity=pt_ambiguity,
            api_key_path=api_key_file,
        )
        assert isinstance(result, DisambiguationResult)
        assert result.result == "chosen"
        assert result.chosen_task_id == 19
        assert result.reason == "morning PT context"
        assert result.suggested_question is None
        assert result.schema_version == 1

    def test_chosen_at_end_of_candidate_list(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        # Pick task_id 17 (last in the candidate list) to make sure the
        # in-set check uses ``in`` semantics, not just ``==`` to the first.
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 17,
                    "reason": "hip context",
                }
            )
        )
        result = disambiguate(
            reply_text="hip PT done",
            ambiguity=pt_ambiguity,
            api_key_path=api_key_file,
        )
        assert result.chosen_task_id == 17

    def test_call_passes_cache_control_marker(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        """Reviewer's load-bearing check: cache-control on the system block."""
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 19,
                    "reason": "...",
                }
            )
        )
        disambiguate(
            reply_text="PT done",
            ambiguity=pt_ambiguity,
            api_key_path=api_key_file,
        )
        assert fake_client.messages.calls, "expected one call"
        call = fake_client.messages.calls[0]
        system = call["system"]
        assert isinstance(system, list)
        assert len(system) == 1
        block = system[0]
        assert block["type"] == "text"
        assert block.get("cache_control") == {"type": "ephemeral"}
        # Confirm the cached prefix is what's actually being cached.
        assert "STRICT JSON" in block["text"].upper() or "Strict JSON" in block["text"]

    def test_call_uses_correct_model_and_max_tokens(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 19,
                    "reason": "...",
                }
            )
        )
        disambiguate(
            reply_text="PT done",
            ambiguity=pt_ambiguity,
            api_key_path=api_key_file,
            model="claude-test-override",
        )
        call = fake_client.messages.calls[0]
        assert call["model"] == "claude-test-override"
        assert call["max_tokens"] == 256

    def test_user_message_contains_reply_text_and_candidates(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 19,
                    "reason": "...",
                }
            )
        )
        disambiguate(
            reply_text="morning PT done",
            ambiguity=pt_ambiguity,
            api_key_path=api_key_file,
        )
        call = fake_client.messages.calls[0]
        user_msg = call["messages"][0]["content"]
        assert "morning PT done" in user_msg
        assert "PT" in user_msg
        # All candidate task_ids must appear in the user message.
        assert "19" in user_msg
        assert "16" in user_msg
        assert "17" in user_msg
        # And all candidate titles.
        assert "Morning shoulder PT" in user_msg
        assert "Evening shoulder PT" in user_msg
        assert "Morning hip PT" in user_msg
        # Inferred state is propagated.
        assert "complete" in user_msg


class TestDisambiguateClarifyHappyPath:
    def test_clarify_returns_result_with_question(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "clarify",
                    "reason": "PT is ambiguous",
                    "suggested_question": (
                        "Did you mean morning shoulder, evening shoulder, "
                        "or morning hip PT?"
                    ),
                }
            )
        )
        result = disambiguate(
            reply_text="Skipped PT",
            ambiguity=pt_ambiguity,
            api_key_path=api_key_file,
        )
        assert result.result == "clarify"
        assert result.chosen_task_id is None
        assert result.suggested_question is not None
        assert "morning" in result.suggested_question
        assert result.reason == "PT is ambiguous"


# ---------------------------------------------------------------------------
# Group 3 -- disambiguate() defense paths (the load-bearing safety checks)
# ---------------------------------------------------------------------------


class TestDisambiguateRejection:
    """The most important section: out-of-set + malformed + shape mismatch."""

    def test_out_of_set_chosen_task_id_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        """Reviewer's load-bearing check: out-of-set rejection."""
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 999,  # NOT in [19, 16, 17]
                    "reason": "hallucinated",
                }
            )
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "out-of-set" in str(exc_info.value)
        assert "999" in str(exc_info.value)

    def test_chosen_task_id_zero_not_in_set_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        """0 is falsy but a valid int; must be rejected if not in candidates."""
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 0,
                    "reason": "drift",
                }
            )
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "out-of-set" in str(exc_info.value)

    def test_malformed_json_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text("not JSON {{}")
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "invalid JSON" in str(exc_info.value)

    def test_json_not_object_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(json.dumps(["not", "an", "object"]))
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "JSON object" in str(exc_info.value)

    def test_invalid_result_value_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps({"result": "unknown", "reason": "..."})
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "result" in str(exc_info.value)
        assert "chosen" in str(exc_info.value)
        assert "clarify" in str(exc_info.value)

    def test_chosen_missing_chosen_task_id_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps({"result": "chosen", "reason": "..."})
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "chosen_task_id" in str(exc_info.value)

    def test_chosen_task_id_wrong_type_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        """A string-typed ``chosen_task_id`` must be rejected."""
        fake_client.messages.set_text(
            json.dumps({"result": "chosen", "chosen_task_id": "19"})
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "must be an int" in str(exc_info.value)

    def test_chosen_task_id_bool_rejected(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        """``True`` is technically ``int`` in Python -- must be rejected."""
        fake_client.messages.set_text(
            json.dumps({"result": "chosen", "chosen_task_id": True})
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "must be an int" in str(exc_info.value)

    def test_clarify_missing_suggested_question_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps({"result": "clarify", "reason": "..."})
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "suggested_question" in str(exc_info.value)

    def test_clarify_empty_suggested_question_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "clarify",
                    "reason": "...",
                    "suggested_question": "   ",
                }
            )
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "non-empty" in str(exc_info.value)

    def test_clarify_over_long_suggested_question_raises(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        long_question = "X" * 250
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "clarify",
                    "reason": "...",
                    "suggested_question": long_question,
                }
            )
        )
        with pytest.raises(DisambiguatorError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )
        assert "exceeds" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group 4 -- API key + prompt template edge cases
# ---------------------------------------------------------------------------


class TestApiKey:
    def test_missing_api_key_raises_filenotfounderror(
        self, fake_client: _FakeClient, tmp_path: Path, pt_ambiguity
    ):
        missing = tmp_path / "does-not-exist.key"
        with pytest.raises(FileNotFoundError):
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=missing,
            )

    def test_empty_api_key_raises_valueerror(
        self, fake_client: _FakeClient, tmp_path: Path, pt_ambiguity
    ):
        empty = tmp_path / "empty.key"
        empty.write_text("   \n", encoding="utf-8")
        with pytest.raises(ValueError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=empty,
            )
        assert "empty" in str(exc_info.value)

    def test_unreadable_api_key_raises_oserror(
        self, fake_client: _FakeClient, tmp_path: Path, pt_ambiguity, monkeypatch
    ):
        """Simulate a permission-denied error reading the key file."""
        path = tmp_path / "perms.key"
        path.write_text("key\n", encoding="utf-8")

        original_read_text = Path.read_text

        def fake_read_text(self, *args, **kwargs):
            if str(self) == str(path):
                raise PermissionError("denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fake_read_text)
        with pytest.raises(OSError) as exc_info:
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=path,
            )
        assert "permission denied" in str(exc_info.value).lower()


class TestPromptTemplate:
    def test_load_prompt_template_returns_two_sections(self):
        cached, user_template = dr._load_prompt_template()
        assert cached
        assert user_template
        # Cached section should NOT contain user-side placeholders.
        assert "{reply_text}" not in cached

    def test_missing_marker_raises_valueerror(
        self, monkeypatch, tmp_path: Path
    ):
        bad_path = tmp_path / "bad.prompt.md"
        bad_path.write_text("no markers here at all", encoding="utf-8")
        monkeypatch.setattr(dr, "PROMPT_PATH", bad_path)
        with pytest.raises(ValueError) as exc_info:
            dr._load_prompt_template()
        assert "CACHE_PREFIX_START" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group 5 -- _format_candidates helper
# ---------------------------------------------------------------------------


class TestFormatCandidates:
    def test_renders_one_line_per_candidate(self, pt_ambiguity):
        rendered = dr._format_candidates(pt_ambiguity)
        lines = rendered.split("\n")
        assert len(lines) == 3
        assert "task_id: 19" in lines[0]
        assert "Morning shoulder PT" in lines[0]
        assert "task_id: 16" in lines[1]
        assert "task_id: 17" in lines[2]

    def test_mismatched_lengths_raises(self):
        bad = JudgmentItem(
            token="PT",
            candidate_task_ids=[19, 16],
            candidate_titles=["only one"],
            inferred_state="complete",
        )
        with pytest.raises(DisambiguatorError):
            dr._format_candidates(bad)


# ---------------------------------------------------------------------------
# Group 6 -- API timeout / network failure propagation
# ---------------------------------------------------------------------------


class TestAnthropicErrorPropagation:
    def test_api_error_propagates(
        self, fake_client: _FakeClient, api_key_file: Path, pt_ambiguity
    ):
        """``anthropic.APIError`` raised by the SDK propagates to the caller.

        The caller (main()) catches APIError and maps to exit 1; the
        ``disambiguate`` function itself does not swallow the exception.
        """

        # Construct a fake APIError subclass we can raise without
        # needing the SDK's specific constructor signature.
        class FakeAPIError(dr.anthropic.APIError):
            def __init__(self, msg: str) -> None:
                # Skip super().__init__ -- we just need the type to match.
                self.message = msg

            def __str__(self) -> str:
                return self.message

        fake_client.messages.set_raise(FakeAPIError("timeout"))
        with pytest.raises(dr.anthropic.APIError):
            disambiguate(
                reply_text="PT done",
                ambiguity=pt_ambiguity,
                api_key_path=api_key_file,
            )


# ---------------------------------------------------------------------------
# Group 7 -- CLI surface
# ---------------------------------------------------------------------------


def _input_doc(ambiguity: JudgmentItem, reply_text: str) -> dict[str, Any]:
    """Build the Entity 3 input shape (matches contracts/cli.md stdin format)."""
    return {
        "schema_version": 1,
        "reply_text": reply_text,
        "ambiguity": {
            "token": ambiguity.token,
            "candidate_task_ids": list(ambiguity.candidate_task_ids),
            "candidate_titles": list(ambiguity.candidate_titles),
            "inferred_state": ambiguity.inferred_state,
        },
    }


class TestCLI:
    def test_help_exits_0(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            dr.main(["--help"])
        assert exc_info.value.code == 0

    def test_bogus_flag_exits_3(self, capsys):
        rc = dr.main(["--bogus"])
        assert rc == 3
        captured = capsys.readouterr()
        # Structured error on stderr.
        err_obj = json.loads(captured.err.strip())
        assert err_obj["step"] == "argparse"

    def test_missing_input_file_exits_3(self, capsys, tmp_path: Path):
        missing = tmp_path / "nope.json"
        rc = dr.main(["--input-file", str(missing)])
        assert rc == 3

    def test_malformed_input_json_exits_3(
        self, capsys, tmp_path: Path
    ):
        bad = tmp_path / "bad.json"
        bad.write_text("not JSON", encoding="utf-8")
        rc = dr.main(["--input-file", str(bad)])
        assert rc == 3

    def test_input_missing_field_exits_3(
        self, capsys, tmp_path: Path
    ):
        partial = tmp_path / "partial.json"
        partial.write_text(
            json.dumps({"reply_text": "PT done"}), encoding="utf-8"
        )
        rc = dr.main(["--input-file", str(partial)])
        assert rc == 3

    def test_chosen_path_exit_0(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 19,
                    "reason": "...",
                }
            )
        )
        input_path = tmp_path / "input.json"
        input_path.write_text(
            json.dumps(_input_doc(pt_ambiguity, "morning PT done")),
            encoding="utf-8",
        )
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(api_key_file),
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert out["result"] == "chosen"
        assert out["chosen_task_id"] == 19
        assert out["schema_version"] == 1

    def test_clarify_path_exit_0(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "clarify",
                    "reason": "ambiguous",
                    "suggested_question": "Which PT?",
                }
            )
        )
        input_path = tmp_path / "input.json"
        input_path.write_text(
            json.dumps(_input_doc(pt_ambiguity, "PT done")),
            encoding="utf-8",
        )
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(api_key_file),
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert out["result"] == "clarify"
        assert out["suggested_question"] == "Which PT?"

    def test_out_of_set_exits_5(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        """Reviewer's load-bearing CLI check: out-of-set -> exit 5."""
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 999,
                    "reason": "drift",
                }
            )
        )
        input_path = tmp_path / "input.json"
        input_path.write_text(
            json.dumps(_input_doc(pt_ambiguity, "PT done")),
            encoding="utf-8",
        )
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(api_key_file),
            ]
        )
        assert rc == 5
        captured = capsys.readouterr()
        err = json.loads(captured.err.strip())
        assert err["step"] == "llm_validate"
        assert "out-of-set" in err["error"]

    def test_malformed_llm_response_exits_3(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        fake_client.messages.set_text("definitely not JSON")
        input_path = tmp_path / "input.json"
        input_path.write_text(
            json.dumps(_input_doc(pt_ambiguity, "PT done")),
            encoding="utf-8",
        )
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(api_key_file),
            ]
        )
        assert rc == 3
        captured = capsys.readouterr()
        err = json.loads(captured.err.strip())
        assert err["step"] == "llm_validate"
        assert "invalid JSON" in err["error"]

    def test_missing_api_key_exits_1(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        pt_ambiguity,
    ):
        input_path = tmp_path / "input.json"
        input_path.write_text(
            json.dumps(_input_doc(pt_ambiguity, "PT done")),
            encoding="utf-8",
        )
        missing_key = tmp_path / "missing.key"
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(missing_key),
            ]
        )
        assert rc == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err.strip())
        assert err["step"] == "config"

    def test_anthropic_api_error_exits_1(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        class FakeAPIError(dr.anthropic.APIError):
            def __init__(self, msg: str) -> None:
                self.message = msg

            def __str__(self) -> str:
                return self.message

        fake_client.messages.set_raise(FakeAPIError("rate-limited"))
        input_path = tmp_path / "input.json"
        input_path.write_text(
            json.dumps(_input_doc(pt_ambiguity, "PT done")),
            encoding="utf-8",
        )
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(api_key_file),
            ]
        )
        assert rc == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err.strip())
        assert err["step"] == "llm_call"

    def test_stdin_input_path(
        self,
        capsys,
        monkeypatch,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        """When --input-file is omitted, the CLI reads from stdin."""
        fake_client.messages.set_text(
            json.dumps(
                {
                    "result": "chosen",
                    "chosen_task_id": 19,
                    "reason": "...",
                }
            )
        )
        stdin_payload = json.dumps(_input_doc(pt_ambiguity, "PT done"))
        monkeypatch.setattr(
            "sys.stdin",
            types.SimpleNamespace(read=lambda: stdin_payload),
        )
        rc = dr.main(["--api-key-path", str(api_key_file)])
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert out["result"] == "chosen"

    def test_input_invalid_inferred_state_exits_3(
        self,
        capsys,
        tmp_path: Path,
        fake_client: _FakeClient,
        api_key_file: Path,
        pt_ambiguity,
    ):
        bad_doc = _input_doc(pt_ambiguity, "PT done")
        bad_doc["ambiguity"]["inferred_state"] = "garbage"
        input_path = tmp_path / "input.json"
        input_path.write_text(json.dumps(bad_doc), encoding="utf-8")
        rc = dr.main(
            [
                "--input-file",
                str(input_path),
                "--api-key-path",
                str(api_key_file),
            ]
        )
        assert rc == 3
