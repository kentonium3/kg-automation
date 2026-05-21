"""Unit tests for ``doc_audit.judgment.cross_file_implication``.

Verifies:
- Empty implications list passes through.
- Single valid implication round-trips with ``suggested_action``
  normalized to ``"judgment"``.
- Malformed JSON safely returns ``[]``.
- Mixed valid/invalid entries: only valid ones survive.
- Entries targeting a touched file are dropped (defense in depth).
"""
from __future__ import annotations

from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.cross_file_implication import PROMPT_PATH, detect


_USAGE = {
    "input_tokens": 880,
    "cache_read_input_tokens": 500,
    "output_tokens": 110,
}


def test_prompt_path_exists() -> None:
    """The checked-in prompt template is reachable."""

    assert PROMPT_PATH.is_file(), f"missing prompt template: {PROMPT_PATH}"


def test_detect_empty_implications(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """``{"implications": []}`` returns an empty list."""

    stub_anthropic_response(
        {"text": '{"implications": []}', "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    implications, response = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="feat: routine refactor",
        diff_excerpt="...",
        touched_files=["docs/INDEX.md"],
        in_scope_files=["docs/INDEX.md", "docs/runbooks/x.md"],
        domain_labels=["area/felix-core"],
    )

    assert implications == []
    assert response.input_tokens == 880


def test_detect_one_valid_implication(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """A single valid implication is returned with suggested_action normalized."""

    payload_text = (
        '{"implications": [{'
        '"untouched_file": "docs/constitution/agent-registry.json",'
        '"implication": "A new agent was deployed but the registry'
        ' has no entry.",'
        '"evidence": "commit deploys felix-admin-escalation",'
        '"suggested_action": "judgment"'
        "}]}"
    )
    stub_anthropic_response({"text": payload_text, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="feat: deploy felix-admin-escalation",
        diff_excerpt="...",
        touched_files=[
            "scripts/openclaw/agents/felix-admin-escalation/AGENTS.md",
            "openclaw.json",
        ],
        in_scope_files=[
            "docs/constitution/agent-registry.json",
            "docs/INDEX.md",
        ],
        domain_labels=["area/felix-core"],
    )

    assert len(implications) == 1
    entry = implications[0]
    assert entry["untouched_file"] == "docs/constitution/agent-registry.json"
    assert entry["suggested_action"] == "judgment"


def test_detect_malformed_json_returns_empty(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Garbage response safely falls back to ``[]``."""

    stub_anthropic_response(
        {"text": "not valid JSON at all", "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="...",
        diff_excerpt="...",
        touched_files=[],
        in_scope_files=["docs/INDEX.md"],
        domain_labels=[],
    )

    assert implications == []


def test_detect_missing_implications_key_returns_empty(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """JSON object without ``implications`` key falls back."""

    stub_anthropic_response(
        {"text": '{"other": "field"}', "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="...",
        diff_excerpt="...",
        touched_files=[],
        in_scope_files=["docs/INDEX.md"],
        domain_labels=[],
    )

    assert implications == []


def test_detect_filters_invalid_entries(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Mixed valid/invalid entries: only valid ones survive."""

    payload_text = (
        '{"implications": ['
        '{"untouched_file": "docs/INDEX.md",'
        ' "implication": "New runbook needs an INDEX entry.",'
        ' "evidence": "commit added a runbook",'
        ' "suggested_action": "judgment"},'
        '{"missing_keys": true},'
        '{"untouched_file": "docs/INDEX.md",'
        ' "implication": "",'
        ' "evidence": "x",'
        ' "suggested_action": "judgment"}'
        "]}"
    )
    stub_anthropic_response({"text": payload_text, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="...",
        diff_excerpt="...",
        touched_files=[],
        in_scope_files=["docs/INDEX.md"],
        domain_labels=[],
    )

    # Only the first (well-formed) entry survives.
    assert len(implications) == 1
    assert implications[0]["untouched_file"] == "docs/INDEX.md"


def test_detect_drops_touched_file_entries(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Defense-in-depth: entries naming a touched file are dropped."""

    payload_text = (
        '{"implications": [{'
        '"untouched_file": "docs/INDEX.md",'
        '"implication": "INDEX needs updating.",'
        '"evidence": "commit added a runbook",'
        '"suggested_action": "judgment"'
        "}]}"
    )
    stub_anthropic_response({"text": payload_text, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="...",
        diff_excerpt="...",
        # The LLM (incorrectly) named a touched file. Defense drops it.
        touched_files=["docs/INDEX.md"],
        in_scope_files=["docs/INDEX.md", "docs/runbooks/x.md"],
        domain_labels=[],
    )

    assert implications == []


def test_detect_drops_out_of_scope_implications(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """Entries whose ``untouched_file`` is outside ``in_scope_files`` are dropped.

    Per contract Moment 3, ``untouched_file`` must be an in-scope,
    untouched path. Out-of-scope entries are LLM hallucinations and
    must be filtered — we never file debt for docs outside the scoped
    audit surface. This locks in the strict-filter behavior.
    """

    payload_text = (
        '{"implications": ['
        # Out-of-scope target — must be dropped.
        '{"untouched_file": "docs/runbooks/out-of-scope.md",'
        ' "implication": "LLM hallucinated a target outside the scoped surface.",'
        ' "evidence": "diff mentions something tangential",'
        ' "suggested_action": "judgment"},'
        # In-scope target — must survive.
        '{"untouched_file": "docs/INDEX.md",'
        ' "implication": "INDEX entry should reference the new runbook.",'
        ' "evidence": "commit added a runbook",'
        ' "suggested_action": "judgment"}'
        "]}"
    )
    stub_anthropic_response({"text": payload_text, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="feat: add new runbook",
        diff_excerpt="...",
        touched_files=["docs/runbooks/new-runbook.md"],
        in_scope_files=["docs/INDEX.md", "docs/runbooks/new-runbook.md"],
        domain_labels=["area/felix-core"],
    )

    # Only the in-scope entry survives.
    assert len(implications) == 1
    assert implications[0]["untouched_file"] == "docs/INDEX.md"


def test_detect_normalizes_suggested_action(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """``suggested_action`` is forced to ``"judgment"`` regardless of input."""

    payload_text = (
        '{"implications": [{'
        '"untouched_file": "docs/runbooks/x.md",'
        '"implication": "Needs update.",'
        '"evidence": "diff shows behavior change",'
        '"suggested_action": "auto_edit"'
        "}]}"
    )
    stub_anthropic_response({"text": payload_text, "usage": _USAGE})
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="...",
        diff_excerpt="...",
        touched_files=[],
        in_scope_files=["docs/runbooks/x.md"],
        domain_labels=[],
    )

    assert len(implications) == 1
    # The contract says these are never auto-edits — force normalize.
    assert implications[0]["suggested_action"] == "judgment"


def test_detect_handles_top_level_array_response(
    tmp_config, mock_anthropic, stub_anthropic_response
) -> None:
    """JSON array (not object) safely falls back to ``[]``."""

    stub_anthropic_response(
        {"text": "[1, 2, 3]", "usage": _USAGE}
    )
    client = JudgmentClient(tmp_config)

    implications, _ = detect(
        client,
        triggering_event_kind="commit",
        triggering_event_summary="...",
        diff_excerpt="...",
        touched_files=[],
        in_scope_files=["docs/INDEX.md"],
        domain_labels=[],
    )

    assert implications == []
