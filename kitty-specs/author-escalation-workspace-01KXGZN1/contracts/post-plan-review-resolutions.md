# Post-Plan Codex Review — Findings & Resolutions

Reviewer: Codex (`spec-kitty-review` profile). Verdict: **NOT ready post-plan** (4 HIGH / 4 MED / 1 LOW). All findings verified against the codebase; dispositions below. Three scope-affecting findings (HIGH-1, HIGH-2, MED-5) were surfaced to Kent and resolved by explicit decision. This file also satisfies the accept-gate `contracts/` directory requirement (no API surface).

## Scope decisions (Kent, 2026-07-14)

- **HIGH-1 → Fix the Z date examples to ET offset.** The mission gains a correctness fix; the moved no-Z rule becomes internally coherent.
- **HIGH-2 → Expand: fully eliminate Goals(11).** Also clean SKILL.md, escalation-ops.md, and the unit test so #724 genuinely closes.
- **MED-5 → Allow the narrow AGENTS truthfulness fix.** FR-008 relaxed to permit two narrow AGENTS edits (the Z example + the enforcement sentence). Everything else in AGENTS stays untouched.

Net effect: scope moves from "pure refactor" to "refactor + internal-coherence fixes + full Goals(11) elimination." No feature/behavior additions; the changes are correctness + consistency + doc-hygiene. Post-merge Codex + live smoke remain load-bearing.

## Findings

### HIGH-1 — Z-suffix due-date examples contradict the moved no-Z rule
- **Evidence**: `TOOLS.md:38` (`"2026-04-10T00:00:00Z"`), `AGENTS.md:232-233` (`"<YYYY-MM-DD>T00:00:00Z"`) vs the no-Z rule in USER date-handling (moving to TOOLS). The Z form writes UTC-midnight, off-by-one in ET — the exact bug the rule prevents.
- **Resolution (FIX)**: rewrite both reschedule examples to the ET-offset form (`...T00:00:00-04:00`, with a note to use `-05:00` during EST), consistent with the date-handling block. → **FR-010**.

### HIGH-2 — #724 not fully absorbed (SKILL.md + runbook still exclude Goals 11)
- **Evidence**: `scripts/openclaw/skills/escalation/SKILL.md:50` (`project_id is NOT 11 (Goals)`) and `:60` (`Tasks in the Goals project (ID 11)`); `docs/runbooks/escalation-ops.md:31,34` name Goals(11). Runtime enumeration is already the deterministic helper (`enumerate_candidates.py` + `vikunja_scope.py` = `[13]`), so these are stale docs.
- **Resolution (FIX, expanded)**: remove Goals(11) from SKILL.md and escalation-ops.md. → **FR-011**. Note: `SKILL.md` is NOT an audited surface and is NOT synced by agent-prompt-sync (which handles only the 5 workspace files, `deploy_agent_prompts.py:61`); its office2 sync path must be verified/handled at deploy (quickstart §7b).

### HIGH-3 — Deploy parity checks target the wrong office2 path
- **Evidence**: quickstart used `/data/services/openclaw/data/felix-admin-escalation/`; the real dest is `/data/services/openclaw/escalation-agent/` (`docs/runbooks/agent-workspace-reconciliation.md:63`, `service-inventory.md:83,391`). Classic slug≠deploy-dir trap.
- **Resolution (FIX)**: all parity/smoke commands corrected to `/data/services/openclaw/escalation-agent/{SOUL,USER,TOOLS,AGENTS,IDENTITY}.md`. → quickstart §4/§6.

### HIGH-4 — Whole-fleet validator command is unusable as written (exits 1)
- **Evidence**: `validate_workspace.py` validates all active workspaces and exits 1 today because `felix-admin-calendar` fails Output Discipline (out of scope, #635).
- **Resolution (FIX)**: acceptance uses an escalation-SCOPED assertion — parse the JSON and assert the `felix-admin-escalation` object has `ok: true`; the known unrelated calendar failure is handled explicitly. → quickstart §2, NFR-001.

### MED-5 — AGENTS enforcement sentence becomes false after SOUL reduction
- **Evidence**: `AGENTS.md:305-308` says privacy "is enforced in SOUL.md, AGENTS.md, and TOOLS.md"; after SOUL → stance, SOUL no longer enforces it.
- **Resolution (FIX, narrow)**: edit that one sentence to "enforced in AGENTS.md and TOOLS.md (SOUL carries only a behavioral stance)". → **FR-012**, FR-008 relaxed.

### MED-6 — Invariant-A verification weaker than the requirement
- **Evidence**: `validate_workspace.py:83-87` passes if EITHER owner file has the token; data-model requires BOTH AGENTS and TOOLS.
- **Resolution (FIX)**: add a non-fakeable conservation check — the enforceable path token is present in BOTH AGENTS.md and TOOLS.md AND absent from SOUL.md. → quickstart §3, NFR-003.

### MED-7 — Conservation checks too token-level
- **Resolution (FIX)**: rewrite quickstart §3 as a row-by-row pass/fail checklist derived from the data-model move-table (Purpose removed, insistence stance present, ADD-justification trimmed, SOUL privacy = stance only, AGENTS/IDENTITY otherwise unchanged, etc.). → quickstart §3, NFR-003.

### MED-8 — "No behavior change" lacks deterministic evidence
- **Evidence**: candidate enumeration is deterministic via `enumerate_candidates.py` + `vikunja_scope.py` (`[13]`).
- **Resolution (FIX)**: NFR-004 evidence = capture before/after `enumerate_candidates` output (candidate IDs + due-date formatting) for the same input/date and assert identical. Note: the prompt refactor cannot change candidate enumeration (that logic lives in the helper, not the prompt) — the only prompt-side behavior surface is the date-format instruction (addressed by FR-010) and message shape. → quickstart §8, NFR-004.

### LOW-9 — Stale/confusing Goals(11) in an active test
- **Evidence**: `tests/escalation/test_enumerate_candidates.py:169-170` demonstrates the exclusion mechanism with `project_id=11` / `[11, 13]`.
- **Resolution (FIX, per HIGH-2 expansion)**: change the generic exclusion test to a non-Goals excluded id (preserving the mechanism assertion) so no active test references the deleted Goals project. → **FR-011**.

## Resulting requirement changes

- **FR-008** relaxed: AGENTS.md may receive exactly two narrow edits (FR-010 Z-example, FR-012 enforcement sentence); no other AGENTS content changes.
- **New**: FR-010 (Z→offset), FR-011 (SKILL.md + escalation-ops.md + test Goals(11) cleanup), FR-012 (AGENTS enforcement-sentence fix).
- **NFR-002** scope set updated to the expanded file list.
- **NFR-001/003/004** verification hardened per MED-6/7/8, HIGH-4.
