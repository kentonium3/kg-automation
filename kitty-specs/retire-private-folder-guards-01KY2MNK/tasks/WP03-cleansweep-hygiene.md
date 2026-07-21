---
work_package_id: WP03
title: Clean-sweep the hygiene guards + inbox scripts
dependencies: []
requirement_refs:
- FR-007
- FR-008
- NFR-003
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
- T014
agent: "claude:sonnet:implementer:implementer"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/inbox/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/escalation/hard_fail.py
- tests/escalation/test_hard_fail.py
- scripts/inbox/mark_processed.py
- tests/inbox/test_mark_processed.py
- scripts/inbox/classify_content.py
- tests/inbox/test_classify_content.py
- scripts/inbox/prescan.py
- tests/scripts/inbox/test_prescan.py
- scripts/inbox/route_and_finalize.py
- scripts/inbox/README.md
- scripts/vault/README.md
- scripts/office2/gitignore-additions.txt
role: implementer
tags: []
shell_pid: "22263"
shell_pid_created_at: "1784651109.595756"
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load implementer-ivan` before anything else.

## Objective

Keep the real leak/mis-write protection but express it in vault/inbox terms, and DELETE the
`_private` literal from operational code (Kent's clean-sweep decision). Authoritative detail:
`data-model.md` IC-07 rows + the DECISION note; FR-007/FR-008/NFR-003; the post-plan Codex MED-1/MED-2
findings are folded into the guidance below. Preserve behavior everywhere except the removed
`_private` literal.

## Subtasks

- **T010** — `scripts/escalation/hard_fail.py`: the alert redaction currently strips `~/second-brain`,
  `/second-brain`, and bare `_private` from title/body/url. **Keep the two `second-brain` fragments**
  (vault paths still fully redacted); **drop the bare `_private` fragment**. Net: every vault-path
  leak is still redacted; `_private` literal gone.
- **T011** — `scripts/inbox/mark_processed.py`: the C-001 refusal currently rejects a path containing
  `04-Growth/_private` before disk read, then ALLOWS notes under the resolved inbox root. **CRITICAL
  (Codex MED-1):** the inbox lives *inside* the vault, so do NOT switch to "refuse any vault/
  second-brain path" — that would reject the legitimate `01-Inbox`. Replace the `_private` pre-read
  refusal with "refuse a path OUTSIDE the resolved inbox root", preserving the inbox-root ALLOW
  semantics. Remove the `_private` literal.
- **T012** — DELETE the `_private` behavior (Kent clean-sweep): in `scripts/inbox/classify_content.py`
  remove the pre-read exit-3 refusal keyed on the `_private` path; in `scripts/inbox/prescan.py`
  remove the `_private` path-component skip in `scan_directory`. Physical exclusion means no
  `_private` content is present, so this is behavior-preserving in practice.
- **T013** — Strip `_private` mentions from `scripts/inbox/route_and_finalize.py` (doc/comment),
  `scripts/inbox/README.md`, `scripts/vault/README.md`, and remove the `_private` line from
  `scripts/office2/gitignore-additions.txt`.
- **T014** — Update tests to match: `tests/escalation/test_hard_fail.py` (keep the `second-brain`
  redaction assertions, drop the bare-`_private` one — overall vault-leak coverage unchanged);
  `tests/inbox/test_mark_processed.py` (refusal → out-of-inbox; ADD/keep a case proving a legitimate
  inbox-root path is ALLOWED); `tests/inbox/test_classify_content.py` and
  `tests/scripts/inbox/test_prescan.py` (remove the `_private` refusal/skip cases). Keep ≥ prior
  leak/refusal coverage on the retained guards (NFR-003).

## Definition of Done

- `pytest tests/escalation/test_hard_fail.py tests/inbox/test_mark_processed.py tests/inbox/test_classify_content.py tests/scripts/inbox/test_prescan.py -q` — all green.
- A legitimate inbox-root path is still allowed by `mark_processed` (proven by a test).
- Vault paths (`~/second-brain`, `/second-brain`) are still redacted by `hard_fail` (proven by tests).
- `grep -rn "_private" scripts/escalation/hard_fail.py scripts/inbox/` returns zero hits (clean sweep).
- Do NOT touch `tests/common/test_sync_cache.py` (`is_private` = unrelated Vikunja feature, FR-008).

## Risks & reviewer guidance

- MED-1: guard against `mark_processed` regressing into rejecting the inbox root.
- MED-1: guard against `hard_fail` dropping a `second-brain` fragment it must still redact.
- Reviewer: confirm the clean-sweep is behavior-preserving (only the `_private` literal removed) and
  the retained guards keep coverage.

## Activity Log

- 2026-07-21T16:26:06Z – claude:sonnet:implementer:implementer – shell_pid=22263 – Assigned agent via action command
- 2026-07-21T16:39:52Z – claude:sonnet:implementer:implementer – shell_pid=22263 – WP03 in lane (d742a032); clean-sweep done, MED-1 guardrails verified (inbox-root allowed + vault redaction retained), 148/755 tests pass. From primary per #710.
