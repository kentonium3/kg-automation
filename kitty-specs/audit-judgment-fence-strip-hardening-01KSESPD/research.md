# Research: Audit Judgment Fence-Strip Hardening

**Phase**: 0 — Outline & Research
**Status**: COMPLETE

## Outstanding clarifications from spec

None. The specification's Assumptions, Dependencies, and Risks sections capture all open items; none require research to resolve.

## Decisions

### D-001 — Adopt existing `_strip_code_fence` verbatim

- **Decision**: Copy the existing implementation from `scripts/doc_audit/judgment/drift_interpretation.py` lines 436-458 into the new `scripts/doc_audit/judgment/_llm_response.py` module without modification (save for module-level docstring).
- **Rationale**: This implementation has been in production since mission #55 merged at `0e87918f`. Mission #55's operational verification confirmed it correctly handles Haiku 4.5's fence-wrapping. Re-implementing introduces risk of subtle behavioral divergence (e.g., whitespace handling, multi-line fence variants) that the existing code already gets right.
- **Alternatives considered**:
  - **Regex-based stripping** (e.g., `re.sub(r"^```(?:json)?\s*|\s*```$", "", text)`): rejected as over-engineered for a known prefix pattern. The line-based approach in the existing code is more explicit and easier to reason about.
  - **JSON-fence-aware parser library**: rejected as needless dependency for a 22-line function with zero current external callers.
  - **In-prompt fix** (instruct Haiku 4.5 to not emit fences): tried in the original prompts and failed (model ignores). Defensive parse-side fix is the proven approach.

### D-002 — Module name `_llm_response.py` per spec C-001

- **Decision**: New module at `scripts/doc_audit/judgment/_llm_response.py`.
- **Rationale**: Single-underscore prefix signals private-to-the-package status (Python convention). Name is descriptive and leaves room for future LLM-response-related helpers (e.g., schema-validation utilities) without expanding scope here.
- **Alternatives considered**: `_strip_fence.py` (too narrow — locks in the helper's current purpose); `_shared.py` (too generic — invites scope creep); `_helpers.py` (anti-pattern; useless name).

### D-003 — Inline fenced-input test cases (no new fixtures)

- **Decision**: Add fenced-input regression cases as inline string literals in the test functions, not as separate JSON fixture files under `tests/doc_audit/fixtures/anthropic_responses/`.
- **Rationale**: The existing fixture directory holds end-to-end Anthropic-response JSON (full envelope structure). The new regression cases test a string-in/string-out pure function, where the input is a brief literal like ` ```json\n{"foo": "bar"}\n``` `. Inlining keeps tests self-contained and avoids inflating the fixtures directory with trivial variants.
- **Alternatives considered**: Adding `*_fenced.json` siblings to existing fixtures: rejected because the fence-wrap is a string-level concern, not a response-envelope concern.

### D-004 — Import style: explicit relative from package

- **Decision**: Each modified script imports the helper via `from scripts.doc_audit.judgment._llm_response import _strip_code_fence`.
- **Rationale**: Matches the absolute-import style used elsewhere in `scripts/doc_audit/`. Keeps the import line visible at the top of each file so future readers can find the helper.
- **Alternatives considered**: Re-exporting from `scripts/doc_audit/judgment/__init__.py`: rejected because it would expand the package's public API for a private helper (violates C-002).

### D-005 — Test the helper's edge cases independently

- **Decision**: `test_llm_response.py` covers, at minimum: fenced with `json` tag, fenced without tag, fenced with leading/trailing whitespace, unfenced (identity-preserving), empty string, whitespace-only string. ≥ 95% branch coverage (NFR-003).
- **Rationale**: These cases enumerate the helper's complete behavior surface. Coverage on the helper protects all four call sites from regressions in this isolated unit.

## Closed-out unknowns

None.

## Dependencies & references

- Mission #55 commit `0e87918f` — source of the `_strip_code_fence` implementation being extracted.
- Diagnostic: `docs/diagnostics/drift-interpretation-payload-shape.md` — captures the observed Haiku 4.5 fence-wrap behavior.
- Issue [#411](https://github.com/kentonium3/kg-automation/issues/411) — the drift_interpretation half of this bug class.
- Issue [#416](https://github.com/kentonium3/kg-automation/issues/416) — this mission's tracking issue.
