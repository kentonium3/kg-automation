---
affected_files: []
cycle_number: 2
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
reproduction_command:
reviewed_at: '2026-05-21T20:25:00Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP04
---

**Issue 1**: `render_bug_body` does not emit the Entity 5 title format verbatim.

The data model and spec define the hard-fail title as:

`Escalation hard-fail: <task title> (task #<vikunja_id>) — <short reason>`

The implementation currently renders `--` instead of the em dash separator, and the tests pin that drift. Dedup still works because it keys on `(task #<id>)` and `Escalation hard-fail`, and the Felix `Bug: ` prefix is transparent, but the title no longer matches the required Entity 5 format.

Remediation: render the Entity 5 title with the em dash separator and update the title-format tests/docstrings to expect the same final title shape after Felix prefixes it: `Bug: Escalation hard-fail: ... (task #N) — ...`.

**Issue 2**: The no-second-brain guarantee is not enforced.

The WP requires that hard-fail bodies do not leak second-brain paths (C-006), and reviewer guidance asks to verify that no second-brain paths can leak into bug bodies. The current test only uses well-behaved inputs, and the test comment explicitly notes adversarial inputs would propagate. `render_bug_body` interpolates `task_title`, `jsonl_path`, `detection_snippet`, Vikunja state, and error text directly into the issue body, so a `~/second-brain` or `/second-brain` substring in any caller-provided field would leak.

Remediation: add a small sanitizer or validation step before body rendering/filing that prevents `~/second-brain`, `/second-brain`, and `_private` path fragments from appearing in the rendered body. Then add tests with adversarial inputs covering at least `jsonl_path` and `detection_snippet` so the C-006 invariant is enforceable.

**Non-blocking notes**

The `felix-file-issue.py` adaptation is acceptable as-is. Since the canonical helper does not accept arbitrary raw issue bodies, passing the Entity 5 body through `--problem-statement-file` and documenting that it lands inside the Bug template Summary section is a reasonable integration choice. A future `--body-file` extension could make the issue body cleaner, but it is not required for WP04.

The `Bug: ` prefix does not break dedup because the search query uses substring anchors: `in:title "(task #<id>)" "Escalation hard-fail"` with `--state open`.

The shared-lane guard warning about `owned_files` appears to be stale lane metadata noise rather than a WP04 implementation problem: the WP04 frontmatter owns only `scripts/escalation/hard_fail.py` and `tests/escalation/test_hard_fail.py`.

Downstream warning: WP05 and WP06 depend on WP04 and should rebase after these changes.
