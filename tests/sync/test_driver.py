"""Tests for scripts/sync/driver.py (WP05 / T021).

Covers CLI surface, env-var resolution, validation errors, and dispatch
to run_cycle vs run_bootstrap.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.sync import driver as d
from scripts.sync.cycle import CycleConfig, CycleResult


def _ok_result(exit_code: int = 0) -> CycleResult:
    return CycleResult(
        success=exit_code == 0,
        exit_code=exit_code,
        tick_id="t",
        cycle_error=None,
        events_emitted={"auto_resolved": 0, "unsafe_to_auto_resolve": 0},
        layer_pointers_before={},
        layer_pointers_after={},
        duration_ms=0,
    )


# ===========================================================================
# Group 1 — Help
# ===========================================================================


class TestHelp:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            d.main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "scripts.sync.driver" in out


# ===========================================================================
# Group 2 — Recipient validation
# ===========================================================================


class TestRecipient:
    def test_missing_recipient_exits_3(self, monkeypatch, capsys):
        monkeypatch.delenv(d.WHATSAPP_RECIPIENT_ENV_VAR, raising=False)
        result = d.main([])
        assert result == 3
        assert "validation_error" in capsys.readouterr().err

    def test_cli_arg_wins_over_env(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+19998887777")
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main(["--whatsapp-recipient", "+15551234567"])
        assert captured["config"].whatsapp_recipient == "+15551234567"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+19998887777")
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main([])
        assert captured["config"].whatsapp_recipient == "+19998887777"

    def test_non_e164_exits_3(self, monkeypatch, capsys):
        monkeypatch.delenv(d.WHATSAPP_RECIPIENT_ENV_VAR, raising=False)
        result = d.main(["--whatsapp-recipient", "notaphone"])
        assert result == 3
        assert "E.164" in capsys.readouterr().err

    def test_e164_with_8_digits_accepted(self, monkeypatch):
        monkeypatch.delenv(d.WHATSAPP_RECIPIENT_ENV_VAR, raising=False)
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main(["--whatsapp-recipient", "+12345678"])
        assert captured["config"].whatsapp_recipient == "+12345678"


# ===========================================================================
# Group 3 — Cadence validation
# ===========================================================================


class TestCadence:
    def test_default_cadence(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        monkeypatch.delenv(d.ENV_CADENCE, raising=False)
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main([])
        assert captured["config"].cadence_seconds == d.CADENCE_DEFAULT

    def test_cadence_too_high_exits_3(self, monkeypatch, capsys):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        result = d.main(["--cadence-seconds", "700"])
        assert result == 3
        assert "out of range" in capsys.readouterr().err

    def test_cadence_too_low_exits_3(self, monkeypatch, capsys):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        result = d.main(["--cadence-seconds", "60"])
        assert result == 3
        assert "out of range" in capsys.readouterr().err

    def test_cadence_floor_accepted(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main(["--cadence-seconds", str(d.CADENCE_FLOOR)])
        assert captured["config"].cadence_seconds == d.CADENCE_FLOOR

    def test_cadence_ceiling_accepted(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main(["--cadence-seconds", str(d.CADENCE_CEILING)])
        assert captured["config"].cadence_seconds == d.CADENCE_CEILING

    def test_unparseable_env_cadence_exits_3(self, monkeypatch, capsys):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        monkeypatch.setenv(d.ENV_CADENCE, "abc")
        result = d.main([])
        assert result == 3
        assert "parse as int" in capsys.readouterr().err


# ===========================================================================
# Group 4 — Dispatch (bootstrap vs cycle)
# ===========================================================================


class TestDispatch:
    def test_default_dispatches_run_cycle(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        run_cycle_mock = MagicMock(return_value=_ok_result())
        run_bootstrap_mock = MagicMock(return_value=_ok_result())
        monkeypatch.setattr("scripts.sync.driver.run_cycle", run_cycle_mock)
        monkeypatch.setattr("scripts.sync.driver.run_bootstrap", run_bootstrap_mock)
        d.main([])
        assert run_cycle_mock.call_count == 1
        assert run_bootstrap_mock.call_count == 0

    def test_bootstrap_flag_dispatches_run_bootstrap(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        run_cycle_mock = MagicMock(return_value=_ok_result())
        run_bootstrap_mock = MagicMock(return_value=_ok_result())
        monkeypatch.setattr("scripts.sync.driver.run_cycle", run_cycle_mock)
        monkeypatch.setattr("scripts.sync.driver.run_bootstrap", run_bootstrap_mock)
        d.main(["--bootstrap"])
        assert run_bootstrap_mock.call_count == 1
        assert run_cycle_mock.call_count == 0


# ===========================================================================
# Group 5 — Dry-run propagation
# ===========================================================================


class TestDryRunPropagation:
    def test_dry_run_in_config(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main(["--dry-run"])
        assert captured["config"].dry_run is True

    def test_no_dry_run_flag_default_false(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        captured = {}
        def _spy(config):
            captured["config"] = config
            return _ok_result()
        monkeypatch.setattr("scripts.sync.driver.run_cycle", _spy)
        d.main([])
        assert captured["config"].dry_run is False


# ===========================================================================
# Group 6 — Exit-code passthrough
# ===========================================================================


class TestExitCodePassthrough:
    def test_run_cycle_exit_0_passes_through(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        monkeypatch.setattr(
            "scripts.sync.driver.run_cycle", lambda c: _ok_result(0)
        )
        assert d.main([]) == 0

    def test_run_cycle_exit_1_passes_through(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        monkeypatch.setattr(
            "scripts.sync.driver.run_cycle", lambda c: _ok_result(1)
        )
        assert d.main([]) == 1

    def test_run_cycle_exit_2_passes_through(self, monkeypatch):
        monkeypatch.setenv(d.WHATSAPP_RECIPIENT_ENV_VAR, "+15551234567")
        monkeypatch.setattr(
            "scripts.sync.driver.run_cycle", lambda c: _ok_result(2)
        )
        assert d.main([]) == 2
