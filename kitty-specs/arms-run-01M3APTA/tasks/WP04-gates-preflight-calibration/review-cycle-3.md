---
affected_files: []
cycle_number: 3
mission_slug: arms-run-01M3APTA
reproduction_command:
reviewed_at: '2026-09-25T03:14:56Z'
reviewer_agent: claude
wp_id: WP04
---

[MAJOR] scripts/research/arms849/preflight.py:161 — Checkers ignore the requested checkout and corpus — the presence guard and recorded commit use `repo_root`, but imported checkers inspect their own checkout and default corpus, allowing evidence from different inputs — bind checker execution to the requested paths or reject unsupported overrides.
[MAJOR] scripts/research/arms849/calibration.py:121 — Jump-over handling accepts `k=0` as successful — G=10000 and R(k)=10000+4000k return `(0, "ok")`, although D-10 requires candidates starting at k=1 and none qualifies — exclude k=0 from successful candidates and add this regression.
[MINOR] scripts/research/arms849/sampler.py:94 — Outstanding reads still mutate `missed_intervals` after context exit — returned diagnostics depend on serialization timing despite the closed-window guard — prevent counter updates after closure and test that the entire returned sample remains unchanged.

Design-lead read (20260925T025535601439Zd87a37e293), folded in the same cycle:
[MAJOR] preflight.py — chat_template_sha256 must be a REQUIRED top-level Preflight field sourced from the cached tokenizer, refused when absent, compared by the in-container gate to ServingConfiguration.chat_template_sha256.
[MINOR] preflight.py — fingerprint compare by !=, not startswith.
[MINOR] preflight.py — cite rubric_commit c166e836.

Source: Codex read-only review, WP04 cycle 3, 2026-09-25. VERDICT: REJECT (cycle-2 four confirmed fixed; three new).
