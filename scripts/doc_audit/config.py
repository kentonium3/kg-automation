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
from dataclasses import dataclass
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
class Config:
    """Top-level driver configuration. Composes the section dataclasses."""

    llm: LLMConfig
    paths: PathsConfig
    signals: SignalsConfig
    github: GitHubConfig


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

    return Config(llm=llm, paths=paths, signals=signals, github=github)


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
