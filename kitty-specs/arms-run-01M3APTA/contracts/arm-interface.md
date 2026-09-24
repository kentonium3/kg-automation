# Contract: arm interface

Every arm is a callable registered in `run_849_harness.ARM_IMPLEMENTATIONS` under `"G"`, `"D"`
or `"R"` with the signature

    arm(question: str, ask_time: datetime, view: Loaded, ctx: CellContext) -> Answer

- `view` is the ArmView the harness already narrowed (`arm_view()`): D and R receive
  `view.links == []`; the arm must not construct links from any other source.
- `ctx` carries `repeat`, `seed` (= 1000 + repeat), the `ServingConfiguration`, the `Prompt`
  (registered text + slot), the shared `Embedder` (G, R), and for R the header's `r_k`.
- The arm **assembles context only**; it calls `ctx.prompt.render(assembled_text)` to obtain the
  request text and `ctx.serving.complete(text, seed)` to obtain the completion. It never builds
  a request any other way (the prompt hash is asserted inside `render`).
- **Before sending**, the arm counts `prompt_tokens` with `ctx.serving.count_tokens(text)`; if the
  count exceeds `ctx.serving.n_ctx_trained` it raises `ContextExceeded(prompt_tokens)` and sends
  nothing.
- `Answer` carries: `text`, `assembled_context_tokens`, `prompt_tokens`, `output_tokens`,
  `finish_reason`, `cache_write_tokens`, `cache_read_tokens`, `uncached_tokens`, `prefill_s`,
  `generation_s`, `generation_tok_s`, `plan: PlanRecord`. The harness adds `peak_gtt_gib`,
  `seed`, `attempt`, `elapsed_s`, the load counts.
- Any other exception is an infrastructure failure: the harness health-checks the substrate,
  retries up to twice, then records `error`.
- G additionally exposes `build_graph(question, view) -> GraphStats` (called once per question,
  before repeat 1) and `drop_graph(question)` (after repeat 3); both idempotent.
- R additionally exposes `derive_k(ledger_rows) -> (k, medians)` used once by the harness when the
  first R cell is reached; the harness writes `r_k` to the header and passes it in `ctx`.
