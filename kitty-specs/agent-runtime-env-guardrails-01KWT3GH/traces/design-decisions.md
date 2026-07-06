# Design Decisions

> Capture the rationale that would otherwise evaporate.

**Prompting questions**
- What decision was made?
- What alternatives were considered?
- What was the rationale — why this option over the others?

---

## Entries

- `[2026-07-05][specify]` Decision: **Guard semantics = anchor-for-portability.** A
  `python3 -m scripts.…` invocation must be robust whether or not it runs under
  `openclaw-gateway.service`. Alternatives: (a) treat gateway-provided PYTHONPATH as a
  compliant contract and pass those invocations; (b) hybrid classification by launch
  context. Rationale (Kent): "allow for the possibility of `-m scripts.` running outside
  the gateway" — so leaning on the gateway env is exactly the unstated assumption we're
  killing. Anchoring also REDUCES Felix's coupling to a native OpenClaw element.
- `[2026-07-05][specify]` Decision: **Canonical anchor form must NOT hardcode a checkout
  path.** Alternatives: naive `cd /home/claude/kg-automation && python3 -m scripts.…`.
  Rationale: hardcoding a checkout is itself one of the three assumptions #658 exists to
  eliminate ("which of office2's two checkouts is the checkout"). The anchor must resolve
  repo-root robustly (thin wrapper / explicitly-consumed declared-root env), not bake a
  path. Exact form deferred to plan phase + flagged as a Codex-review target.
- `[2026-07-05][specify]` Decision: **`-m scripts.` module form is RETAINED, not removed.**
  Rationale: helpers importing `scripts.common.*` REQUIRE the `-m scripts.X.Y` form
  (script-path form fails ModuleNotFoundError — two prior production incidents). The bug
  is the unstated cwd/PYTHONPATH dependency, not the `-m` form itself; we make the
  dependency explicit, we don't change the invocation style.
- `[2026-07-05][specify]` Decision: **`~`/HOME reads vs writes split.** The guard flags
  `~`/HOME-relative WRITES (the #656 stray-dir class) but PERMITS reads of `~/.openclaw/…`
  openclaw-home paths. Rationale (from #658 body): reads of OpenClaw's own home are a
  legitimate, stable contract; only writes landed content in the wrong (unsynced) place.
- `[2026-07-05][specify]` Decision: **Helper/library/skill = domain-co-located helper.**
  The env-assumption check extends `scripts/openclaw/agents/validate_workspace.py` (#587)
  plus a pytest guard — NOT a shared `scripts/lib/` primitive or a skill. Rationale
  (helper-script-conventions §9): its only consumer is the agent-workspace surface.
- `[2026-07-05][specify]` Decision: **Entirely Felix-side; no native OpenClaw elements
  altered.** No change to OpenClaw core, `~/.openclaw/skills/` layout, openclaw.json, or
  `openclaw-gateway.service`. Rationale: keeps the change Tier-3 and the blast radius on
  our side of the fence (Kent's explicit boundary check).
- `[2026-07-05][plan]` Decision: **Scope covers BOTH `-m scripts.` AND abs-path invocations
  (D1); canonical form REUSES gateway PYTHONPATH fail-loud (D2).** Rationale: live scan found
  the checkout-path axis in three shapes (bare, hardcoded-cd, hardcoded abs-path); reuse
  avoids a gateway-unit change. Alternatives: `-m scripts.` only (leaves cruft); FELIX_REPO_ROOT
  var (touches gateway unit).
- `[2026-07-05][plan/codex] REVERSAL` Decision: **canonical form = the CD form
  `cd "${PYTHONPATH:?}" && …`, NOT the non-cd `PYTHONPATH=… python3 -m …`.** Post-plan Codex
  HIGH-3 showed the non-cd form fixes imports but leaves cwd drifted — a helper doing relative
  I/O still breaks (the #656 mode). CD form makes cwd deterministic (repo root). Companion:
  helper args must be absolute + a non-repo-cwd smoke test. Rationale: robustness over the
  cwd-preservation the non-cd form bought (moot since args are absolute).
- `[2026-07-05][plan/codex]` Decision: **"works without gateway" = fail-loud, not magic.**
  Codex HIGH-2: `${PYTHONPATH:?}` fails outside the gateway. Reconciled to "under gateway OR
  exported PYTHONPATH; fail-loud otherwise" — matches Kent's "allow running outside gateway"
  intent (don't silently break). Alternative (magically resolve anywhere) is impossible without
  hardcoding.
- `[2026-07-05][plan/codex]` Decision: **doc-auditor dispositioned RETIRED, not audited.**
  Codex MED-5: FR-008 "audit doc-auditor" contradicted the validator excluding it. It's a
  scripts-first driver with no live agent (#343) → explicit retired disposition, not an
  unverifiable audit.
