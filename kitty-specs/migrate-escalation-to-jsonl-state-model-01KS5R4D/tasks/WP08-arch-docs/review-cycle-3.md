---
affected_files: []
cycle_number: 3
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
reproduction_command:
reviewed_at: '2026-05-21T19:43:50Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP08
---

**Issue 1: Hard-fail helper is documented under the wrong module path.**

WP08 documents `scripts/escalation/schema.py` as the Q10 hard-fail bug-filing helper in `service-inventory.json`, `service-inventory.md`, and `data-flows.view.md`. That is not compatible with the mission contract: `contracts/api.md` defines `schema.py` as the event-parameter validator surface, while `tasks/WP04-hard-fail-dedup.md` owns the actual hard-fail bug filing helper at `scripts/escalation/hard_fail.py`.

Please revise the architecture docs so `schema.py` is described only as schema validation, and the hard-fail bug-filing/dedup surface is registered as `scripts/escalation/hard_fail.py`. Also add `scripts/escalation/hard_fail.py` to the `felix-admin-escalation` dependency list and ensure every touched markdown view distinguishes the schema validator from the hard-fail filer.

**Issue 2: Service-inventory helper entries do not carry the WP-required metadata.**

T024 says each new helper entry should include `name`, `kind`, `path`, `runs_on`, `invoked_by`, `writes_to`, `reads_from`, `credentials`, and `updated_by: "#309"`. The current implementation added the helpers only as `config_files` under `escalation-daily`, with `host`/`introduced_by` but no per-helper `updated_by`, reads/writes, credentials, or invocation metadata.

The `config_files` placement matches the habits precedent and is acceptable as the container pattern, but each helper record still needs the required metadata where the architecture schema can carry it. If the existing schema cannot support those exact keys at top level, add them to the helper objects under `config_files` consistently and mirror the same details in `service-inventory.md`.

**Notes from review**

- The extra markdown files are in scope despite the owned-files mismatch: they are architecture views derived from the same authoritative JSON and are required to keep JSON and markdown synchronized.
- JSON parsing passes for both touched JSON files.
- `python3 tooling/scripts/validate_docs.py docs/design/architecture/data/` currently fails on a pre-existing base-branch frontmatter issue in `docs/design/architecture/baselines/cutover-log.md` (`status: active`, `level: 1`), not on WP08's changed files.
