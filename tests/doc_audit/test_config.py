"""Unit tests for ``doc_audit.config``.

WP02 / T010. Coverage target for ``config.py`` is >=85%.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_audit.config import (
    Config,
    GitHubConfig,
    LLMConfig,
    PathsConfig,
    SignalsConfig,
    load_config,
    read_api_key,
)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_default_config_loads(self) -> None:
        """Default ``scripts/doc_audit/config.toml`` is loadable."""
        cfg = load_config(None)
        assert isinstance(cfg, Config)
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.paths, PathsConfig)
        assert isinstance(cfg.signals, SignalsConfig)
        assert isinstance(cfg.github, GitHubConfig)
        assert cfg.llm.model == "claude-haiku-4-5"
        assert cfg.github.repo == "kentonium3/kg-automation"
        assert cfg.github.bot_identity == "kg-felix-bot"
        assert "gh_issue" in cfg.signals.sources
        assert "drift_event" in cfg.signals.sources

    def test_default_config_paths_are_absolute(self) -> None:
        cfg = load_config(None)
        assert Path(cfg.llm.api_key_path).is_absolute()
        for value in (
            cfg.paths.prompts_dir,
            cfg.paths.drift_events,
            cfg.paths.drift_cursor,
            cfg.paths.drift_unmapped,
            cfg.paths.signal_to_doc_map,
            cfg.paths.doc_domain_map,
            cfg.paths.activity_log_dir,
            cfg.paths.tick_signal_path,
        ):
            assert Path(value).is_absolute(), f"{value!r} must be absolute"

    def test_tmp_config_fixture_loads(self, tmp_config: Config) -> None:
        """The shared ``tmp_config`` fixture round-trips through load_config."""
        assert tmp_config.llm.model == "claude-haiku-4-5"
        assert Path(tmp_config.paths.activity_log_dir).exists()

    def test_override_path(self, tmp_path: Path) -> None:
        alt = tmp_path / "alt.toml"
        alt.write_text(
            f"""
[llm]
model = "claude-sonnet-5"
api_key_path = "{tmp_path / 'key'}"
max_tokens = 4096

[paths]
prompts_dir = "{tmp_path / 'p'}"
drift_events = "{tmp_path / 'de.jsonl'}"
drift_cursor = "{tmp_path / 'cursor'}"
drift_unmapped = "{tmp_path / 'um.jsonl'}"
signal_to_doc_map = "{tmp_path / 's.json'}"
doc_domain_map = "{tmp_path / 'd.json'}"
activity_log_dir = "{tmp_path / 'logs'}"
tick_signal_path = "{tmp_path / 'tick.json'}"

[signals]
sources = ["gh_issue"]

[github]
repo = "kentonium3/kg-automation"
bot_identity = "kg-felix-bot"
""",
            encoding="utf-8",
        )
        cfg = load_config(alt)
        assert cfg.llm.model == "claude-sonnet-5"
        assert cfg.llm.max_tokens == 4096
        assert cfg.signals.sources == ["gh_issue"]

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "does_not_exist.toml")

    def test_malformed_toml_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.toml"
        bad.write_text("this is = not = toml\n[unclosed", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid TOML"):
            load_config(bad)

    def test_missing_required_key_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        partial = tmp_path / "partial.toml"
        partial.write_text(
            f"""
[llm]
model = "claude-haiku-4-5"
api_key_path = "{tmp_path / 'key'}"
max_tokens = 1024

[paths]
prompts_dir = "{tmp_path / 'p'}"
drift_events = "{tmp_path / 'de.jsonl'}"
drift_cursor = "{tmp_path / 'cursor'}"
drift_unmapped = "{tmp_path / 'um.jsonl'}"
signal_to_doc_map = "{tmp_path / 's.json'}"
doc_domain_map = "{tmp_path / 'd.json'}"
activity_log_dir = "{tmp_path / 'logs'}"
tick_signal_path = "{tmp_path / 'tick.json'}"

[signals]
sources = ["gh_issue"]

# Intentionally missing [github] section
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required key"):
            load_config(partial)

    def test_relative_path_in_paths_rejected(self, tmp_path: Path) -> None:
        rel = tmp_path / "rel.toml"
        rel.write_text(
            f"""
[llm]
model = "claude-haiku-4-5"
api_key_path = "{tmp_path / 'key'}"
max_tokens = 1024

[paths]
prompts_dir = "relative/prompts"
drift_events = "{tmp_path / 'de.jsonl'}"
drift_cursor = "{tmp_path / 'cursor'}"
drift_unmapped = "{tmp_path / 'um.jsonl'}"
signal_to_doc_map = "{tmp_path / 's.json'}"
doc_domain_map = "{tmp_path / 'd.json'}"
activity_log_dir = "{tmp_path / 'logs'}"
tick_signal_path = "{tmp_path / 'tick.json'}"

[signals]
sources = ["gh_issue"]

[github]
repo = "kentonium3/kg-automation"
bot_identity = "kg-felix-bot"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be absolute"):
            load_config(rel)

    def test_relative_api_key_path_rejected(self, tmp_path: Path) -> None:
        rel = tmp_path / "rel_key.toml"
        rel.write_text(
            f"""
[llm]
model = "claude-haiku-4-5"
api_key_path = "relative/key"
max_tokens = 1024

[paths]
prompts_dir = "{tmp_path / 'p'}"
drift_events = "{tmp_path / 'de.jsonl'}"
drift_cursor = "{tmp_path / 'cursor'}"
drift_unmapped = "{tmp_path / 'um.jsonl'}"
signal_to_doc_map = "{tmp_path / 's.json'}"
doc_domain_map = "{tmp_path / 'd.json'}"
activity_log_dir = "{tmp_path / 'logs'}"
tick_signal_path = "{tmp_path / 'tick.json'}"

[signals]
sources = ["gh_issue"]

[github]
repo = "kentonium3/kg-automation"
bot_identity = "kg-felix-bot"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be absolute"):
            load_config(rel)

    def test_allow_relative_paths_bypass(self, tmp_path: Path) -> None:
        """``allow_relative_paths=True`` lets tests use relative paths."""
        rel = tmp_path / "ok_rel.toml"
        rel.write_text(
            """
[llm]
model = "claude-haiku-4-5"
api_key_path = "rel/key"
max_tokens = 1024

[paths]
prompts_dir = "rel/prompts"
drift_events = "rel/drift.jsonl"
drift_cursor = "rel/cursor"
drift_unmapped = "rel/unmapped.jsonl"
signal_to_doc_map = "rel/signal.json"
doc_domain_map = "rel/doc.json"
activity_log_dir = "rel/logs"
tick_signal_path = "rel/tick.json"

[signals]
sources = ["gh_issue"]

[github]
repo = "kentonium3/kg-automation"
bot_identity = "kg-felix-bot"
""",
            encoding="utf-8",
        )
        cfg = load_config(rel, allow_relative_paths=True)
        assert cfg.paths.prompts_dir == "rel/prompts"


# ---------------------------------------------------------------------------
# read_api_key
# ---------------------------------------------------------------------------


class TestReadApiKey:
    def test_reads_and_strips_whitespace(self, tmp_config: Config) -> None:
        # tmp_config writes ``test-api-key-not-real\n`` to the key file.
        assert read_api_key(tmp_config) == "test-api-key-not-real"

    def test_missing_key_file_raises(self, tmp_config: Config) -> None:
        Path(tmp_config.llm.api_key_path).unlink()
        with pytest.raises(FileNotFoundError, match="API key file not found"):
            read_api_key(tmp_config)

    def test_does_not_log_key(
        self, tmp_config: Config, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``read_api_key`` MUST NOT print or log the key value."""
        key = read_api_key(tmp_config)
        captured = capsys.readouterr()
        assert key not in captured.out
        assert key not in captured.err

    def test_error_does_not_leak_key_path_contents(
        self, tmp_config: Config
    ) -> None:
        """If the key file is missing the error surfaces the path, not contents."""
        Path(tmp_config.llm.api_key_path).unlink()
        with pytest.raises(FileNotFoundError) as exc:
            read_api_key(tmp_config)
        # The exception message includes the path but obviously cannot
        # leak the file's contents because the file does not exist.
        assert tmp_config.llm.api_key_path in str(exc.value)
