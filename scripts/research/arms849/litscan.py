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

Materialised values are read RECURSIVELY (Codex WP04 c10): str/bytes yield
themselves, list/tuple/set/frozenset/dict (keys AND values) recurse; iterators are
materialised; depth is bounded only by the child's rlimits (a pathological nesting
fails closed).

Unordered containers are hash-seed dependent, so the taint is VALUE-CARRIED
(design-lead ruling 2026-09-25, Codex WP04 c12; it replaced a syntactic enumeration
of set producers that c10–c12 kept finding holes in): evaluation is bottom-up, every
result is `_mark`ed — a set/frozenset becomes `TaintedSet`/`TaintedFrozenset`,
containers are rebuilt with marked members — and the child's `set`/`frozenset`
builtins ARE the Tainted classes, so `map(frozenset, …)`, `[frozenset][0](…)`,
`{"a"}.copy()`, set algebra and every future path yield Tainted values with no
syntax rule. Before ANY allowlisted builtin or ANY method runs, its arguments are
inspected against a CLOSED table keyed by callable identity: scalar-result consumers
(len, any, all, and `in`/`not in`/`==`/`!=`) accept any taint; sorted/min/max accept
a Tainted value only as the DIRECT positional operand with no Tainted members (a set
of scalars) and never with a tainted key=/default= or a `key=` at all (ties fall in
hash order); set/frozenset re-wrap keeps the taint; re-container builders (list,
tuple, reversed, enumerate, zip, dict) iterate in their INPUT's order, so they refuse
a direct set but carry a nested one; map/filter apply a callable to members and
refuse any taint; EVERY other callable or method (join, dict.fromkeys, str()/format/
%-format/f-string, a method on a Tainted receiver, Starred unpacking, BinOp/UnaryOp,
an ordering Compare, a conditional's test) refuses any taint: "order-sensitive
consumption of an unordered value". A gate whose answer can differ between runs is
not a gate. Set members are extracted in sorted order so every scan is reproducible.

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
from collections.abc import (
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    Sequence,
    ValuesView,
)
from typing import Any

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
    """The scan met syntax it does not classify, a literal call that raised, a module that
    rebinds an allowlisted builtin, or an order-sensitive use of an unordered value — the
    gate fails closed rather than pass over what it could not read."""


class TaintedSet(set):                  # type: ignore[type-arg]
    """A set the evaluator built — its iteration order depends on the hash seed."""


class TaintedFrozenset(frozenset):      # type: ignore[type-arg]
    """A frozenset the evaluator built — its iteration order depends on the hash seed."""


_TAINTED = (TaintedSet, TaintedFrozenset)

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
# The child's builtins: exactly the allowlist, with set/frozenset → the Tainted classes.
_EVAL_BUILTINS: dict[str, Any] = {name: getattr(builtins, name) for name in sorted(_PURE_BUILTINS)}
_EVAL_BUILTINS["set"], _EVAL_BUILTINS["frozenset"] = TaintedSet, TaintedFrozenset
# The CLOSED consumer table, by callable IDENTITY (however the callable was reached):
_SCALAR_CONSUMERS: tuple[Any, ...] = (len, any, all)                # a scalar result: any taint is fine
_SORTING: tuple[Any, ...] = (sorted, min, max)                       # elements come back: a DIRECT set of scalars only
_REWRAP: tuple[Any, ...] = (TaintedSet, TaintedFrozenset)            # stays Tainted (nesting survives)
_RECONTAINER: tuple[Any, ...] = (list, tuple, reversed, enumerate, zip, dict)   # iterate in the INPUT's order: a direct set refuses
_APPLYING: tuple[Any, ...] = (map, filter)                           # apply a callable to members: any taint refuses
_ORDER_INSENSITIVE_OPS: tuple[type[ast.cmpop], ...] = (ast.In, ast.NotIn, ast.Eq, ast.NotEq)


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


# ---------------------------------------------------------------------------
# value-carried taint
# ---------------------------------------------------------------------------


def _mark(value: Any) -> Any:
    """Every evaluated result passes through here: sets become Tainted, containers are
    rebuilt with marked members, iterators and dict views are materialised, scalars pass."""
    if isinstance(value, (set, frozenset)):
        cls = TaintedFrozenset if isinstance(value, frozenset) else TaintedSet
        return cls(_mark(v) for v in value)
    if isinstance(value, list):
        return [_mark(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_mark(v) for v in value)
    if isinstance(value, dict):
        return {_mark(k): _mark(v) for k, v in value.items()}
    if isinstance(value, (Iterator, KeysView, ValuesView, ItemsView)):
        return [_mark(v) for v in value]
    return value


def _holds_tainted(value: Any) -> bool:
    if isinstance(value, _TAINTED):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_holds_tainted(v) for v in value)
    if isinstance(value, dict):
        return any(_holds_tainted(k) or _holds_tainted(v) for k, v in value.items())
    return False


def _direct_only(value: Any) -> bool:
    """A Tainted value whose members hold no Tainted value: a set of scalars."""
    return isinstance(value, _TAINTED) and not any(_holds_tainted(v) for v in value)


def _refuse_order(node: ast.AST, what: str) -> None:
    where = f"line {getattr(node, 'lineno', '?')}:{getattr(node, 'col_offset', '?')}"
    raise ScanRefused(f"order-sensitive consumption of an unordered value at {where} ({what}) — "
                      f"the result depends on the hash seed")


# ---------------------------------------------------------------------------
# bottom-up evaluation
# ---------------------------------------------------------------------------


def _bind_value(value: Any, names: dict[str, Any]) -> ast.Name:
    key = f"__v{len(names)}"
    names[key] = value
    return ast.Name(id=key, ctx=ast.Load())


def _bind(child: ast.expr, names: dict[str, Any]) -> ast.Name:
    return _bind_value(_value(child), names)


def _subst(node: ast.AST, names: dict[str, Any]) -> ast.AST:
    """A copy of `node` whose expression children are evaluated and replaced by names bound
    in `names` (Starred keeps its star; f-string structure is kept, its values bound). The
    two places compiled code would EXPAND a child — `*x` in a display and `**x` in a dict
    display — inspect the operand first (Codex WP04 c13): expansion iterates it, so any
    taint refuses, before the compiled container could absorb the set's order."""
    if isinstance(node, ast.Starred):
        operand = _value(node.value)
        if _holds_tainted(operand):
            _refuse_order(node, "starred expansion")
        return ast.Starred(value=_bind_value(operand, names), ctx=ast.Load())
    if isinstance(node, ast.Dict):
        keys: list[Any] = []
        values_out: list[ast.expr] = []
        for k, v in zip(node.keys, node.values):
            if k is None:                                      # `**x`: a set here is a TypeError → refused, not skipped
                unpacked = _value(v)
                if isinstance(unpacked, _TAINTED):
                    _refuse_order(node, "** expansion of an unordered value")
                keys.append(None)
                values_out.append(_bind_value(unpacked, names))   # a dict holding a set as a VALUE carries it (keys ordered)
            else:
                keys.append(_bind(k, names))
                values_out.append(_bind(v, names))
        return ast.Dict(keys=keys, values=values_out)
    if isinstance(node, ast.JoinedStr):
        values: list[ast.expr] = [_subst(v, names) if isinstance(v, ast.FormattedValue) else v   # type: ignore[misc]
                                  for v in node.values]
        return ast.JoinedStr(values=values)
    if isinstance(node, ast.FormattedValue):
        spec: Any = _subst(node.format_spec, names) if node.format_spec is not None else None
        return ast.FormattedValue(value=_bind(node.value, names), conversion=node.conversion, format_spec=spec)
    if isinstance(node, ast.keyword):
        return ast.keyword(arg=node.arg, value=_bind(node.value, names))
    fields: dict[str, Any] = {}
    for name, val in ast.iter_fields(node):
        if isinstance(val, ast.expr):
            fields[name] = _bind(val, names)
        elif isinstance(val, list):
            fields[name] = [_subst(v, names) if isinstance(v, (ast.Starred, ast.keyword))
                            else _bind(v, names) if isinstance(v, ast.expr) else v for v in val]
        elif isinstance(val, ast.keyword):
            fields[name] = _subst(val, names)
        else:
            fields[name] = val
    return type(node)(**fields)


def _eval_subst(rebuilt: ast.AST, names: dict[str, Any]) -> Any:
    expr = ast.Expression(body=rebuilt)                        # type: ignore[arg-type]
    ast.fix_missing_locations(expr)
    return _mark(eval(compile(expr, "<litscan>", "eval"), {"__builtins__": dict(_EVAL_BUILTINS)}, names))


def _call(node: ast.Call) -> Any:
    """Evaluate func, receiver and arguments first; inspect the VALUES for Tainted members
    against the closed consumer list; then invoke. Any exception in the invocation refuses."""
    if isinstance(node.func, ast.Attribute):
        receiver = _value(node.func.value)
        if _holds_tainted(receiver):
            _refuse_order(node, "a method on an unordered receiver")
        try:
            func = getattr(receiver, node.func.attr)
        except Exception as exc:  # an absent method is refused, never skipped
            raise ScanRefused(f"literal call at line {getattr(node, 'lineno', '?')} raised {type(exc).__name__}: {exc}") from exc
    else:
        func = _value(node.func)
    args: list[Any] = []
    for a in node.args:
        if isinstance(a, ast.Starred):
            unpacked = _value(a.value)
            if _holds_tainted(unpacked):
                _refuse_order(node, "unpacking an unordered value")
            args.extend(unpacked)
        else:
            args.append(_value(a))
    kwargs: dict[str, Any] = {}
    for k in node.keywords:
        v = _value(k.value)
        if k.arg is None:
            if _holds_tainted(v):
                _refuse_order(node, "unpacking an unordered value")
            kwargs.update(v)
        else:
            kwargs[k.arg] = v
    tainted_pos = [a for a in args if _holds_tainted(a)]
    tainted_kw = [k for k, v in kwargs.items() if _holds_tainted(v)]
    what = getattr(func, "__name__", type(func).__name__)
    if any(func is f for f in _SCALAR_CONSUMERS):
        pass
    elif any(func is f for f in _SORTING):
        if tainted_kw:
            _refuse_order(node, f"{what}() with an unordered value in {tainted_kw}")
        if any(not _direct_only(a) for a in tainted_pos):
            _refuse_order(node, f"{what}() over a value with an unordered value NESTED inside it")
        if tainted_pos and "key" in kwargs:
            _refuse_order(node, f"{what}() with a key: ties fall in hash order")
    elif any(func is f for f in _REWRAP):
        pass
    elif any(func is f for f in _RECONTAINER):
        if any(isinstance(a, _TAINTED) for a in args):
            _refuse_order(node, f"{what}() iterates an unordered value")
    elif tainted_pos or tainted_kw:                              # map/filter and every other callable or method
        _refuse_order(node, f"{what}() over an unordered value")
    try:
        return _mark(func(*args, **kwargs))
    except (MemoryError, RecursionError, OverflowError):
        raise
    except Exception as exc:  # a literal call that raises is refused, never skipped (fail closed)
        raise ScanRefused(f"literal call at line {getattr(node, 'lineno', '?')} raised {type(exc).__name__}: {exc}") from exc


def _value(node: ast.expr) -> Any:
    """Python's own value of a PURE node, computed bottom-up with every result marked."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return _EVAL_BUILTINS[node.id]
    if isinstance(node, ast.Call):
        return _call(node)
    if isinstance(node, ast.Slice):                            # cannot stand alone as an expression body
        bounds = [_value(b) if b is not None else None for b in (node.lower, node.upper, node.step)]
        if any(_holds_tainted(b) for b in bounds):
            _refuse_order(node, "Slice over an unordered value")
        return slice(*bounds)
    if isinstance(node, ast.IfExp):
        test = _value(node.test)
        if _holds_tainted(test):
            _refuse_order(node, "a conditional on an unordered value")
        return _value(node.body) if test else _value(node.orelse)
    if isinstance(node, ast.BoolOp):                           # the value is one operand; truthiness is order-free
        result: Any = None
        for v in node.values:
            result = _value(v)
            if (isinstance(node.op, ast.Or) and result) or (isinstance(node.op, ast.And) and not result):
                return result
        return result
    names: dict[str, Any] = {}
    rebuilt = _subst(node, names)                              # children evaluated; consumer checks BEFORE execution
    values = list(names.values())
    if isinstance(node, ast.Compare):                          # in / not in / == / != are order-free (any nesting)
        if any(_holds_tainted(v) for v in values) and not all(isinstance(op, _ORDER_INSENSITIVE_OPS) for op in node.ops):
            _refuse_order(node, "an ordering comparison over an unordered value")
    elif isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Slice, ast.Starred, ast.JoinedStr, ast.FormattedValue)):
        if any(_holds_tainted(v) for v in values):
            _refuse_order(node, f"{type(node).__name__} over an unordered value")
    elif isinstance(node, ast.Subscript) and values and (isinstance(values[0], _TAINTED)
                                                          or any(_holds_tainted(v) for v in values[1:])):
        _refuse_order(node, "subscripting an unordered value, or with one")
    return _eval_subst(rebuilt, names)                          # Tuple/List/Set/Dict/Subscript/Attribute: marked, taint carried


def _const_eval(node: ast.AST) -> Any:
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
    if not isinstance(node, ast.expr) or isinstance(node, ast.Starred) or not _is_pure(node):
        return _UNKNOWN                                         # a bare Starred cannot stand alone; its owner evaluates it
    try:
        return _value(node)
    except (MemoryError, RecursionError, OverflowError, ScanRefused):
        raise
    except (ValueError, TypeError, ArithmeticError, LookupError, AttributeError, SyntaxError):
        return _UNKNOWN             # not a constant (a Call that raised has already refused)


def _strings_from(value: Any, out: list[str]) -> None:
    """Every str the materialised value holds, recursively: containers, dict keys AND
    values; set members in sorted order (reproducible)."""
    if isinstance(value, (bytes, bytearray)):
        out.append(bytes(value).decode("utf-8", "replace"))
    elif isinstance(value, str):
        out.append(value)
    elif isinstance(value, (set, frozenset)):
        members: list[str] = []
        for v in value:
            _strings_from(v, members)
        out.extend(sorted(members))
    elif isinstance(value, dict):
        for k, v in value.items():
            _strings_from(k, out)
            _strings_from(v, out)
    elif isinstance(value, (tuple, list)):
        for v in value:
            _strings_from(v, out)


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


def _string_constants_inprocess(source: str) -> list[str]:
    tree = ast.parse(source)
    _refuse_shadowed_builtins(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        val = _const_eval(node)
        if val is _UNKNOWN:
            continue
        _strings_from(val, out)
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
