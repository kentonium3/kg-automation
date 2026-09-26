# Contract: the shared text form — FROZEN BYTES, never a re-dump (research.md D-7, A4)

    arms849.text.event_line(ref) -> bytes        # the exact line from the frozen stream.jsonl for that ref — read, not re-serialised
    arms849.text.record_line(id) -> bytes        # ONE canonical line per entity/edge, produced ONCE by the loader from entities.json at load time,
                                                 #   its digest recorded in preflight.json; every arm reuses those bytes
    arms849.text.render_block(event_refs, record_ids) -> Block   # concatenation ONLY: event lines in the given order, then record lines

- `render_block` may only concatenate; it never serialises. There is no other way to obtain slot
  text: `Prompt.render(block, question_text)` accepts a `Block`, not a string.
- **D**: `render_block([e.ref for e in view.events], [entity ids… then edge ids…])` — the whole
  replay-visible view: events, then entities, then edges.
- **R**: `render_block(top_k_refs_sorted_by_ask_time, [entity ids… then edge ids…])` (A4: records
  always present as the structured half; top-k over events only).
- **G**: `render_block(assembled_episode_refs, assembled_node_ids + assembled_edge_ids)` in D-15
  order; `EpisodicNode.content` at write time is `event_line(ref)` decoded.
- Tests: (1) for every ref, an arm's inserted event line == the corpus line, byte for byte;
  (2) the three arms' line for a ref are one bytes object; (3) a D block's event section equals
  the replayed events' corpus lines concatenated in order; (4) a G cell's inserted block hashes to
  its recorded `assembled_context_sha256`; (5) record lines hash to the preflight-recorded digest.
- Why: `json.dumps(sort_keys=True, default=str)` can differ from the frozen bytes (unicode
  escaping, key order, float formatting); §2's figures must be counted on what was frozen.
