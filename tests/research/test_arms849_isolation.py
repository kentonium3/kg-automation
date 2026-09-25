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
    """Every statically resolvable string: str and bytes constants, f-string literal
    parts, and `+` concatenations of constants (folded)."""
    out: list[str] = []

    def fold(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, bytes):
            return node.value.decode("utf-8", "replace")
        if isinstance(node, ast.JoinedStr):
            parts = [fold(v) for v in node.values]
            return "".join(p if p is not None else "\0" for p in parts)
        if isinstance(node, ast.FormattedValue):
            # A constant interpolation is evaluated: conversion (!s !r !a) and a
            # constant format spec included. Anything non-constant is opaque.
            if isinstance(node.value, ast.Constant):
                val = node.value.value
                conv = {-1: lambda v: v, 115: str, 114: repr, 97: ascii}[node.conversion](val)
                spec = fold(node.format_spec) if node.format_spec is not None else ""
                try:
                    return format(conv, spec) if spec else str(conv)
                except (ValueError, TypeError):
                    return "\0"
            return "\0"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = fold(node.left), fold(node.right)
            if left is not None and right is not None:
                return left + right
        return None

    for node in ast.walk(ast.parse(source)):
        folded = fold(node)
        if folded is not None:
            out.append(folded)
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


@pytest.mark.parametrize("construction", [
    'X = "or" "acle"',                     # adjacent literals (parse-time concatenation)
    'X = "or" + "acle"',                   # `+` of constants (folded)
    'X = f"or{\'\'}acle"',                 # f-string literal parts around an empty expression
    'X = b"or" + b"acle"',                 # bytes literals
    'X = "trace" + "ability"',
    'X = f"or{\'acle\'!s}"',                # conversion on a constant (Codex c2)
    'X = f"or{\'acle\':>4}"',               # constant format spec
    'X = f"{\'or\'}" + "acle"',             # f-string constant + concatenation
], ids=["adjacent", "plus", "fstring", "bytes", "plus2", "conv", "spec", "fplus"])
def test_the_scan_catches_constructed_forbidden_strings(tmp_path, construction):
    """Codex WP02 cycle 1: the first scan missed constructed strings."""
    bad = tmp_path / "bad.py"
    bad.write_text(construction + "\n")
    joined = "\n".join(_string_constants(bad.read_text())).lower()
    assert any(word in joined for word in FORBIDDEN), joined


def test_export_excludes_live_in_a_data_file_not_a_module():
    """The exclusion list must name the paths; a .py module must not."""
    data = PKG / "compose" / "export-excludes.txt"
    assert data.exists()
    body = data.read_text().lower()
    assert all(word in body for word in FORBIDDEN[:1])
