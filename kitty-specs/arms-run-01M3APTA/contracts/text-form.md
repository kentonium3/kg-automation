# Contract: the shared text form, enforced at final assembly (research.md D-7)

    arms849.text.render_line(obj: dict) -> str                       # json.dumps(obj, sort_keys=True, default=str)
    arms849.text.render_block(events, entities, edges) -> str        # events (one line each) \n entities (one line each) \n edges (one line each)

- The **only** way an arm obtains slot text is `render_block(...)`; `Prompt.render(assembled)`
  accepts a `Block` object produced by it, not a string. Bytes and tokens are counted on the
  returned block — what was inserted, not what was stored.
- **D**: `render_block(view.events, view.entities, view.edges)` — the whole replay-visible view,
  events first, then entities, then edges.
- **R**: `render_block(top_k_events_sorted_by_ask_time, view.entities, view.edges)` (pending the
  design lead's population ruling; the entity/edge records block is the same as D's).
- **G**: `render_block(assembled_episodes, assembled_nodes, assembled_edges)` in the deterministic
  order of D-15; `EpisodicNode.content` at write time is `render_line(event)`.
- Tests: for every `ref`, the three arms' event line is one string; a D block's event section is
  byte-identical to the loader's replayed events rendered in order; a G cell's inserted block
  hashes to the recorded `assembled_context_sha256`.
- If the design lead rules in a natural-language rendering, only `render_line` changes; §2's
  prefix token figures are then re-measured and re-registered by the design lead.
