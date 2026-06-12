"""Shared module-as-CLI runner for ``python3 -m scripts.deploy.lib.<module>``.

Each module that wants a CLI surface defines a `_FUNCS` mapping from
function-name strings to callables that take positional ``str`` args and
return a :class:`LibResult`. The module's ``__main__.py`` then calls
:func:`run` with that mapping plus ``sys.argv``.

Output convention (per ``contracts/deploy-library-api.md``):

* ``LibResult.summary`` → stdout line 1.
* ``LibResult.details`` as JSON → stdout line 2 when ``--json`` is set;
  otherwise omitted.
* Exit code: 0 when ``LibResult.ok is True``, else 1.

This is intentionally minimal — modules with richer argparse needs
(``applied``) can implement their own ``__main__`` body.
"""

from __future__ import annotations

import json
import sys
from typing import Callable, Mapping

from . import LibResult


def _usage(prog: str, funcs: Mapping[str, Callable[..., LibResult]]) -> str:
    names = ", ".join(sorted(funcs))
    return (
        f"usage: python3 -m {prog} <function> [args...] [--json]\n"
        f"  functions: {names}\n"
        f"  --json     also print LibResult.details as a single JSON line.\n"
    )


def run(
    funcs: Mapping[str, Callable[..., LibResult]],
    argv: list[str],
    prog: str,
) -> int:
    """Dispatch ``argv`` against ``funcs`` and print/exit appropriately.

    Returns an exit code rather than calling :func:`sys.exit` so callers
    can wrap this in tests if desired.
    """
    args = list(argv)
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(_usage(prog, funcs))
        return 0 if args else 2

    func_name = args[0]
    rest = args[1:]

    want_json = "--json" in rest
    if want_json:
        rest = [a for a in rest if a != "--json"]

    fn = funcs.get(func_name)
    if fn is None:
        sys.stderr.write(
            f"error: unknown function {func_name!r}\n{_usage(prog, funcs)}"
        )
        return 2

    try:
        result = fn(*rest)
    except TypeError as exc:
        # Most likely wrong argument count for the function.
        sys.stderr.write(f"error: {func_name}: {exc}\n")
        return 2

    if not isinstance(result, LibResult):
        sys.stderr.write(
            f"error: {func_name} returned {type(result).__name__}; expected LibResult\n"
        )
        return 2

    sys.stdout.write(result.summary + "\n")
    if want_json:
        sys.stdout.write(json.dumps(dict(result.details), default=str) + "\n")
    return 0 if result.ok else 1


__all__ = ["run"]
