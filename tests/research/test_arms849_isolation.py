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


_UNKNOWN = object()     # distinct from the constant None, which IS a value (Codex c6)


def _const_eval(node: ast.AST):
    """Evaluate a statically resolvable expression: constants of any type (None included),
    arithmetic on numbers, concatenation of str/bytes, f-strings with conversions and
    format specs. Returns _UNKNOWN when anything is not a constant (an opaque
    interpolation renders as a NUL so a word cannot be smuggled around it)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        left, right = _const_eval(node.left), _const_eval(node.right)
        if left is _UNKNOWN or right is _UNKNOWN:
            return _UNKNOWN
        ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
               ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b, ast.Pow: lambda a, b: a ** b}
        fn = ops.get(type(node.op))
        if fn is None:
            return _UNKNOWN
        try:
            return fn(left, right)
        except Exception:  # noqa: BLE001 — a type/zero error is simply "not constant"
            return _UNKNOWN
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _const_eval(node.operand)
        return -v if isinstance(v, (int, float)) else _UNKNOWN
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            piece = _const_eval(v)
            out.append("\0" if piece is _UNKNOWN else str(piece))
        return "".join(out)
    if isinstance(node, ast.FormattedValue):
        val = _const_eval(node.value)
        if val is _UNKNOWN:
            return _UNKNOWN
        conv = {-1: lambda v: v, 115: str, 114: repr, 97: ascii}[node.conversion](val)
        spec = _const_eval(node.format_spec) if node.format_spec is not None else ""
        if spec is _UNKNOWN:
            return _UNKNOWN
        try:
            return format(conv, spec) if spec else str(conv)
        except (ValueError, TypeError):
            return _UNKNOWN
    return _UNKNOWN


def _string_constants(source: str) -> list[str]:
    """Every string a static reading of the module can produce (see _const_eval)."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        val = _const_eval(node)
        if val is _UNKNOWN:
            continue
        if isinstance(val, bytes):
            out.append(val.decode("utf-8", "replace"))
        elif isinstance(val, str):
            out.append(val)
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
    'X = f"or{\'ac\' + \'le\'}"',             # concatenation INSIDE the interpolation (Codex c3)
    'X = f"or{f\'ac{\"le\"}\'}"',             # nested f-string
    'X = f"{111:c}racle"',                   # numeric constant + format spec (Codex c4)
    'X = f"{111:c}" + "racle"',
    'X = f"{110 + 1:c}racle"',               # arithmetic on numeric constants (Codex c5)
    'X = f"{(37 * 3):c}" "racle"',
    'X = "or" * 1 + "acle"',
    'X = f"or{None!s:.0}acle"',              # the constant None is a VALUE, not "unknown" (Codex c6)
    'X = f"or{None!s:.0}" + "acle"',
    'X = f"or{True:d}acle"[0:2] if False else "or" "acle"',
], ids=["adjacent", "plus", "fstring", "bytes", "plus2", "conv", "spec", "fplus", "inner-plus", "nested", "numc", "numc-plus", "arith", "arith2", "mult", "none", "none-plus", "bool"])
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
