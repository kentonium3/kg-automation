"""Tests for prescan DEFAULT_LOG_DIR (FR-006) and dedup import correctness (FR-011).

FR-006: DEFAULT_LOG_DIR must point to /home/kgale/second-brain/agents/logs
        (the Obsidian-synced vault), not the stale /home/claude/... path.

FR-011/SC-8: prescan.py historically used a bare ``from routing_log import
        RoutingLogReader`` that fails from any non-repo cwd even with
        PYTHONPATH=repo_root, silently dropping to dedup-disabled mode.
        The fix converts to a package-absolute import. Proof: from cwd=/tmp
        with only the repo root on PYTHONPATH, the import resolves and dedup
        is ACTIVE (no ImportError emitted, no "dedup-disabled" warning).

Module-level aliasing note
--------------------------
prescan.py's dedup block now does ``from scripts.inbox.routing_log import
RoutingLogReader``. Without aliasing, Python creates a SEPARATE module object
under ``scripts.inbox.routing_log`` alongside the one already loaded as
``routing_log`` (via conftest sys.path). This would break the existing
``monkeypatch.setattr("routing_log.DEFAULT_ROUTING_LOG_PATH", ...)`` pattern
used in test_prescan_parse_failure.py.

The ``sys.modules.setdefault`` call below ensures both aliases point to the
SAME module object, so monkeypatching via either name stays consistent.
It runs at collection time (before any test function executes run_prescan())
so the alias is in place before the local import inside run_prescan() fires.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level sys.modules aliasing (see docstring above).
# ---------------------------------------------------------------------------
import routing_log as _routing_log_mod  # noqa: E402 — must be after conftest sys.path
sys.modules.setdefault("scripts.inbox.routing_log", _routing_log_mod)

# ---------------------------------------------------------------------------
# Import prescan AFTER the alias is in place.
# ---------------------------------------------------------------------------
import prescan  # noqa: E402

from routing_log import RoutingLogWriter, RoutingLogReader  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VAULT_LOG_DIR = Path("/home/kgale/second-brain/agents/logs")


# ---------------------------------------------------------------------------
# T007 — DEFAULT_LOG_DIR points to vault (FR-006)
# ---------------------------------------------------------------------------


class TestDefaultLogDir:
    def test_default_log_dir_is_vault_path(self):
        """FR-006: log dir must be the kgale vault path, not the stale claude path."""
        assert prescan.DEFAULT_LOG_DIR == VAULT_LOG_DIR

    def test_default_log_dir_is_absolute(self):
        assert prescan.DEFAULT_LOG_DIR.is_absolute()

    def test_default_log_dir_does_not_use_home(self, monkeypatch):
        """DEFAULT_LOG_DIR is hardcoded absolute; HOME changes must not affect it."""
        monkeypatch.setenv("HOME", "/some/unrelated/home")
        # The constant is evaluated at module load (not lazily), so it is immune
        # to HOME changes.  Reimport is not needed; just verify the value.
        assert prescan.DEFAULT_LOG_DIR == VAULT_LOG_DIR

    def test_no_claude_path_in_log_dir(self):
        """Regression: /home/claude must not appear in DEFAULT_LOG_DIR."""
        assert "claude" not in str(prescan.DEFAULT_LOG_DIR)


# ---------------------------------------------------------------------------
# T008 — Package-absolute import resolves from /tmp cwd (FR-011 / SC-8)
# ---------------------------------------------------------------------------


class TestDedupImportFromTmp:
    """FR-011 acceptance proofs.

    Each test uses subprocess to create an environment that only has the repo
    root on PYTHONPATH and cwd=/tmp, mirroring the cron runtime.
    """

    def _run(self, script: str) -> subprocess.CompletedProcess:
        env = {
            "PYTHONPATH": str(REPO_ROOT),
            "PATH": os.environ.get("PATH", ""),
        }
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            cwd="/tmp",
            env=env,
            capture_output=True,
            text=True,
        )

    def test_package_absolute_import_resolves_from_tmp_cwd(self):
        """Package-absolute import resolves with only repo root on PYTHONPATH.

        This is the SC-8 acceptance proof.  The import must succeed and the
        reader must be instantiable, demonstrating dedup is ACTIVE.
        """
        result = self._run("""\
            from scripts.inbox.routing_log import RoutingLogReader
            r = RoutingLogReader()
            print("dedup-active")
        """)
        assert result.returncode == 0, (
            "Package-absolute import failed from /tmp with only repo root on "
            f"PYTHONPATH.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "dedup-active" in result.stdout

    def test_bare_import_fails_without_scripts_inbox_on_sys_path(self):
        """Negative proof: bare import fails when only repo root is on PYTHONPATH.

        This documents WHY the package-absolute form is required.  If this test
        ever starts passing it means the bare import now works (probably because
        scripts/inbox/ ended up on sys.path by another route) — investigate.
        """
        result = self._run("""\
            try:
                from routing_log import RoutingLogReader
                print("bare-import-worked")
            except ImportError:
                print("bare-import-failed")
        """)
        assert "bare-import-failed" in result.stdout or result.returncode != 0, (
            "Expected bare import to fail from /tmp without scripts/inbox on "
            "sys.path, but it succeeded.  Dedup may have been active by accident "
            "rather than by design; investigate the PYTHONPATH of the cron job."
        )

    def test_no_dedup_disabled_warning_when_import_resolves(self):
        """Simulates prescan's ImportError handler: dedup-disabled must not fire."""
        result = self._run("""\
            import sys
            dedup_disabled = False
            try:
                from scripts.inbox.routing_log import RoutingLogReader
            except ImportError:
                dedup_disabled = True
            if dedup_disabled:
                print("DEDUP-DISABLED")
                sys.exit(1)
            print("DEDUP-ACTIVE")
        """)
        assert result.returncode == 0, (
            f"Import raised ImportError from /tmp.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "DEDUP-ACTIVE" in result.stdout
        assert "DEDUP-DISABLED" not in result.stdout


# ---------------------------------------------------------------------------
# T009 — append_routing_entry.py import alignment (FR-011)
# ---------------------------------------------------------------------------


class TestAppendRoutingEntryImport:
    def test_append_routing_entry_importable_with_repo_root_on_pythonpath(self):
        """append_routing_entry.py must import cleanly with only repo root on PYTHONPATH."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import scripts.inbox.append_routing_entry; print('ok')",
            ],
            cwd="/tmp",
            env={
                "PYTHONPATH": str(REPO_ROOT),
                "PATH": os.environ.get("PATH", ""),
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"append_routing_entry import failed.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "ok" in result.stdout


# ---------------------------------------------------------------------------
# T010 — Frontmatter-only dedup: ledger is sole guard (H1 contract)
# ---------------------------------------------------------------------------


class TestFrontmatterOnlyDedup:
    """H1: a note with missing/unknown status is treated as unprocessed.

    The routing ledger is the sole dedup guard for such notes.
    - With a ledger entry → the note is skipped (deduped).
    - Without a ledger entry → the note is re-evaluated (handed to the agent).

    This documents the cutover risk that WP05 mitigates atomically:
    during the transition window where old notes lack processed/unprocessed
    status, only the ledger prevents duplicate routing.
    """

    _NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_missing_status_classifies_as_unknown_treated_as_unprocessed(
        self, tmp_path: Path
    ):
        """Notes with missing status frontmatter → unknown-treated-as-unprocessed."""
        note = tmp_path / "capture.md"
        note.write_text("---\ndate: 2026-01-01\n---\nBody.\n", encoding="utf-8")
        inf = prescan.classify_file(note, self._NOW)
        assert inf.classification == "unknown-treated-as-unprocessed"
        assert inf.parse_failure_reason is None

    def test_ledger_deduplicates_unknown_status_note(self, tmp_path: Path):
        """With a ledger entry the note is in routed_names → would be deduped."""
        note = tmp_path / "capture.md"
        note.write_text("---\ndate: 2026-01-01\n---\nBody.\n", encoding="utf-8")
        log = tmp_path / "routing.jsonl"
        writer = RoutingLogWriter(log)
        writer.append(filename=note.name, issue_number=42)

        reader = RoutingLogReader(log)
        routed = reader.routed_filenames()
        assert note.name in routed, (
            "Ledger entry not found; dedup would silently re-route the note"
        )

    def test_empty_ledger_passes_note_through_for_re_evaluation(
        self, tmp_path: Path
    ):
        """Without a ledger entry the note is NOT in routed_names → re-evaluated."""
        note = tmp_path / "capture.md"
        note.write_text("---\ndate: 2026-01-01\n---\nBody.\n", encoding="utf-8")
        empty_log = tmp_path / "routing.jsonl"  # never created

        reader = RoutingLogReader(empty_log)
        routed = reader.routed_filenames()
        assert note.name not in routed, (
            "Note appeared in routed set from an empty/missing ledger"
        )
