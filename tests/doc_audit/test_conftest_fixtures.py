"""Tests for the shared conftest fixtures themselves.

WP02 / T009. Locks in the contract of the ``mock_anthropic`` fixture:
when used, downstream code that does ``import anthropic; client =
anthropic.Anthropic(...)`` MUST receive the fake client (not a real
one that would attempt network I/O).

These tests guard against a regression where the fixture only
returned a fake object without monkeypatching the SDK constructor —
the failure mode codex-cli flagged in cycle 1 review of WP02.
"""
from __future__ import annotations


def test_mock_anthropic_patches_sdk_constructor(mock_anthropic) -> None:
    """``mock_anthropic`` MUST patch ``anthropic.Anthropic``.

    Downstream code paths that do ``import anthropic`` and then call
    ``anthropic.Anthropic(api_key=...)`` should receive the fake
    client this fixture returns — never a real SDK client. Without
    the monkeypatch, tests would silently shell out to the live
    Anthropic API.
    """
    import anthropic  # type: ignore[import-not-found]

    # The patched constructor must return the SAME fake client the
    # fixture handed back to the test. Both call-sites converge on
    # one object the test can inspect.
    constructed = anthropic.Anthropic(api_key="not-real")
    assert constructed is mock_anthropic

    # The fake client exposes the minimal SDK surface downstream
    # code expects.
    assert hasattr(constructed, "messages")
    assert hasattr(constructed.messages, "create")


def test_mock_anthropic_ignores_constructor_kwargs(mock_anthropic) -> None:
    """Real SDK accepts arbitrary kwargs; the fake must too.

    Downstream WP04 code may pass kwargs like ``api_key=``,
    ``timeout=``, ``max_retries=``. The patched constructor must
    accept and ignore them — i.e., the lambda's ``*args, **kwargs``
    signature is load-bearing.
    """
    import anthropic  # type: ignore[import-not-found]

    client = anthropic.Anthropic(
        api_key="x", timeout=10, max_retries=3, base_url="https://e"
    )
    assert client is mock_anthropic
