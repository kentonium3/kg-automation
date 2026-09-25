"""Static string scan for the arms package (WP04, used by the `reference_absent` gate).

Every string a static reading of a module can produce: source text lowered, plus
every expression built ONLY from literals and operators evaluated by Python
itself — in a child process under memory/CPU/time limits that FAIL CLOSED. A
name, call, attribute or comprehension is opaque here (a NUL in its place, so a
word cannot be smuggled around it) and is the RUNTIME boundary's job. This is the
same boundary the WP02 isolation test states; that test carries its own copy so
it can run before this module exists.

The forbidden words are never written here: callers build them from parts or
read them from the export exclusion data file.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
from collections.abc import Iterable, Sequence

__all__ = ["ScanBudgetExceeded", "find_words", "string_constants"]

SCAN_MEMORY_BYTES = 256 * 1024 * 1024
SCAN_CPU_SECONDS = 5
SCAN_WALL_SECONDS = 30
_UNKNOWN = object()
# Every expression node in the grammar is classified: OPAQUE nodes can reference state or
# execute code; everything else is literal structure Python evaluates safely with empty
# builtins (partition asserted by test — a forgotten node cannot become "opaque").
class ScanBudgetExceeded(RuntimeError):
    """The evaluation blew its budget — the gate fails closed."""


_OPAQUE_EXPR = frozenset({ast.Name, ast.Call, ast.Attribute, ast.Lambda, ast.ListComp, ast.SetComp,
                          ast.DictComp, ast.GeneratorExp, ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr})
_PURE_EXPR = frozenset(cls for cls in ast.expr.__subclasses__() if cls not in _OPAQUE_EXPR)
_PURE_HELPERS = (ast.Expression, ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop)


def _is_pure(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, _PURE_HELPERS):
            continue
        if type(sub) in _OPAQUE_EXPR or type(sub) not in _PURE_EXPR:
            return False
    return True


def _const_eval(node: ast.AST):
    if isinstance(node, ast.JoinedStr) and not _is_pure(node):
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
        return eval(compile(expr, "<litscan>", "eval"), {"__builtins__": {}}, {})
    except (MemoryError, RecursionError, OverflowError):
        raise
    except (ValueError, TypeError, ArithmeticError, LookupError, AttributeError, SyntaxError):
        return _UNKNOWN             # not a constant — or a node that cannot stand alone (bare Starred/Slice)


def _string_constants_inprocess(source: str) -> list[str]:
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
            out.extend(v.decode("utf-8", "replace") if isinstance(v, bytes) else v
                       for v in val if isinstance(v, (str, bytes)))
    return out


def string_constants(source: str) -> list[str]:
    """Evaluate in a child under RLIMIT_AS / RLIMIT_CPU and a wall timeout; fail closed."""
    try:
        proc = subprocess.run([sys.executable, "-m", "scripts.research.arms849.litscan", "--scan"],
                              input=source, capture_output=True, text=True,
                              timeout=SCAN_WALL_SECONDS, check=False, cwd=str(_repo_root()))
    except subprocess.TimeoutExpired as exc:
        raise ScanBudgetExceeded(f"scan child exceeded {SCAN_WALL_SECONDS}s") from exc
    if proc.returncode != 0:
        raise ScanBudgetExceeded(f"scan child exited {proc.returncode}: {proc.stderr[-300:]}")
    return json.loads(proc.stdout)


def find_words(paths: Iterable[pathlib.Path], words: Sequence[str]) -> list[str]:
    """Every (file, word) hit in source text or in any statically producible string."""
    hits: list[str] = []
    lowered = [w.lower() for w in words]
    for path in paths:
        source = pathlib.Path(path).read_text(encoding="utf-8")
        low = source.lower()
        joined = "\n".join(string_constants(source)).lower()
        for w in lowered:
            if w in low:
                hits.append(f"{path}: {w!r} in source")
            elif w in joined:
                hits.append(f"{path}: {w!r} in a statically producible string")
    return hits


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3]


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


if __name__ == "__main__":
    raise SystemExit(_scan_main() if "--scan" in sys.argv else 2)
