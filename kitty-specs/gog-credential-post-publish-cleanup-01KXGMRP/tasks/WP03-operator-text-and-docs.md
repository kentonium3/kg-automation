---
work_package_id: WP03
title: Operator-facing text — gog-reauth.sh + docs
dependencies: []
requirement_refs:
- FR-006
- FR-007
- FR-008
tracker_refs: []
planning_base_branch: feat/731-gog-cred-post-publish-cleanup
merge_target_branch: feat/731-gog-cred-post-publish-cleanup
branch_strategy: Planning artifacts for this mission were generated on feat/731-gog-cred-post-publish-cleanup. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/731-gog-cred-post-publish-cleanup unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
- T013
agent: "claude"
shell_pid: "84559"
shell_pid_created_at: "1784046844.430985"
history:
- '2026-07-14: authored from spec + plan (post-plan Codex folded)'
agent_profile: curator-carla
authoritative_surface: docs/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/security/gog-reauth.sh
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/INDEX.md
- docs/runbooks/credential-liveness-probe-ops.md
- docs/runbooks/google-workspace-ops.md
- docs/runbooks/calendar-helper-ops.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load curator-carla` (role: implementer). Adopt its identity,
boundaries, and initialization declaration, then proceed.

## Objective

Correct all operator-facing text that still teaches the obsolete External+Testing
7-day expiry model: the `gog-reauth.sh` re-auth helper (wording + consent guidance)
and the architecture data / narrative / runbook docs. Describe the current reality —
published app, non-expiring tokens, a single `dead` liveness classification.

**Scope guard (C-005)**: touch ONLY credential-liveness / gog-reauth occurrences.
The string `7-day` appears in many unrelated places (habits, vikunja token rotation,
other runbooks) — leave those alone.

Context: [plan.md](../plan.md) (IC-04, IC-06), [research.md](../research.md) (R-07),
[spec.md](../spec.md) (FR-006, FR-007, FR-008).

## Subtasks

### T009 — `gog-reauth.sh` header + closing wording  [P]

File: `scripts/security/gog-reauth.sh`

1. Rewrite the top-of-file comment block (the "Why this exists" paragraph) to state
   the app is **published** and tokens no longer expire on a 7-day cycle; the script is
   run to (re)mint or repair a token after revocation, not weekly. Drop the
   "External + Testing publishing status … hard 7-day expiration … Every ~week" text.
   You may keep the #572 tracking reference and the two-interactive-steps note.
2. Rewrite the closing summary (`==> gog-reauth complete.` block): remove the
   `Next forced re-auth: ~$NEXT_DUE (External+Testing OAuth app 7-day cycle)` line and
   the "Eliminate the cycle: publish the OAuth app…" line (the app is already
   published). Delete the `NEXT_DUE=$(date -u -d '+7 days' …)` computation.
3. **Do not alter the auth flow** — leave `gog auth add … --services …`, the env
   setup, the self-update/git-pull, and the liveness probe intact.

### T010 — `gog-reauth.sh` consent guidance rewrite  [P]

File: `scripts/security/gog-reauth.sh` (the "Browser-side steps" heredoc)

Replace the `4. Check ALL six scope boxes (Gmail, Calendar, Drive, Contacts, Sheets,
Docs)` instruction with accurate guidance reflecting the real consent screen (verified
2026-07-14): the scopes expand to **ten** checkboxes. Instruct the operator to:
- Grant the personal-data scopes (Drive; "Other contacts"; Contacts; Docs; Sheets;
  Calendar; the three Gmail settings/read/compose scopes).
- **Leave "See and download your organization's Google Workspace directory" UNCHECKED**
  unless directory access is explicitly wanted — declining it does not break the
  token (verified: `gog contacts list` works without it). Note that gog's `contacts`
  service is why the directory box appears.
Remove the "six" count. Keep the step numbering coherent.

### T011 — `service-inventory.json`: framing + `exec_start` fix

File: `docs/design/architecture/data/service-inventory.json`

1. In the `credential-liveness-probe` service entry, drop the routine-7day / Testing-app
   framing; describe the probe as classifying a dead credential as a single `dead`.
2. Fix the stale `exec_start`: `scripts.security.credential_liveness_probe` →
   `scripts.security.credential_health_check` (matches the actual unit).
3. Keep JSON valid.

### T012 — `service-inventory.md` + `docs/INDEX.md`  [P]

Files: `docs/design/architecture/service-inventory.md`, `docs/INDEX.md`

Drop routine-7day / Testing-app framing for the credential-liveness surface; describe
the single `dead` classification. Only the credential-liveness references.

### T013 — Runbooks  [P]

Files: `docs/runbooks/credential-liveness-probe-ops.md`,
`docs/runbooks/google-workspace-ops.md`, `docs/runbooks/calendar-helper-ops.md`

1. `credential-liveness-probe-ops.md`: replace the routine-7day/unexpected/Testing-app
   description with the single `dead` classification; remove `reauth_marker_glob`
   references (the field no longer exists).
2. `google-workspace-ops.md`: drop the 7-day Testing-app expiry framing for the gog
   credential re-auth; describe the published-app reality. Keep the mechanical
   `gog auth add … --services …` steps (still valid), but update any "must re-auth
   weekly / 7-day cycle" narrative.
3. `calendar-helper-ops.md`: update the note that the gog 7-day Testing-mode expiry
   affects the credential; the app is published now. Leave the #572 residual reference
   accurate to current state.

## Branch Strategy

Planning/base branch and final merge target are both
`feat/731-gog-cred-post-publish-cleanup`. Independent of WP01/WP02 (parallel).
Execution worktrees are per-lane from `lanes.json`.

## Definition of Done

- [ ] T009–T013 complete.
- [ ] `grep -nE "7-day|Testing|Next forced re-auth|six scope|six scope boxes" scripts/security/gog-reauth.sh` returns nothing; the auth flow is unchanged.
- [ ] The consent guidance names the directory box as decline-by-default and no longer says "six".
- [ ] `service-inventory.json` `exec_start` reads `scripts.security.credential_health_check`; JSON valid.
- [ ] No credential-liveness doc still describes a routine 7-day / Testing-app classification or `reauth_marker_glob`.
- [ ] Unrelated `7-day` occurrences (habits, vikunja, etc.) are untouched.
- [ ] Docs validation passes (`python tooling/scripts/validate_docs.py` if it covers these files).

## Risks / Reviewer guidance

- The biggest risk is **over-reach** — verify the diff touches only credential-liveness /
  gog surfaces. Reject edits to unrelated `7-day` strings.
- Verify `gog-reauth.sh` behavior is unchanged (only comments/echo text edited).
- Verify the `service-inventory.json` `exec_start` correction matches the real unit
  (`/usr/bin/python3 -m scripts.security.credential_health_check`).

## Activity Log

- 2026-07-14T16:26:43Z – claude – shell_pid=82031 – Assigned agent via action command
- 2026-07-14T16:33:59Z – claude – shell_pid=82031 – gog-reauth wording+consent + 6 docs reframed; JSON valid; doc validation passed; grep clean (only retired-history refs remain)
- 2026-07-14T16:34:15Z – claude – shell_pid=84559 – Started review via action command
- 2026-07-14T16:35:00Z – user – shell_pid=84559 – Review passed: gog-reauth wording+consent (auth flow untouched, bash -n OK), 6 docs reframed to single 'dead' + published-app reality, exec_start fixed, JSON valid, doc-CI passed
