# Contract: arm interface

    arm(question: Question, view: Loaded, ctx: CellContext) -> Answer

- `Question` comes from `arms849.questions` (id, ask_time, text) — the oracle-free manifest whose
  digest is in the header; the harness never passes a bare id.
- `view` is the ArmView the harness narrowed (`arm_view()`): D and R receive `view.links == []`.
- `ctx` carries `repeat`, `attempt`, `seed` (= 1000 + repeat), `ServingConfiguration`, `Prompt`,
  the shared `Embedder` (G, R), the `calibration` record (R), and `limits = {trained, configured,
  permitted}` (D-11).
- The arm assembles a `Block` via `arms849.text.render_block` and calls
  `ctx.prompt.render(block, question.text)` → the exact request text (chat template applied by
  `ctx.serving.serialize`); then `ctx.serving.count_tokens(request)`; if the count exceeds the
  limit the ctx names for this ledger (`trained` primary, `permitted` secondary) it raises
  `ContextExceeded(prompt_tokens, limit_applied)` and sends nothing. Otherwise
  `ctx.serving.complete(request, seed)`.
- `Answer` = `text, assembled_context_tokens, prompt_tokens, output_tokens, finish_reason,
  cache_read_tokens, uncached_tokens, cache_write_tokens, cache_state, cache_fraction, prefill_s,
  generation_s, generation_tok_s, assembled_context_sha256, plan: PlanRecord` — every telemetry
  field mandatory (D-13); the harness adds `peak_gtt_gib`, `falkordb_rss_peak_mib` (G), `seed`,
  `attempt`, `elapsed_s`, load counts, `r_g_ratio` (R).
- Any other exception: infrastructure failure → health check → retry ≤ 2 → `error`.
- **G** exposes `build_graph(question, view) -> GraphStats` (once per question, before repeat 1;
  idempotent) and `drop_graph(question)`; assembly follows D-15 exactly.
- **R** exposes `calibrate(g_repeat1_rows, views) -> Calibration` (D-10), called once by the
  harness when all eight G repeat-1 cells are `ok`; the harness writes the `calibration` record.
