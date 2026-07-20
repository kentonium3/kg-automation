"""Repo-wide guard: every OpenClaw *binary* invocation routes through the seam (#811).

On office2 every runtime consumer runs PATH-less (systemd-user units, cron,
non-login ``sg docker -c``), so a hardcoded ``/home/claude/.local/bin/openclaw``
(brittle: breaks on the next relocation) or a bare ``openclaw`` argv[0] (breaks
PATH-lessly, silently) is a regression. The single source of truth is
``scripts/common/openclaw_bin.py`` (``openclaw_bin()`` / ``openclaw_argv()``); the
shell arm is the ``: "${OPENCLAW_BIN:=…}"`` convention.

This is the durable regression fence (mirrors ``tests/common/test_no_bare_astimezone.py``).
It applies two complementary rules over ``scripts/**`` (excluding the seam, test
files, and the documented allowlist):

* **Rule 1 (path literal, .py + .sh):** no line may contain the absolute
  ``/home/claude/.local/bin/openclaw`` or the removed ``/usr/bin/openclaw`` —
  except the shell ``${OPENCLAW_BIN:=…}``/``:-…}`` convention line. (All
  explanatory comments/docstrings were scrubbed to reference the seam, so this
  is false-positive-free.)
* **Rule 2 (bare argv[0], .py, AST):** no ``subprocess.{run,Popen,call,
  check_call,check_output}`` call may have an argv whose first element resolves
  to a bare ``"openclaw"`` or an openclaw path — inline (``["openclaw", …]``) or
  via a module/local variable (``_OPENCLAW = "openclaw"``; ``cmd = ["openclaw",
  …]; run(cmd)``). Variable resolution is intentionally module-wide (last write
  wins) so a guard errs toward catching. Non-argv[0] uses (npm package name,
  ``OPENCLAW_SERVICE_NAMES`` set) are naturally ignored.

**Known limitations** (documented, not enforced here):

* A *function-parameter default* (``def f(bin="openclaw"): subprocess.run([bin,
  …])``) is beyond a static guard's reach. The heartbeat-gate escalator is that
  shape; its regression fence is the targeted assertion in
  ``scripts/openclaw/heartbeat_gate/tests/test_escalator.py`` (``cmd[0] ==
  openclaw_bin()``), not this guard.
* A **shell** bare ``openclaw <subcmd>`` (no path literal) is not caught — Rule 1
  (.sh) matches only absolute path literals. The recurring PATH-less runtime
  shell callers (``audit.sh``) use the ``${OPENCLAW_BIN:=…}`` convention; the
  remaining bare-``openclaw`` ``.sh`` instances are out-of-scope one-shot
  retirement/install scripts that run under felix-deployer's PATH.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"

_PATH_LITERALS = ("/home/claude/.local/bin/openclaw", "/usr/bin/openclaw")

#: The seam itself (defines the default) + the documented bare-``openclaw``
#: exceptions: felix-deployer PATH-safe callers and the two already-applied
#: one-shot cron deploy scripts. Repo-relative POSIX paths.
_ALLOWLIST = frozenset(
    {
        "scripts/common/openclaw_bin.py",
        "scripts/deploy/lib/cron.py",
        "scripts/deploy/deploy-deterministic-monitoring-checks.py",
        "scripts/deploy/reschedule-felix-admin-habits-weekly-cron.py",
        "scripts/deploy/restore-tz-on-habits-weekly-report-cron.py",
    }
)

_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def _is_test_path(rel_posix: str) -> bool:
    return "/tests/" in rel_posix or Path(rel_posix).name.startswith("test_") or Path(
        rel_posix
    ).name == "conftest.py"


def _excluded(rel_posix: str) -> bool:
    return rel_posix in _ALLOWLIST or _is_test_path(rel_posix)


def _iter_files(suffix: str) -> list[Path]:
    return sorted(
        p
        for p in _SCRIPTS_ROOT.rglob(f"*{suffix}")
        if not _excluded(p.relative_to(_REPO_ROOT).as_posix())
    )


def _is_openclaw_binary_str(value: object) -> bool:
    """True if ``value`` names the openclaw binary when used as argv[0]."""
    if not isinstance(value, str):
        return False
    return value == "openclaw" or value.rstrip("/").endswith("/openclaw")


# ---------------------------------------------------------------------------
# Rule 1 — path literal (.py + .sh)
# ---------------------------------------------------------------------------


def _is_shell_convention_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(': "${OPENCLAW_BIN:') or "${OPENCLAW_BIN:=" in line or (
        "${OPENCLAW_BIN:-" in line
    )


def _path_literal_findings(rel_posix: str, source: str) -> list[str]:
    findings: list[str] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if not any(lit in line for lit in _PATH_LITERALS):
            continue
        if rel_posix.endswith(".sh") and _is_shell_convention_line(line):
            continue
        findings.append(
            f"{rel_posix}:{lineno}: hardcoded openclaw path literal — resolve via "
            f"the seam (scripts/common/openclaw_bin.py) or the ${{OPENCLAW_BIN:=…}} "
            f"shell convention"
        )
    return findings


# ---------------------------------------------------------------------------
# Rule 2 — bare argv[0] (.py, AST)
# ---------------------------------------------------------------------------


def _base_name(node: ast.AST) -> str | None:
    """Return the leftmost Name id of an attribute/name chain (e.g. subprocess)."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _list_first_elt(node: ast.AST) -> ast.AST | None:
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        return node.elts[0]
    return None


def _collect_subprocess_refs(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return (module aliases bound to ``subprocess``, directly-imported func names).

    Handles ``import subprocess`` / ``import subprocess as sp`` (alias → matched
    as the receiver of ``.run``/…) and ``from subprocess import run, Popen``
    (name → matched as a bare call). Closes the alias/direct-import blind spot.
    """
    aliases: set[str] = set()
    direct: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    aliases.add(alias.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_FUNCS:
                    direct.add(alias.asname or alias.name)
    return aliases, direct


def _collect_name_bindings(tree: ast.AST) -> tuple[dict[str, object], dict[str, ast.AST]]:
    """Module-wide (last-write-wins) maps: name→str value, name→list-first-elt node."""
    str_vars: dict[str, object] = {}
    list_first: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if isinstance(node.value, ast.Constant):
                str_vars[target.id] = node.value.value
            first = _list_first_elt(node.value)
            if first is not None:
                list_first[target.id] = first
    return str_vars, list_first


def _argv0_is_openclaw(
    first_arg: ast.AST,
    str_vars: dict[str, object],
    list_first: dict[str, ast.AST],
) -> bool:
    # subprocess.run("…string…", shell=True) — check the first shell token
    if isinstance(first_arg, ast.Constant):
        value = first_arg.value
        if isinstance(value, str) and value.split():
            return _is_openclaw_binary_str(value.split()[0])
        return False
    # subprocess.run(["openclaw", …]) / (( "openclaw", … ))
    elt0 = _list_first_elt(first_arg)
    if elt0 is not None:
        if isinstance(elt0, ast.Constant) and _is_openclaw_binary_str(elt0.value):
            return True
        if isinstance(elt0, ast.Name) and _is_openclaw_binary_str(str_vars.get(elt0.id)):
            return True
        return False
    # subprocess.run(CMD)  where CMD is a Name bound to a list or the binary string
    if isinstance(first_arg, ast.Name):
        if _is_openclaw_binary_str(str_vars.get(first_arg.id)):
            return True
        bound_first = list_first.get(first_arg.id)
        if isinstance(bound_first, ast.Constant) and _is_openclaw_binary_str(
            bound_first.value
        ):
            return True
        if isinstance(bound_first, ast.Name) and _is_openclaw_binary_str(
            str_vars.get(bound_first.id)
        ):
            return True
    return False


def _bare_argv_findings(rel_posix: str, source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    str_vars, list_first = _collect_name_bindings(tree)
    aliases, direct = _collect_subprocess_refs(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # subprocess.run(...) / sp.run(...)  — attribute call on a subprocess alias
        is_attr_call = (
            isinstance(func, ast.Attribute)
            and func.attr in _SUBPROCESS_FUNCS
            and _base_name(func) in aliases
        )
        # run(...) / check_output(...)  — a name directly imported from subprocess
        is_direct_call = isinstance(func, ast.Name) and func.id in direct
        if not (is_attr_call or is_direct_call):
            continue
        if not node.args:
            continue
        if _argv0_is_openclaw(node.args[0], str_vars, list_first):
            findings.append(
                f"{rel_posix}:{node.lineno}: subprocess argv[0] is a bare/hardcoded "
                f"openclaw — use openclaw_bin()/openclaw_argv() from the seam"
            )
    return findings


# ---------------------------------------------------------------------------
# Full-tree scan
# ---------------------------------------------------------------------------


def _scan_all() -> list[str]:
    findings: list[str] = []
    for path in _iter_files(".py"):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        findings.extend(_path_literal_findings(rel, src))
        findings.extend(_bare_argv_findings(rel, src))
    for path in _iter_files(".sh"):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        findings.extend(_path_literal_findings(rel, path.read_text(encoding="utf-8")))
    return findings


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_all_openclaw_binary_callers_route_through_seam():
    findings = _scan_all()
    assert not findings, (
        "OpenClaw binary invocation not routed through the seam (#811). Use "
        "scripts/common/openclaw_bin.py (openclaw_bin()/openclaw_argv()) or the "
        "${OPENCLAW_BIN:=…} shell convention, or add a documented allowlist entry:\n  "
        + "\n  ".join(findings)
    )


def test_scan_actually_covers_files():
    """Guard the guard: a broken glob that scanned nothing would be vacuously green."""
    rels = {p.relative_to(_REPO_ROOT).as_posix() for p in _iter_files(".py")}
    shels = {p.relative_to(_REPO_ROOT).as_posix() for p in _iter_files(".sh")}
    assert "scripts/trust/cron_drift_detector.py" in rels
    assert "scripts/sync/send_whatsapp.py" in rels
    assert "scripts/office2/security-monitor/audit.sh" in shels
    # Exclusions actually exclude.
    assert "scripts/common/openclaw_bin.py" not in rels
    assert "scripts/deploy/lib/cron.py" not in rels


# --- positive controls (a reintroduced regression MUST fire) ---------------


def test_positive_inline_list():
    src = "import subprocess\nsubprocess.run(['openclaw', 'cron', 'list'])\n"
    assert _bare_argv_findings("x.py", src)


def test_positive_module_var_indirection():
    src = "import subprocess\n_OPENCLAW = 'openclaw'\nsubprocess.run([_OPENCLAW, 'x'])\n"
    assert _bare_argv_findings("x.py", src)


def test_positive_local_list_var_indirection():
    src = (
        "import subprocess\n"
        "def f():\n"
        "    cmd = ['openclaw', 'system', 'event']\n"
        "    subprocess.run(cmd)\n"
    )
    assert _bare_argv_findings("x.py", src)


def test_positive_subprocess_alias_import():
    src = "import subprocess as sp\nsp.run(['openclaw', 'cron', 'list'])\n"
    assert _bare_argv_findings("x.py", src)


def test_positive_from_subprocess_direct_import():
    src = "from subprocess import run\nrun(['openclaw', 'agent'])\n"
    assert _bare_argv_findings("x.py", src)


def test_positive_absolute_path_argv():
    src = "import subprocess\nsubprocess.run(['/home/claude/.local/bin/openclaw', 'x'])\n"
    assert _bare_argv_findings("x.py", src)


def test_positive_shell_true_string():
    src = "import subprocess\nsubprocess.run('/usr/bin/openclaw cron list', shell=True)\n"
    assert _bare_argv_findings("x.py", src)


def test_positive_path_literal_in_py():
    src = 'X = "/home/claude/.local/bin/openclaw"\n'
    assert _path_literal_findings("x.py", src)


def test_positive_path_literal_in_sh_noncomment():
    src = "/home/claude/.local/bin/openclaw cron list\n"
    assert _path_literal_findings("x.sh", src)


# --- negative controls (legitimate code must NOT fire) ---------------------


def test_negative_seam_helpers():
    src = (
        "import subprocess\n"
        "from scripts.common.openclaw_bin import openclaw_argv, openclaw_bin\n"
        "subprocess.run(openclaw_argv('cron', 'list'))\n"
        "subprocess.run([openclaw_bin(), 'agent'])\n"
    )
    assert _bare_argv_findings("x.py", src) == []


def test_negative_npm_package_name_at_index_2():
    src = "import subprocess\nsubprocess.run(['npm', 'install', 'openclaw'])\n"
    assert _bare_argv_findings("x.py", src) == []


def test_negative_service_name_set():
    src = "OPENCLAW_SERVICE_NAMES = frozenset({'openclaw', 'openclaw-gateway'})\n"
    assert _bare_argv_findings("x.py", src) == []


def test_negative_shell_convention_line():
    src = ': "${OPENCLAW_BIN:=/home/claude/.local/bin/openclaw}"\n'
    assert _path_literal_findings("x.sh", src) == []


def test_negative_dollar_openclaw_bin_call():
    src = '"$OPENCLAW_BIN" cron list --json\n'
    assert _path_literal_findings("x.sh", src) == []
