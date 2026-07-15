"""SC-001 acceptance gate (WP05, mission ``vikunja-reference-seam-01KXK68Z``).

The mission's SC-001 says: *100% of Felix's runtime Vikunja project/label
resolutions go through the single registry — zero remaining by-title or
hardcoded-id lookups in runtime consumer code.* This test is the **durable
regression guard** that keeps future code on the seam. It scans the runtime
consumer surface under ``scripts/`` (in-process, ``pathlib`` — no shell-out)
and asserts **zero** matches for the three ad-hoc-resolution pattern classes
defined in ``spec.md`` § "SC-001 acceptance grep":

- **A — by-title resolution:** a ``title``-equality comparison against a routed
  Vikunja project/label **name** — either a string literal (``title == "Habits"``,
  ``p.get("title") == "Someday"``) or a resolution constant
  (``get("title") == MANUAL_OVERRIDE_LABEL``). Detected line-based (regex).
- **B — hardcoded id resolution target:** a ``*_PROJECT_ID`` / ``*_LABEL_ID``
  constant bound to an integer literal (``HABITS_PROJECT_ID = 13``), including
  the literal buried behind a type annotation and/or a container literal
  (``DEFAULT_TARGET_PROJECT_ID: int = 13``, ``PROJECT_IDS: list[int] = [13]``,
  ``EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({13})``, ``= {13}``); and a
  dict literal on an assignment RHS binding ``"project_id"`` / ``"label_id"`` to
  an integer literal (``TARGET = {"project_id": 13}``). **Detected via ``ast``**
  so a literal split ACROSS multiple lines (the shape a line-based scanner steps
  over) is still caught, and so illustrative sample task data living inside a
  **docstring** (``{"task_id": 17, "title": "Workout", "project_id": 1, ...}``)
  is inherently invisible (a docstring is a string constant, not an ``ast.Dict``).
  The detector is scoped to resolution-intent — ``PROJECT_ID`` / ``LABEL_ID``
  UPPERCASE constants and assigned dict literals — so the accessor-derived form
  (``frozenset({vikunja_refs.project_id("habits")})`` — no int literal in the
  RHS) and lowercase parameter defaults (``def f(project_id: int = 4)``) are
  **not** flagged.
- **C — list-and-filter resolution:** a direct ``GET /projects`` / ``GET /labels``
  collection listing made to resolve a known logical reference (as opposed to a
  ``/projects/<id>/...`` operation on an already-resolved id). Detected
  line-based (regex).

**Exemptions (C-005).** The provisioning / setup tools under ``scripts/vikunja/``
(``setup_vikunja``, ``provision_felix_bot``, ``create_taxonomy_labels``,
``migrate_tasks``, ``reconcile_projects``, ``create_saved_filters``,
``validate_felix_bot``, ``create_task``, …) legitimately create identities and
list live Vikunja, so the whole directory is excluded. The reference-seam
infrastructure itself is also excluded: the accessor
``scripts/common/vikunja_refs.py`` (it *is* the registry, and its docstring
illustrates selector shapes) and the WP02 drift validator(s)
(``validate_refs.py`` / ``vikunja_refs_validate.py``) which legitimately do a
single live list.

On failure the assertion message names **every** offending ``file:line`` and the
matched text, so a regression is immediately actionable. Positive-control tests
below prove the patterns actually fire — including the multiline hardcoded-id
forms that motivated the AST rewrite — so the gate fails-closed by construction.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Scope + exemptions
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"

#: Directory prefixes (relative to the repo root) excluded wholesale (C-005).
_EXEMPT_DIR_PREFIXES = ("scripts/vikunja/",)

#: Individual files excluded: the seam accessor + the WP02 drift validator(s).
_EXEMPT_RELPATHS = frozenset(
    {
        "scripts/common/vikunja_refs.py",
    }
)

#: Exempt by basename regardless of directory (WP02 validators may land in
#: scripts/common/ or scripts/vikunja/; excluding by name is location-robust).
_EXEMPT_BASENAMES = frozenset(
    {
        "validate_refs.py",
        "vikunja_refs_validate.py",
    }
)

# ---------------------------------------------------------------------------
# The routed project/label names Felix resolves on (incl. the retired
# "Someday" so reintroducing a by-title lookup of it is caught).
# ---------------------------------------------------------------------------

_ROUTED_NAMES = (
    "Inbox",
    "Habits",
    "Personal",
    "Felix / kg-automation",
    "Clients",
    "PointerHealth",
    "spec-kitty",
    "Metal Casework",
    "CT-90day",
    "Someday",
    "q:schedule",
    "felix:ignore",
)

_NAME_ALT = "|".join(re.escape(n) for n in _ROUTED_NAMES)
_NAME_LITERAL = rf"""["'](?:{_NAME_ALT})["']"""

# ---------------------------------------------------------------------------
# Line-based deny patterns — Class A (by-title) and Class C (list-and-filter).
# Class B moved to the AST scanner below (multiline-robust). Each entry:
# (name, compiled regex).
# ---------------------------------------------------------------------------

# Class A: a title-equality comparison against a routed-name literal OR a
# PROJECT/LABEL/TITLE resolution constant. A bare name *assignment*
# (SOMEDAY_LABEL_NAME = "q:schedule") is NOT flagged — that is the logical name
# fed to the seam accessor, not a by-title resolution.
_A_TITLE = r"""(?:\.title\b|\btitle\b["'\s\]\)]*)"""
_A_CONST = r"""[A-Z][A-Z0-9_]*(?:PROJECT|LABEL|TITLE)[A-Z0-9_]*"""

_LINE_DENY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "A:title-equality-vs-routed-name-literal",
        re.compile(
            rf"(?:{_A_TITLE}\s*==\s*{_NAME_LITERAL})"
            rf"|(?:{_NAME_LITERAL}\s*==\s*[^=].*\btitle\b)"
        ),
    ),
    (
        "A:title-equality-vs-resolution-constant",
        re.compile(
            rf"(?:{_A_TITLE}\s*==\s*{_A_CONST})"
            rf"|(?:{_A_CONST}\s*==\s*[^=]*\btitle\b)"
        ),
    ),
    (
        "C:list-and-filter-projects-or-labels",
        re.compile(
            r"""\.get\(\s*f?["']/(?:projects|labels)(?:\?[^"']*)?["']"""
        ),
    ),
]

# ---------------------------------------------------------------------------
# Class B — AST scanner (multiline-robust).
#
# Two resolution-intent shapes are flagged:
#
#   B:hardcoded-id-constant — a module-level assignment / annotated-assignment
#     whose target name carries PROJECT_ID / LABEL_ID (UPPERCASE resolution
#     constant) and whose *value* contains an integer literal anywhere, incl.
#     nested inside List / Set / Tuple / Dict / frozenset(...) containers and
#     regardless of type annotation. Because ``ast`` parses whole statements,
#     the literal is caught even when the container spans multiple physical
#     lines. The accessor-derived form
#     ``frozenset({vikunja_refs.project_id("habits")})`` carries NO int literal
#     in its value, so it is correctly NOT flagged.
#
#   B:hardcoded-id-dict-resolution-target — a dict literal on an assignment RHS
#     binding a ``"project_id"`` / ``"label_id"`` key directly to an integer
#     literal (``TARGET = {"project_id": 13}``). Scoped to Dict nodes reached
#     through an assignment's value, so illustrative sample task data that lives
#     inside a docstring is invisible to the AST (a docstring is a string
#     constant, never an ``ast.Dict``), and a dict field bound to a *variable*
#     (``{"project_id": resolved_id}``) is not flagged.
# ---------------------------------------------------------------------------

_B_CONST_NAME_RE = re.compile(r"[A-Z0-9_]*(?:PROJECT_ID|LABEL_ID)[A-Z0-9_]*")
_B_DICT_KEYS = frozenset({"project_id", "label_id"})


def _is_int_literal(node: ast.AST) -> bool:
    """True for an integer literal (``bool`` is a subclass of ``int`` — exclude)."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    )


def _value_has_int_literal(value: ast.AST) -> bool:
    """True if ``value``'s subtree contains an integer literal anywhere."""
    return any(_is_int_literal(sub) for sub in ast.walk(value))


def _dict_binds_id_to_int(dict_node: ast.Dict) -> bool:
    """True if the dict binds ``"project_id"`` / ``"label_id"`` to an int literal."""
    for key, val in zip(dict_node.keys, dict_node.values):
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and key.value in _B_DICT_KEYS
            and _is_int_literal(val)
        ):
            return True
    return False


def _assignment_target_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names: list[str] = []
    for target in targets:
        for sub in ast.walk(target):
            if isinstance(sub, ast.Name):
                names.append(sub.id)
    return names


def _segment(source: str, node: ast.AST) -> str:
    """Return the node's source text, whitespace-collapsed for a one-line report."""
    seg = ast.get_source_segment(source, node) or ""
    return " ".join(seg.split())


def _scan_ast(rel_posix: str, source: str) -> list[str]:
    findings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Real runtime files always parse; a synthetic control *fragment*
        # (e.g. a bare ``if ...:`` header) may not — Class A/C handle those
        # line-based, so skipping AST here is correct.
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:  # bare annotation, e.g. ``x: int``
            continue
        names = _assignment_target_names(node)
        if any(_B_CONST_NAME_RE.fullmatch(nm) for nm in names) and _value_has_int_literal(
            value
        ):
            findings.append(
                f"{rel_posix}:{node.lineno}: "
                f"[B:hardcoded-id-constant] {_segment(source, node)}"
            )
            continue
        for sub in ast.walk(value):
            if isinstance(sub, ast.Dict) and _dict_binds_id_to_int(sub):
                findings.append(
                    f"{rel_posix}:{node.lineno}: "
                    f"[B:hardcoded-id-dict-resolution-target] {_segment(source, node)}"
                )
                break
    return findings


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _is_exempt(rel_posix: str, basename: str) -> bool:
    if rel_posix in _EXEMPT_RELPATHS:
        return True
    if basename in _EXEMPT_BASENAMES:
        return True
    return any(rel_posix.startswith(prefix) for prefix in _EXEMPT_DIR_PREFIXES)


def _runtime_consumer_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(_SCRIPTS_ROOT.rglob("*.py")):
        rel_posix = path.relative_to(_REPO_ROOT).as_posix()
        if _is_exempt(rel_posix, path.name):
            continue
        files.append(path)
    return files


def _scan_source(rel_posix: str, source: str) -> list[str]:
    """Scan one source string: line-based (Class A + C) + AST-based (Class B)."""
    findings: list[str] = []
    for lineno, text in enumerate(source.splitlines(), start=1):
        for name, pattern in _LINE_DENY_PATTERNS:
            if pattern.search(text):
                findings.append(f"{rel_posix}:{lineno}: [{name}] {text.strip()}")
    findings.extend(_scan_ast(rel_posix, source))
    return findings


def _scan_all() -> list[str]:
    findings: list[str] = []
    for path in _runtime_consumer_files():
        rel_posix = path.relative_to(_REPO_ROOT).as_posix()
        findings.extend(_scan_source(rel_posix, path.read_text(encoding="utf-8")))
    return findings


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_sc001_no_adhoc_vikunja_resolution_in_runtime_surface():
    """SC-001: zero by-title / hardcoded-id / list-and-filter resolutions remain
    in the migrated runtime consumer surface (C-005 exemptions excluded)."""
    findings = _scan_all()
    assert not findings, (
        "SC-001 gate: found ad-hoc Vikunja resolution(s) in the runtime "
        "consumer surface — migrate these to the reference seam "
        "(scripts.common.vikunja_refs):\n  " + "\n  ".join(findings)
    )


def test_sc001_scan_actually_covers_files():
    """Guard the guard: the scan must actually see runtime consumer files (a
    broken glob/exemption that silently scans nothing would make the gate
    vacuously green)."""
    files = _runtime_consumer_files()
    rels = {p.relative_to(_REPO_ROOT).as_posix() for p in files}
    # Known migrated consumers must be in scope.
    assert "scripts/inbox/route_someday.py" in rels
    assert "scripts/sync/classify.py" in rels
    # Exemptions must be honored.
    assert "scripts/common/vikunja_refs.py" not in rels
    assert not any(r.startswith("scripts/vikunja/") for r in rels)


def test_sc001_patterns_fire_on_known_bad_lines():
    """Positive control: each deny class MUST fire on a reintroduced ad-hoc
    resolution, otherwise the gate is a no-op. Fails-closed by construction."""
    bad_cases = {
        "A:title-equality-vs-routed-name-literal": 'if p.get("title") == "Someday":',
        "A:title-equality-vs-resolution-constant": 'if p["title"] == SOMEDAY_PROJECT_TITLE:',
        "B:hardcoded-id-constant": "HABITS_PROJECT_ID = 13",
        "C:list-and-filter-projects-or-labels": 'projects = client.get("/projects")',
    }
    for expected_name, snippet in bad_cases.items():
        hits = _scan_source("synthetic.py", snippet)
        assert any(f"[{expected_name}]" in h for h in hits), (
            f"pattern {expected_name!r} failed to fire on {snippet!r} — the "
            f"SC-001 gate would not catch this regression"
        )


def test_sc001_broadened_b_patterns_fire_on_each_new_form():
    """Positive control for the broadened Class-B forms: each
    typed-assignment / container-literal / dict-resolution shape MUST make the
    gate fail if reintroduced. One assertion per form so a regression in any
    single shape is pinpointed.

    (These are precisely the shapes the *narrow* line-based Class-B pattern
    stepped over — the gap that let
    ``EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({13})`` slip through the
    runtime surface before the AST rewrite.)"""
    constant_forms = [
        "DEFAULT_TARGET_PROJECT_ID: int = 13",            # typed assignment
        "PROJECT_IDS: list[int] = [13]",                  # list container
        "EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({13})",  # frozenset
        "EXCLUDED_PROJECT_IDS = {13}",                    # set literal
    ]
    for snippet in constant_forms:
        hits = _scan_source("synthetic.py", snippet)
        assert any("[B:hardcoded-id-constant]" in h for h in hits), (
            f"broadened Class-B (typed/container) failed to fire on {snippet!r} — "
            f"the SC-001 gate would not catch this hardcoded-id regression"
        )

    dict_forms = [
        'DEFAULT_TARGET = {"project_id": 13}',
        'EXCLUDED = {"label_id": 23}',
    ]
    for snippet in dict_forms:
        hits = _scan_source("synthetic.py", snippet)
        assert any("[B:hardcoded-id-dict-resolution-target]" in h for h in hits), (
            f"broadened Class-B (dict resolution field) failed to fire on "
            f"{snippet!r} — the SC-001 gate would not catch this regression"
        )


def test_sc001_gate_catches_multiline_hardcoded_id_forms():
    """Positive control for the AST rewrite: hardcoded ids split ACROSS LINES
    (the exact gap the old line-based scanner stepped over) MUST fail the gate.
    ``ast`` parses whole statements, so a line break no longer hides a literal."""
    # Multiline dict resolution target.
    multiline_dict = 'DEFAULT_TARGET = {\n    "project_id": 13,\n}\n'
    hits = _scan_source("synthetic.py", multiline_dict)
    assert any("[B:hardcoded-id-dict-resolution-target]" in h for h in hits), (
        f"multiline dict form not caught — the AST scanner regressed: {hits}"
    )

    # Multiline frozenset / container constant.
    multiline_container = (
        "EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({\n    13,\n})\n"
    )
    hits = _scan_source("synthetic.py", multiline_container)
    assert any("[B:hardcoded-id-constant]" in h for h in hits), (
        f"multiline frozenset/container form not caught — the AST scanner "
        f"regressed: {hits}"
    )


def test_sc001_patterns_ignore_legitimate_seam_usage():
    """Negative control: legitimate seam usage and non-Vikunja title comparisons
    must NOT trip the gate (precision — no false positives)."""
    good_lines = [
        'SOMEDAY_LABEL_NAME = "q:schedule"',  # logical name fed to the accessor
        'lbl = vikunja_refs.label_id("q:schedule", "kent")',
        'pid = vikunja_refs.project_id("inbox")',
        'if props.get("title") == tab:',  # Google Sheets tab, variable RHS
        'if _normalize(habit.title) == target:',  # habit-name match, variable RHS
        'response = client.put(f"/projects/{project_id}/tasks", json=payload)',
        'if label.get("id") == ignore_id:',  # id comparison, already resolved
        # Broadened-Class-B precision guards:
        'EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({vikunja_refs.project_id("habits")})',  # accessor-derived — the migrated shape
        'ESCALATION_EXCLUDED_PROJECT_IDS: list[int] = [vikunja_refs.project_id("habits")]',  # sibling derived form (vikunja_scope)
        '    def reconcile(project_id: int = 4):',  # lowercase param default, not a resolution constant
        'excluded_project_ids: Iterable[int] = EXCLUDED_PROJECT_IDS,',  # param default = named constant, no literal
        '        {"task_id": 17, "title": "Workout", "project_id": 1,',  # sample task data (no assignment) — must NOT flag
        'payload = {"project_id": resolved_id, "title": name}',  # dict field bound to a variable, not a literal
    ]
    for line in good_lines:
        hits = _scan_source("synthetic.py", line)
        assert hits == [], f"false positive on legitimate line {line!r}: {hits}"


def test_sc001_docstring_sample_data_is_invisible_to_ast():
    """Negative control (AST-specific): illustrative sample task data that lives
    inside a module/function docstring — the real
    ``scripts/habits/identify_workout_task.py`` case — must NOT flag, because a
    docstring is a string constant, never an ``ast.Dict``."""
    source = (
        'def helper():\n'
        '    """Return the workout task, e.g.\n'
        '\n'
        '        {"task_id": 17, "title": "Workout", "project_id": 1}\n'
        '    """\n'
        '    return None\n'
    )
    hits = _scan_source("synthetic.py", source)
    assert hits == [], f"docstring sample data falsely flagged: {hits}"
