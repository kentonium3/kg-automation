"""The shared text form returns frozen bytes and only concatenates (WP01 T001).

Every assertion runs against the REAL frozen corpus — a fixture would prove the
code works on the fixture. Each check is paired with an injected defect where
one is expressible.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.arms849 import text as T
from scripts.research.load_849_corpus import DEFAULT_CORPUS, replay

pytestmark = pytest.mark.skipif(
    not (DEFAULT_CORPUS / "entities.json").exists(),
    reason="rendered corpus absent; run render_849_corpus first")


@pytest.fixture(scope="module")
def fct() -> T.FrozenCorpusText:
    return T.FrozenCorpusText(DEFAULT_CORPUS)


def test_every_event_line_is_the_corpus_bytes(fct):
    raw = (DEFAULT_CORPUS / "stream.jsonl").read_bytes().split(b"\n")
    lines = [l for l in raw if l.strip()]
    assert len(lines) == 5750
    for line in lines:
        ref = json.loads(line)["ref"]
        assert fct.event_line(ref) == line


def test_an_event_line_is_never_a_re_dump(tmp_path):
    """The frozen corpus happens to be canonical JSON today, so equality with a
    re-dump proves nothing there. Inject a NON-canonical line (unsorted keys,
    odd spacing, an escaped non-ASCII char) and require it back verbatim."""
    odd = b'{"ref":"e00001",  "channel": "note", "text": "caf\\u00e9", "at": "2026-01-01"}'
    (tmp_path / "stream.jsonl").write_bytes(odd + b"\n")
    (tmp_path / "entities.json").write_text('[{"kind": "Task", "id": "T_X", "description": "x"}]')
    fct = T.FrozenCorpusText(tmp_path)
    assert fct.event_line("e00001") == odd
    assert fct.event_line("e00001") != json.dumps(json.loads(odd), sort_keys=True).encode()


def test_render_block_is_pure_concatenation(fct):
    refs = ["e00009", "e00010"]
    keys = [fct.entity_keys[0], fct.edge_keys[0]]
    block = fct.render_block(refs, keys)
    expected = b"".join(fct.event_line(r) + b"\n" for r in refs) + \
               b"".join(fct.record_line(k) + b"\n" for k in keys)
    assert block.data == expected
    assert block.event_refs == tuple(refs) and block.record_keys == tuple(keys)
    assert block.sha256 == hashlib.sha256(expected).hexdigest()


def test_block_cannot_be_built_from_strings():
    with pytest.raises(TypeError):
        T.Block(event_refs=(), record_keys=(), data="not bytes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        T.Block(event_refs=["e1"], record_keys=(), data=b"")  # type: ignore[arg-type]


def test_record_lines_digest_is_stable_and_covers_every_record(fct):
    other = T.FrozenCorpusText(DEFAULT_CORPUS)
    assert fct.record_lines_digest == other.record_lines_digest
    assert len(fct.record_keys) == 66
    assert len(fct.entity_keys) == 50 and len(fct.edge_keys) == 16


def test_record_line_is_the_one_serialisation(fct):
    entity = json.loads((DEFAULT_CORPUS / "entities.json").read_text())[0]
    key = T.edge_key(entity) if entity.get("kind") == "Edge" else T.entity_key(entity)
    assert fct.record_line(key) == T.record_line_bytes(entity)


def test_unknown_keys_are_named(fct):
    with pytest.raises(KeyError, match="e99999"):
        fct.event_line("e99999")
    with pytest.raises(KeyError, match="NOPE"):
        fct.record_line("NOPE")


def test_render_full_view_is_events_then_entities_then_edges(fct):
    view = replay(DEFAULT_CORPUS, datetime.fromisoformat("2026-04-28T09:06:00-04:00"), verify=False)
    block = fct.render_full_view(view)
    assert block.event_refs == tuple(e["ref"] for e in view.events)
    n_ent = len(view.entities)
    assert block.record_keys[:n_ent] == tuple(T.entity_key(e) for e in view.entities)
    assert block.record_keys[n_ent:] == tuple(T.edge_key(e) for e in view.edges)
    event_section = b"".join(fct.event_line(r) + b"\n" for r in block.event_refs)
    assert block.data.startswith(event_section)


def test_full_view_events_are_a_byte_prefix_across_ask_times(fct):
    """The §2 layout protocol: the event section of an earlier question is a prefix of a later's."""
    early = fct.render_full_view(replay(DEFAULT_CORPUS, datetime.fromisoformat("2026-04-28T09:06:00-04:00"), verify=False))
    later = fct.render_full_view(replay(DEFAULT_CORPUS, datetime.fromisoformat("2026-06-09T09:15:00-04:00"), verify=False))
    early_events = b"".join(fct.event_line(r) + b"\n" for r in early.event_refs)
    assert later.data.startswith(early_events)
