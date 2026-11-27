"""Tests for the #1146 announce-agent tool-deny deploy entrypoint and manifest.

Offline: the openclaw CLI is a stateful in-process fake over a temporary
``openclaw.json``; the gateway identity, journal, clock and state directory
are injected. Nothing here touches office2, systemd or any path outside tmp.

Every refusal is paired with a passing control on the same fixture.
"""

from __future__ import annotations

import copy
import fnmatch
import hashlib
import importlib.util
import json
import os
import stat
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "scripts" / "deploy" / "deploy-announce-agent-tool-deny.py"
_spec = importlib.util.spec_from_file_location("deploy_announce_agent_tool_deny", _PATH)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

MANIFEST_PATH = _ROOT / "deploys" / "queued" / "announce-agent-tool-deny.yaml"
SCHEMA_PATH = _ROOT / "deploys" / "schema" / "manifest-v1.schema.json"

TARGETS = ("felix-admin-capture", "felix-admin-escalation", "felix-admin-habits")
NON_TARGETS = ("main", "felix-admin-calendar", "felix-admin-tasker")
DENY = ["conversations_*", "sessions_*", "message", "automations"]
T0 = datetime(2026, 11, 27, 21, 0, 0, tzinfo=UTC)

BASE_TOOLS = [
    "exec", "process", "read", "write", "conversations_list", "conversations_send",
    "sessions_list", "sessions_spawn", "automations", "gateway",
]


def base_config() -> dict[str, Any]:
    """Live shape (keys only, no secrets): agents.entries.<id>, no per-agent tools."""

    def entry(name: str, skills: list[str]) -> dict[str, Any]:
        return {
            "agentDir": f"/home/claude/.openclaw/agents/{name}/agent",
            "model": "anthropic/claude-haiku-4-5",
            "name": name,
            "skills": skills,
            "workspace": f"/data/services/openclaw/{name}",
        }

    return {
        "agents": {
            "defaults": {"workspace": "/data/services/openclaw/data"},
            "ownership": "explicit",
            "entries": {
                "main": entry("main", []),
                "felix-admin-calendar": entry("felix-admin-calendar", ["calendar"]),
                "felix-admin-capture": entry("felix-admin-capture", ["vikunja_api", "github"]),
                "felix-admin-escalation": entry("felix-admin-escalation", ["escalation"]),
                "felix-admin-habits": entry("felix-admin-habits", ["vikunja_api"]),
                "felix-admin-tasker": entry("felix-admin-tasker", ["vikunja_api"]),
            },
        },
        "tools": {"profile": "coding", "web": {"search": {"enabled": True}}},
        "gateway": {"auth": {"token": "REDACTED"}},
    }


def sha(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# The fake world.
# --------------------------------------------------------------------------- #
@dataclass
class World:
    tmp: Path
    config: dict[str, Any] = field(default_factory=base_config)
    pid: str = "153444"
    started: str = "Mon 2026-11-23 20:07:05 UTC"
    now: datetime = T0
    journal_lines: list[tuple[datetime, str]] = field(default_factory=list)
    after_calls: list[str] = field(default_factory=list)
    patch_calls: list[dict[str, Any]] = field(default_factory=list)
    # Failure injection.
    touch_main_on_patch: bool = False
    change_pid_on_patch: bool = False
    emit_ack: bool = True
    emit_restart_required: bool = False
    validate_fails: bool = False
    stale_effective: bool = False
    no_sessions: bool = False

    def __post_init__(self) -> None:
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.cfg_path = self.tmp / "openclaw.json"
        self.flush()

    def flush(self) -> None:
        self.cfg_path.write_text(json.dumps(self.config, indent=2))

    @property
    def entries(self) -> dict[str, Any]:
        return self.config["agents"]["entries"]

    @property
    def real_patches(self) -> list[dict[str, Any]]:
        return [p for p in self.patch_calls if not p["dry_run"]]

    # -- the CLI ------------------------------------------------------------
    def run(self, argv: list[str], input_text: str | None, timeout: float) -> tuple[int, str, str]:
        args = argv[1:]
        if args[:2] == ["config", "validate"]:
            return (1, "", "invalid") if self.validate_fails else (0, "", "")
        if args[:2] == ["config", "file"]:
            return 0, json.dumps({"path": str(self.cfg_path)}), ""
        if args[:2] == ["config", "get"]:
            return self._get(args[2])
        if args[:2] == ["config", "patch"]:
            return self._patch(args[2:], input_text or "")
        if args[:1] == ["sessions"]:
            if self.no_sessions:
                return 0, json.dumps({"sessions": []}), ""
            agent = args[args.index("--agent") + 1]
            return 0, json.dumps({"sessions": [{"key": f"agent:{agent}:main"}]}), ""
        if args[:3] == ["gateway", "call", "tools.effective"]:
            key = json.loads(args[args.index("--params") + 1])["sessionKey"]
            agent = key.split(":")[1]
            deny = [] if self.stale_effective else (self.entries[agent].get("tools", {}).get("deny", []))
            tools = [t for t in BASE_TOOLS if not any(fnmatch.fnmatchcase(t, d) for d in deny)]
            return 0, json.dumps({"groups": [{"id": "core", "tools": [{"id": t} for t in tools]}]}), ""
        return 127, "", f"fake: unhandled {args}"

    def _get(self, path: str) -> tuple[int, str, str]:
        node: Any = self.config
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                env = {"ok": False, "error": {"type": "cli_error", "message": f"Config path is valid but unset: {path}."}}
                return 1, json.dumps(env), ""
            node = node[part]
        return 0, json.dumps(node), ""

    def _patch(self, args: list[str], stdin: str) -> tuple[int, str, str]:
        dry = "--dry-run" in args
        replace = [args[i + 1] for i, a in enumerate(args) if a == "--replace-path"]
        patch = json.loads(stdin)
        self.patch_calls.append({"dry_run": dry, "patch": patch, "replace": replace})
        if dry:
            return 0, json.dumps({"ok": True}), ""
        self._merge(self.config, patch, "", replace)
        if self.touch_main_on_patch:
            self.entries["main"]["tools"] = {"deny": ["exec"]}
        self.flush()
        if self.change_pid_on_patch:
            self.pid = "999999"
        if self.emit_ack:
            self.journal_lines.append((self.now, "[reload] config hot reload applied (agents.entries.felix-admin-capture.tools.deny)"))
        if self.emit_restart_required:
            self.journal_lines.append((self.now, "[reload] config change requires gateway restart (agents.entries)"))
        return 0, "", ""

    def _merge(self, dst: dict[str, Any], src: dict[str, Any], prefix: str, replace: list[str]) -> None:
        for k, v in src.items():
            path = f"{prefix}.{k}" if prefix else k
            if v is None:
                dst.pop(k, None)
            elif path in replace or not isinstance(v, dict) or not isinstance(dst.get(k), dict):
                dst[k] = copy.deepcopy(v)
            else:
                self._merge(dst[k], v, path, replace)

    # -- effects ------------------------------------------------------------
    def effects(self, **overrides: Any) -> Any:
        def sleep(s: float) -> None:
            self.now += timedelta(seconds=s)

        def journal_cursor() -> str:
            return f"c{len(self.journal_lines)}"

        def journal_after(cursor: str) -> str:
            self.after_calls.append(cursor)
            return "\n".join(line for _, line in self.journal_lines[int(cursor[1:]):])

        kw: dict[str, Any] = {
            "run": self.run,
            "gateway_identity": lambda: (self.pid, self.started),
            "journal_cursor": journal_cursor,
            "journal_after": journal_after,
            "now": lambda: self.now,
            "sleep": sleep,
            "state_dir": self.state,
        }
        kw.update(overrides)
        return mod.Effects(**kw)

    def main(self, *flags: str, **overrides: Any) -> int:
        return mod.main(list(flags), self.effects(**overrides))

    @property
    def receipt_path(self) -> Path:
        return self.state / mod.RECEIPT_NAME



def good_receipt(w: World) -> dict[str, Any]:
    """A valid receipt describing the world's current (pre-apply) state."""
    snap = mod.Snapshot(entries=w.entries, top_tools=w.config["tools"])
    return mod.build_receipt(snap, w.state / "x.bak", T0)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def assert_untouched(w: World, original: dict[str, Any]) -> None:
    assert w.config == original
    assert not w.real_patches
    assert not w.receipt_path.exists()


# --------------------------------------------------------------------------- #
# Happy path, idempotence, dry-run.
# --------------------------------------------------------------------------- #
def test_apply_sets_exactly_the_three_denies(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    before = copy.deepcopy(world.config)
    assert world.main("--apply") == 0
    for t in TARGETS:
        assert world.entries[t]["tools"] == {"deny": DENY}
        rest_after = {k: v for k, v in world.entries[t].items() if k != "tools"}
        assert rest_after == before["agents"]["entries"][t]
    for n in NON_TARGETS:
        assert sha(world.entries[n]) == sha(before["agents"]["entries"][n])
    assert sha(world.config["tools"]) == sha(before["tools"])
    # One dry-run, then one real patch carrying only the three deny arrays.
    assert [p["dry_run"] for p in world.patch_calls] == [True, False]
    assert world.real_patches[0]["patch"] == {
        "agents": {"entries": {t: {"tools": {"deny": DENY}} for t in TARGETS}}
    }
    out = capsys.readouterr().out
    assert "PASS reload" in out and "PASS gateway-identity" in out
    assert "REDACTED" not in out  # no config values beyond tools are echoed


def test_apply_writes_receipt_and_private_backup_before_patching(world: World) -> None:
    original = copy.deepcopy(world.config)
    assert world.main("--apply") == 0
    receipt = json.loads(world.receipt_path.read_text())
    for t in TARGETS:
        assert receipt["targets"][t]["tools"] == {"present": False}
    assert set(receipt["non_target_hashes"]) == set(NON_TARGETS)
    assert receipt["non_target_hashes"]["main"] == sha(original["agents"]["entries"]["main"])
    assert receipt["top_level_tools_hash"] == sha(original["tools"])
    backups = list(world.state.glob("openclaw.json.*.bak"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text()) == original
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_reapply_is_a_noop(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    assert world.main("--apply") == 0
    receipt_before = world.receipt_path.read_text()
    assert json.loads(receipt_before)["reload_verified"] is True
    patches_before = len(world.patch_calls)
    capsys.readouterr()
    assert world.main("--apply") == 0
    assert len(world.patch_calls) == patches_before  # no patch of any kind issued
    assert world.receipt_path.read_text() == receipt_before
    assert "NOOP" in capsys.readouterr().out


def test_deny_in_a_different_order_counts_as_the_target_set(world: World) -> None:
    for t in TARGETS:
        world.entries[t]["tools"] = {"deny": list(reversed(DENY))}
    world.flush()
    assert world.main("--apply") == 0
    assert not world.real_patches


def test_dry_run_writes_nothing_and_prints_the_patch(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    original = copy.deepcopy(world.config)
    assert world.main("--dry-run") == 0
    assert world.config == original
    assert not world.real_patches
    assert [p["dry_run"] for p in world.patch_calls] == [True]
    assert not world.receipt_path.exists()
    assert list(world.state.iterdir()) == []
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "felix-admin-habits" in out and "conversations_*" in out


def test_dry_run_on_an_already_applied_config_is_a_noop(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    assert world.main("--apply") == 0
    n = len(world.patch_calls)
    capsys.readouterr()
    assert world.main("--dry-run") == 0
    assert len(world.patch_calls) == n
    assert "NOOP" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Refusals, each paired with a control on the same fixture.
# --------------------------------------------------------------------------- #
def _missing_entry(cfg: dict[str, Any]) -> None:
    del cfg["agents"]["entries"]["felix-admin-habits"]


def _existing_allow(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-capture"]["tools"] = {"allow": ["exec"]}


def _existing_also_allow(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-escalation"]["tools"] = {"alsoAllow": []}


def _different_deny(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-habits"]["tools"] = {"deny": ["web_search"]}


def _superset_deny(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-habits"]["tools"] = {"deny": [*DENY, "browser"]}


def _entry_not_object(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-capture"] = "oops"


def _tools_not_object(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-capture"]["tools"] = ["deny"]


def _deny_not_list(cfg: dict[str, Any]) -> None:
    cfg["agents"]["entries"]["felix-admin-capture"]["tools"] = {"deny": "message"}


@pytest.mark.parametrize(
    "mutate",
    [_missing_entry, _existing_allow, _existing_also_allow, _different_deny, _superset_deny,
     _entry_not_object, _tools_not_object, _deny_not_list],
)
def test_unexpected_shapes_are_refused_and_nothing_is_written(tmp_path: Path, mutate: Any) -> None:
    refused = World(tmp_path / "refused") if (tmp_path / "refused").mkdir() is None else None
    assert refused is not None
    mutate(refused.config)
    refused.flush()
    original = copy.deepcopy(refused.config)
    assert refused.main("--apply") != 0
    assert_untouched(refused, original)
    assert not list(refused.state.iterdir())

    # Control: the identical fixture, unmutated, applies cleanly.
    (tmp_path / "control").mkdir()
    control = World(tmp_path / "control")
    assert control.main("--apply") == 0
    assert len(control.real_patches) == 1


def test_refusal_message_names_the_agent(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _existing_allow(world.config)
    world.flush()
    assert world.main("--apply") != 0
    out = capsys.readouterr()
    assert "felix-admin-capture" in out.out + out.err
    assert "tools.allow" in out.out + out.err


def test_validate_failure_before_the_change_refuses(tmp_path: Path) -> None:
    bad = World(tmp_path)
    bad.validate_fails = True
    assert bad.main("--apply") != 0
    assert not bad.real_patches and not bad.receipt_path.exists()


def test_unreadable_gateway_identity_refuses_before_the_change(world: World) -> None:
    def broken() -> tuple[str, str]:
        raise mod.DeployError("no MainPID")

    assert world.main("--apply", gateway_identity=broken) != 0
    assert not world.real_patches and not world.receipt_path.exists()


def test_missing_state_dir_refuses_before_the_change(world: World, tmp_path: Path) -> None:
    assert world.main("--apply", state_dir=tmp_path / "nope") != 0
    assert not world.real_patches


# --------------------------------------------------------------------------- #
# Non-target protection (read-back).
# --------------------------------------------------------------------------- #
def test_patch_that_also_touches_main_fails_readback(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.touch_main_on_patch = True
    assert world.main("--apply") != 0
    out = capsys.readouterr().out
    assert "FAIL" in out and "main" in out
    assert "--rollback" in out  # recovery block names the rollback command


def test_control_clean_patch_passes_the_same_fixture(world: World) -> None:
    assert world.touch_main_on_patch is False
    assert world.main("--apply") == 0


def test_patch_failure_prints_recovery_block(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    real = world.run

    def failing(argv: list[str], input_text: str | None, timeout: float) -> tuple[int, str, str]:
        if "patch" in argv and "--dry-run" not in argv:
            return 1, "", "schema refusal"
        return real(argv, input_text, timeout)

    assert world.main("--apply", run=failing) != 0
    out = capsys.readouterr().out
    assert "RECOVERY" in out and str(world.receipt_path) in out


def test_validate_after_patch_failing_is_a_failure(world: World) -> None:
    real = world.run
    calls = {"validate": 0}

    def run(argv: list[str], input_text: str | None, timeout: float) -> tuple[int, str, str]:
        if argv[1:3] == ["config", "validate"]:
            calls["validate"] += 1
            if world.real_patches:  # only after the real patch landed
                return 1, "", "invalid"
        return real(argv, input_text, timeout)

    assert world.main("--apply", run=run) != 0


# --------------------------------------------------------------------------- #
# Receipt write-once.
# --------------------------------------------------------------------------- #
def test_existing_receipt_is_never_overwritten(world: World) -> None:
    receipt = good_receipt(world)
    receipt["sentinel"] = True
    sentinel = json.dumps(receipt)
    world.receipt_path.write_text(sentinel)
    assert world.main("--apply") == 0
    kept = json.loads(world.receipt_path.read_text())
    assert kept["sentinel"] is True
    assert kept["targets"] == json.loads(sentinel)["targets"]
    assert kept["non_target_hashes"] == json.loads(sentinel)["non_target_hashes"]


def test_retry_after_a_failed_apply_keeps_the_original_receipt(world: World) -> None:
    world.touch_main_on_patch = True
    assert world.main("--apply") != 0  # patch landed, read-back failed
    first = world.receipt_path.read_text()
    assert all(json.loads(first)["targets"][t]["tools"] == {"present": False} for t in TARGETS)
    # The retry sees the already-denied state, yet the receipt still holds the original.
    world.touch_main_on_patch = False
    world.entries["main"].pop("tools", None)
    world.flush()
    world.main("--apply")
    kept, orig = json.loads(world.receipt_path.read_text()), json.loads(first)
    assert kept["targets"] == orig["targets"]
    assert kept["non_target_hashes"] == orig["non_target_hashes"]


def test_corrupt_existing_receipt_refuses(world: World) -> None:
    world.receipt_path.write_text("{not json")
    assert world.main("--apply") != 0
    assert not world.real_patches


# --------------------------------------------------------------------------- #
# Rollback.
# --------------------------------------------------------------------------- #
def test_rollback_distinguishes_absent_from_empty_and_restores_other_keys(world: World) -> None:
    world.entries["felix-admin-capture"]["tools"] = {}
    world.entries["felix-admin-habits"]["tools"] = {"profile": "minimal"}
    world.flush()
    original = copy.deepcopy(world.config)
    assert world.main("--apply") == 0
    assert world.entries["felix-admin-capture"]["tools"] == {"deny": DENY}
    assert world.entries["felix-admin-habits"]["tools"] == {"profile": "minimal", "deny": DENY}

    assert world.main("--rollback") == 0
    assert world.entries["felix-admin-capture"]["tools"] == {}  # present-but-empty restored
    assert "tools" not in world.entries["felix-admin-escalation"]  # absent restored
    assert world.entries["felix-admin-habits"]["tools"] == {"profile": "minimal"}
    assert world.config == original
    # One validated Gateway patch, scoped, with replace-path only where a value existed.
    last = world.real_patches[-1]
    assert sorted(last["replace"]) == [
        "agents.entries.felix-admin-capture.tools",
        "agents.entries.felix-admin-habits.tools",
    ]
    assert last["patch"]["agents"]["entries"]["felix-admin-escalation"] == {"tools": None}
    assert set(last["patch"]["agents"]["entries"]) == set(TARGETS)
    # The receipt is archived so a later apply starts fresh.
    assert not world.receipt_path.exists()
    assert list(world.state.glob(mod.RECEIPT_NAME + ".rolled-back-*"))


def test_rollback_refuses_without_a_receipt(world: World) -> None:
    assert world.main("--apply") == 0
    world.receipt_path.unlink()
    snapshot = copy.deepcopy(world.config)
    patches = len(world.real_patches)
    assert world.main("--rollback") != 0
    assert world.config == snapshot and len(world.real_patches) == patches


def test_rollback_with_receipt_is_the_control(world: World) -> None:
    assert world.main("--apply") == 0
    assert world.receipt_path.exists()
    assert world.main("--rollback") == 0


def test_rollback_leaves_non_targets_alone(world: World) -> None:
    assert world.main("--apply") == 0
    world.entries["felix-admin-tasker"]["name"] = "changed-later"
    world.flush()
    assert world.main("--rollback") == 0
    assert world.entries["felix-admin-tasker"]["name"] == "changed-later"


# --------------------------------------------------------------------------- #
# Reload confirmation.
# --------------------------------------------------------------------------- #
def test_gateway_pid_change_is_a_failure(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.change_pid_on_patch = True
    assert world.main("--apply", gateway_identity=lambda: (world.pid, world.started)) != 0
    out = capsys.readouterr().out
    assert "FAIL gateway-identity" in out and "--rollback" in out


def test_gateway_start_time_change_is_a_failure(world: World) -> None:
    identity = [("153444", "t1"), ("153444", "t2")]
    assert world.main("--apply", gateway_identity=lambda: identity.pop(0)) != 0


def test_missing_reload_acknowledgement_fails_after_the_bounded_wait(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.emit_ack = False
    start = world.now
    assert world.main("--apply") != 0
    assert "FAIL reload" in capsys.readouterr().out
    waited = (world.now - start).total_seconds()
    assert mod.RELOAD_WAIT_S <= waited < mod.RELOAD_WAIT_S + 10


def test_restart_required_is_a_failure_even_with_an_ack(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.emit_restart_required = True
    assert world.main("--apply") != 0
    assert "restart" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Effective-catalog check (advisory; R1-1 / T011).
# --------------------------------------------------------------------------- #
def test_effective_catalog_passes_when_denied_tools_are_gone(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    assert world.main("--apply") == 0
    out = capsys.readouterr().out
    assert "PASS effective-catalog" in out


def test_effective_catalog_stale_preview_warns_but_does_not_fail(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.stale_effective = True
    assert world.main("--apply") == 0
    out = capsys.readouterr().out
    assert "WARN effective-catalog" in out and "weaker" in out


def test_effective_catalog_without_a_session_is_reported_as_skipped(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.no_sessions = True
    assert world.main("--apply") == 0
    assert "SKIP effective-catalog" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Verify mode (manifest post check).
# --------------------------------------------------------------------------- #
def test_verify_passes_after_apply_and_fails_before(world: World) -> None:
    assert world.main("--verify") != 0  # control for the pass below: nothing applied yet
    assert world.main("--apply") == 0
    assert world.main("--verify") == 0


def test_verify_fails_when_a_non_target_changed_since_the_receipt(world: World) -> None:
    assert world.main("--apply") == 0
    world.entries["felix-admin-calendar"]["model"] = "other"
    world.flush()
    assert world.main("--verify") != 0


def test_verify_is_read_only(world: World) -> None:
    n = len(world.patch_calls)
    world.main("--verify")
    assert len(world.patch_calls) == n


# --------------------------------------------------------------------------- #
# Binary resolution and argv handling.
# --------------------------------------------------------------------------- #
def test_default_runner_uses_the_repo_resolver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "fake-openclaw"
    exe.write_text('#!/bin/sh\necho "ARGV:$@"\n')
    exe.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_BIN", str(exe))
    argv = mod.openclaw_cmd("config", "validate")
    assert argv[0] == str(exe)
    rc, out, _ = mod.run_subprocess(argv, None, 10)
    assert rc == 0 and out == "ARGV:config validate"


def test_default_runner_reports_a_missing_binary(tmp_path: Path) -> None:
    rc, _, err = mod.run_subprocess([str(tmp_path / "absent")], None, 5)
    assert rc == 127 and err


@pytest.mark.parametrize("argv", [[], ["--bogus"], ["--apply", "--dry-run"], ["--apply", "--rollback"]])
def test_bad_usage_exits_2(argv: list[str], world: World) -> None:
    assert mod.main(argv, world.effects()) == 2


def test_default_state_dir_is_the_felix_deployer_state_dir() -> None:
    assert Path("/data/services/felix-deployer/state") == mod.DEFAULT_STATE_DIR


# --------------------------------------------------------------------------- #
# Entrypoint file hygiene and the queued manifest.
# --------------------------------------------------------------------------- #
def test_entrypoint_is_executable_with_a_shebang() -> None:
    assert os.access(_PATH, os.X_OK)
    assert _PATH.read_text().startswith("#!/usr/bin/env python3\n")


def test_manifest_is_unnumbered_and_validates() -> None:
    assert not MANIFEST_PATH.name[:1].isdigit()
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = yaml.safe_load(MANIFEST_PATH.read_text())
    errors = list(Draft202012Validator(schema).iter_errors(doc))
    assert not errors, errors
    from scripts.deploy.lib import manifest as lib_manifest

    result = lib_manifest.validate_manifest(doc, schema_path=SCHEMA_PATH)
    assert result.ok, result.summary


def test_manifest_shape() -> None:
    doc = yaml.safe_load(MANIFEST_PATH.read_text())
    assert doc["name"] == "announce-agent-tool-deny"
    assert doc["issue"] == "kentonium3/kg-automation#1146"
    assert doc["tier"] == 2
    assert doc["entrypoint"] == "scripts/deploy/deploy-announce-agent-tool-deny.py"
    assert doc["audited_surface"] is True
    assert doc["expected_baselines"] == ["openclaw-config.txt"]
    assert (_ROOT / doc["entrypoint"]).is_file()
    assert doc["verification"]["pre"] == [f"{doc['entrypoint']} --dry-run"]
    assert any(c.startswith(f"{doc['entrypoint']} --verify") for c in doc["verification"]["post"])
    text = MANIFEST_PATH.read_text()
    assert "backup-confirmed" not in text
    assert "ssh office2" not in text
    for needle in ("#1143", "#1146", "206884", "--rollback", "deploys/queued"):
        assert needle in doc["notes"], needle


def test_manifest_has_no_apply_time_fields() -> None:
    doc = yaml.safe_load(MANIFEST_PATH.read_text())
    assert not {"apply_mode", "applied_at", "rebaseline"} & set(doc)


# --------------------------------------------------------------------------- #
# Review round 1, item 1: a retry must not hide a failed reload.
# --------------------------------------------------------------------------- #
def test_retry_after_missing_ack_does_not_succeed_on_persisted_config_alone(world: World) -> None:
    world.emit_ack = False
    world.stale_effective = True  # the runtime preview still lists the tools
    assert world.main("--apply") != 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is False
    patches = len(world.patch_calls)
    assert world.main("--apply") != 0  # persisted deny, but no runtime confirmation
    assert len(world.patch_calls) == patches  # and nothing was re-patched
    assert world.main("--verify") != 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is False


def test_retry_succeeds_once_a_fresh_ack_arrives(world: World) -> None:
    world.emit_ack = False
    world.stale_effective = True
    assert world.main("--apply") != 0
    world.journal_lines.append((world.now, "[reload] config hot reload applied (agents.entries)"))
    assert world.main("--apply") == 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is True
    assert world.main("--verify") == 0


def test_retry_succeeds_when_the_effective_catalog_shows_the_tools_gone(world: World) -> None:
    world.emit_ack = False  # first apply fails; the preview is fresh, so the retry can prove it
    assert world.main("--apply") != 0
    assert world.main("--apply") == 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is True


def test_retry_after_restart_required_still_fails(world: World) -> None:
    world.emit_restart_required = True
    assert world.main("--apply") != 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is False
    patches = len(world.patch_calls)
    assert world.main("--apply") != 0
    assert len(world.patch_calls) == patches
    assert world.main("--verify") != 0


def test_control_same_fixture_without_restart_flag_verifies(world: World) -> None:
    assert world.main("--apply") == 0
    assert world.main("--apply") == 0
    assert world.main("--verify") == 0


# --------------------------------------------------------------------------- #
# Item 2: --verify needs the receipt's hash protection.
# --------------------------------------------------------------------------- #
def test_verify_without_a_receipt_fails_even_when_denied(world: World) -> None:
    assert world.main("--apply") == 0
    assert world.main("--verify") == 0  # control: receipt present
    world.receipt_path.unlink()
    assert world.main("--verify") != 0


def test_verify_with_incomplete_hashes_fails(world: World) -> None:
    assert world.main("--apply") == 0
    receipt = json.loads(world.receipt_path.read_text())
    receipt["non_target_hashes"] = {}
    world.receipt_path.write_text(json.dumps(receipt))
    assert world.main("--verify") != 0


# --------------------------------------------------------------------------- #
# Item 3: the receipt is fully validated and reconciled before any change.
# --------------------------------------------------------------------------- #
def test_stale_receipt_is_refused_by_apply_and_rollback(tmp_path: Path) -> None:
    (tmp_path / "stale").mkdir()
    stale = World(tmp_path / "stale")
    stale.receipt_path.write_text(json.dumps(good_receipt(stale)))  # says: capture tools absent
    stale.entries["felix-admin-capture"]["tools"] = {"profile": "minimal"}  # changed since
    stale.flush()
    before = copy.deepcopy(stale.config)
    assert stale.main("--apply") != 0
    assert stale.main("--rollback") != 0
    assert stale.config == before and not stale.real_patches

    # Control: the receipt matches the current state, so apply proceeds.
    (tmp_path / "ok").mkdir()
    ok = World(tmp_path / "ok")
    ok.receipt_path.write_text(json.dumps(good_receipt(ok)))
    assert ok.main("--apply") == 0


def _bad_present_value(r: dict[str, Any]) -> None:
    r["targets"]["felix-admin-habits"]["tools"] = {"present": True, "value": "oops"}


def _bad_present_no_value(r: dict[str, Any]) -> None:
    r["targets"]["felix-admin-habits"]["tools"] = {"present": True}


def _bad_present_flag(r: dict[str, Any]) -> None:
    r["targets"]["felix-admin-habits"]["tools"] = {"present": "yes"}


def _bad_schema(r: dict[str, Any]) -> None:
    r["schema"] = 99


def _bad_deny(r: dict[str, Any]) -> None:
    r["deny"] = ["message"]


def _missing_target(r: dict[str, Any]) -> None:
    del r["targets"]["felix-admin-habits"]


def _bad_hash(r: dict[str, Any]) -> None:
    r["non_target_hashes"]["main"] = "not-a-hash"


def _no_hashes(r: dict[str, Any]) -> None:
    r["non_target_hashes"] = {}


def _bad_top_hash(r: dict[str, Any]) -> None:
    r["top_level_tools_hash"] = ""


@pytest.mark.parametrize(
    "mutate",
    [_bad_present_value, _bad_present_no_value, _bad_present_flag, _bad_schema, _bad_deny,
     _missing_target, _bad_hash, _no_hashes, _bad_top_hash],
)
def test_malformed_receipt_is_refused_cleanly(tmp_path: Path, mutate: Any) -> None:
    (tmp_path / "bad").mkdir()
    bad = World(tmp_path / "bad")
    receipt = good_receipt(bad)
    mutate(receipt)
    bad.receipt_path.write_text(json.dumps(receipt))
    before = copy.deepcopy(bad.config)
    assert bad.main("--apply") == 1  # a clean refusal, not a traceback
    assert bad.main("--rollback") == 1
    assert bad.config == before and not bad.real_patches

    (tmp_path / "good").mkdir()
    good = World(tmp_path / "good")
    good.receipt_path.write_text(json.dumps(good_receipt(good)))
    assert good.main("--apply") == 0
    assert good.main("--rollback") == 0


# --------------------------------------------------------------------------- #
# Review round 2: acknowledgements are correlated by journal cursor.
# --------------------------------------------------------------------------- #
ACK = "[reload] config hot reload applied (agents.entries)"
RESTART = "[reload] config change requires gateway restart (agents.entries)"


def test_ack_before_the_cursor_does_not_confirm_and_one_after_it_does(world: World) -> None:
    world.emit_ack = False
    world.stale_effective = True  # keep the supplementary catalog path out of this
    world.journal_lines.append((world.now, ACK))  # an unrelated reload, before the patch
    assert world.main("--apply") != 0
    receipt = json.loads(world.receipt_path.read_text())
    assert receipt["patch_cursor"] == "c1"  # captured after the old line, before the patch
    assert world.main("--apply") != 0  # the old line still does not count on retry
    world.journal_lines.append((world.now, ACK))  # this one is after the cursor
    assert world.main("--apply") == 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is True


def test_stored_cursor_is_reused_on_retry(world: World) -> None:
    world.emit_ack = False
    world.stale_effective = True
    assert world.main("--apply") != 0
    stored = json.loads(world.receipt_path.read_text())["patch_cursor"]
    world.journal_lines.append((world.now, "unrelated line"))
    world.after_calls.clear()
    assert world.main("--apply") != 0
    assert world.after_calls == [stored]  # read after the stored cursor, not a fresh one
    assert json.loads(world.receipt_path.read_text())["patch_cursor"] == stored


def test_restart_required_before_the_cursor_is_ignored(world: World) -> None:
    world.journal_lines.append((world.now, RESTART))  # stale line from an earlier change
    assert world.main("--apply") == 0
    assert json.loads(world.receipt_path.read_text())["reload_verified"] is True


def test_restart_required_after_the_cursor_still_fails(world: World) -> None:
    world.emit_restart_required = True
    world.journal_lines.append((world.now, RESTART))  # one before as well
    assert world.main("--apply") != 0


def test_unreadable_journal_cursor_refuses_before_the_change(world: World) -> None:
    def broken() -> str:
        raise mod.DeployError("journalctl unavailable")

    assert world.main("--apply", journal_cursor=broken) != 0
    assert not world.real_patches
