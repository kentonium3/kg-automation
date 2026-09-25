"""The static half of FR-013: the arms package never names what it must not see (WP02 T010).

The strings are assembled from parts here so this test file itself does not
contain them either — a grep of the tests directory must not be the thing that
trips the gate.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PKG = REPO_ROOT / "scripts" / "research" / "arms849"
FORBIDDEN = ("or" + "acle", "se" + "ed/", "trace" + "ability")


def _string_constants(source: str) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


@pytest.mark.parametrize("module", sorted(PKG.glob("*.py")), ids=lambda p: p.name)
def test_no_module_names_the_excluded_material(module: pathlib.Path):
    source = module.read_text(encoding="utf-8")
    low = source.lower()
    for word in FORBIDDEN:
        assert word not in low, f"{module.name} contains {word!r} in source"
    # Also the AST's string constants, so concatenation cannot hide one.
    joined = "\n".join(_string_constants(source)).lower()
    for word in FORBIDDEN:
        assert word not in joined


def test_the_scan_itself_can_fail(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('X = "or" "acle"\n')  # adjacent literals concatenate at parse time
    joined = "\n".join(_string_constants(bad.read_text())).lower()
    assert FORBIDDEN[0] in joined


def test_export_excludes_live_in_a_data_file_not_a_module():
    """The exclusion list must name the paths; a .py module must not."""
    data = PKG / "compose" / "export-excludes.txt"
    assert data.exists()
    body = data.read_text().lower()
    assert all(word in body for word in FORBIDDEN[:1])
