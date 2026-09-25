"""The serving configuration and the client every arm uses (research.md D-5, D-6, D-11, D-13).

Three things live here and nowhere else:

* :class:`ServingConfiguration` — every field the ledger header binds (data-model.md
  §ServingConfiguration). ``primary()`` and ``secondary_yarn()`` differ in exactly
  ``{rope_scaling, rope_scale, yarn_orig_ctx, n_ctx}``, which SC-006 asserts.
* :class:`Tokenizer` — the Qwen tokenizer from the local cache, refused if ``torch``
  is importable (env_clean), with the equivalence check against the pinned server's
  ``/tokenize`` (D-11): an upstream tokenizer is only usable once shown equal to the
  served one.
* :func:`complete` — the ``/completion`` client with the **explicit** llama.cpp
  ``timings`` mapping (D-13, corrected: ``prompt_n`` excludes cache hits, so
  total = ``prompt_n + cache_n``). A scored row is never produced without every
  required measurement: a missing field raises :class:`TelemetryMissing`.

On the chat template (rubric §3.2 @939d9b29, superseding WP01 T004 step 4): the
request goes to llama.cpp's native ``/completion`` as a raw ``prompt`` string, and
that string is the registered text wrapped as the SINGLE USER TURN by the cached
tokenizer's own chat template (``add_generation_prompt=True``). It is the "exact
serialised request" §3.2 speaks of and what :func:`count_tokens` counts, so §2's
figures include the template overhead. Gate (b) measured the raw form; that is why
§2 is re-measured at code freeze (T039) on the templated bytes. The configuration
records ``chat_template_applied: True`` + ``chat_template_sha256`` so nobody later
routes this through ``/v1/chat/completions`` and silently changes every count.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

__all__ = [
    "Completion",
    "Limits",
    "ServingConfiguration",
    "ServingIdentity",
    "TelemetryMissing",
    "Tokenizer",
    "UnsafeEndpoint",
    "complete",
    "count_tokens",
    "serialize",
]

TRAINED_CONTEXT = 262_144
PRIMARY_N_CTX = 262_144
SECONDARY_N_CTX = 393_216
MAX_TOKENS = 2_048
SEED_BASE = 1_000

SAMPLING: dict[str, float | int] = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "repeat_penalty": 1.05,
    "min_p": 0,
}

#: Hosts a request may go to: loopback on office4, or the compose-network name
#: inside the runner container. Anything else is refused (adversarial A4).
#: Adversarial A4: the run can only ever talk to the compose stack. A constant, not
#: configuration — an environment variable that widened it would make the guard pass
#: while the property is violated (design-lead read, 2026-09-25).
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "llama"})

REQUIRED_TIMINGS = ("prompt_n", "cache_n", "prompt_ms", "predicted_n", "predicted_ms")


class TelemetryMissing(RuntimeError):
    """A required llama.cpp timing field was absent; no scored row may be made."""


class PromptTruncated(RuntimeError):
    """The server reports ``truncated: true`` — the prompt was cut to fit; never a scored row."""


class ContextExceeded(RuntimeError):
    """Client-side count exceeds the permitted limit — refused BEFORE sending (last line of D-11)."""


class UnsafeEndpoint(RuntimeError):
    """The request would leave the sandbox (non-allowed host or an API key in the environment)."""


@dataclass(frozen=True)
class ServingIdentity:
    """The artefact identities WP02's ``setup`` records; equal for primary and secondary."""

    gguf_sha256: str
    image_digest: str
    embedder_model_sha256: str
    tokenizer_files_sha256: str
    chat_template_sha256: str      # sha256 of the tokenizer's chat_template string (rubric 939d9b29)


@dataclass(frozen=True)
class Limits:
    trained: int
    configured: int
    permitted: int


@dataclass(frozen=True)
class ServingConfiguration:
    model: str
    gguf_sha256: str
    image_digest: str
    n_ctx: int
    rope_scaling: str | None
    rope_scale: int | None
    yarn_orig_ctx: int | None
    parallel: int
    cache_prompt: bool
    sampling: dict[str, float | int]
    seed_policy: str
    max_tokens: int
    embedder: str
    embedder_model_sha256: str
    reranker: str
    tokenizer: str
    tokenizer_files_sha256: str
    chat_template_applied: bool
    chat_template_sha256: str
    kind: Literal["primary", "secondary"] = "primary"

    MODEL = "Qwen3-Next-80B-A3B-Instruct UD-Q4_K_XL"
    EMBEDDER = "fastembed BAAI/bge-small-en-v1.5"
    RERANKER = "cosine (#974)"
    TOKENIZER = "Qwen/Qwen3-Next-80B-A3B-Instruct"

    @classmethod
    def primary(cls, identity: ServingIdentity) -> ServingConfiguration:
        return cls(
            model=cls.MODEL, gguf_sha256=identity.gguf_sha256, image_digest=identity.image_digest,
            n_ctx=PRIMARY_N_CTX, rope_scaling=None, rope_scale=None, yarn_orig_ctx=None,
            parallel=1, cache_prompt=True, sampling=dict(SAMPLING), seed_policy=f"{SEED_BASE}+repeat",
            max_tokens=MAX_TOKENS, embedder=cls.EMBEDDER,
            embedder_model_sha256=identity.embedder_model_sha256, reranker=cls.RERANKER,
            tokenizer=cls.TOKENIZER, tokenizer_files_sha256=identity.tokenizer_files_sha256,
            chat_template_applied=True, chat_template_sha256=identity.chat_template_sha256, kind="primary",
        )

    @classmethod
    def secondary_yarn(cls, identity: ServingIdentity) -> ServingConfiguration:
        base = cls.primary(identity)
        return ServingConfiguration(**{
            **asdict(base),
            "n_ctx": SECONDARY_N_CTX, "rope_scaling": "yarn", "rope_scale": 2,
            "yarn_orig_ctx": TRAINED_CONTEXT, "kind": "secondary",
        })

    def as_header_dict(self) -> dict[str, Any]:
        return asdict(self)

    def differs_from(self, other: ServingConfiguration) -> set[str]:
        """Field names whose values differ — ``kind`` is a label, not a difference."""
        a, b = asdict(self), asdict(other)
        return {k for k in a if k != "kind" and a[k] != b[k]}

    def limits(self) -> Limits:
        """D-11: trained (model), configured (n_ctx), permitted (n_ctx − output allowance)."""
        return Limits(trained=TRAINED_CONTEXT, configured=self.n_ctx,
                      permitted=self.n_ctx - self.max_tokens)

    def limit_applied(self) -> tuple[str, int]:
        """Which limit the context gate uses for this ledger kind, and its value."""
        lim = self.limits()
        return ("trained", lim.trained) if self.kind == "primary" else ("permitted", lim.permitted)

    def seed_for(self, repeat: int) -> int:
        return SEED_BASE + repeat


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------


def _cache_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("ARMS849_CACHE", "build/849-cache"))


class Tokenizer:
    """The Qwen tokenizer from the local cache; never fetched at run time."""

    def __init__(self, path: pathlib.Path | None = None) -> None:
        if importlib.util.find_spec("torch") is not None:
            raise RuntimeError("torch is importable in this environment; env_clean forbids it "
                               "(the tokenizer classes are all that may be installed)")
        try:
            transformers = importlib.import_module("transformers")
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError("transformers (tokenizer classes) is not installed; run "
                               "substrate setup") from exc
        self.path = pathlib.Path(path) if path else _cache_dir() / "qwen-tokenizer"
        if not self.path.exists():
            raise RuntimeError(f"tokenizer cache absent at {self.path}; run substrate setup — "
                               f"the run never fetches")
        self._tok = transformers.AutoTokenizer.from_pretrained(str(self.path))

    def count(self, text: str | bytes) -> int:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        return len(self._tok(text, add_special_tokens=False)["input_ids"])

    def chat_template(self) -> str:
        """The template string the cached tokenizer carries (never fetched, never edited)."""
        template = getattr(self._tok, "chat_template", None)
        if not isinstance(template, str) or not template:
            raise RuntimeError(f"tokenizer at {self.path} carries no chat_template string")
        return template

    def chat_template_sha256(self) -> str:
        return hashlib.sha256(self.chat_template().encode("utf-8")).hexdigest()

    def apply_chat_template(self, user_turn: str) -> str:
        """Rubric §3.2 @939d9b29: the registered text is the SINGLE USER TURN; the template is
        applied client-side and the result is the raw ``/completion`` prompt. No system turn."""
        out = self._tok.apply_chat_template([{"role": "user", "content": user_turn}],
                                            add_generation_prompt=True, tokenize=False)
        if not isinstance(out, str):
            raise TypeError("apply_chat_template did not return a string")
        return out

    def encode(self, text: str) -> list[int]:
        return list(self._tok(text, add_special_tokens=False)["input_ids"])

    def equivalence_sample(self, lines: Iterable[str], probe: str = "equivalence probe") -> list[str]:
        """Corpus lines plus one TEMPLATED request, so special-token parsing is measured too."""
        return [*lines, self.apply_chat_template(probe)]

    def equivalence_check(self, base_url: str, lines: Iterable[str]) -> tuple[bool, str]:
        """D-11: client-side ids must equal the pinned server's ``/tokenize`` for every line.

        The sample must contain at least one templated request (``<|im_start|>``):
        agreement on the chat template's special tokens is otherwise assumed, not
        measured (design-lead read, 2026-09-25). Use :meth:`equivalence_sample`.
        """
        _assert_safe(base_url)
        lines = list(lines)
        require_templated_sample(lines)
        for i, line in enumerate(lines):
            body = json.dumps({"content": line, "add_special": False}).encode("utf-8")
            req = urllib.request.Request(f"{base_url.rstrip('/')}/tokenize", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                server = json.loads(resp.read().decode("utf-8"))["tokens"]
            server_ids = [t["id"] if isinstance(t, dict) else t for t in server]
            if server_ids != self.encode(line):
                return False, f"line {i} differs: client {len(self.encode(line))} ids vs server {len(server_ids)}"
        return True, "client tokenizer == server /tokenize on every sampled line"


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


def require_templated_sample(lines: Sequence[str]) -> None:
    if not any("<|im_start|>" in line and "<|im_end|>" in line for line in lines):
        raise ValueError("D-11 equivalence sample carries no templated request; add one via equivalence_sample()")


def _assert_safe(base_url: str) -> None:
    if os.environ.get("OPENAI_API_KEY"):
        raise UnsafeEndpoint("OPENAI_API_KEY is set; the run must not be able to reach a provider")
    host = urllib.parse.urlsplit(base_url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise UnsafeEndpoint(f"endpoint host {host!r} is not in {sorted(ALLOWED_HOSTS)}")



def serialize(request_text: bytes, config: ServingConfiguration, seed: int,
              tokenizer: Tokenizer) -> dict[str, Any]:
    """The exact ``/completion`` body. The ``prompt`` field is what is counted.

    Rubric §3.2 @939d9b29 supersedes WP01 T004 step 4 ("sent raw"): the rendered
    registered text is wrapped as the single user turn by the cached tokenizer's
    chat template (``add_generation_prompt=True``), and THAT string is the
    ``prompt`` — still ``/completion``, still a raw string, never
    ``/v1/chat/completions`` (the D-13 timings mapping is unchanged). The template
    is a serving fact: its sha256 is bound in the configuration and must equal the
    tokenizer's; ``prompt.verify`` stays over the registered text.
    """
    if not config.chat_template_applied:
        raise ValueError("the registered protocol applies the chat template (939d9b29); "
                         "a configuration without it is a different serving configuration")
    actual = tokenizer.chat_template_sha256()
    if actual != config.chat_template_sha256:
        raise ValueError(f"tokenizer chat template {actual[:12]} != configuration {config.chat_template_sha256[:12]}")
    # The sampling block may carry EXACTLY the registered keys — a stray key such as
    # "prompt" or "seed" would otherwise overwrite an authoritative field (Codex WP01
    # cycle 4). Authoritative fields are set LAST.
    extra = set(config.sampling) - set(SAMPLING)
    missing = set(SAMPLING) - set(config.sampling)
    if extra or missing:
        raise ValueError(f"sampling keys must be exactly {sorted(SAMPLING)}; extra {sorted(extra)}, missing {sorted(missing)}")
    return {
        **config.sampling,
        "prompt": tokenizer.apply_chat_template(request_text.decode("utf-8")),
        "n_predict": config.max_tokens,
        "seed": seed,
        "cache_prompt": config.cache_prompt,
        "stream": False,
    }


def count_tokens(body: dict[str, Any], tokenizer: Tokenizer) -> int:
    """Count the exact ``prompt`` string that will be sent — not the block alone."""
    return tokenizer.count(body["prompt"])


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    output_tokens: int
    finish_reason: Literal["stop", "length"]
    truncated: bool
    cache_read_tokens: int
    uncached_tokens: int
    cache_write_tokens: int
    cache_state: Literal["cold", "warm"]
    cache_fraction: float
    prefill_s: float
    generation_s: float
    generation_tok_s: float
    client_prompt_tokens: int
    raw_timings: dict[str, Any] = field(default_factory=dict)


def map_timings(response: dict[str, Any], client_prompt_tokens: int) -> Completion:
    """D-13's explicit mapping; refuses rather than guessing a missing field.

    Two further refusals (design-lead read of 4029e012): the server's own
    ``truncated`` flag means the prompt was cut to fit the context — that row
    is never scored; and the client's count of the sent ``prompt`` must equal
    the server's ``prompt_n + cache_n`` — they are one quantity (§2 and §5
    columns), so a difference is tokenizer drift and refuses the row instead of
    leaving a silent column mismatch.

    llama.cpp semantics (tools/server, confirmed by Codex WP01 cycle 2 against
    the source): ``prompt_n`` is the number of prompt tokens PROCESSED this
    request — it already EXCLUDES cache hits — and ``cache_n`` is the number
    reused from the prompt cache. So the whole prompt is ``prompt_n +
    cache_n``, the uncached (and therefore newly cached) tokens are
    ``prompt_n``, and the cache fraction is ``cache_n / (prompt_n + cache_n)``.
    The first version subtracted the cache twice and went negative on a warm
    request.
    """
    if response.get("truncated"):
        raise PromptTruncated("llama.cpp reports truncated=true: the prompt was cut to fit the context; "
                              "this is the exceeds_model_context case, never a scored row")
    timings = response.get("timings") or {}
    missing = [k for k in REQUIRED_TIMINGS if k not in timings]
    if missing:
        raise TelemetryMissing(f"llama.cpp response lacks timings {missing}; no scored row")
    processed = int(timings["prompt_n"])
    cached = int(timings["cache_n"])
    total = processed + cached
    if int(client_prompt_tokens) != total:
        raise TelemetryMissing(f"client counted {client_prompt_tokens} prompt tokens but the server processed "
                               f"{total} (prompt_n {processed} + cache_n {cached}); tokenizer drift, no scored row")
    predicted_n = int(timings["predicted_n"])
    prompt_ms = float(timings["prompt_ms"])
    predicted_ms = float(timings["predicted_ms"])
    stop_type = response.get("stop_type")
    stopped_limit = bool(response.get("stopped_limit"))
    finish: Literal["stop", "length"] = "length" if (stop_type == "limit" or stopped_limit) else "stop"
    return Completion(
        text=str(response.get("content", "")),
        prompt_tokens=total,
        output_tokens=predicted_n,
        finish_reason=finish,
        truncated=finish == "length",
        cache_read_tokens=cached,
        uncached_tokens=processed,
        cache_write_tokens=processed,
        cache_state="cold" if cached == 0 else "warm",
        cache_fraction=(cached / total) if total else 0.0,
        prefill_s=prompt_ms / 1000.0,
        generation_s=predicted_ms / 1000.0,
        generation_tok_s=(predicted_n / (predicted_ms / 1000.0)) if predicted_ms else 0.0,
        client_prompt_tokens=int(client_prompt_tokens),
        raw_timings=dict(timings),
    )


def complete(body: dict[str, Any], tokenizer: Tokenizer, permitted_limit: int,
             base_url: str = "http://127.0.0.1:18080", timeout_s: float = 6000.0) -> Completion:
    """POST the exact body to ``/completion`` and map its timings.

    The client count of ``body["prompt"]`` is taken first: above ``permitted_limit``
    the request is refused BEFORE sending (the WP04 gate is the first line, this is
    the last — the pinned build's context-shift default is never relied on), and
    afterwards it must equal the server's ``prompt_n + cache_n``.
    """
    _assert_safe(base_url)
    client = count_tokens(body, tokenizer)
    if client > permitted_limit:
        raise ContextExceeded(f"prompt is {client} tokens; permitted limit {permitted_limit} — not sent")
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/completion", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return map_timings(payload, client)
