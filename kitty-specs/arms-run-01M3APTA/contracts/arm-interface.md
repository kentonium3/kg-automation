# Contract: arm interface

    arm(question: Question, view: Loaded, ctx: CellContext) -> Answer

- `Question` comes from `arms849.questions` (id, ask_time, text) — the oracle-free manifest whose
  digest is in the header; the harness never passes a bare id.
- `view` is the ArmView the harness narrowed (`arm_view()`): D and R receive `view.links == []`.
- `ctx` carries `repeat`, `attempt`, `seed` (= 1000 + repeat), `ServingConfiguration`, `Prompt`,
  the shared `Embedder` (G, R), the `calibration` record (R), and `limits = {trained, configured,
  permitted}` (D-11). **Dated 2026-09-25 (design-lead ruling, bus msg
  20260925T185141534756Z7fc2eda03e):** `limits`, `limit_applied` and `limit` are derived by the
  `CellContext` constructor from the configuration; arms check the applied pair against the
  configuration and never receive them independently (an incoherent `CellContext` cannot be built —
  WP08's contract, one implementation).
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
- **Exception classes (dated note 2026-09-25, design-lead ruling, bus msg
  20260925T043533517516Z003ce84a20, landed with the WP06 cycle-2 fold):** an arm lets out exactly
  three classes. (1) `ContextExceeded` → the context outcome row (`exceeds_model_context`),
  complete with the plan and `prompt_tokens` — the arm re-raises a bare `serving.ContextExceeded`
  from `complete`'s last-line guard as its own carrying the plan, so the row is complete whichever
  line fired. (2) `ArmRefusal` (a configuration defect: a view carrying loader links handed to a
  flat arm, `cache_prompt` off, an empty / recordless / eventless view) → a **terminal `error` row
  on the first attempt, zero retries**; the row's `error` carries the refusal message
  (`ArmRefusal: …`); retrying a permanent defect would burn a primary attempt and count against
  NFR-008's per-attempt bound. (3) Everything else → the infrastructure ladder above (≤ 2
  retries). The ledger treats an `error` row whose `error` begins `ArmRefusal:` as terminal without
  the `AttemptsExhausted` path.
- **G** exposes `build_graph(question, view) -> GraphStats` (once per question, before repeat 1;
  idempotent) and `drop_graph(question)`; assembly follows D-15 exactly.
- **R** exposes the ONE bound adapter `calibration_inputs(text, tokenizer, embedder, views:
  Mapping[qid, Loaded], index_cache) -> (availability: dict[qid, int], assemble_r_tokens:
  Callable[[qid, k], int])`, which resolves each question's view and index internally and populates
  the same index cache the R cells later read (calibration and cells embed once, identically);
  `r_tokens_for` / `availability_cap` remain the primitives it composes. D-10 itself is implemented
  ONCE, in `arms849.calibration.calibrate(ledger, availability, assemble_r_tokens)`, which the harness
  calls as `calibrate(ledger, *R.calibration_inputs(...))` once all eight G repeat-1 cells are `ok`;
  the harness writes the `calibration` record. **(Dated 2026-09-25, design-lead ruling R-1, bus msg
  20260925T184854956609Z73c64e07a6; supersedes the earlier `calibrate(g_repeat1_rows, views)` line.)**
