"""Behavioural tests for validate_docs.py (#987 FR-004, FR-006, C-001).

The validator is a script whose work happens at import, so these run it as a
subprocess against a synthetic repo. That also exercises the exit codes, which
are what the pre-commit hook and CI actually consume.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VALIDATOR = REPO / "tooling" / "scripts" / "validate_docs.py"
STANDARDS = REPO / "docs" / "design" / "standards"


STRICT_POLICY = json.dumps(
    {"blockers": ["required_keys", "enum_membership", "decision_log"]}
)


@pytest.fixture
def repo(tmp_path):
    """A minimal synthetic repo the validator will accept as its ROOT."""
    (tmp_path / "tooling" / "scripts").mkdir(parents=True)
    for name in ("validate_docs.py", "doc_taxonomy.py"):
        shutil.copy(REPO / "tooling" / "scripts" / name, tmp_path / "tooling" / "scripts" / name)
    (tmp_path / "docs" / "design" / "standards").mkdir(parents=True)
    for name in ("allowed-values.json", "validator-policy.json"):
        shutil.copy(STANDARDS / name, tmp_path / "docs" / "design" / "standards" / name)
    return tmp_path


def run(repo: Path):
    return subprocess.run(
        [sys.executable, "tooling/scripts/validate_docs.py"],
        cwd=repo, capture_output=True, text=True,
    )


def doc(**kw):
    fm = {"title": "T", "doc_type": "runbook", "status": "draft"}
    fm.update(kw)
    body = kw.pop("_body", "")
    lines = ["---"] + [f"{k}: {v}" for k, v in fm.items() if not k.startswith("_")] + ["---", "", "# T", ""]
    return "\n".join(lines) + body


def write(repo: Path, rel: str, text: str):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --------------------------------------------------- doc_type-scoped status --


def test_decision_may_use_superseded(repo):
    log = "\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n| 2026-09-18 | superseded-by | k | replaced | ADR-0010 |\n"
    write(repo, "docs/a.md", doc(doc_type="decision", status="superseded", _body=log))
    r = run(repo)
    assert r.returncode == 0, r.stdout


def test_ordinary_doc_may_not_use_superseded(repo):
    write(repo, "docs/a.md", doc(doc_type="runbook", status="superseded"))
    r = run(repo)
    assert r.returncode == 1
    assert "Invalid status 'superseded'" in r.stdout


def test_decision_may_not_use_active(repo):
    """The leakage FR-004 exists to prevent."""
    write(repo, "docs/a.md", doc(doc_type="decision", status="active", _body="\n## Decision log\n\n*No entries.*\n"))
    r = run(repo)
    assert r.returncode == 1
    assert "Invalid status 'active'" in r.stdout


def test_message_names_the_doc_type_and_its_own_set(repo):
    """NFR-004: naming the union would send the author to the wrong list."""
    write(repo, "docs/a.md", doc(doc_type="decision", status="archived", _body="\n## Decision log\n\n*No entries.*\n"))
    r = run(repo)
    assert "doc_type 'decision'" in r.stdout
    assert "superseded" in r.stdout          # its permitted set
    assert "archived" not in r.stdout.split("allowed:")[1]  # not the default set


def test_message_always_names_the_doc_type(repo):
    """F1: reporting only 'the default set' leaves the author guessing which
    set applies to their document."""
    write(repo, "docs/a.md", doc(doc_type="runbook", status="superseded"))
    out = run(repo).stdout
    assert "doc_type 'runbook'" in out and "default scope" in out


# --------------------------------------------------------- fail-closed load --


def test_malformed_taxonomy_aborts_rather_than_falling_back(repo):
    (repo / "docs/design/standards/allowed-values.json").write_text("{not json", encoding="utf-8")
    write(repo, "docs/a.md", doc())
    r = run(repo)
    assert r.returncode == 2, r.stdout
    assert "FATAL" in r.stderr and "invalid JSON" in r.stderr


# ------------------------------------------------------- scope boundary C-001 --


def test_spec_kitty_trees_are_never_frontmatter_validated(repo):
    """C-001/SC-005. NOTE the rule is 'never frontmatter-validate', NOT 'never
    walk' — see the secret-scan test below, which must keep passing."""
    bad = doc(doc_type="not-a-real-type", status="not-a-real-status")
    for d in ("kitty-specs", ".kittify", ".agents", ".claude", ".codex", "dist"):
        write(repo, f"{d}/thing.md", bad)
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "not-a-real-type" not in r.stdout


def test_secret_scanning_still_covers_kitty_specs(repo):
    """The dangerous misreading: a 'never walk' test could silently disable
    secret coverage. A 2026-04-08 key leak went unnoticed for a month because
    the secret scanner reused SKIP_DIRS."""
    write(repo, "kitty-specs/leak.md", "token: AKIAIOSFODNN7EXAMPLE\n")
    r = run(repo)
    assert r.returncode == 1
    assert "leak.md" in r.stdout


# ------------------------------------------------------------ decision log --


def _decision(body):
    return doc(doc_type="decision", status="approved", _body=body)


def test_decision_log_empty_form_is_valid(repo):
    """F6: run PROMOTED — asserting exit 0 while advisory would pass even if the
    check emitted spurious warnings, i.e. future commit-blocking false
    positives."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    write(repo, "docs/a.md", _decision("\n## Decision log\n\n*No entries.*\n"))
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "WARN" not in r.stdout


def test_decision_log_populated_form_is_valid(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | Kent | reasoning wrong, conclusion stands | ADR-0004 |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "WARN" not in r.stdout
    assert r.returncode == 0, r.stdout


def test_crlf_log_is_accepted(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n")
    p = write(repo, "docs/a.md", _decision(body))
    p.write_bytes(p.read_text().replace("\n", "\r\n").encode())
    assert run(repo).returncode == 0


def test_fenced_log_does_not_satisfy_validation(repo):
    """F2: a heading and table inside a code fence must not count."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = "\n```md\n## Decision log\n\n*No entries.*\n```\n"
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "expected exactly one" in r.stdout


def test_log_must_be_the_last_section(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = "\n## Decision log\n\n*No entries.*\n\n## Afterword\n\ntext\n"
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "must be the last section" in r.stdout


def test_placeholder_must_stand_alone(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = "\n## Decision log\n\n*No entries.*\n\nbut actually some prose\n"
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "must be the only content" in r.stdout


def test_stray_prose_between_rows_is_rejected(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n\nnote\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "must be contiguous" in r.stdout or "and nothing else" in r.stdout


def test_wrong_header_is_rejected(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| When | Kind | Who | What | Links |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "header must be" in r.stdout


def test_impossible_date_is_rejected(repo):
    """F4: the shape regex accepted 2026-99-99."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-99-99 | erratum | k | s | r |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "not a real ISO" in r.stdout


def test_missing_vocabulary_aborts(repo):
    """F5: keeping a built-in fallback for a missing key reintroduces silent
    divergence."""
    src = repo / "docs/design/standards/allowed-values.json"
    data = json.loads(src.read_text())
    del data["audience"]
    src.write_text(json.dumps(data), encoding="utf-8")
    write(repo, "docs/a.md", doc())
    r = run(repo)
    assert r.returncode == 2
    assert "no vocabulary named" in r.stderr


@pytest.mark.parametrize("body,expected", [
    ("\n", "expected exactly one"),
    ("\n## Decision log\n\n## Decision log\n\n*No entries.*\n", "expected exactly one"),
    ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n| 29-08-2026 | erratum | k | s | r |\n", "not a real ISO"),
    ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n| 2026-08-29 | invented | k | s | r |\n", "is not one of"),
        # A short table now fails at the header check, which fires first and gives
    # the author the more useful message.
    ("\n## Decision log\n\n| Date | Type | By |\n|---|---|---|\n| 2026-08-29 | erratum | k |\n", "header must be"),
    # Wrong column count with the right header still reports the count.
    ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n| 2026-08-29 | erratum | k |\n", "expected 5"),
])
def test_decision_log_negative_cases(repo, body, expected):
    """Each promised check gets a failing case (FR-003)."""
    write(repo, "docs/design/standards/validator-policy.json",
          json.dumps({"blockers": ["required_keys", "enum_membership", "decision_log"]}))
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1, r.stdout
    assert expected in r.stdout


def test_superseded_by_requires_superseded_status(repo):
    """Contract rule 5: neither is meaningful alone."""
    write(repo, "docs/design/standards/validator-policy.json",
          json.dumps({"blockers": ["required_keys", "enum_membership", "decision_log"]}))
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | superseded-by | k | replaced | ADR-0010 |\n")
    write(repo, "docs/a.md", doc(doc_type="decision", status="approved", _body=body))
    r = run(repo)
    assert r.returncode == 1, r.stdout
    assert "expected 'superseded'" in r.stdout


def test_superseded_status_requires_a_superseded_by_row(repo):
    write(repo, "docs/design/standards/validator-policy.json",
          json.dumps({"blockers": ["required_keys", "enum_membership", "decision_log"]}))
    write(repo, "docs/a.md", doc(doc_type="decision", status="superseded",
                                 _body="\n## Decision log\n\n*No entries.*\n"))
    r = run(repo)
    assert r.returncode == 1, r.stdout
    assert "no 'superseded-by' row" in r.stdout


def test_decision_log_is_now_a_blocker(repo):
    """WP06 promoted it, which was the last step of the migration ordering:
    the check landed advisory (WP03) so it could not turn the repo red before
    the documents it governs existed, and is promoted only after WP05 migrated
    them."""
    write(repo, "docs/a.md", _decision("\n"))
    r = run(repo)
    assert r.returncode == 1, r.stdout
    assert "Decision log" in r.stdout


def test_the_shipped_policy_lists_decision_log_as_a_blocker(repo):
    """The promotion is a data change; assert it in the shipped policy rather
    than only in behaviour."""
    policy = json.loads(
        (REPO / "docs" / "design" / "standards" / "validator-policy.json").read_text()
    )
    assert "decision_log" in policy["blockers"]


def test_non_decision_docs_need_no_log(repo):
    write(repo, "docs/a.md", doc(doc_type="runbook", status="draft"))
    assert run(repo).returncode == 0


# --------------------------------------- narrowed-grammar regressions (cycle 3) --


def test_escaped_pipe_is_accepted(repo):
    """The grammar is narrowed rather than the parser widened: a literal pipe
    must be escaped, including inside a code span. That deleted the code-span
    state machine where three review rounds kept finding edge cases."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            r"| 2026-08-29 | amendment | Kent | renamed `a\|b` and x \| y | #1 |" "\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 0, r.stdout


def test_unescaped_pipe_is_a_visible_error_not_a_silent_misparse(repo):
    """The cost of the narrower grammar, made explicit — and the message must
    teach the rule, or enforcement just moves the failure to the author."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | amendment | Kent | a|b | #1 |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "expected 5" in r.stdout
    assert r"escape any literal pipe as \|" in r.stdout


def test_backslash_does_not_escape_arbitrary_characters(repo):
    r"""Escaping every character let `err\atum` normalise into a valid Type."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            r"| 2026-08-29 | err\atum | k | s | r |" "\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "is not one of" in r.stdout


def test_blank_line_between_rows_is_rejected(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n\n| 2026-08-30 | context | k | s | r |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "must be contiguous" in r.stdout


def test_separator_cardinality_must_match_the_header(repo):
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "separator row is malformed" in r.stdout


def test_indented_code_block_is_not_a_section(repo):
    """An indented `## Decision log` is code, not a heading."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    write(repo, "docs/a.md", _decision("\n    ## Decision log\n\n    *No entries.*\n"))
    r = run(repo)
    assert r.returncode == 1
    assert "expected exactly one" in r.stdout


def test_fence_like_line_with_trailing_text_is_not_a_closer(repo):
    """Treating it as a closer exposed the fenced content."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = "\n```md\n## Decision log\n\n*No entries.*\n``` not-a-closer\nstill inside\n```\n"
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "expected exactly one" in r.stdout


def test_backtick_info_string_is_not_a_valid_opener(repo):
    """CommonMark 4.5: a backtick fence's info string may not contain a
    backtick. Accepting one as an opener could hide the real log."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = "\n``` `weird`\n## Decision log\n\n*No entries.*\n"
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    # The pseudo-opener is NOT a fence, so the real heading is still seen.
    assert r.returncode == 0, r.stdout


# ------------------------------------- blockquote preamble (found by WP06) --


def test_blockquote_preamble_before_the_table_is_allowed(repo):
    """Found by WP06's end-to-end check, once the lanes merged: ADR-0004's
    canonical log needs a note explaining the legacy/canonical split, and
    'table and nothing else' forbade it. A '>' line can never be confused with
    a '|' row, so allowing it keeps the grammar unambiguous."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n> **Note.** This is the canonical log.\n> New entries go here.\n\n"
            "| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 0, r.stdout


def test_non_blockquote_prose_before_the_table_is_still_rejected(repo):
    """The allowance is bounded: only blockquotes, not arbitrary prose."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\nSome explanatory prose.\n\n"
            "| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "blockquote note" in r.stdout


def test_blockquote_after_the_table_is_still_rejected(repo):
    """Only a preamble is allowed; trailing prose would make the table's end
    ambiguous."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n\n> trailing note\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1


def test_fenced_content_after_the_table_is_rejected(repo):
    """Cycle-2 F2: _strip_fenced blanks fenced blocks so they cannot SATISFY
    validation — but that also let one HIDE after the table, which the contract
    forbids. Checked against the raw text now."""
    write(repo, "docs/design/standards/validator-policy.json", STRICT_POLICY)
    body = ("\n## Decision log\n\n| Date | Type | By | Summary | Refs |\n|---|---|---|---|---|\n"
            "| 2026-08-29 | erratum | k | s | r |\n\n```md\nsneaky trailing block\n```\n")
    write(repo, "docs/a.md", _decision(body))
    r = run(repo)
    assert r.returncode == 1
    assert "must end with the table" in r.stdout
