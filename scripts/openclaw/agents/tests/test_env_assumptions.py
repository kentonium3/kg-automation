"""Unit tests for the env-assumption checker (kentonium3/kg-automation#662,
corrects #658, WP01).

Policy is inverted from #658: the self-contained checkout-``cd`` form is now the
compliant one, and the ``${PYTHONPATH:?}`` anchor (which fails under OpenClaw exec)
is a violation.
"""

from __future__ import annotations

from scripts.openclaw.agents.env_assumptions import (
    CANONICAL_CHECKOUT,
    Finding,
    ViolationKind,
    scan_text,
)


def _kinds(text: str) -> list[ViolationKind]:
    return [f.kind for f in scan_text(text)]


# --- Canonical (compliant) forms: true negatives ------------------------------


def test_canonical_checkout_cd_m_form_passes():
    text = "cd /home/claude/kg-automation && python3 -m scripts.inbox.prescan --self-check"
    assert scan_text(text) == []


def test_canonical_checkout_cd_relative_script_form_passes():
    text = "cd /home/claude/kg-automation && python3 scripts/inbox/prescan.py --self-check"
    assert scan_text(text) == []


def test_canonical_checkout_constant_matches_literal():
    # The compliant anchor is an exact match of CANONICAL_CHECKOUT.
    assert CANONICAL_CHECKOUT == "/home/claude/kg-automation"


def test_home_read_of_openclaw_not_flagged():
    # A read of ~/.openclaw/... (no redirect) is a legitimate contract, never flagged.
    text = "- **task-intelligence**: `~/.openclaw/skills/task-intelligence/SKILL.md`"
    assert scan_text(text) == []


# --- True positives, one per ViolationKind ------------------------------------


def test_bare_m_scripts_flagged():
    assert _kinds("python3 -m scripts.inbox.prescan --self-check") == [
        ViolationKind.BARE_M_SCRIPTS
    ]


def test_pythonpath_anchor_flagged():
    # The #658 canonical form is now a violation — exec strips PYTHONPATH.
    text = 'cd "${PYTHONPATH:?run under gateway}" && python3 -m scripts.inbox.prescan'
    assert _kinds(text) == [ViolationKind.PYTHONPATH_ANCHOR]


def test_pythonpath_anchor_abs_path_form_flagged():
    # The old "compliant" file-path variant also depends on PYTHONPATH → violation.
    text = 'python "${PYTHONPATH:?msg}/scripts/openclaw/observation/log_action.py"'
    assert _kinds(text) == [ViolationKind.PYTHONPATH_ANCHOR]


def test_hardcoded_abs_path_python3_flagged():
    text = "python3 /home/claude/kg-automation/scripts/openclaw/observation/log_action.py --x 1"
    assert _kinds(text) == [ViolationKind.HARDCODED_ABS_PATH]


def test_hardcoded_abs_path_bare_python_flagged():
    # Codex MED-1: live lines use bare `python` (not python3).
    text = "python /home/claude/kg-automation/scripts/openclaw/observation/log_action.py"
    assert _kinds(text) == [ViolationKind.HARDCODED_ABS_PATH]


def test_hardcoded_abs_path_quoted_flagged():
    # Post-merge Codex MED-2: quoted hardcoded absolute paths must not slip through.
    assert _kinds('python3 "/home/claude/kg-automation/scripts/inbox/prescan.py"') == [
        ViolationKind.HARDCODED_ABS_PATH
    ]
    assert _kinds("python3 '/home/claude/kg-automation/scripts/inbox/prescan.py'") == [
        ViolationKind.HARDCODED_ABS_PATH
    ]


def test_home_relative_write_flagged():
    assert _kinds('echo hi >> ~/second-brain/agents/logs/x.md') == [
        ViolationKind.HOME_RELATIVE_WRITE
    ]
    assert _kinds('cmd | tee $HOME/logs/y.md') == [ViolationKind.HOME_RELATIVE_WRITE]


# --- RELATIVE_SCRIPT (new, Codex HIGH-2) --------------------------------------


def test_relative_script_python3_form_unanchored_flagged():
    assert _kinds("python3 scripts/inbox/prescan.py --self-check") == [
        ViolationKind.RELATIVE_SCRIPT
    ]


def test_relative_script_bare_imperative_flagged():
    # capture AGENTS.md:97-style prose: "invoke `scripts/.../felix-file-issue.py`".
    text = "invoke `scripts/openclaw/agents/main/felix-file-issue.py` to open the issue"
    assert _kinds(text) == [ViolationKind.RELATIVE_SCRIPT]


def test_relative_script_with_checkout_cd_passes():
    text = "cd /home/claude/kg-automation && python3 scripts/openclaw/agents/main/felix-file-issue.py"
    assert scan_text(text) == []


def test_relative_script_backslash_continuation_anchored_passes():
    text = (
        "cd /home/claude/kg-automation && python3 scripts/inbox/prescan.py \\\n"
        "  --input-file /tmp/reply.json"
    )
    assert scan_text(text) == []


def test_relative_script_backslash_continuation_unanchored_flagged():
    text = "python3 scripts/inbox/prescan.py \\\n  --input-file /tmp/reply.json"
    findings = scan_text(text)
    assert [f.kind for f in findings] == [ViolationKind.RELATIVE_SCRIPT]
    assert findings[0].line == 1  # reports the STARTING line


def test_relative_script_governed_by_pythonpath_suppressed():
    # A relative script after a ${PYTHONPATH:?} cd is only reported as PYTHONPATH_ANCHOR.
    text = 'cd "${PYTHONPATH:?x}" && python3 scripts/inbox/prescan.py'
    assert _kinds(text) == [ViolationKind.PYTHONPATH_ANCHOR]


def test_relative_script_placeholder_not_flagged():
    text = "Invoke `scripts/inbox/<helper>.py` (the helper name is filled in per step)."
    assert scan_text(text) == []


# --- Wrong-path cd must NOT satisfy the anchor (Codex MED-4) -------------------


def test_wrong_path_cd_kgale_flagged():
    text = "cd /home/kgale/repos/kg-automation && python3 -m scripts.habits.morning_checkin_list"
    assert _kinds(text) == [ViolationKind.BARE_M_SCRIPTS]


def test_wrong_path_cd_tmp_relative_script_flagged():
    text = "cd /tmp/kg-automation && python3 scripts/inbox/prescan.py"
    assert _kinds(text) == [ViolationKind.RELATIVE_SCRIPT]


def test_longer_path_does_not_satisfy_anchor():
    # `/home/claude/kg-automation-fork` must not pass as the exact checkout.
    text = "cd /home/claude/kg-automation-fork && python3 -m scripts.inbox.prescan"
    assert _kinds(text) == [ViolationKind.BARE_M_SCRIPTS]


# --- Anchor-position semantics ------------------------------------------------


def test_invocation_before_checkout_cd_is_flagged():
    # An invocation that PRECEDES the checkout-cd runs before it → still flagged.
    text = (
        "python3 -m scripts.inbox.bad && "
        "cd /home/claude/kg-automation && python3 -m scripts.inbox.ok"
    )
    assert _kinds(text) == [ViolationKind.BARE_M_SCRIPTS]


def test_invocation_after_checkout_cd_passes():
    text = (
        "cd /home/claude/kg-automation && "
        "python3 -m scripts.inbox.a && python3 -m scripts.inbox.b"
    )
    assert scan_text(text) == []


# --- Must-not-flag: documentation of the pattern ------------------------------


def test_placeholder_module_not_flagged():
    # capture AGENTS.md:74 documents the pattern with a <helper> placeholder.
    text = "Invoke via `python3 -m scripts.inbox.<helper>` form (`--help` for its CLI)."
    assert scan_text(text) == []


def test_html_comment_not_flagged():
    text = "<!-- Step 1 contract; helper at /home/claude/kg-automation/scripts/inbox/prescan.py -->"
    assert scan_text(text) == []


def test_multiline_html_comment_not_flagged():
    text = "<!--\npython3 /home/claude/kg-automation/scripts/inbox/prescan.py\n-->"
    assert scan_text(text) == []


# --- Codex HIGH-1: inline imperative commands ARE real ------------------------


def test_inline_imperative_command_flagged():
    # capture's real commands are inline-backtick imperatives, not fenced blocks.
    text = "Invoke `python3 -m scripts.inbox.prescan`. Consume the JSON output."
    assert _kinds(text) == [ViolationKind.BARE_M_SCRIPTS]


# --- Codex MED-2: multiline / backslash-continuation --------------------------


def test_backslash_continuation_joined_and_anchored_passes():
    text = (
        "cd /home/claude/kg-automation && python3 -m scripts.habits.parse_morning_reply \\\n"
        "  --input-file /tmp/reply.json"
    )
    assert scan_text(text) == []


def test_continuation_hardcoded_path_on_second_line_flagged():
    text = "python3 \\\n  /home/claude/kg-automation/scripts/inbox/prescan.py"
    assert _kinds(text) == [ViolationKind.HARDCODED_ABS_PATH]


# --- NFR-003: the two #656 seed shapes ----------------------------------------


def test_seed_cwd_drift_shape():
    # #656: a bare -m scripts. that fails on cwd/PYTHONPATH drift.
    assert ViolationKind.BARE_M_SCRIPTS in _kinds("python3 -m scripts.inbox.mark_processed --path /x")


def test_seed_stray_dir_write_shape():
    # #656: a HOME-relative write landed content in the unsynced /home/claude tree.
    assert ViolationKind.HOME_RELATIVE_WRITE in _kinds("printf '%s' x > ~/second-brain/state.json")


# --- Waivers ------------------------------------------------------------------


def test_waiver_same_line_suppresses():
    text = "python3 -m scripts.inbox.prescan  # env-guard: waive bare_m_scripts — intentional"
    assert scan_text(text) == []


def test_waiver_previous_line_suppresses():
    text = "# env-guard: waive bare_m_scripts — documented reliance\npython3 -m scripts.inbox.prescan"
    assert scan_text(text) == []


def test_waiver_wrong_kind_does_not_suppress():
    text = "python3 -m scripts.inbox.prescan  # env-guard: waive pythonpath_anchor — mismatch"
    assert _kinds(text) == [ViolationKind.BARE_M_SCRIPTS]


def test_waiver_relative_script_suppresses():
    text = "python3 scripts/inbox/prescan.py  # env-guard: waive relative_script — intentional"
    assert scan_text(text) == []


# --- Determinism + Finding shape ----------------------------------------------


def test_deterministic():
    text = "python3 -m scripts.inbox.prescan\ncd /home/kgale/kg-automation && python foo"
    assert scan_text(text) == scan_text(text)


def test_finding_carries_line_and_remediation():
    findings = scan_text("python3 -m scripts.inbox.prescan")
    assert isinstance(findings[0], Finding)
    assert findings[0].line == 1
    # Remediation steers to the checkout-cd form.
    assert "/home/claude/kg-automation" in findings[0].remediation
