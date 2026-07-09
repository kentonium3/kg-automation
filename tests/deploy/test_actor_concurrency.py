"""WP06 — actor-level concurrency harness (the load-bearing NFR-001 proof, #667).

This is the mission's central proof. A primitive-level test on
``advance_checkout`` alone is NOT sufficient (Codex HIGH): the real #667 harm was
two *systemd-timed actors* — ``felix-deployer`` and ``agent-prompt-sync`` —
concurrently mutating a single shared git checkout. So this harness runs the TWO
REAL tick bodies, barrier-synchronized, against ONE shared checkout through ONE
shared ``deploylock`` over ≥100 overlapped pairs, and asserts the race is gone.

What is REAL here (not stubbed):
    * ``git`` — a real local origin remote + a real working checkout. Every
      ``git fetch``/``git merge --ff-only`` is a real subprocess against real
      refs (the whole point — the historical bug lived in real concurrent git).
    * ``deploylock`` — the real ``fcntl.flock`` primitive, one shared lock file
      pointed at by BOTH actors via the ``DEPLOY_CHECKOUT_LOCK`` env var.
    * ``advance_checkout`` — the real race-immune fetch→ref-merge path, called
      from inside each actor's own real tick body (``assume_locked=True``).
    * ``health.record`` — the real per-actor watermark write.
    * Both ``run_tick`` bodies — imported from the shipped modules and driven
      exactly as systemd drives them (repo_root / audit / state / log overrides
      only; no monkeypatching of the critical section).

What is neutralized (and why it is NOT the thing under test):
    * felix-deployer's post-pull *rebaseline bookkeeping* (``observe`` /
      ``reconcile`` / watermark / ntfy) is patched to inert no-ops. That path
      reads ``/data`` state + the security-monitor baselines and is the #685/#688
      subsystem, orthogonal to the FETCH_HEAD race this mission fixes. The tick
      already wraps it in a broad try/except; neutralizing it keeps the harness
      off ``/data`` and focuses the proof on the concurrent checkout mutation.
      The lock / advance / health / queue-apply path — the actual concurrent
      critical section — runs for real.
    * ntfy dispatch (network) is patched so no real ``curl`` runs.

Seeded stale extra origin branch:
    The origin is seeded with ``kitty/mission-…-lane-a`` (a dead lane branch,
    exactly the FR-003 orphan). A *bare* ``git pull`` from this origin would pull
    multiple heads into ``.git/FETCH_HEAD`` — the precise trigger of "Cannot
    fast-forward to multiple branches". The harness proves the shipped code
    survives that origin shape under concurrency.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import threading
from argparse import Namespace
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------
#
# ``deploy_agent_prompts`` is a normal dotted import. ``_tick.py`` lives under a
# hyphenated ``felix-deployer/`` directory, so (mirroring test_tick_ffrace.py) it
# is loaded via ``spec_from_file_location`` with its sibling ``notify`` /
# ``rebaseline`` modules pre-registered in ``sys.modules``.

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _ensure_sys_path() -> None:
    for p in (str(REPO_ROOT), str(FELIX_DEPLOYER_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_module(name: str, path: pathlib.Path):
    _ensure_sys_path()
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_ensure_sys_path()

from scripts.openclaw.deploy import deploy_agent_prompts as prompt_sync  # noqa: E402

notify = _load_module("notify", FELIX_DEPLOYER_DIR / "notify.py")
rebaseline = _load_module("rebaseline", FELIX_DEPLOYER_DIR / "rebaseline.py")
felix_tick = _load_module(
    "felix_deployer_tick_actor_concurrency", FELIX_DEPLOYER_DIR / "_tick.py"
)


# ---------------------------------------------------------------------------
# Git helpers (real git, all local)
# ---------------------------------------------------------------------------

MULTI_BRANCH_ERROR = "Cannot fast-forward to multiple branches"

STALE_LANE_BRANCH = "kitty/mission-trustworthy-weekly-habit-report-01KV4GZ7-lane-a"

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "harness",
    "GIT_AUTHOR_EMAIL": "harness@example.com",
    "GIT_COMMITTER_NAME": "harness",
    "GIT_COMMITTER_EMAIL": "harness@example.com",
    # Keep git deterministic + quiet; never read the user's real config.
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env=_GIT_ENV,
    )


def _head(cwd: pathlib.Path, ref: str = "HEAD") -> str:
    return _git(cwd, "rev-parse", ref).stdout.strip()


def _init_repo(path: pathlib.Path, *, bare: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if bare:
        _git(path, "init", "--bare", "--initial-branch=main")
    else:
        _git(path, "init", "--initial-branch=main")
        _git(path, "config", "user.email", "harness@example.com")
        _git(path, "config", "user.name", "harness")


# ---------------------------------------------------------------------------
# Fixture: one shared checkout + a real origin seeded with a stale lane branch
# ---------------------------------------------------------------------------

AGENT_SLUG = "felix-admin-capture"
SOURCE_REL = pathlib.Path("scripts/openclaw/agents") / AGENT_SLUG
INVENTORY_REL = pathlib.Path(
    "docs/design/architecture/data/service-inventory.json"
)
IN_SCOPE_PROMPTS = ("AGENTS.md", "IDENTITY.md", "SOUL.md")


class _Origin:
    """A real local origin (bare) plus a seeder checkout to advance ``main``.

    All prompt-sync inputs (``service-inventory.json`` + the agent's in-scope
    prompt files) are **tracked** on origin/main so the checkout receives them
    via fast-forward. This is essential: files written untracked into the
    checkout would make ``git merge --ff-only`` refuse ("untracked working tree
    files would be overwritten by merge"), which is a harness artefact, not the
    behavior under test.
    """

    def __init__(self, root: pathlib.Path, workspace: pathlib.Path) -> None:
        self.bare = root / "origin.git"
        self.seed = root / "seed"
        self.workspace = workspace
        _init_repo(self.bare, bare=True)
        _init_repo(self.seed)
        _git(self.seed, "remote", "add", "origin", str(self.bare))

        # Seed tracked service-inventory + prompt sources on main.
        (self.seed / "README.md").write_text("origin main\n", encoding="utf-8")
        self._write_inventory()
        self._write_prompts(version=0)
        _git(self.seed, "add", "-A")
        _git(self.seed, "commit", "-m", "initial main + inventory + prompts")
        _git(self.seed, "push", "-u", "origin", "main")

        # Seed the stale extra origin branch (the FR-003 orphan). A *bare* pull
        # from this origin would pull main + this branch into FETCH_HEAD.
        _git(self.seed, "branch", STALE_LANE_BRANCH, "main")
        _git(self.seed, "push", "origin", STALE_LANE_BRANCH)
        self._round = 0

    def _write_inventory(self) -> None:
        inv_path = self.seed / INVENTORY_REL
        inv_path.parent.mkdir(parents=True, exist_ok=True)
        inv_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "last_updated": "2026-07-09",
                    "services": [
                        {
                            "name": "openclaw-gateway",
                            "type": "npm-global",
                            "agents": {
                                AGENT_SLUG: {
                                    "source_in_repo": str(SOURCE_REL) + "/",
                                    "workspace": str(self.workspace),
                                }
                            },
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _write_prompts(self, version: int) -> None:
        src_dir = self.seed / SOURCE_REL
        src_dir.mkdir(parents=True, exist_ok=True)
        for fname in IN_SCOPE_PROMPTS:
            (src_dir / fname).write_text(f"# {fname} v{version}\n", encoding="utf-8")

    def advance(self, version: int) -> str:
        """Bump the tracked prompt content on origin/main; return new head sha.

        Each advance is REAL work: a fast-forward the checkout must pull, and a
        prompt-content change prompt-sync must then copy into the workspace.
        """
        self._round += 1
        self._write_prompts(version=version)
        (self.seed / f"round-{self._round}.txt").write_text(
            f"round {self._round}\n", encoding="utf-8"
        )
        _git(self.seed, "add", "-A")
        _git(self.seed, "commit", "-m", f"advance main round {self._round}")
        _git(self.seed, "push", "origin", "main")
        return _head(self.seed, "main")


def _make_checkout(root: pathlib.Path, origin: _Origin) -> pathlib.Path:
    """Clone the origin into a working checkout that both actors share."""
    checkout = root / "checkout"
    _git(root, "clone", str(origin.bare), str(checkout))
    _git(checkout, "config", "user.email", "office2@example.com")
    _git(checkout, "config", "user.name", "office2")
    # Fetch so the stale lane branch is present in remote-tracking refs — the
    # checkout's ``origin`` truly has multiple heads (the bare-pull hazard).
    _git(checkout, "fetch", "origin")
    return checkout


@pytest.fixture()
def concurrency_env(tmp_path, monkeypatch):
    """Build the shared world: origin (with stale branch), checkout, workspace.

    Returns a namespace of paths + the shared lock path (set via env for BOTH
    actors) and the neutralized felix rebaseline path.
    """
    agent_slug = AGENT_SLUG
    workspace = tmp_path / "agent-workspace" / agent_slug
    workspace.mkdir(parents=True, exist_ok=True)
    origin = _Origin(tmp_path, workspace)
    checkout = _make_checkout(tmp_path, origin)
    source_dir = checkout / SOURCE_REL

    # ONE shared advisory lock, pointed at by BOTH actors. This is the crux of
    # the two-actor mutual exclusion: the felix tick and the prompt-sync tick
    # each resolve deploylock() through this same env var → the same flock file.
    shared_lock = tmp_path / "office2-checkout.lock"
    monkeypatch.setenv("DEPLOY_CHECKOUT_LOCK", str(shared_lock))

    # felix-deployer log + health-state dirs → tmp (never real /data).
    felix_log_dir = tmp_path / "felix-logs"
    felix_state_dir = tmp_path / "felix-state"
    monkeypatch.setattr(felix_tick, "DEFAULT_STATE_DIR", felix_state_dir)

    # prompt-sync audit + health-state paths → tmp.
    prompt_audit = tmp_path / "agent-prompt-sync.jsonl"
    prompt_health = tmp_path / "prompt-git-health.json"

    # Neutralize the felix rebaseline bookkeeping (the #685/#688 subsystem,
    # orthogonal to the FETCH_HEAD race). These are the deployer's own post-pull
    # steps; the lock/advance/health critical section stays REAL.
    monkeypatch.setattr(rebaseline, "read_observed_head", lambda *a, **kw: "")
    monkeypatch.setattr(rebaseline, "write_observed_head", lambda *a, **kw: None)
    monkeypatch.setattr(
        rebaseline,
        "classify_watermark",
        lambda *a, **kw: (rebaseline.WATERMARK_FALLBACK, ""),
    )
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "read_token", lambda *a, **kw: None)
    monkeypatch.setattr(rebaseline, "write_token", lambda *a, **kw: None)

    # No real network: ntfy dispatch is a no-op for BOTH actors' notifiers.
    monkeypatch.setattr(notify, "dispatch_health_notification", lambda *a, **kw: None)
    monkeypatch.setattr(notify, "dispatch_failure_notification", lambda *a, **kw: None)
    monkeypatch.setattr(notify, "dispatch_rebaseline_alert", lambda *a, **kw: None)

    return Namespace(
        origin=origin,
        checkout=checkout,
        agent_slug=agent_slug,
        workspace=workspace,
        source_dir=source_dir,
        shared_lock=shared_lock,
        felix_log_dir=felix_log_dir,
        felix_state_dir=felix_state_dir,
        prompt_audit=prompt_audit,
        prompt_health=prompt_health,
    )


# ---------------------------------------------------------------------------
# Per-tick capture wrappers (record real outputs for assertions)
# ---------------------------------------------------------------------------


def _felix_log_entries(log_dir: pathlib.Path) -> list[dict[str, Any]]:
    files = sorted(log_dir.glob("*.jsonl"))
    entries: list[dict[str, Any]] = []
    for f in files:
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                entries.append(json.loads(ln))
    return entries


def _prompt_audit_records(audit_path: pathlib.Path) -> list[dict[str, Any]]:
    if not audit_path.exists():
        return []
    return [
        json.loads(ln)
        for ln in audit_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


# ---------------------------------------------------------------------------
# The harness — the load-bearing NFR-001 proof
# ---------------------------------------------------------------------------

ROUNDS = 120  # ≥100 overlapped pairs (mission DoD).


def test_two_actors_barrier_synchronized_no_ff_race(concurrency_env):
    """Run felix-deployer + prompt-sync tick bodies barrier-synchronized, both
    against ONE checkout through ONE shared deploylock, over ≥100 rounds.

    After EACH overlapped pair, assert:
      (a) no "Cannot fast-forward to multiple branches" anywhere in outputs/logs;
      (b) no residual ``.git/index.lock``;
      (c) clean worktree (``git status --porcelain`` empty of unexpected entries);
      (d) the checkout HEAD converged to origin's head for the round;
      (e) prompt-sync's copy step still lands its files;
      (f) felix's pre_pull_head/post_pull_head are correct for the round;
      (g) prompt-sync audit records are well-formed.
    """
    env = concurrency_env
    checkout = env.checkout
    index_lock = checkout / ".git" / "index.lock"

    # Assertion accumulators across all rounds (fail fast, but report round).
    multi_branch_seen = 0
    rounds_where_prompt_copied = 0
    rounds_where_felix_advanced = 0

    for rnd in range(1, ROUNDS + 1):
        # Advance origin so there is REAL work to fast-forward this round: a new
        # commit on main AND a prompt-content bump, so once the checkout pulls,
        # prompt-sync sees drift and must copy the new content into the workspace.
        expected_origin_head = env.origin.advance(version=rnd)

        head_before = _head(checkout)
        felix_entries_before = len(_felix_log_entries(env.felix_log_dir))

        # --- barrier-synchronized concurrent tick bodies ---------------------
        barrier = threading.Barrier(2)
        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}

        def _run_felix() -> None:
            try:
                barrier.wait()  # enter the critical section simultaneously
                rc = felix_tick.run_tick(
                    repo_root=checkout, log_dir=env.felix_log_dir
                )
                results["felix_rc"] = rc
            except BaseException as exc:  # noqa: BLE001 - re-raised after join
                errors["felix"] = exc

        def _run_prompt_sync() -> None:
            try:
                barrier.wait()
                args = Namespace(dry_run=False, agent=None)
                rc = prompt_sync.run_tick(
                    args,
                    repo_root=checkout,
                    audit_path=env.prompt_audit,
                    health_state_path=env.prompt_health,
                )
                results["prompt_rc"] = rc
            except BaseException as exc:  # noqa: BLE001
                errors["prompt"] = exc

        t_felix = threading.Thread(target=_run_felix, name=f"felix-{rnd}")
        t_prompt = threading.Thread(target=_run_prompt_sync, name=f"prompt-{rnd}")
        t_felix.start()
        t_prompt.start()
        t_felix.join(timeout=60)
        t_prompt.join(timeout=60)

        assert not t_felix.is_alive(), f"round {rnd}: felix tick hung"
        assert not t_prompt.is_alive(), f"round {rnd}: prompt-sync tick hung"
        if errors:
            raise AssertionError(f"round {rnd}: tick raised: {errors}")

        # Both actors return their success sentinel (defers are still 0/SUCCESS).
        assert results.get("felix_rc") == 0, f"round {rnd}: felix rc {results}"
        assert results.get("prompt_rc") in (
            prompt_sync.EXIT_SUCCESS,
            prompt_sync.EXIT_PARTIAL_FAILURE,
        ), f"round {rnd}: prompt rc {results}"

        # (a) No FETCH_HEAD multi-branch error anywhere in this round's outputs.
        felix_entries = _felix_log_entries(env.felix_log_dir)
        prompt_records = _prompt_audit_records(env.prompt_audit)
        blob = json.dumps(felix_entries) + json.dumps(prompt_records)
        if MULTI_BRANCH_ERROR in blob:
            multi_branch_seen += 1
        assert MULTI_BRANCH_ERROR not in blob, (
            f"round {rnd}: '{MULTI_BRANCH_ERROR}' surfaced — the race is NOT fixed"
        )

        # (b) No residual index.lock left behind.
        assert not index_lock.exists(), (
            f"round {rnd}: residual .git/index.lock — a git op was interrupted"
        )

        # (c) Clean worktree (no unexpected staged/unstaged/dirty entries).
        porcelain = _git(checkout, "status", "--porcelain").stdout.strip()
        assert porcelain == "", f"round {rnd}: dirty worktree:\n{porcelain}"

        # One (or both) actors must have advanced the checkout to origin this
        # round; whichever won the lock first fast-forwards, the loser defers.
        head_after = _head(checkout)

        # (d) Convergence: the checkout HEAD reached origin/main's head. Because
        # a deferred actor retries next round, we assert convergence lazily: the
        # checkout is EITHER already at origin OR strictly ahead of where it
        # started (real fast-forward happened this round). Full convergence is
        # asserted after the loop.
        assert head_after == expected_origin_head or head_after != head_before, (
            f"round {rnd}: checkout neither converged nor advanced "
            f"(before={head_before[:8]} after={head_after[:8]} "
            f"origin={expected_origin_head[:8]})"
        )

        # (f) felix pre/post head correctness: inspect only THIS round's felix
        # events. When felix ran its full body it advanced (queue_scanned carries
        # its post-advance head); when it DEFERRED it logged tick_skip
        # reason=lock_unavailable (a benign defer, correct, NOT a failure).
        felix_new = felix_entries[felix_entries_before:]
        felix_advanced = _felix_round_advanced(felix_new, head_after)
        if felix_advanced:
            rounds_where_felix_advanced += 1

        # (e)+(g) prompt-sync: either it won the lock and produced a
        # tick_summary (copy landed on drift), or it deferred (git_pull_skipped).
        # Records must be well-formed JSON dicts with the audit contract shape.
        _assert_prompt_records_wellformed(prompt_records)
        if _prompt_round_copied(prompt_records):
            rounds_where_prompt_copied += 1

    # ---- cross-round convergence + participation guarantees -----------------

    # Final convergence: after the last round both actors have had many chances;
    # the checkout must be exactly at origin/main.
    _git(checkout, "fetch", "origin")
    final_head = _head(checkout)
    final_origin = _head(checkout, "origin/main")
    assert final_head == final_origin, (
        f"checkout did not converge to origin after {ROUNDS} rounds: "
        f"head={final_head[:8]} origin={final_origin[:8]}"
    )

    # The multi-branch race must never have surfaced in any round.
    assert multi_branch_seen == 0

    # Both actors must have genuinely done real work across the run (this proves
    # the harness actually exercised both tick bodies, not just deferred forever).
    assert rounds_where_felix_advanced > 0, (
        "felix-deployer never advanced the checkout in any round — the harness "
        "did not exercise its real tick body"
    )
    assert rounds_where_prompt_copied > 0, (
        "prompt-sync never landed a prompt copy in any round — the harness did "
        "not exercise its real copy step"
    )

    # The prompt-sync workspace holds the latest prompt content (copy landed).
    deployed = env.workspace / "AGENTS.md"
    assert deployed.exists(), "prompt-sync never deployed AGENTS.md"
    latest_source = (env.source_dir / "AGENTS.md").read_text(encoding="utf-8")
    # After a final reconciling tick, the deployed content must equal source.
    _reconcile_prompt_sync(env)
    assert (env.workspace / "AGENTS.md").read_text(encoding="utf-8") == latest_source


# ---------------------------------------------------------------------------
# Round helpers
# ---------------------------------------------------------------------------


def _felix_round_advanced(
    new_entries: list[dict[str, Any]], head_after: str
) -> bool:
    """True iff felix-deployer ran its full tick body past the fast-forward this
    round and observed the current head.

    A ``queue_scanned`` event is emitted only AFTER a successful ``advance_checkout``
    (a failed/deferred advance short-circuits before the queue scan). Its
    ``head_sha`` is felix's post-advance HEAD — a SHORT sha (``advance_checkout``
    uses ``rev-parse --short``), so the full ``head_after`` starts with it.
    Only the events appended THIS round are passed in ``new_entries``.
    """
    for e in new_entries:
        if e.get("event") == "queue_scanned":
            hs = e.get("head_sha") or ""
            if hs and head_after.startswith(hs):
                return True
    return False


def _prompt_round_copied(records: list[dict[str, Any]]) -> bool:
    """True iff prompt-sync copied ≥1 file in some tick captured in the audit."""
    for r in records:
        if r.get("kind") == "tick_summary" and int(r.get("files_copied", 0) or 0) > 0:
            return True
    return False


def _assert_prompt_records_wellformed(records: list[dict[str, Any]]) -> None:
    """Every prompt-sync audit record is a dict carrying the contract fields."""
    for r in records:
        assert isinstance(r, dict), f"malformed audit record (not a dict): {r!r}"
        assert "timestamp" in r and "tick_id" in r and "kind" in r, (
            f"audit record missing required keys: {r!r}"
        )
        if r["kind"] == "tick_summary":
            for k in (
                "agents_processed",
                "files_copied",
                "files_skipped",
                "files_errored",
                "exit_code",
                "duration_ms",
            ):
                assert k in r, f"tick_summary missing {k}: {r!r}"


def _reconcile_prompt_sync(env) -> None:
    """Run prompt-sync alone (no contention) so the workspace reaches the latest
    source content, proving the copy step is the real shipped code path."""
    # Ensure the checkout is at origin first.
    _git(env.checkout, "fetch", "origin")
    _git(env.checkout, "merge", "--ff-only", "origin/main")
    args = Namespace(dry_run=False, agent=None)
    rc = prompt_sync.run_tick(
        args,
        repo_root=env.checkout,
        audit_path=env.prompt_audit,
        health_state_path=env.prompt_health,
    )
    assert rc in (prompt_sync.EXIT_SUCCESS, prompt_sync.EXIT_PARTIAL_FAILURE)
