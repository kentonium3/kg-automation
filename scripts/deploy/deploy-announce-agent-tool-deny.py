#!/usr/bin/env python3
"""Deploy entrypoint: deny the delivery tools to the three announce agents (#1146).

Tier 2 (application config on office2: ``~/.openclaw/openclaw.json``).

WHY. The delivery doctrine (#1143) tells the announce agents
(felix-admin-capture, felix-admin-escalation, felix-admin-habits) never to send,
route or record a result themselves: the Gateway delivers their final reply.
Wording alone is not enforcement, so this sets

    agents.entries.<id>.tools.deny = ["conversations_*","sessions_*","message","automations"]

for exactly those three agents. Deny wins over every allow and each level can
only restrict, so the groups leave the agents' effective tool catalog. ``exec``
and the runtime tools are untouched.

HOW. Never a direct file write. ``openclaw config patch`` makes one validated
write that the Gateway owns, hot-applied under the default ``hybrid`` reload
mode. Arrays REPLACE under patch, so a pre-existing ``tools.deny`` would be lost;
the preconditions refuse anything but "absent" or "exactly the target set".

SAFETY, in order (apply):
  1. preconditions: ``config validate``; the live shape; the three entries
     exist; none has ``tools.allow``/``tools.alsoAllow``; none has a different
     ``tools.deny``; the gateway identity (PID and start time) is readable;
  2. a WRITE-ONCE recovery receipt (original ``tools`` of each target, absent
     distinguished from ``{}``; sorted-JSON sha256 of every other agent entry
     and of the top-level ``tools``). A retry keeps the original receipt;
  3. a private (0600) timestamped copy of ``openclaw.json`` for last-resort
     recovery only (it holds secrets: never printed);
  4. ``config patch --dry-run``, then the real patch, then ``config validate``;
  5. read-back: targets hold exactly the deny set and nothing else of theirs
     changed; every non-target hash and the top-level ``tools`` hash equal the
     pre-patch values;
  6. reload confirmation: the Gateway's "hot reload applied" log line within a
     bounded wait, no "requires gateway restart" line, and an unchanged
     gateway PID and start time (proves hot reload, not a restart);
  7. advisory: the effective tool catalog (``tools.effective``) no longer lists
     the denied tools. A stale or unavailable preview is reported as a weaker
     check; it never fails the deploy.

ROLLBACK (``--rollback``): one Gateway ``config patch`` restoring only the
three targets' original ``tools`` values from the receipt (null where the key
was absent). If the manifest was never applied, remove it from
``deploys/queued/`` first, or the deployer will re-apply it. Restoring the
whole-file copy is the last resort: it can overwrite unrelated later config.

Usage:
    scripts/deploy/deploy-announce-agent-tool-deny.py --dry-run
    scripts/deploy/deploy-announce-agent-tool-deny.py --apply
    scripts/deploy/deploy-announce-agent-tool-deny.py --verify    # read-only
    scripts/deploy/deploy-announce-agent-tool-deny.py --rollback

Never wrap a command here in a remote shell to office2: this runs ON office2.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.common.openclaw_bin import openclaw_argv  # noqa: E402

TARGETS: tuple[str, ...] = ("felix-admin-capture", "felix-admin-escalation", "felix-admin-habits")
DENY: tuple[str, ...] = ("conversations_*", "sessions_*", "message", "automations")
DEFAULT_STATE_DIR = Path("/data/services/felix-deployer/state")
RECEIPT_NAME = "announce-agent-tool-deny.receipt.json"
GATEWAY_UNIT = "openclaw-gateway.service"
RELOAD_WAIT_S = 30.0
POLL_S = 2.0
CMD_TIMEOUT_S = 60.0
RECEIPT_SCHEMA = 1
ABSENT = {"present": False}

Runner = Callable[[list[str], "str | None", float], "tuple[int, str, str]"]


class DeployError(Exception):
    """A refusal or failure with an operator-readable message."""


# --------------------------------------------------------------------------- #
# Effects (defaults; every one is injectable).
# --------------------------------------------------------------------------- #
def openclaw_cmd(*args: str) -> list[str]:
    """argv for the openclaw CLI, resolved through the repo's single seam."""
    return openclaw_argv(*args)


def run_subprocess(argv: list[str], input_text: str | None, timeout: float) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            argv, input=input_text, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout} s"
    except OSError as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def systemd_gateway_identity() -> tuple[str, str]:
    """(MainPID, ExecMainStartTimestamp) of the gateway user unit; raises if unreadable."""
    rc, out, err = run_subprocess(
        ["systemctl", "--user", "show", GATEWAY_UNIT, "-p", "MainPID", "-p", "ExecMainStartTimestamp"],
        None,
        15,
    )
    if rc != 0:
        raise DeployError(f"cannot read {GATEWAY_UNIT} identity: {err or out}")
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    pid, start = kv.get("MainPID", ""), kv.get("ExecMainStartTimestamp", "")
    if not pid or pid == "0" or not start:
        raise DeployError(f"{GATEWAY_UNIT} has no running main process (MainPID={pid!r})")
    return pid, start


def journal_cursor_now() -> str:
    """The gateway journal's current cursor (read-only; ``-n 0`` prints no entries)."""
    rc, out, err = run_subprocess(
        ["journalctl", "--user", "-u", GATEWAY_UNIT, "--show-cursor", "-n", "0", "--no-pager", "-o", "cat"],
        None,
        30,
    )
    for line in (out + "\n" + err).splitlines():
        if line.startswith("-- cursor: "):
            return line[len("-- cursor: "):].strip()
    raise DeployError(f"cannot read a journal cursor for {GATEWAY_UNIT} (rc={rc}): {(err or out)[:200]}")


def journal_after_cursor(cursor: str) -> str:
    """Gateway journal lines strictly after ``cursor``; raises if the journal cannot be read."""
    rc, out, err = run_subprocess(
        ["journalctl", "--user", "-u", GATEWAY_UNIT, f"--after-cursor={cursor}", "--no-pager", "-o", "cat"],
        None,
        30,
    )
    if rc != 0:
        raise DeployError(f"cannot read the journal after the stored cursor (rc={rc}): {(err or out)[:200]}")
    return out


@dataclass
class Effects:
    run: Runner = run_subprocess
    gateway_identity: Callable[[], tuple[str, str]] = systemd_gateway_identity
    journal_cursor: Callable[[], str] = journal_cursor_now
    journal_after: Callable[[str], str] = journal_after_cursor
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleep: Callable[[float], None] = time.sleep
    state_dir: Path = DEFAULT_STATE_DIR


def say(line: str) -> None:
    print(line, flush=True)


def report(status: str, check: str, evidence: str) -> None:
    say(f"{status} {check}: {evidence}")


# --------------------------------------------------------------------------- #
# Pure helpers.
# --------------------------------------------------------------------------- #
def digest(obj: object) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def is_deny_set(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value) and sorted(value) == sorted(DENY)


@dataclass(frozen=True)
class Snapshot:
    entries: dict[str, Any]
    top_tools: Any  # the top-level ``tools`` value, or ABSENT marker

    def non_target_hashes(self) -> dict[str, str]:
        return {k: digest(v) for k, v in sorted(self.entries.items()) if k not in TARGETS}

    @property
    def top_tools_hash(self) -> str:
        return digest(self.top_tools)

    def target_tools(self, agent: str) -> dict[str, Any]:
        """``{"present": False}`` or ``{"present": True, "value": <tools>}``."""
        entry = self.entries[agent]
        if "tools" not in entry:
            return dict(ABSENT)
        return {"present": True, "value": entry["tools"]}

    def target_rest(self, agent: str) -> dict[str, Any]:
        return {k: v for k, v in self.entries[agent].items() if k != "tools"}


def check_preconditions(entries: object) -> tuple[list[str], list[str]]:
    """Return (refusals, agents still needing the deny)."""
    if not isinstance(entries, dict):
        return ["agents.entries is not an object"], []
    refusals: list[str] = []
    needed: list[str] = []
    for agent in TARGETS:
        if agent not in entries:
            refusals.append(f"{agent}: no agents.entries.{agent} entry")
            continue
        entry = entries[agent]
        if not isinstance(entry, dict):
            refusals.append(f"{agent}: entry is not an object")
            continue
        tools = entry.get("tools")
        if "tools" in entry and not isinstance(tools, dict):
            refusals.append(f"{agent}: tools is not an object")
            continue
        tools = tools or {}
        conflict = False
        for key in ("allow", "alsoAllow"):
            if key in tools:
                refusals.append(f"{agent}: has tools.{key}; refusing to combine it with a deny")
                conflict = True
        if "deny" in tools and not is_deny_set(tools["deny"]):
            refusals.append(
                f"{agent}: has a tools.deny that is not the target set ({tools['deny']!r}); "
                "patch replaces arrays, so it would be lost"
            )
            conflict = True
        if conflict:
            continue
        if not is_deny_set(tools.get("deny")):
            needed.append(agent)
    return refusals, needed


def build_patch(agents: Sequence[str]) -> dict[str, Any]:
    return {"agents": {"entries": {a: {"tools": {"deny": list(DENY)}} for a in agents}}}


def build_rollback_patch(receipt: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    entries: dict[str, Any] = {}
    replace: list[str] = []
    for agent in TARGETS:
        original = receipt["targets"][agent]["tools"]
        if original.get("present"):
            entries[agent] = {"tools": original["value"]}
            replace.append(f"agents.entries.{agent}.tools")
        else:
            entries[agent] = {"tools": None}
    return {"agents": {"entries": entries}}, replace


# --------------------------------------------------------------------------- #
# CLI access.
# --------------------------------------------------------------------------- #
class Cli:
    def __init__(self, fx: Effects) -> None:
        self.fx = fx

    def call(self, *args: str, input_text: str | None = None, timeout: float = CMD_TIMEOUT_S) -> tuple[int, str, str]:
        return self.fx.run(openclaw_cmd(*args), input_text, timeout)

    def get_json(self, path: str, *, allow_unset: bool = False) -> Any:
        rc, out, err = self.call("config", "get", path, "--json")
        if rc != 0:
            if allow_unset and "unset" in out:
                return dict(ABSENT)
            raise DeployError(f"config get {path} failed (rc={rc}): {(err or out)[:300]}")
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise DeployError(f"config get {path} returned non-JSON: {exc}") from exc

    def validate(self) -> None:
        rc, out, err = self.call("config", "validate")
        if rc != 0:
            raise DeployError(f"config validate failed (rc={rc}): {(err or out)[:300]}")

    def snapshot(self) -> Snapshot:
        entries = self.get_json("agents.entries")
        if not isinstance(entries, dict):
            raise DeployError("agents.entries is not an object")
        return Snapshot(entries=entries, top_tools=self.get_json("tools", allow_unset=True))

    def patch(self, patch: dict[str, Any], replace: Sequence[str] = (), *, dry_run: bool) -> None:
        argv = ["config", "patch", "--stdin"]
        for path in replace:
            argv += ["--replace-path", path]
        if dry_run:
            argv.append("--dry-run")
        rc, out, err = self.call(*argv, input_text=json.dumps(patch))
        if rc != 0:
            kind = "dry-run " if dry_run else ""
            raise DeployError(f"config patch {kind}failed (rc={rc}): {(err or out)[:300]}")

    def config_path(self) -> Path:
        rc, out, err = self.call("config", "file", "--json")
        if rc != 0:
            raise DeployError(f"config file failed (rc={rc}): {(err or out)[:200]}")
        try:
            return Path(json.loads(out)["path"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise DeployError(f"config file returned an unexpected shape: {exc}") from exc


# --------------------------------------------------------------------------- #
# Receipt and backup.
# --------------------------------------------------------------------------- #
def receipt_path(fx: Effects) -> Path:
    return fx.state_dir / RECEIPT_NAME


def build_receipt(snap: Snapshot, backup: Path, now: datetime) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "created_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deny": list(DENY),
        "targets": {a: {"tools": snap.target_tools(a)} for a in TARGETS},
        "non_target_hashes": snap.non_target_hashes(),
        "top_level_tools_hash": snap.top_tools_hash,
        "config_backup": str(backup),
        "reload_verified": False,
        "patch_started_at": None,
        "patch_cursor": None,
    }


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def validate_receipt(data: object) -> dict[str, Any]:
    """Full structural validation; raises DeployError naming the first defect."""
    if not isinstance(data, dict):
        raise DeployError("receipt is not an object")
    if data.get("schema") != RECEIPT_SCHEMA:
        raise DeployError(f"receipt schema is {data.get('schema')!r}, expected {RECEIPT_SCHEMA}")
    if not is_deny_set(data.get("deny")):
        raise DeployError("receipt deny set is not the target set")
    targets = data.get("targets")
    if not isinstance(targets, dict) or set(targets) != set(TARGETS):
        raise DeployError("receipt targets are not exactly the three announce agents")
    for agent in TARGETS:
        tools = targets[agent].get("tools") if isinstance(targets[agent], dict) else None
        if not isinstance(tools, dict) or not isinstance(tools.get("present"), bool):
            raise DeployError(f"receipt original for {agent} has no boolean 'present'")
        if tools["present"]:
            if set(tools) != {"present", "value"} or not isinstance(tools["value"], dict):
                raise DeployError(f"receipt original for {agent} is present but its value is not an object")
        elif set(tools) != {"present"}:
            raise DeployError(f"receipt original for {agent} is absent but carries a value")
    hashes = data.get("non_target_hashes")
    if (
        not isinstance(hashes, dict)
        or not hashes
        or any(not isinstance(k, str) or k in TARGETS or not isinstance(v, str) or not _HEX64.match(v) for k, v in hashes.items())
    ):
        raise DeployError("receipt non-target hashes are missing or incomplete")
    top = data.get("top_level_tools_hash")
    if not isinstance(top, str) or not _HEX64.match(top):
        raise DeployError("receipt top-level tools hash is missing or invalid")
    if not isinstance(data.get("reload_verified"), bool):
        raise DeployError("receipt reload_verified is not a boolean")
    started = data.get("patch_started_at")
    if started is not None:
        try:
            datetime.fromisoformat(started)
        except (TypeError, ValueError) as exc:
            raise DeployError("receipt patch_started_at is not an ISO timestamp") from exc
    cursor = data.get("patch_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise DeployError("receipt patch_cursor is not a non-empty string")
    return data


def load_receipt(fx: Effects) -> dict[str, Any]:
    path = receipt_path(fx)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DeployError(f"no recovery receipt at {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError(f"recovery receipt {path} is unreadable: {exc}") from exc
    try:
        return validate_receipt(data)
    except DeployError as exc:
        raise DeployError(f"recovery receipt {path} is invalid: {exc}") from exc


def reconcile_receipt(receipt: dict[str, Any], snap: Snapshot) -> None:
    """Each target must currently hold its recorded original, or that original plus the deny."""
    for agent in TARGETS:
        original = receipt["targets"][agent]["tools"]
        if snap.target_tools(agent) == original:
            continue
        current = snap.target_tools(agent)
        base = original["value"] if original["present"] else {}
        patched = (
            current["present"]
            and is_deny_set(current["value"].get("deny"))
            and {k: v for k, v in current["value"].items() if k != "deny"} == {k: v for k, v in base.items() if k != "deny"}
        )
        if not patched:
            raise DeployError(
                f"recovery receipt is stale: {agent} tools is neither its recorded original nor the patched form"
            )


def update_receipt(fx: Effects, **fields: Any) -> None:
    """Atomically rewrite the receipt with changed mutable fields only (never the originals)."""
    path = receipt_path(fx)
    data = load_receipt(fx)
    data.update(fields)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    # Atomic on POSIX. Writes only the receipt in the deployer state dir (never a drift-surface
    # file), so the installed-file report (#1072) does not apply.
    tmp.rename(path)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_receipt_once(fx: Effects, receipt: dict[str, Any]) -> bool:
    """Create the receipt exclusively. True if written, False if one already exists (kept)."""
    path = receipt_path(fx)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        load_receipt(fx)  # must be valid, or refuse
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    return True


def backup_config(cli: Cli, fx: Effects) -> Path:
    src = cli.config_path()
    stamp = fx.now().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = fx.state_dir / f"openclaw.json.{stamp}.bak"
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out, src.open("rb") as inp:
        shutil.copyfileobj(inp, out)
    return dest


# --------------------------------------------------------------------------- #
# Verification pieces.
# --------------------------------------------------------------------------- #
def verify_targets_denied(after: Snapshot, before: Snapshot | None) -> list[str]:
    problems: list[str] = []
    for agent in TARGETS:
        entry = after.entries.get(agent)
        tools = entry.get("tools") if isinstance(entry, dict) else None
        if not isinstance(tools, dict) or not is_deny_set(tools.get("deny")):
            problems.append(f"{agent}: tools.deny is not the target set")
            continue
        if before is not None:
            was = before.target_tools(agent)
            expect = {k: v for k, v in (was["value"] if was["present"] else {}).items() if k != "deny"}
            got = {k: v for k, v in tools.items() if k != "deny"}
            if got != expect:
                problems.append(f"{agent}: other tools keys changed")
            if after.target_rest(agent) != before.target_rest(agent):
                problems.append(f"{agent}: non-tools keys of the entry changed")
    return problems


def verify_untouched(after: Snapshot, hashes: dict[str, str], top_hash: str) -> list[str]:
    problems: list[str] = []
    now_hashes = after.non_target_hashes()
    for name in sorted(set(hashes) | set(now_hashes)):
        if hashes.get(name) != now_hashes.get(name):
            problems.append(f"agents.entries.{name} changed (hash mismatch)")
    if after.top_tools_hash != top_hash:
        problems.append("top-level tools changed (hash mismatch)")
    return problems


def wait_for_reload(fx: Effects, cursor: str) -> tuple[bool, str]:
    """Bounded wait for a hot-reload acknowledgement logged after ``cursor`` (not a time window)."""
    deadline = fx.now() + timedelta(seconds=RELOAD_WAIT_S)
    while True:
        lines = fx.journal_after(cursor).splitlines()
        restart = [ln for ln in lines if "requires gateway restart" in ln]
        if restart:
            return False, f"Gateway reports a restart is required: {restart[-1].strip()[:200]}"
        acks = [ln for ln in lines if "[reload]" in ln and "hot reload applied" in ln]
        if acks:
            return True, acks[-1].strip()[:200]
        if fx.now() >= deadline:
            return False, f"no 'hot reload applied' line within {RELOAD_WAIT_S:.0f} s"
        fx.sleep(POLL_S)


def effective_catalog_check(cli: Cli, fx: Effects, *, expect_denied: bool) -> str:
    """Advisory (R1-1): ``tools.effective`` for each target. Never raises, never fails the deploy."""
    weaker: list[str] = []
    for agent in TARGETS:
        rc, out, _ = cli.call("sessions", "--agent", agent, "--json")
        key = None
        if rc == 0:
            try:
                sessions = json.loads(out).get("sessions") or []
                key = sessions[0].get("key") if sessions else None
            except (json.JSONDecodeError, AttributeError, IndexError):
                key = None
        if not key:
            weaker.append(f"{agent}: no stored session to preview")
            continue
        rc, out, _ = cli.call("gateway", "call", "tools.effective", "--params", json.dumps({"sessionKey": key}), "--json")
        try:
            groups = json.loads(out)["groups"] if rc == 0 else None
            ids = sorted({t["id"] for g in groups for t in g.get("tools", [])}) if groups is not None else None
        except (json.JSONDecodeError, KeyError, TypeError):
            ids = None
        if ids is None:
            weaker.append(f"{agent}: tools.effective unavailable")
            continue
        listed = [t for t in ids if any(fnmatch.fnmatchcase(t.lower(), d.lower()) for d in DENY)]
        listed += [t for t in ids if t.lower() == "cron"]
        if expect_denied and listed:
            weaker.append(f"{agent}: preview still lists {','.join(listed)} (may be a cached projection)")
        elif expect_denied and "exec" not in ids:
            weaker.append(f"{agent}: preview lacks exec")
    if not weaker:
        report("PASS", "effective-catalog", "denied groups absent and exec present for all three agents")
        return "PASS"
    status = "SKIP" if all("no stored session" in w or "unavailable" in w for w in weaker) else "WARN"
    report(status, "effective-catalog", "; ".join(weaker) + " (weaker check: rests on persisted config + policy order)")
    return status


def recovery_block(fx: Effects, why: str) -> None:
    say("")
    say("RECOVERY: the change may be partly applied.")
    say(f"  reason:  {why}")
    say(f"  receipt: {receipt_path(fx)}")
    say("  1. If this manifest is still in deploys/queued/, remove it first so the deployer does not re-apply it.")
    say("  2. Restore the three targets through the Gateway (scoped, validated):")
    say("       scripts/deploy/deploy-announce-agent-tool-deny.py --rollback")
    say("  3. Last resort only: the timestamped openclaw.json.<ts>.bak next to the receipt (0600).")


# --------------------------------------------------------------------------- #
# Modes.
# --------------------------------------------------------------------------- #
def preflight(cli: Cli, fx: Effects) -> tuple[Snapshot, list[str], tuple[str, str]]:
    cli.validate()
    snap = cli.snapshot()
    refusals, needed = check_preconditions(snap.entries)
    if refusals:
        for r in refusals:
            report("FAIL", "precondition", r)
        raise DeployError("refusing: the live config is not the expected shape")
    identity = fx.gateway_identity()
    return snap, needed, identity


def mode_dry_run(cli: Cli, fx: Effects) -> int:
    _, needed, identity = preflight(cli, fx)
    report("PASS", "preconditions", f"3 entries present, no conflicting allow/deny; gateway pid {identity[0]}")
    if not needed:
        say("NOOP: all three agents already carry exactly the target deny set.")
        return 0
    patch = build_patch(needed)
    cli.patch(patch, dry_run=True)
    say("DRY-RUN: config patch accepted. Would apply:")
    say(json.dumps(patch, indent=2, sort_keys=True))
    say(f"DRY-RUN: would write receipt {receipt_path(fx)} and a 0600 openclaw.json copy beside it.")
    return 0


def confirm_persisted(cli: Cli, fx: Effects, receipt: dict[str, Any] | None) -> int:
    """The deny is already persisted: succeed only with runtime confirmation (review R1/1)."""
    if receipt is not None and receipt["reload_verified"]:
        say("NOOP: all three agents already carry exactly the target deny set (reload verified earlier).")
        return 0
    cursor = receipt["patch_cursor"] if receipt is not None else None
    ok = False
    if cursor is not None:
        lines = fx.journal_after(cursor).splitlines()
        restart = [ln for ln in lines if "requires gateway restart" in ln]
        if restart:
            report("FAIL", "reload", f"Gateway reports a restart is required: {restart[-1].strip()[:200]}")
            recovery_block(fx, "deny persisted but the Gateway needs a restart; not confirmed")
            return 1
        acks = [ln for ln in lines if "[reload]" in ln and "hot reload applied" in ln]
        if acks:
            report("PASS", "reload", acks[-1].strip()[:200])
            ok = True
    if not ok and effective_catalog_check(cli, fx, expect_denied=True) == "PASS":
        ok = True
    if not ok:
        report("FAIL", "reload", "deny is persisted but no runtime confirmation (no ack after the change, no clean effective catalog)")
        recovery_block(fx, "deny persisted but reload unconfirmed")
        return 1
    if receipt is not None:
        update_receipt(fx, reload_verified=True, reload_verified_at=iso(fx.now()))
        say("CONFIRMED: persisted deny now runtime-verified; receipt updated.")
    else:
        say("NOOP: deny persisted and runtime-verified, but no receipt exists (--verify will fail without one).")
    return 0


def mode_apply(cli: Cli, fx: Effects) -> int:
    snap, needed, identity_before = preflight(cli, fx)
    receipt: dict[str, Any] | None = None
    if receipt_path(fx).exists():
        receipt = load_receipt(fx)  # full validation
        reconcile_receipt(receipt, snap)  # against the current state, before any change
    if not needed:
        return confirm_persisted(cli, fx, receipt)
    if not fx.state_dir.is_dir():
        raise DeployError(f"state directory {fx.state_dir} does not exist; cannot write the recovery receipt")
    patch = build_patch(needed)

    backup = backup_config(cli, fx)
    created = write_receipt_once(fx, build_receipt(snap, backup, fx.now()))
    report("PASS", "receipt", f"{'written' if created else 'existing receipt kept (write-once)'}: {receipt_path(fx)}")
    report("PASS", "backup", f"{backup} (0600)")

    try:
        cli.patch(patch, dry_run=True)
        say("config patch dry-run accepted; applying:")
        say(json.dumps(patch, sort_keys=True))
        # Immediately before the real patch: the cursor that later acknowledgements are read after.
        cursor = fx.journal_cursor()
        update_receipt(fx, reload_verified=False, patch_started_at=iso(fx.now()), patch_cursor=cursor)
        cli.patch(patch, dry_run=False)
        cli.validate()
        after = cli.snapshot()
        problems = verify_targets_denied(after, snap)
        problems += verify_untouched(after, snap.non_target_hashes(), snap.top_tools_hash)
        if problems:
            for p in problems:
                report("FAIL", "read-back", p)
            raise DeployError("read-back mismatch: " + "; ".join(problems))
        report("PASS", "read-back", "targets hold the deny set; every non-target entry and top-level tools unchanged")

        ok, evidence = wait_for_reload(fx, cursor)
        report("PASS" if ok else "FAIL", "reload", evidence)
        if not ok:
            raise DeployError(evidence)
        identity_after = fx.gateway_identity()
        if identity_after != identity_before:
            report("FAIL", "gateway-identity", f"changed {identity_before} -> {identity_after}: a restart, not a hot reload")
            raise DeployError("gateway PID or start time changed")
        report("PASS", "gateway-identity", f"pid {identity_after[0]} and start time unchanged")
        update_receipt(fx, reload_verified=True, reload_verified_at=iso(fx.now()))
    except DeployError as exc:
        recovery_block(fx, str(exc))
        return 1

    effective_catalog_check(cli, fx, expect_denied=True)
    say("APPLIED: announce agents now deny conversations_*, sessions_*, message, automations.")
    return 0


def mode_verify(cli: Cli, fx: Effects) -> int:
    snap = cli.snapshot()
    problems = verify_targets_denied(snap, None)
    try:
        receipt = load_receipt(fx)  # missing or incomplete hash protection is a failure
    except DeployError as exc:
        problems.append(f"cannot prove the other agents are unchanged: {exc}")
    else:
        problems += verify_untouched(snap, receipt["non_target_hashes"], receipt["top_level_tools_hash"])
        if not receipt["reload_verified"]:
            problems.append("receipt is not reload-verified: the Gateway reload was never confirmed")
    if problems:
        for p in problems:
            report("FAIL", "verify", p)
        return 1
    report("PASS", "verify", "all three targets deny the set; other agents and top-level tools match the receipt hashes; reload verified")
    return 0


def mode_rollback(cli: Cli, fx: Effects) -> int:
    receipt = load_receipt(fx)  # refuses when missing
    identity_before = fx.gateway_identity()
    cli.validate()
    before = cli.snapshot()
    missing = [a for a in TARGETS if a not in before.entries]
    if missing:
        raise DeployError(f"cannot roll back: entries missing from live config: {missing}")
    reconcile_receipt(receipt, before)  # refuse a stale receipt before any change
    patch, replace = build_rollback_patch(receipt)
    cli.patch(patch, replace, dry_run=True)
    say("rollback patch dry-run accepted; applying:")
    say(json.dumps(patch, sort_keys=True))
    try:
        cursor = fx.journal_cursor()
        cli.patch(patch, replace, dry_run=False)
        cli.validate()
        after = cli.snapshot()
        problems: list[str] = []
        for agent in TARGETS:
            if after.target_tools(agent) != receipt["targets"][agent]["tools"]:
                problems.append(f"{agent}: tools is not the original value")
            if after.target_rest(agent) != before.target_rest(agent):
                problems.append(f"{agent}: non-tools keys changed")
        problems += verify_untouched(after, before.non_target_hashes(), before.top_tools_hash)
        if problems:
            for p in problems:
                report("FAIL", "rollback-read-back", p)
            raise DeployError("rollback read-back mismatch")
        report("PASS", "rollback-read-back", "targets restored; nothing else changed")
        ok, evidence = wait_for_reload(fx, cursor)
        report("PASS" if ok else "FAIL", "reload", evidence)
        if not ok:
            raise DeployError(evidence)
        identity_after = fx.gateway_identity()
        if identity_after != identity_before:
            report("FAIL", "gateway-identity", f"changed {identity_before} -> {identity_after}")
            raise DeployError("gateway PID or start time changed")
        report("PASS", "gateway-identity", "unchanged")
    except DeployError as exc:
        say(f"ROLLBACK INCOMPLETE: {exc}. The receipt is kept: {receipt_path(fx)}")
        return 1
    archived = receipt_path(fx).with_name(
        f"{RECEIPT_NAME}.rolled-back-{fx.now().astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    receipt_path(fx).rename(archived)
    say(f"ROLLED BACK. Receipt archived: {archived}")
    return 0


MODES: dict[str, Callable[[Cli, Effects], int]] = {
    "--dry-run": mode_dry_run,
    "--apply": mode_apply,
    "--verify": mode_verify,
    "--rollback": mode_rollback,
}
USAGE = "usage: deploy-announce-agent-tool-deny.py (--dry-run | --apply | --verify | --rollback)"


def main(argv: Sequence[str] | None = None, effects: Effects | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in MODES:
        print(USAGE, file=sys.stderr)
        return 2
    fx = effects or Effects()
    try:
        return MODES[args[0]](Cli(fx), fx)
    except DeployError as exc:
        report("FAIL", args[0].lstrip("-"), str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
