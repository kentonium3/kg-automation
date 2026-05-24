"""Configuration layer for the felix-doc-auditor driver.

Loads the default ``config.toml`` (or an operator-supplied override
via ``--config <path>``) using stdlib ``tomllib`` (Python 3.11+).

The Anthropic API key is held on disk at ``[llm].api_key_path``. It
is read by ``read_api_key()`` on demand and is NEVER logged or
echoed by this module (it does not call ``print``, ``logger``, or
return the key in any error message).

Path policy: all entries under ``[paths]`` and ``[llm].api_key_path``
MUST be absolute. ``load_config()`` raises ``ValueError`` on a
relative path unless ``allow_relative_paths=True`` (used by tests).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    """``[llm]`` section: model + API-key path + max_tokens."""

    model: str
    api_key_path: str
    max_tokens: int


@dataclass(frozen=True)
class PathsConfig:
    """``[paths]`` section: filesystem locations the driver reads/writes."""

    prompts_dir: str
    drift_events: str
    drift_cursor: str
    drift_unmapped: str
    signal_to_doc_map: str
    doc_domain_map: str
    activity_log_dir: str
    tick_signal_path: str


@dataclass(frozen=True)
class SignalsConfig:
    """``[signals]`` section: enabled signal-source adapters."""

    sources: list[str]


@dataclass(frozen=True)
class GitHubConfig:
    """``[github]`` section: repo + bot identity for actor-verification."""

    repo: str
    bot_identity: str


@dataclass(frozen=True)
class DriftInterpretationConfig:
    """``[drift_interpretation]`` section — Moment 0 feature flag + knobs.

    Introduced by mission ``drift-event-auto-resolution-01KS8J32`` (#362).
    Per FR-012/FR-013, the entire Moment 0 path is gated by ``enabled``;
    when ``False`` the pipeline runs in pre-#362 mode (file ``[doc-audit]``
    issue per matched mapping) for a clean rollback (NFR-007).

    Missing-block default: ``DriftInterpretationConfig(enabled=False, ...)``
    so a config that hasn't yet been updated keeps the pre-#362 behavior.
    """

    enabled: bool = False
    ledger_path: str = (
        "/data/services/security-monitor/logs/drift-events-ledger.jsonl"
    )
    model: str = "claude-haiku-4-5-20251001"
    api_key_path: str = "/data/services/openclaw/secrets/anthropic"
    timeout_seconds: int = 30
    confidence_threshold: float = 0.80


@dataclass(frozen=True)
class AuditInterpretationConfig:
    """``[audit_interpretation]`` section — Moment 0 feature flag + knobs.

    Introduced by mission ``audit-interpretation-moment0-01KSBGBS`` (#400).
    Mirrors :class:`DriftInterpretationConfig` 1:1 in field shape — the
    commit-audit Moment 0 path is the structural twin of drift Moment 0
    (per spec C-004). Per FR-013, the entire commit-audit Moment 0 path
    is gated by ``enabled``; when ``False`` the pipeline behaves
    identically to the pre-#400 no-proposals path (lock release +
    "no automatable edits" comment from ``handle_audit_routing.py``)
    for a clean rollback.

    Missing-block default: ``AuditInterpretationConfig(enabled=False, ...)``
    so a config that hasn't yet been updated keeps the pre-#400 behavior.
    """

    enabled: bool = False
    ledger_path: str = (
        "/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl"
    )
    model: str = "claude-haiku-4-5-20251001"
    api_key_path: str = "/data/services/openclaw/secrets/anthropic"
    timeout_seconds: int = 30
    confidence_threshold: float = 0.80


@dataclass(frozen=True)
class Config:
    """Top-level driver configuration. Composes the section dataclasses.

    ``drift_interpretation`` defaults to an ``enabled=False`` block so
    legacy callers that constructed :class:`Config` without the new
    section keep working unchanged (pre-#362 pipeline behavior).
    ``audit_interpretation`` follows the same default-disabled pattern
    so pre-#400 callers and tests keep working without code changes.
    """

    llm: LLMConfig
    paths: PathsConfig
    signals: SignalsConfig
    github: GitHubConfig
    drift_interpretation: DriftInterpretationConfig = field(
        default_factory=DriftInterpretationConfig
    )
    audit_interpretation: AuditInterpretationConfig = field(
        default_factory=AuditInterpretationConfig
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _require_absolute(label: str, value: str) -> None:
    if not Path(value).is_absolute():
        raise ValueError(
            f"Config path {label!r} must be absolute, got: {value!r}"
        )


def load_config(
    path: Optional[Path] = None,
    *,
    allow_relative_paths: bool = False,
) -> Config:
    """Load and validate a driver Config.

    Args:
        path: Path to a TOML file. Defaults to the in-tree
            ``scripts/doc_audit/config.toml`` when ``None``.
        allow_relative_paths: Bypass the absolute-path policy on
            ``[paths]`` and ``[llm].api_key_path``. Tests use this
            to point at ``tmp_path`` subtrees without invoking the
            production layout.

    Raises:
        FileNotFoundError: If ``path`` (or the default file) does
            not exist.
        ValueError: On malformed TOML or relative paths in production
            mode.
    """

    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Driver config not found: {config_path}"
        )

    try:
        with config_path.open("rb") as fp:
            raw = tomllib.load(fp)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(
            f"Driver config is not valid TOML ({config_path}): {exc}"
        ) from exc

    try:
        llm = LLMConfig(
            model=raw["llm"]["model"],
            api_key_path=raw["llm"]["api_key_path"],
            max_tokens=int(raw["llm"]["max_tokens"]),
        )
        paths = PathsConfig(
            prompts_dir=raw["paths"]["prompts_dir"],
            drift_events=raw["paths"]["drift_events"],
            drift_cursor=raw["paths"]["drift_cursor"],
            drift_unmapped=raw["paths"]["drift_unmapped"],
            signal_to_doc_map=raw["paths"]["signal_to_doc_map"],
            doc_domain_map=raw["paths"]["doc_domain_map"],
            activity_log_dir=raw["paths"]["activity_log_dir"],
            tick_signal_path=raw["paths"]["tick_signal_path"],
        )
        signals = SignalsConfig(sources=list(raw["signals"]["sources"]))
        github = GitHubConfig(
            repo=raw["github"]["repo"],
            bot_identity=raw["github"]["bot_identity"],
        )
    except KeyError as exc:
        raise ValueError(
            f"Driver config {config_path} is missing required key: {exc}"
        ) from exc

    # ``[drift_interpretation]`` is optional. A config that has not yet
    # been updated to include the block defaults to ``enabled=False`` so
    # the pipeline behaves exactly like the pre-#362 path (FR-013, NFR-007).
    drift_raw = raw.get("drift_interpretation", {})
    try:
        drift_interpretation = DriftInterpretationConfig(
            enabled=bool(drift_raw.get("enabled", False)),
            ledger_path=str(
                drift_raw.get(
                    "ledger_path",
                    "/data/services/security-monitor/logs/drift-events-ledger.jsonl",
                )
            ),
            model=str(
                drift_raw.get("model", "claude-haiku-4-5-20251001")
            ),
            api_key_path=str(
                drift_raw.get(
                    "api_key_path",
                    raw["llm"]["api_key_path"],
                )
            ),
            timeout_seconds=int(drift_raw.get("timeout_seconds", 30)),
            confidence_threshold=float(
                drift_raw.get("confidence_threshold", 0.80)
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Driver config {config_path} has invalid "
            f"[drift_interpretation] block: {exc}"
        ) from exc

    # ``[audit_interpretation]`` is optional. Mirrors the
    # ``[drift_interpretation]`` default-disabled pattern so a config
    # without the block keeps the pre-#400 no-proposals behavior
    # (FR-013).
    audit_raw = raw.get("audit_interpretation", {})
    try:
        audit_interpretation = AuditInterpretationConfig(
            enabled=bool(audit_raw.get("enabled", False)),
            ledger_path=str(
                audit_raw.get(
                    "ledger_path",
                    "/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl",
                )
            ),
            model=str(
                audit_raw.get("model", "claude-haiku-4-5-20251001")
            ),
            api_key_path=str(
                audit_raw.get(
                    "api_key_path",
                    raw["llm"]["api_key_path"],
                )
            ),
            timeout_seconds=int(audit_raw.get("timeout_seconds", 30)),
            confidence_threshold=float(
                audit_raw.get("confidence_threshold", 0.80)
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Driver config {config_path} has invalid "
            f"[audit_interpretation] block: {exc}"
        ) from exc

    if not allow_relative_paths:
        _require_absolute("llm.api_key_path", llm.api_key_path)
        for field_name in (
            "prompts_dir",
            "drift_events",
            "drift_cursor",
            "drift_unmapped",
            "signal_to_doc_map",
            "doc_domain_map",
            "activity_log_dir",
            "tick_signal_path",
        ):
            _require_absolute(
                f"paths.{field_name}", getattr(paths, field_name)
            )
        # Only enforce absolute-path policy on the drift_interpretation
        # block when the feature is enabled. A disabled block with default
        # placeholder paths should not block test or sandbox configs.
        if drift_interpretation.enabled:
            _require_absolute(
                "drift_interpretation.ledger_path",
                drift_interpretation.ledger_path,
            )
            _require_absolute(
                "drift_interpretation.api_key_path",
                drift_interpretation.api_key_path,
            )
        # Same gating for the audit_interpretation block (#400).
        if audit_interpretation.enabled:
            _require_absolute(
                "audit_interpretation.ledger_path",
                audit_interpretation.ledger_path,
            )
            _require_absolute(
                "audit_interpretation.api_key_path",
                audit_interpretation.api_key_path,
            )

    return Config(
        llm=llm,
        paths=paths,
        signals=signals,
        github=github,
        drift_interpretation=drift_interpretation,
        audit_interpretation=audit_interpretation,
    )


# ---------------------------------------------------------------------------
# API-key reader (never logs)
# ---------------------------------------------------------------------------


def read_api_key(config: Config) -> str:
    """Read the Anthropic API key from ``config.llm.api_key_path``.

    Returns the file contents with surrounding whitespace stripped.

    This function NEVER logs the key, NEVER includes the key in an
    error message, and NEVER returns the key via any side channel
    other than its return value.
    """

    key_path = Path(config.llm.api_key_path)
    try:
        raw = key_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        # Intentionally only surface the path, not any value.
        raise FileNotFoundError(
            f"API key file not found at {key_path}"
        ) from exc
    return raw.strip()
