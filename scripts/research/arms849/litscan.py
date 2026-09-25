"""Static string scan for the arms package (WP04, used by the `reference_absent` gate).

Every string a static reading of a module can produce: source text lowered, plus
every expression built ONLY from literals, operators, the CLOSED builtin allowlist
and methods of literals, evaluated by Python itself — in a child process under
memory/CPU/time limits that FAIL CLOSED. A Call is classified BY ITS PARTS
(design-lead ruling 2026-09-25, Codex WP04 c9): (i) func is a Name in
`_PURE_BUILTINS` and every arg/kwarg is pure → evaluated; (ii) func is an Attribute
on a pure receiver — ANY method name; receiver purity recurses through evaluated
calls, so `bytes([...]).decode()` and `"x y".split()[0]` are covered — and every arg
is pure → evaluated, and a method that raises or is absent REFUSES the scan
(`ScanRefused`). EVERYTHING ELSE IS OPAQUE: a literal-only call to any other name
(`RuntimeError("or" + "acle")`, `@dataclass(frozen=True)`) is opaque — its pure
arguments are still evaluated on their own, so the BinOp above is caught — and a
name, comprehension, lambda or attribute of a name is the RUNTIME boundary's job
(a NUL in its place inside an f-string, so a word cannot be smuggled around it).

Shadowing: a module that rebinds any allowlisted builtin name at any scope
(assignment target, def/class name, import alias, global/nonlocal, comprehension,
for/with/except target, parameter) is REFUSED — the allowlist is only closed while
its names mean what the interpreter says they mean.

The grammar is enumerated EXPLICITLY (Codex WP04 c8): every expression node is in
`_PURE_EXPR`, `_BY_PARTS_EXPR` or `_OPAQUE_EXPR` by name. A node in none — a new
Python version's grammar, or anything synthetic — makes the scan REFUSE instead of
silently passing. The partition test asserts every `ast.expr` subclass of the running
interpreter is in exactly one set.

Closure (2026-09-25, design-lead ruling): A further finding is folded only if it is a
construction built from literals + operators + the closed builtin allowlist + methods
of literals that the scan misclassifies (an implementation bug of this ruling). A
finding that needs a name binding, an import, or attribute access on a module is
runtime-boundary territory (D-8) and is out of scope.

This is the same boundary the WP02 isolation test states; that test carries its own
copy so it can run before this module exists. The forbidden words are never written
here: callers build them from parts or read them from the export exclusion data file.
"""

from __future__ import annotations

import ast
import builtins
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
    """The scan met syntax it does not classify, a literal call that raised, or a module
    that rebinds an allowlisted builtin — the gate fails closed rather than pass over what
    it could not read."""


# Literal structure Python evaluates safely. Listed by NAME, never derived as "everything
# that is not opaque": a node absent from ALL three tuples is refused.
_PURE_EXPR: tuple[type[ast.expr], ...] = (
    ast.Constant, ast.JoinedStr, ast.FormattedValue,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Tuple, ast.List, ast.Set, ast.Dict, ast.Subscript, ast.Slice, ast.Starred,
)
# Classified by their parts (see _is_pure): an allowlisted builtin Name is pure, any other
# Name is opaque; an Attribute is as pure as its receiver; a Call as its func and args.
_BY_PARTS_EXPR: tuple[type[ast.expr], ...] = (ast.Name, ast.Call, ast.Attribute)
# Nodes that reference state or execute code — always opaque.
_OPAQUE_EXPR: tuple[type[ast.expr], ...] = (
    ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr,
)
# Non-expression nodes that occur INSIDE a pure expression tree.
_PURE_HELPERS: tuple[type[ast.AST], ...] = (
    ast.Expression, ast.expr_context, ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
)
# The CLOSED allowlist (design-lead ruling 2026-09-25): deterministic, no I/O, no imports,
# no attribute reflection. NOT hash / id (salted, address-based); never type, getattr,
# setattr, vars, dir, globals, locals, eval, exec, compile, open, __import__, input, print,
# breakpoint, memoryview, object, super, iter, next, callable, isinstance, issubclass,
# property, staticmethod, classmethod.
_PURE_BUILTINS: frozenset[str] = frozenset({
    "str", "bytes", "bytearray", "int", "float", "bool", "complex", "len", "repr", "chr", "ord",
    "tuple", "list", "dict", "set", "frozenset", "sorted", "reversed", "min", "max", "sum", "abs",
    "round", "divmod", "pow", "hex", "oct", "bin", "format", "slice", "range", "enumerate", "zip",
    "map", "filter", "any", "all",
})
_EVAL_BUILTINS: dict[str, object] = {name: getattr(builtins, name) for name in sorted(_PURE_BUILTINS)}


def _is_pure(node: ast.AST) -> bool:
    """True when the subtree is literal structure the child can evaluate; False when it
    touches state; a node in NO explicit set raises ScanRefused (fail closed)."""
    if isinstance(node, _PURE_HELPERS):
        return True
    kind = type(node)
    if kind is ast.Name:
        return node.id in _PURE_BUILTINS                       # type: ignore[attr-defined]
    if kind is ast.Attribute:
        return _is_pure(node.value)                            # type: ignore[attr-defined]
    if kind is ast.Call:
        call: ast.Call = node                                  # type: ignore[assignment]
        args_pure = all(_is_pure(a) for a in call.args) and all(_is_pure(k.value) for k in call.keywords)
        if isinstance(call.func, ast.Name):
            return args_pure and call.func.id in _PURE_BUILTINS
        return args_pure and _is_pure(call.func)               # an Attribute on a pure receiver, any method
    if kind in _OPAQUE_EXPR:
        return False
    if kind not in _PURE_EXPR:
        where = f"line {getattr(node, 'lineno', '?')}:{getattr(node, 'col_offset', '?')}"
        raise ScanRefused(f"unclassified expression node {kind.__name__} at {where} — the scan cannot vouch for it")
    return all(_is_pure(child) for child in ast.iter_child_nodes(node))


def _bound_names(tree: ast.AST) -> Iterable[tuple[str, ast.AST]]:
    """Every name the module binds, at any scope, with the node that binds it."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            yield node.id, node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, node
        elif isinstance(node, ast.arg):
            yield node.arg, node
        elif isinstance(node, ast.alias):
            yield (node.asname or node.name.split(".", 1)[0]), node
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                yield name, node
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
            yield node.name, node
        elif isinstance(node, ast.MatchMapping) and node.rest:
            yield node.rest, node


def _refuse_shadowed_builtins(tree: ast.AST) -> None:
    shadowed = sorted(f"{name} at line {getattr(node, 'lineno', '?')}"
                      for name, node in _bound_names(tree) if name in _PURE_BUILTINS)
    if shadowed:
        raise ScanRefused(f"module rebinds allowlisted builtin(s) {shadowed} — the scan cannot vouch for it")


def _eval(node: ast.expr) -> object:
    expr = ast.Expression(body=node)
    ast.fix_missing_locations(expr)
    return eval(compile(expr, "<litscan>", "eval"), {"__builtins__": dict(_EVAL_BUILTINS)}, {})


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
    if isinstance(node, ast.Call):
        try:
            return _eval(node)
        except (MemoryError, RecursionError, OverflowError):
            raise
        except Exception as exc:  # a literal call that raises (or a method that is absent) is refused, never skipped
            raise ScanRefused(f"literal call at line {getattr(node, 'lineno', '?')} raised {type(exc).__name__}: {exc}") from exc
    try:
        return _eval(node)
    except (MemoryError, RecursionError, OverflowError):
        raise
    except (ValueError, TypeError, ArithmeticError, LookupError, AttributeError, SyntaxError):
        return _UNKNOWN             # not a constant — or a node that cannot stand alone (bare Starred/Slice)


def _string_constants_inprocess(source: str) -> list[str]:
    tree = ast.parse(source)
    _refuse_shadowed_builtins(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        val = _const_eval(node)
        if val is _UNKNOWN:
            continue
        if isinstance(val, (bytes, bytearray)):
            out.append(bytes(val).decode("utf-8", "replace"))
        elif isinstance(val, str):
            out.append(val)
        elif isinstance(val, (tuple, list, set, frozenset)):
            out.extend(bytes(v).decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else v
                       for v in val if isinstance(v, (str, bytes, bytearray)))
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
