"""The static half of FR-013: the arms package never names what it must not see (WP02 T010).

The strings are assembled from parts here so this test file itself does not
contain them either — a grep of the tests directory must not be the thing that
trips the gate.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PKG = REPO_ROOT / "scripts" / "research" / "arms849"
FORBIDDEN = ("or" + "acle", "se" + "ed/", "trace" + "ability")


_UNKNOWN = object()     # distinct from the constant None, which IS a value (Codex c6)

# The gate's boundary, stated: every expression built ONLY from literals and operators is
# evaluated by Python itself (no hand-written evaluator to keep extending — Codex c3..c7
# each found a construction it missed); anything involving a name, call, attribute or
# comprehension is opaque here and is the RUNTIME boundary's job (the export exclusion
# and the in-container self-test). An opaque interpolation renders as a NUL so a word
# cannot be smuggled around it.
_PURE_NODES = (ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
               ast.JoinedStr, ast.FormattedValue, ast.Tuple, ast.List, ast.Set, ast.Dict, ast.Subscript,
               ast.Slice, ast.Load, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)


def _is_pure(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, _PURE_NODES):
            return False
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Pow):
            exp = sub.right
            if not (isinstance(exp, ast.Constant) and isinstance(exp.value, int) and abs(exp.value) <= 64):
                return False        # no unbounded exponentiation in a scan
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mult):
            for side in (sub.left, sub.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, int) and abs(side.value) > 10_000:
                    return False    # no giant repetition
    return True


def _const_eval(node: ast.AST):
    """Python's own value of a pure-literal expression, or _UNKNOWN."""
    if isinstance(node, ast.JoinedStr) and not _is_pure(node):
        # Evaluate the resolvable interpolations, NUL the opaque ones.
        out = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                out.append(str(v.value))
            else:
                piece = _const_eval(v)
                out.append("\0" if piece is _UNKNOWN else str(piece))
        return "".join(out)
    if isinstance(node, ast.FormattedValue):
        if not _is_pure(node):
            return _UNKNOWN
        node = ast.JoinedStr(values=[node])
    if not isinstance(node, ast.expr) or not _is_pure(node):
        return _UNKNOWN
    try:
        expr = ast.Expression(body=node)
        ast.fix_missing_locations(expr)
        return eval(compile(expr, "<isolation-scan>", "eval"), {"__builtins__": {}}, {})
    except (MemoryError, RecursionError, OverflowError):
        raise                       # a budget blow-up is NEVER "not a constant": the child exits, the gate fails closed
    except (ValueError, TypeError, ArithmeticError, LookupError, AttributeError):
        return _UNKNOWN             # a type/zero/format error is simply "not a constant"


def _string_constants_inprocess(source: str) -> list[str]:
    """Every string a static reading of the module can produce (see _const_eval). Runs
    only inside the rlimited child (see _string_constants)."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        val = _const_eval(node)
        if val is _UNKNOWN:
            continue
        if isinstance(val, bytes):
            out.append(val.decode("utf-8", "replace"))
        elif isinstance(val, str):
            out.append(val)
        elif isinstance(val, (tuple, list, set, frozenset)):
            out.extend(v.decode("utf-8", "replace") if isinstance(v, bytes) else v for v in val if isinstance(v, (str, bytes)))
    return out


SCAN_MEMORY_BYTES = 256 * 1024 * 1024
SCAN_CPU_SECONDS = 5
SCAN_WALL_SECONDS = 30


class ScanBudgetExceeded(RuntimeError):
    """The literal evaluation blew its memory/CPU/time budget — the gate FAILS CLOSED
    (Codex WP02 c8: a giant format spec, shift or repetition must not hang pytest)."""


def _string_constants(source: str) -> list[str]:
    """Run the evaluation in a child process under RLIMIT_AS / RLIMIT_CPU and a wall-clock
    timeout; any violation raises ScanBudgetExceeded, which fails the gate."""
    import subprocess
    proc = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "--scan"],
                          input=source, capture_output=True, text=True, timeout=SCAN_WALL_SECONDS, check=False)
    if proc.returncode != 0:
        raise ScanBudgetExceeded(f"scan child exited {proc.returncode}: {proc.stderr[-300:]}")
    return json.loads(proc.stdout)


def _scan_main() -> int:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (SCAN_MEMORY_BYTES, SCAN_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (SCAN_CPU_SECONDS, SCAN_CPU_SECONDS))
    source = sys.stdin.read()
    try:
        strings = _string_constants_inprocess(source)
    except (MemoryError, RecursionError, OverflowError) as exc:
        print(f"budget: {type(exc).__name__}", file=sys.stderr)
        return 3
    sys.stdout.write(json.dumps(strings))
    return 0


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
    'X = f"{+111:c}racle"',                  # unary plus (Codex c7)
    'X = f"or{1 / 2!s:.0}acle"',             # true division
    'X = "%s%s" % ("or", "acle")',           # %-formatting with a tuple
    'X = "{}{}".format if False else ("or" "acle",)[0]',   # tuple subscript
    'X = "".join(["or", "acle"]) if False else "orac" "le"',
    'X = "or" + str("acle") if False else "or" "acle"',
], ids=["adjacent", "plus", "fstring", "bytes", "plus2", "conv", "spec", "fplus", "inner-plus", "nested", "numc", "numc-plus", "arith", "arith2", "mult", "none", "none-plus", "bool", "uplus", "div", "percent", "tuple-sub", "call-opaque", "call-opaque2"])
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


@pytest.mark.parametrize("construction", [
    'X = f"{0:1000000000}"',                 # a 1 GB format spec (Codex c8)
    'X = 1 << 10000000000',                  # a giant shift
    'X = "x" * (10000 ** 3)',                # a giant repetition through an expression
], ids=["fmt-1G", "shift", "repeat"])
def test_the_scan_fails_closed_on_a_budget_violation(construction):
    """A literal that would exhaust memory or time must FAIL the gate, never pass it or hang."""
    with pytest.raises((ScanBudgetExceeded, __import__("subprocess").TimeoutExpired)):
        _string_constants(construction + "\n")


if __name__ == "__main__" and "--scan" in sys.argv:
    raise SystemExit(_scan_main())
