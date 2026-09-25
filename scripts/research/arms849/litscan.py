"""Static string scan for the arms package (WP04, used by the `reference_absent` gate).

Every string a static reading of a module can produce: source text lowered, plus
every expression built ONLY from literals and operators evaluated by Python
itself — in a child process under memory/CPU/time limits that FAIL CLOSED. A
name, comprehension, lambda or attribute is opaque here (a NUL in its place, so a
word cannot be smuggled around it) and is the RUNTIME boundary's job. The one
call that is NOT opaque is a pure string method on a literal receiver with literal
arguments (`"{}{}".format("or", "acle")`, `"".join([...])`, `.replace`, …): Python
evaluates it in the same child, and any exception there REFUSES the scan (Codex WP04
c8). This is the same boundary the WP02 isolation test states; that test carries its
own copy so it can run before this module exists.

The grammar is enumerated EXPLICITLY (Codex WP04 c8): every expression node is in
`_PURE_EXPR` or `_OPAQUE_EXPR` by name. A node in neither — a new Python version's
grammar, or anything synthetic — makes the scan REFUSE (`ScanRefused`, which the gate
turns into a failure) instead of silently passing. The partition test asserts every
`ast.expr` subclass of the running interpreter is in exactly one set.

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

__all__ = ["ScanBudgetExceeded", "ScanRefused", "find_words", "string_constants"]

SCAN_MEMORY_BYTES = 256 * 1024 * 1024
SCAN_CPU_SECONDS = 5
SCAN_WALL_SECONDS = 30
_EXIT_BUDGET = 3
_EXIT_REFUSED = 4
_UNKNOWN = object()


class ScanBudgetExceeded(RuntimeError):
    """The evaluation blew its budget — the gate fails closed."""


class ScanRefused(RuntimeError):
    """The scan met syntax it does not classify, or a literal call that raised — the gate
    fails closed rather than pass over what it could not read."""


# Literal structure Python evaluates safely with empty builtins. Listed by NAME, never
# derived as "everything that is not opaque": a node absent from BOTH tuples is refused.
_PURE_EXPR: tuple[type[ast.expr], ...] = (
    ast.Constant, ast.JoinedStr, ast.FormattedValue,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Tuple, ast.List, ast.Set, ast.Dict, ast.Subscript, ast.Slice, ast.Starred,
)
# Nodes that can reference state or execute code (a Call is opaque UNLESS it is a
# literal string-method call, see _literal_method_call).
_OPAQUE_EXPR: tuple[type[ast.expr], ...] = (
    ast.Name, ast.Call, ast.Attribute, ast.Lambda,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr,
)
# Non-expression nodes that occur INSIDE a pure expression tree.
_PURE_HELPERS: tuple[type[ast.AST], ...] = (
    ast.Expression, ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
)
# Pure str/bytes methods: no state, no side effects, a literal in → a literal out.
_LITERAL_STR_METHODS = frozenset({
    "format", "format_map", "join", "replace", "upper", "lower", "casefold", "strip", "lstrip",
    "rstrip", "title", "capitalize", "swapcase", "center", "ljust", "rjust", "zfill",
    "removeprefix", "removesuffix", "translate", "expandtabs", "encode", "decode",
})


def _literal_method_call(node: ast.AST) -> bool:
    """`<pure literal>.<allowlisted str method>(<pure literals> …)` — the ONE call shape the scan
    evaluates instead of treating as opaque (Codex WP04 c8: `"{}{}".format("or", "acle")`)."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _LITERAL_STR_METHODS or not _is_pure(node.func.value):
        return False
    return all(_is_pure(a) for a in node.args) and all(_is_pure(k.value) for k in node.keywords)


def _is_pure(node: ast.AST) -> bool:
    """True when the subtree is literal structure; False when it touches state; a node in
    NEITHER explicit set raises ScanRefused (the grammar has grown — fail closed)."""
    if isinstance(node, _PURE_HELPERS):
        return True
    if _literal_method_call(node):
        return True
    kind = type(node)
    if kind in _OPAQUE_EXPR:
        return False
    if kind not in _PURE_EXPR:
        where = f"line {getattr(node, 'lineno', '?')}:{getattr(node, 'col_offset', '?')}"
        raise ScanRefused(f"unclassified expression node {kind.__name__} at {where} — the scan cannot vouch for it")
    return all(_is_pure(child) for child in ast.iter_child_nodes(node))


def _eval(node: ast.expr) -> object:
    expr = ast.Expression(body=node)
    ast.fix_missing_locations(expr)
    return eval(compile(expr, "<litscan>", "eval"), {"__builtins__": {}}, {})


def _const_eval(node: ast.AST) -> object:
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
    if _literal_method_call(node):
        try:
            return _eval(node)
        except (MemoryError, RecursionError, OverflowError):
            raise
        except Exception as exc:  # a literal call that raises is refused, never skipped (fail closed)
            raise ScanRefused(f"literal call at line {getattr(node, 'lineno', '?')} raised {type(exc).__name__}: {exc}") from exc
    try:
        return _eval(node)
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
    if proc.returncode == _EXIT_REFUSED:
        raise ScanRefused(proc.stderr.strip()[-300:])
    if proc.returncode != 0:
        raise ScanBudgetExceeded(f"scan child exited {proc.returncode}: {proc.stderr[-300:]}")
    return json.loads(proc.stdout)


def find_words(paths: Iterable[pathlib.Path], words: Sequence[str]) -> list[str]:
    """Every (file, word) hit in source text or in any statically producible string.
    Raises ScanBudgetExceeded / ScanRefused (naming the file) when a module cannot be read
    to the end — the caller fails closed."""
    hits: list[str] = []
    lowered = [w.lower() for w in words]
    for path in paths:
        source = pathlib.Path(path).read_text(encoding="utf-8")
        low = source.lower()
        try:
            joined = "\n".join(string_constants(source)).lower()
        except ScanRefused as exc:
            raise ScanRefused(f"{path}: {exc}") from exc
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
        return _EXIT_BUDGET
    except ScanRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return _EXIT_REFUSED
    sys.stdout.write(json.dumps(strings))
    return 0


if __name__ == "__main__":
    raise SystemExit(_scan_main() if "--scan" in sys.argv else 2)
