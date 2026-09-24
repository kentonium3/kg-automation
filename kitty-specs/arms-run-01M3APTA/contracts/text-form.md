# Contract: the shared text form (research.md D-7)

    arms849.text.render_event_text(event: dict) -> str     # json.dumps(event, sort_keys=True, default=str)
    arms849.text.render_entity_text(entity: dict) -> str   # json.dumps(entity, sort_keys=True, default=str)

- D's dump = `"\n".join(render_event_text(e) for e in view.events)` + `"\n"` +
  entities as `json.dumps(view.entities, indent=2, sort_keys=True)` — **events first, then
  entities** (§2 prompt-layout protocol). This is byte-identical to what gate (b) measured.
- R's chunk for event `e` = `render_event_text(e)`; R's records block = the same entity block as D.
- G's `EpisodicNode.content` for event `e` = `render_event_text(e)`.
- Test: for every `ref` in the corpus, the three arms' text for that event is one string.
- If the design lead rules in a natural-language rendering at post-plan, only these two functions
  change; §2's prefix token figures are then re-measured and re-registered (design lead's hand).
