# Research Decision Log

This is research-kitty's decision-log artifact. It captures the Phase 0 decisions made before research execution starts — i.e., decisions baked into the spec and plan that downstream WPs should not re-litigate.

## Summary

- **Mission**: `felix-vikunja-sync-architecture-research-01KT7Q15`
- **Date**: 2026-06-03
- **Researchers**: Kent Gale (operator); Claude (orchestrator + dispatched implementers)
- **Open Questions**: None at Phase 0. Six sub-questions (RQ-1 through RQ-6) are the research itself; they have explicit methodology in plan.md and are not open in the "needs clarification" sense.

## Decisions & Rationale

| Decision | Rationale | Evidence | Status |
|----------|-----------|----------|--------|
| Mission type = `research` (set at create time) | Prior session's software-dev default mis-shaped the artifact layout; research-kitty's two-location convention (kitty-specs/.../research/ for planning; docs/research/<slug>/ for deliverables) is the canonical research-mission shape. | Prior aborted session; spec-kitty mission templates at `~/.local/pipx/venvs/spec-kitty-cli/lib/python3.13/site-packages/specify_cli/missions/research/`. | final |
| Sequential single-lane execution (WP01 → WP02 → WP03 in `lane-planning`) | Research artifacts are markdown; per-WP sequencing cost is small; sidesteps spec-kitty #1684 (sibling-lane non-propagation); matches research-kitty's `planning_artifact` execution-mode default. | spec-kitty diagnostic `docs/diagnostics/1684_lane-base-not-inferred-from-wp-deps.md`; prior session's option-A choice. | final |
| Live-probe scope = read-only GET only | Prior session's plan default; read-only is sufficient to answer RQ-1; write probes would create test residue on the live Vikunja and are not required to answer any RQ. | spec.md FR-001 explicit. | final |
| Sourcing depth = exhaustive (every callsite, not representative) for RQ-2 | Mission #408 WP01 was a single-callsite bug; representative coverage would miss the same class. | spec.md FR-004; prior session memory of #408. | final |
| Artifact layout = per-RQ files in `findings/` subdir inside the deliverables path | Spec-kitty's owned_files disjointness rule forces per-WP file separation; per-RQ files map cleanly to per-WP ownership while keeping the synthesis as a single index in `findings.md`. | spec-kitty finalize-tasks ownership rules (observed in prior session). | final |
| Deliverables path = `docs/research/felix-vikunja-sync-architecture/` (clean slug, no ULID suffix) | The mission slug carries a mid8 ULID for uniqueness, but the deliverables path is project-permanent and benefits from a clean kebab-case slug. Establishes naming convention for future research missions. | research-kitty plan-template § Research Deliverables Location (line 118: "Update this path during planning"). | final |
| Conflict surfacing = silent log + WhatsApp router for unsafe class only | Operator decision in prior session: log-first emission (forward-compatible with #516); WhatsApp for unsafe class; no GitHub-issue auto-file as primary surface. | spec.md C-003; cross-reference issue #516. | final |
| Polling-only, not webhooks | Operator decision predating this research per memory `feedback_vikunja_sync_polling_not_webhooks`. | spec.md C-001. | final |
| Vikunja wins conflicts | Operator decision per Epic #507 and spec.md RQ-3 framing. | spec.md C-002. | final |
| Sub-issues land at `spec: brief`, NOT `spec: ready` | Two-stage spec lifecycle per memory `feedback_spec_lifecycle`; operator formalization is a separate gate. | spec.md C-008. | final |
| Codex paused; review = Claude self-review or operator review | Memory `feedback_codex_paused`; codex 0.135.0+ silently drops profile sandbox setting (`openai/codex#26207`). | spec.md C-007. | final |
| Roadmap mission count: 2–4 (default tilt fewer-larger) | Smaller mission count = lower coordination overhead; expand only when a hard sequencing dependency forces a split. | spec.md FR-012 + prior session plan default. | final |
| Charter governance unresolved — scheduled as post-mission maintenance | Diagnostic `governance unresolved (pytest/python)` fires on every mission's setup output; the deferred-after-#343 condition is satisfied but issue not yet filed; scheduled to be addressed after this mission merges. | Memory `project_charter_tool_registry_mismatch`. | follow-up |

## Evidence Highlights

(This section will populate as Phase 0 evidence accumulates in evidence-log.csv. At plan time, no rows exist yet — the gathering phase belongs to WP01.)

- **Key insight 1** — _(populated by WP01 substrate findings)_
- **Key insight 2** — _(populated by WP01 substrate findings)_
- **Risks / Concerns**:
  - Charter governance unresolved (low — scheduled as post-mission maintenance).
  - Live Vikunja instance availability during WP01 (mitigated by stop conditions in plan.md RQ-1; fallback to docs-only with `documented` tagging per NFR-006).
  - Vikunja API may lack a stable identifier sufficient for cross-cycle re-identification — would surface as a research-blocking finding per plan.md RQ-3 stop conditions.

## Next Actions

1. `/spec-kitty.tasks` to materialize the three WPs.
2. Implementation handoff (per `/spec-kitty.tasks` Step 10) — Kent's prior preference was WP01-only dispatch before authorizing WP02+WP03 (lower-risk staging given WP03's irreversible sub-issue filing).
3. Charter governance maintenance scheduled post-merge (memory `project_charter_tool_registry_mismatch`).

> This decision log is living. As Phase 0 evidence accumulates and the locked decisions get tested against real probes/code, update entries here with `follow-up` status if needed so downstream implementers can trust the history.
