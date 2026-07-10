"""Tests for audit.sh → alert_bus.sh migration (WP04 / T016).

These assert the audit script's *notification shape* rather than running the
full audit (which probes live office2 system state). Two layers:

1. Static text assertions on ``audit.sh`` — the hardcoded topic and the raw
   ``curl``/``ntfy.sh`` block are gone (SC-006), and the felix-alert shim is
   invoked instead.
2. A behavioral bash-level assertion that the emit call stays *non-fatal*: even
   when the shim path is missing / returns non-zero, the surrounding
   ``… || true`` guard keeps the caller's control flow intact.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_SH = REPO_ROOT / "scripts" / "office2" / "security-monitor" / "audit.sh"


def _audit_text() -> str:
    return AUDIT_SH.read_text(encoding="utf-8")


class TestAuditScriptStatic:
    def test_audit_script_exists(self):
        assert AUDIT_SH.is_file(), f"audit.sh not found at {AUDIT_SH}"

    def test_no_hardcoded_topic_remains(self):
        text = _audit_text()
        # The old private topic must not appear anywhere in the script.
        assert "felix-office2-k9x4m2" not in text
        # No assignment of a topic variable is reintroduced.
        assert "NTFY_TOPIC=" not in text

    def test_no_raw_curl_ntfy_block_remains(self):
        text = _audit_text()
        # SC-006: no migrated emitter contains its own curl/ntfy code.
        assert "ntfy.sh/" not in text
        assert "curl" not in text

    def test_invokes_alert_bus_shim(self):
        text = _audit_text()
        assert "alert_bus.sh" in text
        assert 'emit' in text
        assert '--source "security-monitor/audit"' in text
        assert '--title "Felix Security Alert — office2"' in text

    def test_emit_guarded_non_fatal(self):
        text = _audit_text()
        # The emit invocation is followed by a `|| true` guard so a delivery
        # failure can never propagate a non-zero status into audit control flow.
        assert "|| true" in text

    def test_severity_is_always_error(self):
        text = _audit_text()
        # Security findings always map to `error` (ntfy Priority: high), matching
        # the old always-"Priority: high" path. No warn/error threshold branching.
        assert 'SEVERITY="error"' in text
        assert 'SEVERITY="warn"' not in text
        # The always-error rationale is documented in a comment.
        assert "always `error`" in text


class TestAuditEmitNonFatal:
    """Prove the emit line stays non-fatal even when the shim fails.

    Rather than run the full audit (live system probes), we exercise the exact
    guarded-invocation *shape* the script uses, with the shim stubbed to fail.
    """

    def _run_guarded_emit(self, alert_bus: str) -> subprocess.CompletedProcess:
        # Mirror the audit.sh construct exactly: an *external* command
        # (``"$ALERT_BUS" …``) guarded by ``&& log … || true`` inside a
        # non-`set -e` shell, followed by a sentinel that must run. Because the
        # shim is an external process, its exit status cannot abort the parent;
        # ``|| true`` then neutralizes any non-zero status for control flow.
        script = (
            f'ALERT_BUS="{alert_bus}"\n'
            '"$ALERT_BUS" emit --source x >/dev/null 2>&1 && echo emit-ok || true\n'
            "echo REACHED_END\n"
        )
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_success_path_reaches_end(self):
        # `/usr/bin/true` (or `true`) stands in for a shim that exits 0.
        proc = self._run_guarded_emit(alert_bus="true")
        assert proc.returncode == 0
        assert "REACHED_END" in proc.stdout

    def test_failure_path_still_reaches_end(self):
        # A shim that exits non-zero (`false`) is swallowed by `|| true`.
        proc = self._run_guarded_emit(alert_bus="false")
        assert proc.returncode == 0
        assert "REACHED_END" in proc.stdout

    def test_missing_shim_path_still_reaches_end(self):
        # A non-existent shim path (exit 127) must also be swallowed.
        proc = self._run_guarded_emit(alert_bus="/nonexistent/alert_bus.sh")
        assert proc.returncode == 0
        assert "REACHED_END" in proc.stdout
