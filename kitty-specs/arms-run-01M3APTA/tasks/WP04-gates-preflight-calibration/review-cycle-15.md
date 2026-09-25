---
affected_files: []
cycle_number: 15
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T21:15:49Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/litscan.py:324 — `"".join(("or","acle")[::1 if "a".__hash__()>4000000000000000000 else -1])` produces a label hit under seed 0 but no hit under seed 3 through the real `string_constants()` API; an invoked hash method escapes the determinism check — why: identical source passes or fails the blindness scan depending on the process seed — fix: refuse process-dependent hash method invocations, including bound and descriptor forms, and add this two-seed regression.
[MINOR] scripts/research/arms849/litscan.py:392 — `list[None]` raises ScanRefused under both seeds because `_inert_type_expr` accepts `type(None)` but not `None` — why: contradicts the stated accommodation — fix: also accept `p is None`. (Superseded: the design lead ruled option (d) at 21:14Z, which deletes `_inert_type_expr`.)

Carrier audit (the design lead's stopping question) — COMPLETE per Codex: plain values (scalars, marked containers, slice, range); allowlisted identity (`().__class__` resolves to tuple); materialised (reversed/zip/enumerate/map/filter iterators, dict views); refused carriers (bound methods, method-wrappers, unbound method descriptors, non-allowlisted objects); opaque (excluded names, generators, comprehensions, lambdas); inert types. "No additional uncovered carrier type was demonstrated." Real package "12 modules scanned (12 registered present), no hit" under both seeds. 118 passed / 191 sandbox socket failures (environment).

The MAJOR is a NEW class, not a carrier: a process-dependent method RESULT (hash) from a method of a literal receiver invoked in its own node. Routed to the design lead before any fold. Source: Codex read-only review (gpt-6-astra), WP04 cycle 15 on lane-d @75f679a4, 2026-09-25. VERDICT: REJECT.
