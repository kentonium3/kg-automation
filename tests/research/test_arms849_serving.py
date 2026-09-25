"""Serving configuration, limits, telemetry mapping and endpoint safety (WP01 T004)."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import serving as S

IDENT = S.ServingIdentity("gguf-sha", "sha256:img", "emb-sha", "tok-sha")


def test_primary_and_secondary_differ_in_exactly_four_fields():
    p, s = S.ServingConfiguration.primary(IDENT), S.ServingConfiguration.secondary_yarn(IDENT)
    assert p.differs_from(s) == {"n_ctx", "rope_scaling", "rope_scale", "yarn_orig_ctx"}
    assert s.n_ctx == 393_216 and s.rope_scaling == "yarn" and s.rope_scale == 2 and s.yarn_orig_ctx == 262_144
    assert p.differs_from(S.ServingConfiguration.primary(IDENT)) == set()


def test_limits_and_the_limit_applied():
    p, s = S.ServingConfiguration.primary(IDENT), S.ServingConfiguration.secondary_yarn(IDENT)
    assert p.limits() == S.Limits(trained=262_144, configured=262_144, permitted=262_144 - 2_048)
    assert s.limits() == S.Limits(trained=262_144, configured=393_216, permitted=393_216 - 2_048)
    assert p.limit_applied() == ("trained", 262_144)
    assert s.limit_applied() == ("permitted", 391_168)


def test_sampling_seed_and_output_limit_are_the_ruled_values():
    p = S.ServingConfiguration.primary(IDENT)
    assert p.sampling == {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repeat_penalty": 1.05, "min_p": 0}
    assert p.max_tokens == 2048 and p.seed_for(1) == 1001 and p.seed_for(3) == 1003
    assert p.chat_template_applied is False


def test_serialize_carries_the_exact_prompt_and_sampling():
    p = S.ServingConfiguration.primary(IDENT)
    body = S.serialize(b"hello {x}", p, seed=1002)
    assert body["prompt"] == "hello {x}" and body["seed"] == 1002 and body["n_predict"] == 2048
    assert body["cache_prompt"] is True and body["stream"] is False and body["top_k"] == 20


def test_missing_telemetry_refuses_a_scored_row():
    with pytest.raises(S.TelemetryMissing, match="cache_n"):
        S.map_timings({"content": "x", "timings": {"prompt_n": 10, "prompt_ms": 1, "predicted_n": 1, "predicted_ms": 1}})


def test_telemetry_mapping_is_explicit():
    c = S.map_timings({"content": "answer", "stop_type": "eos",
                       "timings": {"prompt_n": 1000, "cache_n": 900, "prompt_ms": 2000.0,
                                   "predicted_n": 50, "predicted_ms": 2500.0}})
    assert c.prompt_tokens == 1000 and c.cache_read_tokens == 900
    assert c.uncached_tokens == 100 and c.cache_write_tokens == 100
    assert c.cache_state == "warm" and c.cache_fraction == 0.9
    assert c.prefill_s == 2.0 and c.generation_s == 2.5 and c.generation_tok_s == 20.0
    assert c.finish_reason == "stop" and not c.truncated
    cold = S.map_timings({"content": "", "stopped_limit": True,
                          "timings": {"prompt_n": 10, "cache_n": 0, "prompt_ms": 1, "predicted_n": 2048, "predicted_ms": 1}})
    assert cold.cache_state == "cold" and cold.finish_reason == "length" and cold.truncated


def test_endpoint_safety(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    with pytest.raises(S.UnsafeEndpoint, match="OPENAI_API_KEY"):
        S._assert_safe("http://127.0.0.1:18080")
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(S.UnsafeEndpoint, match="api.openai.com"):
        S._assert_safe("https://api.openai.com/v1")
    S._assert_safe("http://127.0.0.1:18080")
    S._assert_safe("http://llama:8080")


needs_tokenizer = pytest.mark.skipif(
    importlib.util.find_spec("transformers") is None
    or not (pathlib.Path(os.environ.get("ARMS849_CACHE", "build/849-cache")) / "qwen-tokenizer").exists(),
    reason="tokenizer classes or cache absent (substrate setup, WP02)")


@needs_tokenizer
def test_b2_full_block_exceeds_the_trained_context():
    """T005 (j): the six-of-eight finding is visible from WP01 alone."""
    from datetime import datetime

    from scripts.research.arms849.prompt import Prompt
    from scripts.research.arms849.text import FrozenCorpusText
    from scripts.research.load_849_corpus import DEFAULT_CORPUS, replay

    tok = S.Tokenizer()
    fct = FrozenCorpusText(DEFAULT_CORPUS)
    view = replay(DEFAULT_CORPUS, datetime.fromisoformat("2026-10-16T09:00:00-04:00"), verify=False)
    body = S.serialize(Prompt().render(fct.render_full_view(view), "Why did I miss sub-10?"),
                       S.ServingConfiguration.primary(IDENT), 1001)
    assert S.count_tokens(body, tok) > 262_144
