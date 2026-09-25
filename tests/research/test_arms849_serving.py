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

IDENT = S.ServingIdentity("gguf-sha", "sha256:img", "emb-sha", "tok-sha", "a" * 64)


class _FakeTok:
    """A stand-in tokenizer with a fixed template sha, for the serialisation shape test."""
    def __init__(self, sha="a" * 64): self.sha = sha
    def chat_template_sha256(self): return self.sha
    def apply_chat_template(self, user_turn): return f"<|im_start|>user\n{user_turn}<|im_end|>\n<|im_start|>assistant\n"


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
    assert p.chat_template_applied is True and p.chat_template_sha256 == "a" * 64


def test_serialize_carries_the_exact_prompt_and_sampling():
    p = S.ServingConfiguration.primary(IDENT)
    body = S.serialize(b"hello {x}", p, seed=1002, tokenizer=_FakeTok())
    # The prompt is the templated single user turn carrying the registered text verbatim (939d9b29).
    assert body["prompt"] == "<|im_start|>user\nhello {x}<|im_end|>\n<|im_start|>assistant\n"
    assert body["seed"] == 1002 and body["n_predict"] == 2048
    assert body["cache_prompt"] is True and body["stream"] is False and body["top_k"] == 20


def test_missing_telemetry_refuses_a_scored_row():
    with pytest.raises(S.TelemetryMissing, match="cache_n"):
        S.map_timings({"content": "x", "timings": {"prompt_n": 10, "prompt_ms": 1, "predicted_n": 1, "predicted_ms": 1}}, 10)


def test_telemetry_mapping_is_explicit():
    """prompt_n EXCLUDES cache hits (llama.cpp tools/server): total = prompt_n + cache_n."""
    c = S.map_timings({"content": "answer", "stop_type": "eos",
                       "timings": {"prompt_n": 100, "cache_n": 900, "prompt_ms": 2000.0,
                                   "predicted_n": 50, "predicted_ms": 2500.0}}, 1000)
    assert c.prompt_tokens == 1000 and c.cache_read_tokens == 900
    assert c.uncached_tokens == 100 and c.cache_write_tokens == 100
    assert c.cache_state == "warm" and c.cache_fraction == 0.9
    assert c.prefill_s == 2.0 and c.generation_s == 2.5 and c.generation_tok_s == 20.0
    assert c.finish_reason == "stop" and not c.truncated
    cold = S.map_timings({"content": "", "stopped_limit": True,
                          "timings": {"prompt_n": 10, "cache_n": 0, "prompt_ms": 1, "predicted_n": 2048, "predicted_ms": 1}}, 10)
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
    ident = S.ServingIdentity("gguf-sha", "sha256:img", "emb-sha", "tok-sha", tok.chat_template_sha256())
    body = S.serialize(Prompt().render(fct.render_full_view(view), "Why did I miss sub-10?"),
                       S.ServingConfiguration.primary(ident), 1001, tokenizer=tok)
    assert S.count_tokens(body, tok) > 262_144


def test_warm_request_regression_from_codex_cycle_2():
    """Codex WP01 cycle 2: prompt_n=1, cache_n=236 must give total 237, uncached 1,
    fraction 236/237 — the first mapping produced -235 and a fraction of 236."""
    c = S.map_timings({"content": "x", "stop_type": "eos",
                       "timings": {"prompt_n": 1, "cache_n": 236, "prompt_ms": 10.0,
                                   "predicted_n": 3, "predicted_ms": 30.0}}, 237)
    assert c.prompt_tokens == 237 and c.uncached_tokens == 1 and c.cache_write_tokens == 1
    assert c.cache_read_tokens == 236 and c.cache_state == "warm"
    assert abs(c.cache_fraction - 236 / 237) < 1e-12
    assert c.uncached_tokens >= 0 and 0.0 <= c.cache_fraction <= 1.0


def test_serialize_applies_the_template_and_binds_its_sha():
    """939d9b29: the prompt is the templated user turn; a template mismatch is refused."""
    p = S.ServingConfiguration.primary(IDENT)
    body = S.serialize(b"REGISTERED", p, seed=1001, tokenizer=_FakeTok())
    assert body["prompt"].startswith("<|im_start|>user\nREGISTERED") and body["prompt"].endswith("<|im_start|>assistant\n")
    with pytest.raises(ValueError, match="chat template"):
        S.serialize(b"REGISTERED", p, seed=1001, tokenizer=_FakeTok("b" * 64))
    off = S.ServingConfiguration(**{**p.as_header_dict(), "chat_template_applied": False})
    with pytest.raises(ValueError, match="939d9b29"):
        S.serialize(b"REGISTERED", off, seed=1001, tokenizer=_FakeTok())


@needs_tokenizer
def test_real_tokenizer_template_is_qwen_chat_and_counted():
    tok = S.Tokenizer()
    ident = S.ServingIdentity("gguf-sha", "sha256:img", "emb-sha", "tok-sha", tok.chat_template_sha256())
    p = S.ServingConfiguration.primary(ident)
    body = S.serialize(b"hello world", p, seed=1001, tokenizer=tok)
    assert body["prompt"].startswith("<|im_start|>user\nhello world<|im_end|>") and body["prompt"].endswith("<|im_start|>assistant\n")
    assert S.count_tokens(body, tok) > tok.count("hello world")   # the template overhead is counted
    assert len(tok.chat_template_sha256()) == 64


def test_hosts_allowlist_is_a_constant_not_configuration(monkeypatch):
    """Design-lead MAJOR 1: an env var must not widen the guard."""
    monkeypatch.setenv("ARMS849_LLAMA_HOSTS", "api.openai.com,127.0.0.1")
    importlib.reload(S)
    with pytest.raises(S.UnsafeEndpoint):
        S._assert_safe("https://api.openai.com/v1")
    assert S.ALLOWED_HOSTS == frozenset({"127.0.0.1", "localhost", "llama"})


def _ok_response(prompt_n=100, cache_n=0, **over):
    r = {"content": "x", "stop_type": "eos",
         "timings": {"prompt_n": prompt_n, "cache_n": cache_n, "prompt_ms": 10.0, "predicted_n": 5, "predicted_ms": 50.0}}
    r.update(over)
    return r


def test_server_truncation_is_refused_not_scored():
    """Design-lead MAJOR 2: truncated=true is the context case, never a plausible ok row."""
    with pytest.raises(S.PromptTruncated):
        S.map_timings(_ok_response(truncated=True), 100)
    c = S.map_timings(_ok_response(truncated=False), 100)
    assert c.client_prompt_tokens == 100 and c.prompt_tokens == 100


def test_client_and_server_prompt_counts_must_agree():
    """Design-lead MAJOR 3: §2 (client) and §5 (server) count the same quantity."""
    with pytest.raises(S.TelemetryMissing, match="drift"):
        S.map_timings(_ok_response(prompt_n=60, cache_n=40), 99)
    assert S.map_timings(_ok_response(prompt_n=60, cache_n=40), 100).cache_state == "warm"


class _CountingTok(_FakeTok):
    def count(self, text): return len(text.split())


def test_complete_refuses_before_sending_when_over_the_permitted_limit(monkeypatch):
    import urllib.request
    def never(*a, **k): raise AssertionError("request must not be sent")
    monkeypatch.setattr(urllib.request, "urlopen", never)
    body = {"prompt": "one two three four five"}
    with pytest.raises(S.ContextExceeded):
        S.complete(body, _CountingTok(), permitted_limit=4)


def test_equivalence_sample_must_carry_a_templated_line():
    with pytest.raises(ValueError, match="templated"):
        S.require_templated_sample(['{"ref": 1}', '{"ref": 2}'])
    S.require_templated_sample(['{"ref": 1}', "<|im_start|>user\nx<|im_end|>\n<|im_start|>assistant\n"])


@needs_tokenizer
def test_real_equivalence_sample_appends_the_templated_probe():
    tok = S.Tokenizer()
    sample = tok.equivalence_sample(['{"ref": 1}'])
    assert len(sample) == 2 and sample[1].startswith("<|im_start|>user")
    S.require_templated_sample(sample)
