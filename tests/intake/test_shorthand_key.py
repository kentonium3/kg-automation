"""Tests for the intake shorthand reference card (#755).

The load-bearing test is the drift guard: every token the parser accepts
(`shorthand` alias tables) must appear in the rendered card, so the card can
never fall out of sync with what a reply can actually use.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from scripts.intake import shorthand, shorthand_key


class TestDriftGuard:
    def test_card_lists_every_documented_token(self):
        card = shorthand_key.render_card()

        # Every distinct canonical project's display short-name appears.
        for name in shorthand_key._project_display_names():
            assert name in card, f"project {name!r} missing from card"

        # Every friction descriptor appears (flow / growth / edge / overload).
        for canonical in shorthand.FRICTION_ALIASES.values():
            descriptor = canonical.split("-", 1)[1]
            assert descriptor in card, f"friction {descriptor!r} missing from card"

        # Every quadrant name appears (do / schedule / delegate / eliminate).
        for canonical in set(shorthand.QUADRANT_ALIASES.values()):
            name = canonical.split(":", 1)[1]
            assert name in card, f"quadrant {name!r} missing from card"

        # Every LOE size appears in the rendered loe segment (e.g. "loe:s/m/l").
        loe_render = "loe:" + "/".join(shorthand_key._loe_sizes())
        assert loe_render in card
        assert set(shorthand_key._loe_sizes()) == {
            canonical.split(":", 1)[1] for canonical in shorthand.LOE_ALIASES.values()
        }

    def test_new_friction_token_auto_appears(self, monkeypatch):
        """A token added to the parser shows up in the card without editing it."""
        patched = dict(shorthand.FRICTION_ALIASES)
        patched["f5"] = "f:5-experimental"
        monkeypatch.setattr(shorthand, "FRICTION_ALIASES", patched)
        monkeypatch.setattr(shorthand_key, "FRICTION_ALIASES", patched)
        card = shorthand_key.render_card()
        assert "f5=experimental" in card


class TestRendering:
    def test_hint_is_a_single_line(self):
        hint = shorthand_key.render_hint()
        assert "\n" not in hint
        assert "intake key" in hint

    def test_card_is_deterministic(self):
        assert shorthand_key.render_card() == shorthand_key.render_card()

    def test_card_is_one_block_with_the_line_format(self):
        card = shorthand_key.render_card()
        assert "<n> <project> f<1-3> <quadrant>" in card
        # f:4 is a decomposition trigger, surfaced as such.
        assert "decompose" in card

    def test_project_display_dedupes_aliases(self):
        # spec-kitty and spec_kitty both map to spec_kitty → one display entry.
        names = shorthand_key._project_display_names()
        assert names.count("spec-kitty") + names.count("spec_kitty") == 1


class TestCli:
    def test_cli_text_default_prints_card(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = shorthand_key.main([])
        assert rc == 0
        assert buf.getvalue().strip() == shorthand_key.render_card()

    def test_cli_hint_flag(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = shorthand_key.main(["--hint"])
        assert rc == 0
        assert buf.getvalue().strip() == shorthand_key.render_hint()

    def test_cli_json_flag(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = shorthand_key.main(["--json"])
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert payload["text"] == shorthand_key.render_card()

    def test_cli_json_hint(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = shorthand_key.main(["--hint", "--json"])
        assert rc == 0
        assert json.loads(buf.getvalue())["text"] == shorthand_key.render_hint()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
