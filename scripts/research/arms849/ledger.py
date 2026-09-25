"""The ledger — the one place the run's state lives (WP03; data-model.md §Ledger; contracts/ledger-schema.md).

An append-only JSONL file. Line 1 is the immutable **header**, which binds the
ledger to one corpus, one prompt, one question manifest, one serving
configuration and one set of code hashes (research.md D-16); every later line
is a record: ``attempt_start``, ``run``, ``calibration`` or ``event``.

Three properties, each because a run without it produces numbers that look
like numbers from a run with it:

* **Binding.** A resume compares every header field against the environment
  and refuses on any difference — runs from two configurations averaged
  together are indistinguishable from runs from one.
* **Durability.** An ``attempt_start`` row precedes every attempt (a death
  mid-cell still counts toward the three); every append is flushed and
  fsynced; the reader tolerates exactly one torn FINAL line under the lock
  and rejects any interior corruption (D-12).
* **Never averaging a non-scored cell.** ``summarise`` sums ``ok`` rows only;
  ``exceeds_model_context``, ``error`` and ``not_implemented`` are counted,
  never summed (Engineering Principle 14).

The per-attempt timeout is a VALUE this module stores on a row; enforcing it
is the harness's job (WP08).
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import pathlib
import re
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from scripts.research.arms849 import prompt as prompt_mod
from scripts.research.arms849 import questions as questions_mod
from scripts.research.load_849_corpus import (
    REGISTRATION,
    UnfrozenCorpus,
    verify_registration,
)

__all__ = [
    "ARMS", "MAX_ATTEMPTS", "OUTCOMES", "REPEATS", "SCORED_OUTCOME",
    "AttemptsExhausted", "Binding", "Header", "Ledger", "LedgerBoundToAnotherConfig",
    "LedgerClosed", "LedgerCorrupt", "LedgerLocked", "LedgerWriteFailed", "RunKey", "SecondScoredRow", "open_ledger", "plan_keys",
]

ARMS = ("G", "D", "R")
REPEATS = 3
MAX_ATTEMPTS = 3
#: Fields the ledger itself authors on a run row; a payload carrying one is refused.
RESERVED_RUN_FIELDS = frozenset({"record", "arm", "question", "repeat", "attempt", "outcome", "serving", "ts",
                                 "truncated"})   # truncated is DERIVED from finish_reason
#: The run-row contract (data-model.md "Row run"): a row missing a required field is refused.
RUN_ROW_ALWAYS = ("ask_time", "elapsed_s")                       # every run row, any outcome
ERROR_ROW_FIELDS = ("error", "peak_gtt_gib")                       # every error row
SCORED_INT_FIELDS = ("prompt_tokens", "client_prompt_tokens", "assembled_context_tokens", "output_tokens",
                     "cache_read_tokens", "uncached_tokens", "cache_write_tokens", "seed",
                     "events_loaded", "nodes_loaded", "edges_loaded", "links_loaded")
SCORED_FLOAT_FIELDS = ("cache_fraction", "prefill_s", "generation_s", "generation_tok_s", "peak_gtt_gib")
SCORED_OTHER_FIELDS = ("finish_reason", "cache_state", "assembled_context_sha256", "text", "plan")
SCORED_ROW_FIELDS = SCORED_INT_FIELDS + SCORED_FLOAT_FIELDS + SCORED_OTHER_FIELDS
SCORED_ARM_FIELDS = {"G": ("falkordb_rss_peak_mib",), "R": ("r_g_ratio",), "D": ()}
D_ROW_FIELDS = ("context_limit_applied",)          # every D row, any outcome
CACHE_STATES = ("cold", "warm")
FINISH_REASONS = ("stop", "length")
CONTEXT_LIMITS = ("trained", "permitted")
QUESTION_IDS = tuple(q.id for q in questions_mod.QUESTIONS)
REFUSAL_PREFIX = "ArmRefusal:"                      # an error row so prefixed is terminal on attempt 1
RESERVED_CALIBRATION_FIELDS = frozenset({"record", "ts"})
SCORED_OUTCOME = "ok"
OUTCOMES = ("ok", "exceeds_model_context", "error", "not_implemented")
Outcome = Literal["ok", "exceeds_model_context", "error", "not_implemented"]

#: Code whose content is bound into the header (D-16). Relative to the repo root.
BOUND_CODE_GLOBS = ("scripts/research/arms849/*.py", "scripts/research/run_849_harness.py",
                    "scripts/research/load_849_corpus.py")


def _utc_now() -> str:
    # Explicit UTC, never a bare astimezone() (#759).
    return datetime.now(timezone.utc).isoformat()


_SHA256 = re.compile(r"[0-9a-f]{64}")  # used with fullmatch: `$` would admit a trailing newline (Codex c9)


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive int, got {value!r}")
    return value


def _require_sha256(name: str, value: Any) -> None:
    """A gate record sha is a lowercase 64-hex string — None, a placeholder or the wrong length is
    a missing binding wearing a value (Codex WP03 c7). ``fullmatch``, not ``$``: a 65-byte
    "<hex>\\n" is not a digest either (Codex WP03 c9)."""
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a 64-hex sha256, got {value!r}")


def _require_measurement(name: str, value: Any) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")


class LedgerBoundToAnotherConfig(RuntimeError):
    """The ledger's header does not match the environment; never append."""


class LedgerLocked(RuntimeError):
    """Another process holds this ledger."""


class LedgerCorrupt(RuntimeError):
    """A malformed line that is not the final one."""


class LedgerClosed(RuntimeError):
    """An append after close(): the lock is no longer held, so the write is not ours to make."""


class LedgerWriteFailed(RuntimeError):
    """An append hit an I/O error. The line may or may not have reached disk, so the in-memory rows
    can no longer be trusted: the ledger is poisoned, every further write is refused and the lock
    is released. Reopen it — the file is the only truth (Codex WP03 c14)."""


class AttemptsExhausted(RuntimeError):
    """A fourth attempt was requested for a key (FR-007 allows three)."""


class SecondScoredRow(RuntimeError):
    """An `ok` row already exists for this key (invariant I2)."""


@dataclass(frozen=True)
class RunKey:
    arm: str
    question: str
    repeat: int

    def __post_init__(self) -> None:
        # data-model.md § Cell: a key outside the domain is a phantom cell (Opus WP03 c11).
        if self.arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}, got {self.arm!r}")
        if self.question not in QUESTION_IDS:
            raise ValueError(f"question must be one of {QUESTION_IDS}, got {self.question!r}")
        if type(self.repeat) is not int or not 1 <= self.repeat <= REPEATS:
            raise ValueError(f"repeat must be an int in 1..{REPEATS}, got {self.repeat!r}")

    def as_dict(self) -> dict[str, Any]:
        return {"arm": self.arm, "question": self.question, "repeat": self.repeat}

    @classmethod
    def of(cls, row: dict[str, Any]) -> RunKey:
        """The key of a persisted row, WITHOUT coercion: a repeat of 1.9, "1" or True is not
        repeat 1 — int() made it so and let an invalid cell satisfy the repeat-1 checks on
        resume (Codex WP03 c15). __post_init__ then validates the domain."""
        arm, question, repeat = row.get("arm"), row.get("question"), row.get("repeat")
        if not isinstance(arm, str) or not isinstance(question, str):
            raise ValueError(f"arm and question must be strings, got {arm!r}, {question!r}")
        if type(repeat) is not int:
            raise ValueError(f"repeat must be an int, got {repeat!r}")
        return cls(arm, question, repeat)


def plan_keys(arms: Sequence[str] = ARMS, questions: Sequence[str] | None = None,
              repeats: int = REPEATS) -> list[RunKey]:
    """Arm-major, repeat-major, questions in manifest (ask_time) order — protocol (C-008)."""
    qs = list(questions) if questions is not None else [q.id for q in questions_mod.QUESTIONS]
    return [RunKey(a, q, r) for a in arms for r in range(1, repeats + 1) for q in qs]


# --------------------------------------------------------------------------
# Binding and header
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """Everything a resume must find unchanged (D-16)."""

    registration_commit: str
    corpus: dict[str, str]
    prompt_hash: str
    question_manifest_sha: str
    serving: dict[str, Any]
    model_context_tokens: int
    limit_applied: str
    run_env_commit: str
    run_env_manifest_sha: str
    code_hashes: dict[str, str]
    preflight_sha: str
    gate_host_sha: str            # the HOST-phase gate record (design-lead ruling 2026-09-25)
    gate_container_sha: str       # the CONTAINER-phase gate record

    @classmethod
    def from_environment(cls, corpus_dir: pathlib.Path, serving: dict[str, Any],
                         limit_applied: str, run_env_commit: str, run_env_manifest_sha: str,
                         preflight_sha: str, gate_host_sha: str, gate_container_sha: str,
                         repo_root: pathlib.Path | None = None,
                         model_context_tokens: int | None = None) -> Binding:
        # VERIFIED, not computed-and-stored: a missing or tampered file is refused here, so the
        # header can never bind a partial or foreign corpus (Opus WP03 c10).
        try:
            corpus = verify_registration(pathlib.Path(corpus_dir))
        except UnfrozenCorpus as exc:
            raise LedgerBoundToAnotherConfig(str(exc)) from exc
        if limit_applied not in CONTEXT_LIMITS:
            raise ValueError(f"limit_applied must be one of {CONTEXT_LIMITS}, got {limit_applied!r}")
        ok_p, detail_p = prompt_mod.verify()
        ok_q, detail_q = questions_mod.verify()
        if not (ok_p and ok_q):
            raise LedgerBoundToAnotherConfig(f"registered constants do not verify: {detail_p}; {detail_q}")
        for name, value in (("preflight_sha", preflight_sha), ("gate_host_sha", gate_host_sha),
                            ("gate_container_sha", gate_container_sha)):
            _require_sha256(name, value)
        return cls(
            registration_commit=str(REGISTRATION["commit"]), corpus=corpus,
            prompt_hash=prompt_mod.REGISTERED_DIGEST, question_manifest_sha=questions_mod.MANIFEST_DIGEST,
            serving=dict(serving), model_context_tokens=_positive_int("model_context_tokens", model_context_tokens if model_context_tokens is not None else serving.get("n_ctx")),
            limit_applied=limit_applied, run_env_commit=run_env_commit,
            run_env_manifest_sha=run_env_manifest_sha, code_hashes=code_hashes(repo_root),
            preflight_sha=preflight_sha, gate_host_sha=gate_host_sha,
            gate_container_sha=gate_container_sha,
        )

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def code_hashes(repo_root: pathlib.Path | None = None) -> dict[str, str]:
    """sha256 of every bound code file's CONTENT, keyed by repo-relative path."""
    root = pathlib.Path(repo_root) if repo_root else pathlib.Path(__file__).resolve().parents[3]
    out: dict[str, str] = {}
    for pattern in BOUND_CODE_GLOBS:
        for p in sorted(root.glob(pattern)):
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@dataclass
class Header:
    binding: Binding
    started: str
    blinding_seed: int
    plan: int
    record: str = "header"

    def as_dict(self) -> dict[str, Any]:
        return {"record": "header", "started": self.started, "blinding_seed": self.blinding_seed,
                "plan": self.plan, **self.binding.as_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Header:
        fields = {k: d[k] for k in Binding.__dataclass_fields__}
        return cls(binding=Binding(**fields), started=d["started"], blinding_seed=int(d["blinding_seed"]),
                   plan=int(d["plan"]))


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


@dataclass
class Summary:
    n_scored: int
    mean_assembled_tokens: float | None
    range_assembled_tokens: tuple[int, int] | None
    mean_prompt_tokens: float | None
    range_prompt_tokens: tuple[int, int] | None
    cache_read_tokens: int
    uncached_tokens: int
    cache_write_tokens: int
    cold: int
    warm: int
    r_g_ratios: list[Any]
    counts: dict[str, int]
    attempts: int


class Ledger:
    """One open ledger: header verified, lock held, rows parsed."""

    def __init__(self, path: pathlib.Path, header: Header, rows: list[dict[str, Any]],
                 lock_fd: int) -> None:
        self.path = pathlib.Path(path)
        # The authoritative header is PRIVATE and its own deep copy: a caller who edits
        # `ledger.header.binding.serving` edits a copy (Codex WP03 c4).
        self._header = Header.from_dict(copy.deepcopy(header.as_dict()))
        self._rows = rows
        self._lock_fd = lock_fd
        self._failed: str | None = None          # set by the first append I/O failure; never cleared

    @property
    def header(self) -> Header:
        """A deep copy; editing it changes nothing the ledger compares against."""
        return Header.from_dict(copy.deepcopy(self._header.as_dict()))

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._lock_fd >= 0:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = -1

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- append ------------------------------------------------------------

    def _append(self, record: dict[str, Any], *, keep: bool = True) -> None:
        """One JSON line, flushed and fsynced before returning (NFR-001); never after close().
        ``keep=False`` writes the header without making it a row: ``rows`` is the same on a
        fresh and a resumed ledger."""
        if self._failed is not None:
            raise LedgerWriteFailed(f"{self.path}: {self._failed}")
        if self._lock_fd < 0:
            raise LedgerClosed(f"{self.path}: ledger is closed; the lock is not held")
        try:
            line = json.dumps(record, sort_keys=True)          # no default=str: a set or datetime is refused
        except TypeError as exc:
            raise ValueError(f"payload is not JSON-serialisable: {exc}") from exc
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            # An fsync failure after a successful flush leaves the row on disk but absent from
            # `_rows`; a retry then records a second `ok` row and both average after resume
            # (Codex WP03 c14). Whether or not the line landed, memory and disk may now differ,
            # so the ledger is poisoned: writes refused, lock released, reopen re-reads the file.
            self._failed = (f"append failed ({exc.__class__.__name__}: {exc}); the row may or may not "
                            f"be on disk — reopen the ledger, the file is the truth")
            self.close()
            raise LedgerWriteFailed(f"{self.path}: {self._failed}") from exc
        if keep:
            self._rows.append(json.loads(line))

    @property
    def rows(self) -> list[dict[str, Any]]:
        """Deep copies: a caller can never edit the rows the invariants are checked against."""
        return copy.deepcopy(self._rows)

    def run_rows(self) -> list[dict[str, Any]]:
        return copy.deepcopy([r for r in self._rows if r.get("record") == "run"])

    # -- attempts ----------------------------------------------------------

    def attempts_for(self, key: RunKey) -> int:
        return sum(1 for r in self._rows if r.get("record") == "attempt_start" and RunKey.of(r) == key)

    def begin_attempt(self, key: RunKey) -> int:
        """Append the attempt_start row BEFORE anything happens (D-12); return the attempt number."""
        n = self._check_attempt_start(key)
        self._append({"record": "attempt_start", **key.as_dict(), "attempt": n, "ts": _utc_now()})
        return n

    def _check_attempt_start(self, key: RunKey) -> int:
        """The invariants an attempt_start row must satisfy against the rows so far; returns the
        attempt number. Shared by begin_attempt() and the resume replay (Codex WP03 c14)."""
        if self._terminal_row(key) is not None:
            raise SecondScoredRow(f"{key} is already terminal ({self._terminal_row(key)})")
        if self.terminal(key) == "error" and self.attempts_for(key) < MAX_ATTEMPTS:
            raise SecondScoredRow(f"{key} is terminal: a configuration refusal is never retried")
        n = self.attempts_for(key) + 1
        if n > MAX_ATTEMPTS:
            # Three attempts begun and none terminal: exhausted (FR-007, D-12) — the harness
            # catches THIS type, so it must be the one raised (Opus WP03 c10).
            raise AttemptsExhausted(f"{key} already used {MAX_ATTEMPTS} attempts")
        return n

    def record(self, key: RunKey, outcome: Outcome, row: dict[str, Any],
               serving: dict[str, Any]) -> dict[str, Any]:
        """Append the ONE `run` row for the current attempt, enforcing I2–I4, serving equality
        and the scored-row telemetry contract. Authoritative fields are set last so a payload
        can never overwrite them; carrying one is refused outright."""
        attempt = self._check_run(key, outcome, row, serving)
        full = {**row, "record": "run", **key.as_dict(), "attempt": attempt, "outcome": outcome,
                "serving": serving, "ts": _utc_now()}
        if outcome == SCORED_OUTCOME:
            full["truncated"] = row["finish_reason"] == "length"     # derived, never supplied
        self._append(full)
        return copy.deepcopy(self._rows[-1])                          # the round-tripped row, as persisted

    def _check_run(self, key: RunKey, outcome: Outcome, row: dict[str, Any],
                   serving: dict[str, Any]) -> int:
        """Every invariant a run row must satisfy against the rows so far (I2–I4, serving
        equality, the telemetry contract, D-10/D-11 ordering); returns the attempt number.
        Shared by record() and the resume replay, so a persisted row the ledger would have
        refused to write is refused on read (Codex WP03 c14)."""
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        reserved = RESERVED_RUN_FIELDS & set(row)
        if reserved:
            raise ValueError(f"payload carries ledger-authored fields {sorted(reserved)}")
        if serving != self._header.binding.serving:
            raise LedgerBoundToAnotherConfig("serving configuration differs from the header on append")
        if outcome == SCORED_OUTCOME and any(
                r.get("record") == "run" and r.get("outcome") == SCORED_OUTCOME and RunKey.of(r) == key
                for r in self._rows):
            raise SecondScoredRow(f"{key} already has an ok row")
        attempt = self.attempts_for(key)
        if attempt == 0:
            raise ValueError(f"{key}: record() before begin_attempt()")
        if any(r.get("record") == "run" and RunKey.of(r) == key and r.get("attempt") == attempt
               for r in self._rows):
            raise ValueError(f"{key}: attempt {attempt} already has a result; begin_attempt() first")
        missing = [f for f in RUN_ROW_ALWAYS if f not in row]
        if key.arm == "D":
            missing += [f for f in D_ROW_FIELDS if f not in row]
        if outcome == "error":
            missing += [f for f in ERROR_ROW_FIELDS if f not in row]
        if outcome == "exceeds_model_context":
            if key.arm != "D":
                raise ValueError("exceeds_model_context is a D outcome only (data-model.md § Outcome)")
            pt = row.get("prompt_tokens")
            if type(pt) is not int:
                raise ValueError(f"exceeds_model_context row must carry an int prompt_tokens, got {pt!r}")
            if pt <= self._header.binding.model_context_tokens:
                raise ValueError(f"exceeds_model_context row must carry prompt_tokens > model context ({pt})")
        if outcome == SCORED_OUTCOME:
            missing += [f for f in SCORED_ROW_FIELDS + SCORED_ARM_FIELDS.get(key.arm, ()) if f not in row]
        if missing:
            raise ValueError(f"{key} {outcome} row is missing required telemetry {missing}")
        if key.arm == "D" and row["context_limit_applied"] not in CONTEXT_LIMITS:
            raise ValueError(f"context_limit_applied must be one of {CONTEXT_LIMITS}")
        if key.arm == "D" and row["context_limit_applied"] != self._header.binding.limit_applied:
            raise ValueError(f"D row applied the {row['context_limit_applied']} limit under a header bound to "
                             f"{self._header.binding.limit_applied} (D-11: one limit per ledger)")
        if key.arm == "R" and outcome == SCORED_OUTCOME and self.calibration() is None:
            raise ValueError("an R ok row needs the calibration record first (D-10: k is never defaulted)")
        # A measurement is a FINITE non-negative number — None, NaN and inf are a missing
        # measurement wearing a value (Codex WP03 c5); error text is a non-empty string.
        if outcome == SCORED_OUTCOME:
            for f in SCORED_INT_FIELDS:
                if type(row[f]) is not int or row[f] < 0:
                    raise ValueError(f"scored row field {f} must be a non-negative int, got {row[f]!r}")
            for f in SCORED_FLOAT_FIELDS + tuple(x for x in SCORED_ARM_FIELDS.get(key.arm, ()) if x != "r_g_ratio"):
                _require_measurement(f, row[f])
        if outcome == "error":
            if not isinstance(row["error"], str) or not row["error"].strip():
                raise ValueError("error rows must carry a non-empty error string")
            _require_measurement("peak_gtt_gib", row["peak_gtt_gib"])
        if outcome == SCORED_OUTCOME:
            if row["cache_state"] not in CACHE_STATES:
                raise ValueError(f"cache_state must be one of {CACHE_STATES}, got {row['cache_state']!r}")
            if row["finish_reason"] not in FINISH_REASONS:
                raise ValueError(f"finish_reason must be one of {FINISH_REASONS}, got {row['finish_reason']!r}")
            sha = row["assembled_context_sha256"]
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise ValueError("assembled_context_sha256 must be a 64-hex sha256 STRING (an int would "
                                 "compare unequal after the JSON round-trip)")
            if not isinstance(row["text"], str) or not isinstance(row["plan"], dict):
                raise ValueError("text must be a str and plan a dict")
            # §2 (client count of the sent prompt) and §5 (server prompt_n + cache_n) are ONE quantity.
            if row["client_prompt_tokens"] != row["prompt_tokens"]:
                raise ValueError(f"client_prompt_tokens {row['client_prompt_tokens']} != prompt_tokens "
                                 f"{row['prompt_tokens']}: tokenizer drift is never a scored row")
            if key.arm == "R":
                ratio = row["r_g_ratio"]
                ok_ratio = (type(ratio) in (int, float) and math.isfinite(ratio) and ratio > 0) or (
                    isinstance(ratio, str) and ratio.startswith("unavailable:") and len(ratio) > len("unavailable:"))
                if not ok_ratio:
                    raise ValueError(f"r_g_ratio must be a positive number or 'unavailable:<reason>', got {ratio!r} (D-10)")
        _require_measurement("elapsed_s", row["elapsed_s"])
        return attempt

    def _terminal_row(self, key: RunKey) -> Outcome | None:
        """A recorded outcome that ends the key (ok / exceeds / not_implemented), or None."""
        for r in self._rows:
            if r.get("record") == "run" and RunKey.of(r) == key and \
                    r["outcome"] in ("ok", "exceeds_model_context", "not_implemented"):
                return r["outcome"]
        return None

    def terminal(self, key: RunKey) -> Outcome | None:
        found = self._terminal_row(key)
        if found is not None:
            return found
        # A configuration refusal is permanent: terminal error on the first attempt, no retries
        # (contracts/arm-interface.md dated note 2026-09-25).
        if any(r.get("record") == "run" and RunKey.of(r) == key and r.get("outcome") == "error"
               and str(r.get("error", "")).startswith(REFUSAL_PREFIX) for r in self._rows):
            return "error"
        # Three attempts begun and none reached a terminal outcome — whether they
        # recorded `error` or died before recording — is exhausted: terminal error.
        if self.attempts_for(key) >= MAX_ATTEMPTS:
            return "error"
        return None

    def pending_keys(self, plan: Iterable[RunKey]) -> list[RunKey]:
        """Protocol-ordered keys not yet terminal; an interrupted attempt counts as used."""
        return [k for k in plan if self.terminal(k) is None]

    # -- other record kinds ------------------------------------------------

    def event(self, kind: str, detail: Any = None) -> None:
        _check_event_kind(kind)                 # the same check replay applies (Codex WP03 c15)
        self._append({"record": "event", "kind": kind, "detail": detail, "ts": _utc_now()})

    def write_calibration(self, calibration: dict[str, Any]) -> None:
        """Once, and only after every G repeat-1 cell is scored (k comes from their medians, A3)."""
        self._check_calibration(calibration)
        self._append({**calibration, "record": "calibration", "ts": _utc_now()})

    def _check_calibration(self, calibration: dict[str, Any]) -> None:
        """Shared by write_calibration() and the resume replay (Codex WP03 c14)."""
        if self.calibration() is not None:
            raise ValueError("a calibration record already exists; it is written once")
        unscored = [q.id for q in questions_mod.QUESTIONS if self.terminal(RunKey("G", q.id, 1)) != SCORED_OUTCOME]
        if unscored:
            raise ValueError(f"calibration needs all eight G repeat-1 cells scored; unscored: {unscored}")
        reserved = RESERVED_CALIBRATION_FIELDS & set(calibration)
        if reserved:
            raise ValueError(f"calibration payload carries ledger-authored fields {sorted(reserved)}")

    def calibration(self) -> dict[str, Any] | None:
        found = next((r for r in self._rows if r.get("record") == "calibration"), None)
        return copy.deepcopy(found) if found is not None else None

    def has_terminal_error(self, arm: str, repeat: int) -> list[str]:
        """Questions whose (arm, repeat) cell is terminal `error` — D-10's halt input."""
        out = []
        for q in [q.id for q in questions_mod.QUESTIONS]:
            if self.terminal(RunKey(arm, q, repeat)) == "error":
                out.append(q)
        return out

    # -- reading -----------------------------------------------------------

    def grading_rows(self) -> list[dict[str, Any]]:
        return [r for r in self.run_rows() if r.get("outcome") == SCORED_OUTCOME]

    def summarise(self) -> dict[tuple[str, str], Summary]:
        """Per (arm, question): sums over `ok` rows only; every other key is COUNTED by its
        terminal outcome (`pending` when none yet), including keys that only ever began
        attempts and died — an exhausted cell with no run row is still a terminal error."""
        keys: set[RunKey] = set()
        attempts: dict[tuple[str, str], int] = {}
        for r in self._rows:
            if r.get("record") in ("run", "attempt_start"):
                keys.add(RunKey.of(r))
            if r.get("record") == "attempt_start":
                k = (r["arm"], r["question"]); attempts[k] = attempts.get(k, 0) + 1
        ok_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        counts: dict[tuple[str, str], dict[str, int]] = {}
        runs = [r for r in self._rows if r.get("record") == "run"]
        for key in sorted(keys, key=lambda k: (k.arm, k.question, k.repeat)):
            cell = (key.arm, key.question)
            counts.setdefault(cell, {})
            key_runs = [r for r in runs if RunKey.of(r) == key]
            # Every recorded non-scored row is COUNTED (T014), even when the key later
            # succeeded; a key exhausted with no run rows at all counts as one error.
            for r in key_runs:
                if r["outcome"] != SCORED_OUTCOME:
                    counts[cell][r["outcome"]] = counts[cell].get(r["outcome"], 0) + 1
            if not key_runs and self.terminal(key) == "error":
                counts[cell]["error"] = counts[cell].get("error", 0) + 1
            elif not key_runs:
                counts[cell]["pending"] = counts[cell].get("pending", 0) + 1     # in flight, nothing recorded
            ok_rows.setdefault(cell, []).extend(r for r in key_runs if r["outcome"] == SCORED_OUTCOME)
        out: dict[tuple[str, str], Summary] = {}
        for cell, cnt in counts.items():
            ok = ok_rows.get(cell, [])
            assembled = [int(r["assembled_context_tokens"]) for r in ok]
            prompt = [int(r["prompt_tokens"]) for r in ok]
            out[cell] = Summary(
                n_scored=len(ok),
                mean_assembled_tokens=statistics.fmean(assembled) if assembled else None,
                range_assembled_tokens=(min(assembled), max(assembled)) if assembled else None,
                mean_prompt_tokens=statistics.fmean(prompt) if prompt else None,
                range_prompt_tokens=(min(prompt), max(prompt)) if prompt else None,
                cache_read_tokens=sum(int(r["cache_read_tokens"]) for r in ok),
                uncached_tokens=sum(int(r["uncached_tokens"]) for r in ok),
                cache_write_tokens=sum(int(r["cache_write_tokens"]) for r in ok),
                cold=sum(1 for r in ok if r["cache_state"] == "cold"),
                warm=sum(1 for r in ok if r["cache_state"] == "warm"),
                r_g_ratios=[r["r_g_ratio"] for r in ok if "r_g_ratio" in r],
                counts=dict(cnt), attempts=attempts.get(cell, 0),
            )
        return out


# --------------------------------------------------------------------------
# open / read
# --------------------------------------------------------------------------


_UNPARSED = object()          # json.loads raised — distinct from a line that parsed to None


def _check_event_kind(kind: Any) -> None:
    """An event's kind is a non-empty string — enforced on write so the public writer can never
    persist a row the resume replay refuses (Codex WP03 c15)."""
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError(f"event kind must be a non-empty string, got {kind!r}")
_RECORD_KINDS = ("attempt_start", "run", "calibration", "event")


def _replay_validate(path: pathlib.Path, header: Header, rows: list[dict[str, Any]]) -> None:
    """Resume re-derives, row by row in file order, every invariant begin_attempt(), record() and
    write_calibration() enforce on write, so a persisted row the ledger would have refused to
    write — outcome "banana", an R `ok` row with no calibration record before it, a D row under
    the other limit, a run with no attempt_start, a retried refusal — is refused on read instead
    of reaching grading and averaging (Codex WP03 c14). Runs on the SCANNED rows before any
    repair: an invalid ledger is never modified by the opener that refuses it."""
    shadow = Ledger(path, header, [], -1)          # never writes: lock_fd -1, rows appended by hand
    for i, row in enumerate(rows, start=2):         # line 1 is the header
        kind = row.get("record")
        try:
            if not isinstance(row.get("ts"), str) or not row["ts"]:
                raise ValueError("record carries no ts")
            if kind == "attempt_start":
                key = RunKey.of(row)
                n = shadow._check_attempt_start(key)
                if type(row.get("attempt")) is not int or row["attempt"] != n:        # 1.0 == 1, so type first
                    raise ValueError(f"attempt_start carries attempt {row.get('attempt')!r}, expected {n}")
            elif kind == "run":
                key = RunKey.of(row)
                outcome = row.get("outcome")
                if outcome not in OUTCOMES:
                    raise ValueError(f"unknown outcome {outcome!r}")
                payload = {k: v for k, v in row.items() if k not in RESERVED_RUN_FIELDS}
                serving = row.get("serving")
                if not isinstance(serving, dict):
                    raise ValueError("run row carries no serving configuration")
                attempt = shadow._check_run(key, outcome, payload, serving)
                if type(row.get("attempt")) is not int or row["attempt"] != attempt:
                    raise ValueError(f"run row carries attempt {row.get('attempt')!r}, expected {attempt}")
                if outcome == SCORED_OUTCOME:
                    if row.get("truncated") is not (payload["finish_reason"] == "length"):
                        raise ValueError("truncated disagrees with finish_reason (it is derived, never supplied)")
                elif "truncated" in row:
                    raise ValueError("truncated on a non-scored row")
            elif kind == "calibration":
                shadow._check_calibration({k: v for k, v in row.items() if k not in RESERVED_CALIBRATION_FIELDS})
            elif kind == "event":
                _check_event_kind(row.get("kind"))
            else:
                raise ValueError(f"unknown record kind {kind!r} (expected one of {_RECORD_KINDS})")
        except (ValueError, KeyError, TypeError, SecondScoredRow, AttemptsExhausted,
                LedgerBoundToAnotherConfig) as exc:
            raise LedgerCorrupt(f"line {i} of {path} violates the ledger contract on resume: {exc}") from None
        shadow._rows.append(row)


def _scan(path: pathlib.Path) -> tuple[list[dict[str, Any]], str | None, int]:
    """Parse every line WITHOUT touching the file. Returns (rows, torn_kind, byte offset of
    the torn/unterminated final line). Exactly one torn FINAL line is tolerated; interior
    corruption raises."""
    raw = path.read_bytes()
    terminated = raw.endswith(b"\n")
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    parsed: list[dict[str, Any]] = []
    offset = 0
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        try:
            obj: Any = json.loads(line)
        except json.JSONDecodeError:
            obj = _UNPARSED
        if obj is _UNPARSED:
            if not last:
                raise LedgerCorrupt(f"malformed line {i + 1} of {len(lines)} in {path}") from None
            return parsed, "truncated_torn_tail", offset
        # A line that PARSES but is not an object — `null`, a number, a list, a string — is
        # corruption, never a torn tail: a parsed `None` is not "could not parse" (Codex WP03 c14).
        if not isinstance(obj, dict):
            raise LedgerCorrupt(f"line {i + 1} of {len(lines)} in {path} is not a JSON object")
        parsed.append(obj)
        if last and not terminated:
            return parsed, "terminated_final_line", offset
        offset += len(line) + 1
    return parsed, None, offset


def _repair(path: pathlib.Path, torn_kind: str, offset: int) -> None:
    """Repair IN PLACE — truncate at the byte offset (never a rewrite of the durable prefix)
    or terminate a complete final record that lost its newline — and fsync."""
    with path.open("r+b") as fh:
        if torn_kind == "truncated_torn_tail":
            fh.truncate(offset)
        else:
            fh.seek(0, os.SEEK_END)
            fh.write(b"\n")
        fh.flush()
        os.fsync(fh.fileno())


def _read_with_recovery(path: pathlib.Path) -> tuple[list[dict[str, Any]], str | None]:
    """Scan then repair (kept for callers that own the ledger already)."""
    rows, kind, offset = _scan(path)
    if kind:
        _repair(path, kind, offset)
    return rows, kind


def open_ledger(path: pathlib.Path, binding: Binding, blinding_seed: int, plan: int) -> Ledger:
    """Write the header on first use; on resume compare EVERY binding field; hold the lock."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        holder = ""
        try:
            holder = os.read(fd, 64).decode(errors="replace").strip()
        except OSError:
            pass
        os.close(fd)
        raise LedgerLocked(f"{path} is held by pid {holder or '?'}; one writer per ledger") from None
    try:
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        return _open_locked(path, binding, blinding_seed, plan, fd)
    except LedgerWriteFailed:
        raise                 # the header append failed: _append already closed fd (one owner — Codex c15)
    except BaseException:
        os.close(fd)          # releases the flock; a failed open must never hold the ledger
        raise


def _open_locked(path: pathlib.Path, binding: Binding, blinding_seed: int, plan: int, fd: int) -> Ledger:
    # Snapshot: the header's binding is OURS, not the caller's mutable dicts (Codex WP03 c3).
    binding = Binding(**copy.deepcopy(binding.as_dict()))
    # A Binding built directly (not via from_environment) is validated HERE, before any header
    # can be written: a ledger persisted with a bad sha could never resume (Codex WP03 c8).
    for name in ("preflight_sha", "gate_host_sha", "gate_container_sha"):
        _require_sha256(name, getattr(binding, name))
    if binding.limit_applied not in CONTEXT_LIMITS:
        raise ValueError(f"limit_applied must be one of {CONTEXT_LIMITS}, got {binding.limit_applied!r}")
    _positive_int("model_context_tokens", binding.model_context_tokens)
    if binding.corpus != REGISTRATION["files"]:
        raise LedgerBoundToAnotherConfig("binding.corpus is not the registered corpus fingerprints "
                                         "(data-model.md § Ledger: must equal REGISTRATION.files)")
    if not path.exists() or path.stat().st_size == 0:
        header = Header(binding=binding, started=_utc_now(), blinding_seed=blinding_seed, plan=plan)
        ledger = Ledger(path, header, [], fd)
        ledger._append(header.as_dict(), keep=False)      # the header is not a row (Opus c10, minor)
        return ledger

    # Validate the header and the binding BEFORE repairing anything: a mismatched
    # opener must not modify a ledger it is refused (Codex WP03 c3, minor).
    rows, torn_kind, offset = _scan(path)
    if not rows or rows[0].get("record") != "header":
        raise LedgerCorrupt(f"{path}: first line is not a header")
    missing_fields = [f for f in (*Binding.__dataclass_fields__, "blinding_seed", "plan", "started") if f not in rows[0]]
    if missing_fields:
        raise LedgerCorrupt(f"{path}: header lacks binding field(s) {missing_fields} — every gate sha is required")
    for name in ("preflight_sha", "gate_host_sha", "gate_container_sha"):
        try:
            _require_sha256(name, rows[0].get(name))
        except ValueError as exc:
            raise LedgerCorrupt(f"{path}: header {exc}") from None
    header = Header.from_dict(rows[0])
    differences = {k: (getattr(header.binding, k), getattr(binding, k))
                   for k in Binding.__dataclass_fields__ if getattr(header.binding, k) != getattr(binding, k)}
    # Every Header field that is not the record marker or the start time is compared too:
    # `plan` says whether this is the 72-cell primary or the 24-cell secondary and
    # `blinding_seed` fixes the grading ids (Opus WP03 c10).
    for k, ours in (("blinding_seed", int(blinding_seed)), ("plan", int(plan))):
        if getattr(header, k) != ours:
            differences[k] = (getattr(header, k), ours)
    if differences:
        detail = "\n".join(f"  {k}: ledger={a!r} environment={b!r}" for k, (a, b) in differences.items())
        raise LedgerBoundToAnotherConfig(
            f"{path} was written against a different configuration; runs from two configurations "
            f"averaged together are indistinguishable from runs from one. Start a new ledger.\n{detail}")
    _replay_validate(path, header, rows[1:])          # refuse an invalid ledger BEFORE touching it
    if torn_kind:
        _repair(path, torn_kind, offset)
    ledger = Ledger(path, header, rows[1:], fd)
    if torn_kind:
        ledger.event("recovered_torn_tail", {"how": torn_kind, "at": _utc_now()})
    return ledger
