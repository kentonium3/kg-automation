"""scripts.common.deadman — bounded, secret-safe dead-man ping (#1077).

Every test injects the subprocess runner, so nothing touches the network,
except the one hostile-.curlrc test, which runs the real curl against a closed
local port to prove ``-q`` makes curl ignore ambient configuration.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.common import deadman

SENTINEL = "https://hc-ping.com/0f5e5c2a-sentinel-not-a-real-check"


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Recorder:
    """Records each subprocess.run call; returns scripted results in order."""

    def __init__(self, *results):
        self.results = list(results) or [_Proc(0)]
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), **kwargs})
        result = self.results[min(len(self.calls), len(self.results)) - 1]
        if isinstance(result, BaseException):
            raise result
        return result


def _env_file(tmp_path: Path, **values: str) -> Path:
    path = tmp_path / "env"
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    return path


def _sleep_rec():
    slept: list[float] = []
    return slept, slept.append


# --------------------------------------------------------------------------- #
# Unconfigured is a silent no-op (FR-005).
# --------------------------------------------------------------------------- #

def test_missing_file_is_unconfigured_and_never_runs(tmp_path):
    run = _Recorder()
    res = deadman.ping("canary", "success", env_file=tmp_path / "absent", run=run)
    assert res == deadman.PingResult(False, "unconfigured")
    assert run.calls == []


def test_file_without_the_label_is_unconfigured(tmp_path):
    f = _env_file(tmp_path, FELIX_DEADMAN_HEALTHCHECK_URL=SENTINEL)
    run = _Recorder()
    assert deadman.ping("canary", "success", env_file=f, run=run).reason == "unconfigured"
    assert run.calls == []


def test_process_environment_is_never_a_url_source(tmp_path, monkeypatch):
    """URLs come only from the file (NFR-005); an env var is ignored."""
    monkeypatch.setenv("FELIX_DEADMAN_CANARY_URL", SENTINEL)
    run = _Recorder()
    res = deadman.ping("canary", "success", env_file=tmp_path / "absent", run=run)
    assert res.reason == "unconfigured" and run.calls == []


# --------------------------------------------------------------------------- #
# Transport shape and secrecy (FR-007, NFR-003, NFR-005).
# --------------------------------------------------------------------------- #

def test_success_ping_transport_is_hardened_and_url_only_on_stdin(tmp_path, capsys):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=SENTINEL)
    run = _Recorder(_Proc(0))
    res = deadman.ping("canary", "success", env_file=f, run=run)
    assert res == deadman.PingResult(True, "ok")
    (call,) = run.calls
    assert call["argv"] == list(deadman.PING_ARGV)
    assert call["argv"][1] == "-q", "-q must be the first argument"
    assert all(SENTINEL not in a for a in call["argv"])
    assert call["input"] == f'url = "{SENTINEL}"\n'
    assert call["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C"}
    assert call["capture_output"] is True
    assert call["timeout"] == deadman.SUBPROCESS_TIMEOUT_SECONDS
    out = capsys.readouterr()
    assert SENTINEL not in out.out + out.err
    assert "deadman canary success: ok" in out.err


def test_fail_ping_targets_fail_endpoint(tmp_path):
    f = _env_file(tmp_path, FELIX_DEADMAN_HEALTHCHECK_URL=SENTINEL + "/")
    run = _Recorder(_Proc(0))
    deadman.ping("healthcheck", "fail", env_file=f, run=run)
    assert run.calls[0]["input"] == f'url = "{SENTINEL}/fail"\n'


def test_quoted_value_in_env_file_is_accepted(tmp_path):
    path = tmp_path / "env"
    path.write_text(f'# comment\n\nFELIX_DEADMAN_CANARY_URL="{SENTINEL}"\ngarbage line\n')
    run = _Recorder(_Proc(0))
    assert deadman.ping("canary", "success", env_file=path, run=run).sent is True


# --------------------------------------------------------------------------- #
# Canonical endpoint validation (NFR-004).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url",
    [
        "http://hc-ping.com/abc",
        "https://hc-ping.com/abc?x=1",
        "https://hc-ping.com/abc#frag",
        "https://user@hc-ping.com/abc",
        "https://hc-ping.com/ab c",
        'https://hc-ping.com/ab"c',
        "https://hc-ping.com/ab\\c",
        "https://hc-ping.com/abc/fail",
        "https://hc-ping.com/abc/start",
        "https://hc-ping.com/abc/log",
        "https://hc-ping.com/abc/0",
        "https://hc-ping.com/abc/" + "x" * 600,
        "hc-ping.com/abc",
        "https:///abc",
        # WP01 review: suffix bypasses and path tricks
        "https://hc-ping.com/u/fail//",
        "https://hc-ping.com/u//",
        "https://hc-ping.com//u",
        "https://hc-ping.com/u/..",
        "https://hc-ping.com/u/../x",
        "https://hc-ping.com/u/.",
        "https://hc-ping.com/u/FAIL",
        "https://hc-ping.com/u/Start",
        "https://hc-ping.com/u/%66ail",
        "https://hc-ping.com:abc/u",
        "https://hc-ping.com:99999/u",
        "https://hc-pïng.com/u",
    ],
)
def test_non_canonical_urls_are_rejected_and_never_contacted(tmp_path, url, capsys):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=url)
    run = _Recorder()
    assert deadman.ping("canary", "success", env_file=f, run=run).reason == "invalid"
    assert run.calls == []
    assert url not in capsys.readouterr().err


def test_unknown_label_or_outcome_is_invalid(tmp_path):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=SENTINEL)
    run = _Recorder()
    assert deadman.ping("other", "success", env_file=f, run=run).reason == "invalid"
    assert deadman.ping("canary", "maybe", env_file=f, run=run).reason == "invalid"
    assert run.calls == []


# --------------------------------------------------------------------------- #
# Failure mapping, retry, totality (FR-006, NFR-001).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (_Proc(22), "http_error"),
        (_Proc(28), "timeout"),
        (_Proc(7), "unreachable"),
        (_Proc(6), "unreachable"),
        (_Proc(35), "curl_exit:35"),
        (subprocess.TimeoutExpired(["curl"], 8), "timeout"),
        (FileNotFoundError("curl"), "curl_missing"),
        (RuntimeError("boom " + SENTINEL), "error:RuntimeError"),
    ],
)
def test_failures_map_retry_once_and_never_leak(tmp_path, result, reason, capsys):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=SENTINEL)
    run = _Recorder(result, result)
    slept, sleep = _sleep_rec()
    res = deadman.ping("canary", "success", env_file=f, run=run, sleep=sleep)
    assert res == deadman.PingResult(False, reason)
    assert len(run.calls) == deadman.MAX_ATTEMPTS == 2
    assert slept == [deadman.RETRY_DELAY_SECONDS]
    out = capsys.readouterr()
    assert SENTINEL not in out.out + out.err


def test_retry_succeeds_on_second_attempt(tmp_path):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=SENTINEL)
    run = _Recorder(_Proc(7), _Proc(0))
    slept, sleep = _sleep_rec()
    assert deadman.ping("canary", "success", env_file=f, run=run, sleep=sleep).sent is True
    assert len(run.calls) == 2 and slept == [2]


def test_no_retry_after_success(tmp_path):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=SENTINEL)
    run = _Recorder(_Proc(0))
    slept, sleep = _sleep_rec()
    deadman.ping("canary", "success", env_file=f, run=run, sleep=sleep)
    assert len(run.calls) == 1 and slept == []


def test_ping_is_total_even_if_loading_explodes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(deadman, "_load", lambda p: (_ for _ in ()).throw(OSError("x")))
    res = deadman.ping("canary", "success", env_file=tmp_path / "e")
    assert res == deadman.PingResult(False, "error:OSError")


# --------------------------------------------------------------------------- #
# Real curl ignores a hostile ambient .curlrc (post-plan Codex round 1, item 4).
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(shutil.which("curl") is None, reason="curl not installed")
def test_real_curl_ignores_hostile_curlrc(tmp_path, monkeypatch):
    trace = tmp_path / "trace.txt"
    rc = tmp_path / ".curlrc"
    rc.write_text(f'trace-ascii = "{trace}"\n')
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CURL_HOME", str(tmp_path))
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL="https://127.0.0.1:9/abc")
    real_run = subprocess.run

    def run(argv, **kwargs):  # the module passes a minimal env; widen it to the hostile one
        kwargs["env"] = {**kwargs["env"], "HOME": str(tmp_path), "CURL_HOME": str(tmp_path)}
        return real_run(argv, **kwargs)

    res = deadman.ping("canary", "success", env_file=f, run=run, sleep=lambda s: None)
    assert res.sent is False
    assert not trace.exists(), "-q must stop curl from reading the ambient .curlrc"


# --------------------------------------------------------------------------- #
# channel_ok: fresh, stateless, delivery-matched (FR-003; rounds 3 and 4).
# --------------------------------------------------------------------------- #

def _healthy():
    return _Proc(0, stdout=json.dumps({"healthy": True}))


def test_topic_missing_fails_without_probing():
    run = _Recorder()
    assert deadman.channel_ok({}, True, run=run) == (False, "topic_missing")
    assert deadman.channel_ok({"FELIX_ALERT_NTFY_TOPIC": "  "}, True, run=run) == (False, "topic_missing")
    assert run.calls == []


def test_healthy_probe_and_delivered_is_ok():
    env = {"FELIX_ALERT_NTFY_TOPIC": "t", "HTTPS_PROXY": "http://proxy:3128", "HOME": "/home/claude"}
    run = _Recorder(_healthy())
    assert deadman.channel_ok(env, True, run=run) == (True, "ok")
    (call,) = run.calls
    assert call["argv"][-1] == "https://ntfy.sh/v1/health"
    assert "-q" not in call["argv"], "probe must use curl's default config, like delivery"
    assert call["env"] == env, "probe inherits the delivery environment (proxies, HOME)"


def test_custom_base_url_is_probed():
    env = {"FELIX_ALERT_NTFY_TOPIC": "t", "FELIX_ALERT_NTFY_BASE_URL": "https://ntfy.example.org/"}
    run = _Recorder(_healthy())
    deadman.channel_ok(env, True, run=run)
    assert run.calls[0]["argv"][-1] == "https://ntfy.example.org/v1/health"


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (_Proc(0, stdout=json.dumps({"healthy": False})), "ntfy_unhealthy"),
        (_Proc(0, stdout="not json"), "probe_error"),
        (_Proc(7), "probe_error"),
        (subprocess.TimeoutExpired(["curl"], 8), "probe_error"),
        (FileNotFoundError("curl"), "probe_error"),
    ],
)
def test_unhealthy_or_unprobeable_channel_fails_closed(result, reason):
    run = _Recorder(result, result)
    assert deadman.channel_ok({"FELIX_ALERT_NTFY_TOPIC": "t"}, True, run=run, sleep=lambda s: None) == (False, reason)
    assert len(run.calls) == 2


def test_undelivered_this_run_fails_even_when_channel_probes_healthy():
    run = _Recorder(_healthy())
    assert deadman.channel_ok({"FELIX_ALERT_NTFY_TOPIC": "t"}, False, run=run) == (False, "undelivered")


def test_channel_ok_is_total():
    class Exploding(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    assert deadman.channel_ok(Exploding(), True) == (False, "error:RuntimeError")


# --------------------------------------------------------------------------- #
# Operator CLI.
# --------------------------------------------------------------------------- #

def test_cli_prints_no_url(tmp_path, monkeypatch, capsys):
    f = _env_file(tmp_path, FELIX_DEADMAN_CANARY_URL=SENTINEL)
    monkeypatch.setenv(deadman.ENV_FILE_OVERRIDE_VAR, str(f))
    monkeypatch.setattr(deadman.subprocess, "run", _Recorder(_Proc(0)))
    rc = deadman.main(["--label", "canary", "--outcome", "fail"])
    out = capsys.readouterr()
    assert rc == 0
    assert "sent=True reason=ok" in out.out
    assert SENTINEL not in out.out + out.err


@pytest.mark.parametrize(
    ("url", "success", "fail"),
    [
        ("https://hc-ping.com/abc", "https://hc-ping.com/abc", "https://hc-ping.com/abc/fail"),
        ("https://hc-ping.com/abc/", "https://hc-ping.com/abc", "https://hc-ping.com/abc/fail"),
        ("https://hc-ping.com:443/p/key/slug", "https://hc-ping.com:443/p/key/slug",
         "https://hc-ping.com:443/p/key/slug/fail"),
        ("https://hc.example.org", "https://hc.example.org", "https://hc.example.org/fail"),
    ],
)
def test_canonical_endpoints(url, success, fail):
    assert deadman._canonical(url) == (success, fail)
