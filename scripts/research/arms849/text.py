"""The shared text form — frozen bytes, never a re-dump (contracts/text-form.md, research.md D-7).

An arm's context is made of three kinds of line:

* an **event** line is the exact line from the frozen ``stream.jsonl`` for its
  ``ref`` — read as bytes and handed back unchanged. It is never re-serialised,
  because ``json.dumps`` can differ from the frozen bytes (escaping, key order,
  float formatting) and rubric §2's token figures were measured on what was
  frozen;
* an **entity** or **edge** line is one canonical line per record, produced
  ONCE here from ``entities.json`` (the only serialisation in the package) and
  reused by every arm; its digest is recorded by the preflight so the loaded
  form is bound into the run;
* a **block** is concatenation and nothing else.

The only way an arm obtains slot text is :func:`FrozenCorpusText.render_block`
(or :func:`render_full_view` for D). ``Prompt.render`` accepts a :class:`Block`,
not a string, so text cannot enter the prompt through any other door.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from scripts.research.load_849_corpus import DEFAULT_CORPUS, Loaded

__all__ = [
    "Block",
    "FrozenCorpusText",
    "edge_key",
    "entity_key",
    "record_line_bytes",
]


def entity_key(entity: Mapping[str, object]) -> str:
    """The record key of an entity: its ``id``."""
    return str(entity["id"])


def edge_key(edge: Mapping[str, object]) -> str:
    """The record key of an edge: ``<from>-<type>-><to>``."""
    return f"{edge['from']}-{edge['type']}->{edge['to']}"


def record_line_bytes(record: Mapping[str, object]) -> bytes:
    """THE one serialisation in the arms package (D-7).

    Deterministic and stable across processes: sorted keys, UTF-8 without
    ASCII escaping, ``default=str`` for the dates YAML parsed into objects.
    """
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


@dataclass(frozen=True)
class Block:
    """The bytes an arm inserts into the prompt slot, and what they were made of.

    ``data`` is bytes on purpose: a ``str`` block cannot be built, so a caller
    cannot smuggle re-rendered text past the frozen-bytes rule.
    """

    event_refs: tuple[str, ...]
    record_keys: tuple[str, ...]
    data: bytes

    def __post_init__(self) -> None:
        # A frozen dataclass does not check types at runtime; the contract does.
        # ``bytes`` exactly: a bytearray is mutable and its sha would change after
        # construction, which is the frozen-bytes contract broken from inside.
        if type(self.data) is not bytes:
            raise TypeError("Block.data must be bytes (not bytearray) — text enters the prompt only as frozen bytes")
        if not isinstance(self.event_refs, tuple) or not isinstance(self.record_keys, tuple):
            raise TypeError("Block refs and keys must be tuples")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def __len__(self) -> int:
        return len(self.data)


class FrozenCorpusText:
    """Frozen event lines by ref; canonical record lines by key; concatenation."""

    def __init__(self, corpus_dir: pathlib.Path = DEFAULT_CORPUS) -> None:
        self.corpus_dir = pathlib.Path(corpus_dir)
        self._event_lines: dict[str, bytes] = {}
        raw = (self.corpus_dir / "stream.jsonl").read_bytes()
        for line in raw.split(b"\n"):
            if not line.strip():
                continue
            # Parse only to learn the ref; the line itself is kept verbatim.
            ref = json.loads(line)["ref"]
            if ref in self._event_lines:
                raise ValueError(f"duplicate ref in frozen stream: {ref}")
            self._event_lines[ref] = line

        entities = json.loads((self.corpus_dir / "entities.json").read_text(encoding="utf-8"))
        self._record_lines: dict[str, bytes] = {}
        self.entity_keys: tuple[str, ...] = tuple(
            entity_key(e) for e in entities if e.get("kind") != "Edge")
        self.edge_keys: tuple[str, ...] = tuple(
            edge_key(e) for e in entities if e.get("kind") == "Edge")
        for record in entities:
            key = edge_key(record) if record.get("kind") == "Edge" else entity_key(record)
            if key in self._record_lines:
                raise ValueError(f"duplicate record key: {key}")
            self._record_lines[key] = record_line_bytes(record)

    # -- lookups -----------------------------------------------------------

    def event_line(self, ref: str) -> bytes:
        try:
            return self._event_lines[ref]
        except KeyError:
            raise KeyError(f"no frozen event line for ref {ref!r}") from None

    def record_line(self, key: str) -> bytes:
        try:
            return self._record_lines[key]
        except KeyError:
            raise KeyError(f"no canonical record line for key {key!r}") from None

    @property
    def record_keys(self) -> tuple[str, ...]:
        """Every record key in load order: entities, then edges."""
        return self.entity_keys + self.edge_keys

    @property
    def record_lines_digest(self) -> str:
        """sha256 over every canonical record line, in SORTED key order, LF-joined + LF.

        Sorted, not load order: the digest must be reproducible by anyone from
        ``entities.json`` alone without knowing how this class iterates (Codex,
        WP01 cycle 1). Recorded by the preflight (WP04) so the loaded record
        form is bound into the run.
        """
        joined = b"\n".join(self._record_lines[k] for k in sorted(self._record_lines)) + b"\n"
        return hashlib.sha256(joined).hexdigest()

    # -- assembly ----------------------------------------------------------

    def render_block(self, event_refs: Iterable[str], record_keys: Iterable[str]) -> Block:
        """Concatenate: event lines in the given order, then record lines, each + LF."""
        refs = tuple(event_refs)
        keys = tuple(record_keys)
        parts = [self.event_line(r) + b"\n" for r in refs]
        parts += [self.record_line(k) + b"\n" for k in keys]
        return Block(event_refs=refs, record_keys=keys, data=b"".join(parts))

    def render_full_view(self, view: Loaded) -> Block:
        """Arm D's block: every event in view order, then entities, then edges.

        Events first because each D prompt must be a byte prefix of the next
        in ask-time order (rubric §2 layout protocol); edges last because they
        were the part Codex found missing from the "full" dump.
        """
        refs: Sequence[str] = [str(e["ref"]) for e in view.events]
        keys = [entity_key(e) for e in view.entities] + [edge_key(e) for e in view.edges]
        return self.render_block(refs, keys)
