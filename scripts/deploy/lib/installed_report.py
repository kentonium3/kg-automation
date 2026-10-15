"""The installed-file report: how a deploy tells felix-deployer what it put on
the host (kentonium3/kg-automation#1072).

felix-deployer used to infer which security-monitor baselines a deploy would
drift only from the files changed in the git range it pulled. Drift comes from
what is installed, so a deploy that re-installed files committed earlier
(deploy 0029) ended in a false ``unexpected_drift`` alert. Deploy-library
installers now report what they actually wrote. felix-deployer maps those
files to baselines and expects that drift.

This module is the only place that names the channel, writes it, or reads it.
Contract: ``kitty-specs/deploy-runtime-installed-report-01M4ZP8E/contracts/
installed-report.md``.

* Channel: the environment variable :data:`ENV_VAR` names a file.
  ``scripts/deploy/lib/apply.py`` sets it for an entrypoint's ``--apply``
  only, and removes it everywhere else.
* Format: JSON Lines, one ``{"source": abs, "dest": abs}`` object per changed
  file, appended after the file has landed.
* Producer :func:`record_installed` is advisory. A write failure never fails
  an install; it prints one :data:`WRITE_FAILED_MARKER` line to stderr, the
  only output this library produces.
* Reader :func:`read_report` fails closed and wholesale. Any irregularity
  rejects the entire report, because the report can only ever *widen* what the
  security monitor tolerates, and a partial, suspicious report must not.

Trust model: the entrypoint runs as the same user and is PR-reviewed. This
guards against bugs, not a malicious entrypoint (which could already write
anything that user can).
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

ENV_VAR = "FELIX_DEPLOY_INSTALLED_REPORT"
WRITE_FAILED_MARKER = "FELIX_DEPLOY_INSTALLED_REPORT_WRITE_FAILED"
MAX_BYTES = 1024 * 1024
MAX_ENTRIES = 10_000


def record_installed(source: os.PathLike | str, dest: os.PathLike | str) -> None:
    """Append one entry for a file whose bytes were just written to the host.

    Call only after the file has landed (e.g. after ``os.replace``), and only
    for files whose bytes changed. A no-op when :data:`ENV_VAR` is unset.
    Never raises.
    """
    target = os.environ.get(ENV_VAR, "")
    if not target:
        return
    try:
        line = json.dumps({"source": str(Path(source).resolve()), "dest": str(Path(dest).resolve())})
        # O_NONBLOCK so a FIFO with no reader fails (ENXIO) instead of hanging
        # the install; O_NOFOLLOW so a planted symlink is refused.
        fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("report target is not a regular file")
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - advisory; never fail an install
        try:
            print(f"{WRITE_FAILED_MARKER}: {type(exc).__name__}: {exc}", file=sys.stderr)
        except Exception:  # pragma: no cover - stderr itself unusable
            pass


def _result(*, entries=None, rejected=False, missing=False, warnings=None) -> dict[str, Any]:
    return {"entries": entries or [], "rejected": rejected, "missing": missing, "warnings": warnings or []}


def _reject(why: str) -> dict[str, Any]:
    return _result(rejected=True, warnings=[why])


def read_report(path: os.PathLike | str) -> dict[str, Any]:
    """Read a report file, failing closed and wholesale. Never raises, never blocks.

    Returns ``{"entries", "rejected", "missing", "warnings"}``. A missing file is
    ``missing`` (the entrypoint reported nothing), not an error. Anything else
    irregular, such as a symlink, FIFO, directory, oversized file, invalid
    UTF-8, a bad line, a relative path or too many entries, rejects the whole
    report.
    """
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return _result(missing=True)
    except OSError as exc:
        return _reject(f"cannot open report: {type(exc).__name__}: {exc}")
    try:
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                return _reject("report is not a regular file")
            chunks: list[bytes] = []
            total = 0
            while total <= MAX_BYTES:
                chunk = os.read(fd, MAX_BYTES + 1 - total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        except OSError as exc:
            return _reject(f"cannot read report: {type(exc).__name__}: {exc}")
    finally:
        os.close(fd)
    if total > MAX_BYTES:
        return _reject(f"report exceeds {MAX_BYTES} bytes")
    try:
        text = b"".join(chunks).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return _reject(f"report is not valid UTF-8: {exc}")

    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        # split("\n"), not splitlines(): only a newline separates records
        # (splitlines also breaks on \x85, \u2028, ... inside a line).
        for n, raw in enumerate(text.split("\n"), start=1):
            line = raw[:-1] if raw.endswith("\r") else raw
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                return _reject(f"line {n} is not a JSON object")
            src, dst = obj.get("source"), obj.get("dest")
            if not isinstance(src, str) or not isinstance(dst, str):
                return _reject(f"line {n}: source and dest must be strings")
            if "\x00" in src or "\x00" in dst:
                return _reject(f"line {n}: NUL byte in a path")
            if not os.path.isabs(src) or not os.path.isabs(dst):
                return _reject(f"line {n}: source and dest must be absolute")
            key = (src, dst)
            if key in seen:
                continue  # duplicates do not count against MAX_ENTRIES
            seen.add(key)
            entries.append({"source": src, "dest": dst})
            if len(entries) > MAX_ENTRIES:
                return _reject(f"report has more than {MAX_ENTRIES} entries")
    except Exception as exc:  # noqa: BLE001 - e.g. RecursionError on deep nesting; never raise
        return _reject(f"unparseable report: {type(exc).__name__}")
    return _result(entries=entries)


__all__ = ["ENV_VAR", "MAX_BYTES", "MAX_ENTRIES", "WRITE_FAILED_MARKER", "read_report", "record_installed"]
