# Data Model / Surface Inventory: Retire _private folder guard apparatus

This mission's "data model" is the **classification of every live surface** that references the
`_private` folder guard. It is the enforcement of "not a blind sweep" — each surface has an explicit
action. Frozen/workflow-owned surfaces (`docs/archive/`, `kitty-specs/`, `.kittify/`, and the
migration runbook allowlist) are **out of scope by C-001** and are not listed for edit.

## Conceptual entities

- **PrivacyBoundaryToken** — the enforced literal `04-Growth/_private` string embedded in prompts,
  validator constants, and "absolute rule" docs. *Being removed.*
- **GeneralVaultHygiene** — behavior that redacts vault paths from surfaced alerts and refuses
  writes to arbitrary vault paths. *Retained + generalized (folder-independent).*
- **SecondBrainRepoBoundary** — "the second brain is a separate repo; kg-automation tasks don't
  write to it." *Retained unchanged.*
- **PhysicalExclusionModel** — the new narrative: the private content lives only on devices Felix
  cannot reach, so it is never present. *Added where a doc previously stated the absolute rule.*
- **VikunjaIsPrivate** — the unrelated Vikunja private-project `is_private` field. *Untouched.*

## Actions legend

- **REMOVE** — delete the file/step entirely.
- **STRIP** — remove the folder-specific red-line/constants; keep the file.
- **REFRAME** — replace "absolute rule / never touch" enforcement text with the physical-exclusion
  model.
- **KEEP+GEN** — retain the behavior, generalize away from the `_private` literal.
- **LEAVE** — no change (listed to record the deliberate decision).

## IC-01 — Stale-path lint validator + wiring

| Surface | Action | Notes |
|---|---|---|
| `tooling/scripts/validate_privacy_boundary.py` | REMOVE | The whole stale-path linter. |
| `.githooks/pre-commit` | STRIP | Remove the validator invocation; keep validate_docs/privacy-of-tree/arch-data steps. |
| `.github/workflows/docs-ci.yml` | STRIP | Remove the "Validate privacy boundary lint" step + its #560 comment block. |
| `Makefile` | STRIP | Remove the validator target/call. |
| `.agents/autopilot/adapters/kg-automation.md` | STRIP | Remove the validator reference from the gate list. |
| `docs/runbooks/local-test-gate.md` | REFRAME | Drop the validator from the documented local gate. |

## IC-02 — Workspace-validator privacy invariants

| Surface | Action | Notes |
|---|---|---|
| `scripts/openclaw/agents/validate_workspace.py` | STRIP | Remove `check_privacy_boundary` (Inv A), `check_privacy_path_canonical` (Inv D), `PRIVACY_TOKEN`/`CANONICAL_PRIVATE_PATH`/`NONCANONICAL_PRIVATE_TOKEN`, owner-set config, and their entries in the checks list. Keep all other invariants. |
| `scripts/openclaw/agents/tests/test_validate_workspace.py` | STRIP | Remove the privacy-invariant test cases; keep the rest. |
| `tests/openclaw/test_privacy_pointer.py` | REMOVE | Ties `PRIVACY_TOKEN` to the vault registry — moot once the token is gone. |

## IC-03 — Deployed agent prompts (→ agent-prompt-sync deploy + smoke)

| Surface | Action | Notes |
|---|---|---|
| `scripts/openclaw/agents/main/{TOOLS,USER}.md` | STRIP | Remove the enforceable `_private` red-line. main deploy dir = `/data/services/openclaw/data/`. |
| `scripts/openclaw/agents/felix-admin-capture/{AGENTS,TOOLS}.md` | STRIP | " |
| `scripts/openclaw/agents/felix-admin-escalation/{AGENTS,TOOLS}.md` | STRIP | " |
| `scripts/openclaw/agents/felix-admin-habits/{AGENTS,TOOLS}.md` | STRIP | " |
| `scripts/openclaw/agents/felix-admin-tasker/{AGENTS,TOOLS}.md` | STRIP | " |
| `scripts/openclaw/agents/felix-admin-calendar/{SOUL,TOOLS,USER}.md` | STRIP | calendar carries its block in SOUL.md (#805). |
| `scripts/openclaw/agents/felix-doc-auditor/{AGENTS,SOUL,TOOLS}.md` | STRIP (repo-only) | **Post-plan Codex LOW-1:** felix-doc-auditor is suspended (#539), excluded from the workspace validator + drift roster, and is NOT in the OpenClaw agents map — agent-prompt-sync does NOT deploy it. Strip the red-line for repo consistency, but expect **no deployed parity and no smoke** for this agent. |

> Exact owner file(s) per agent are confirmed during implement by grepping each workspace; only the
> file(s) that actually carry the red-line are edited. The 6 deployed agents (main, capture,
> escalation, habits, tasker, calendar) get parity + smoke; felix-doc-auditor is repo-only.

## IC-04 — Governance/instruction docs (partial edits — keep the repo boundary)

| Surface | Action | Notes |
|---|---|---|
| `CLAUDE.md` | STRIP | "Second Brain Boundary" §: remove the `_private` **Absolute rule** line ONLY; KEEP "separate repo / do not write to second-brain paths". |
| `CODEX.md` | STRIP | Same treatment. |
| `ai-agents/claude-instructions.md` | STRIP | " |
| `ai-agents/claude-code-instructions.md` | STRIP | " |
| `ai-agents/gemini-instructions.md` | STRIP | " |
| `docs/constitution/FELIX-CONSTITUTION.md` | REFRAME | Remove the folder-absolute-rule directive text; keep the general privacy/boundary principle, noting physical exclusion. |

## IC-05 — Design/architecture/runbook docs (reframe to physical exclusion)

| Surface | Action | Notes |
|---|---|---|
| `docs/design/architecture/glossary.md` | REFRAME | Redefine the boundary entry to physical exclusion. |
| `docs/design/architecture/security-posture.md` | REFRAME | The `_private` guard is now "content physically excluded from office2". |
| `docs/design/architecture/service-inventory.md` + `service-inventory.json` | REFRAME | Drop stale "enforces _private" claims; keep JSON well-formed (arch-data validator). |
| `docs/design/coherence/doctrine.md` | REFRAME | If a doctrine/decision cites the absolute rule, reframe. |
| `docs/design/openclaw-workspace-authoring-standard.md` | REFRAME | Remove the "prompts must carry the privacy red-line" authoring requirement (pairs with IC-02). |
| `docs/design/felix-capability-roadmap.md` | REFRAME | "privacy is absolute" entries → physical-exclusion model. |
| `docs/design/process-flows/{inbox-routing,journal}.md` | REFRAME | Reframe any "never route/write _private" step to the general vault-path guard (IC-07). |
| `docs/runbooks/{escalation-ops,habits-ops,inbox-ops,openclaw-agent-setup,tasker-ops}.md` | REFRAME | Drop the "agent must carry the _private rule" operational notes. |
| `scripts/inbox/README.md`, `scripts/vault/README.md` | REFRAME | Doc mentions → general vault-path phrasing. |

## IC-06 — Graph-ingest model (#692/#696)

| Surface | Action | Notes |
|---|---|---|
| `docs/design/second-brain-graph-layer.md` | REFRAME | Privacy section: "never ingest _private" → "verify the private content is not present" (physical exclusion). |
| `docs/design/executive-assistant-architecture.md` | REFRAME | Same model reframe; #696 gate = a verification, not an in-repo rule. |

## IC-07 — General vault hygiene (keep + generalize)

| Surface | Action | Notes |
|---|---|---|
| `scripts/escalation/hard_fail.py` | KEEP+GEN | Redaction MUST keep stripping ALL current fragments — `~/second-brain`, `/second-brain`, AND bare `_private` — from alert title/body/url (post-plan Codex: these are the exact current coverage). Generalize the *framing* (folder-independent), NOT the matched set: do not drop any fragment it currently redacts. |
| `tests/escalation/test_hard_fail.py` | KEEP+GEN | Keep ≥ prior leak assertions; the `_private`, `~/second-brain`, `/second-brain` redaction assertions all stay. Reframe wording only. |
| `scripts/inbox/mark_processed.py` | KEEP+GEN | **Precise semantics (post-plan Codex MED-1):** keep the inbox-root ALLOW semantics — a note under the resolved inbox root is allowed even though the inbox lives *inside* the vault. Generalize the pre-read refusal to "refuse a path OUTSIDE the resolved inbox root" (NOT "any vault/second-brain path" — that would reject the legitimate `01-Inbox`). Retain the current `04-Growth/_private` pre-read refusal coverage as a subset. |
| `tests/inbox/test_mark_processed.py` | KEEP+GEN | Keep the refusal semantics + a case proving a legitimate inbox-root path is still ALLOWED. |
| `scripts/inbox/classify_content.py` | KEEP+GEN | **Live behavior (post-plan Codex MED-2):** exits 3 (pre-read refusal) when the path contains a private marker. KEEP as general "never classify private-marked content" hygiene, generalized to a `_private` path *component* (folder-agnostic), decoupled from the `04-Growth` folder. |
| `tests/inbox/test_classify_content.py` | KEEP+GEN | Retain/adjust the refusal test to the generalized component check; keep coverage. |
| `scripts/inbox/prescan.py` | KEEP+GEN | **Live behavior (post-plan Codex MED-2):** `scan_directory` skips any entry/symlink-target with `_private` as a path component. Already folder-agnostic → KEEP as general hygiene (never scan private-marked content); confirm it is decoupled from the specific folder. |
| `tests/scripts/inbox/test_prescan.py` | KEEP+GEN | Retain the skip test; keep coverage. |
| `scripts/inbox/route_and_finalize.py` | TRIAGE | Per-file at implement: reframe doc/comment mentions; if it delegates to the above guards, no behavior change. |
| `scripts/office2/gitignore-additions.txt` | KEEP | Gitignoring vault content is still valid; keep (generalize wording if folder-specific). |

> **DECISION (post-plan Codex, surfaced to Kent):** `prescan` + `classify_content` refuse/skip any
> `_private`-marked content as *general* hygiene ("never process private-marked content"), which is
> folder-agnostic and independent of the removed folder guard → **KEEP+GENERALIZE**, not remove. This
> means a `_private` *component* check intentionally survives in the codebase (allowlisted in SC-001).
> Alternative (delete these too for a cleaner sweep) is available if Kent prefers; the safe/consistent
> default is to keep the general-hygiene protection.

## IC-08 — Verify / LEAVE

| Surface | Action | Notes |
|---|---|---|
| `tests/common/test_sync_cache.py` (`is_private`) | LEAVE | Vikunja private-project feature — unrelated to the vault folder (FR-008). |
| `docs/runbooks/vault-path-registry-migration.md` | LEAVE | Intentional dual-path migration doc (validator allowlist) — out of scope. |
| `scripts/openclaw/observation/tests/fixtures/*.jsonl` | LEAVE | Historical captured fixtures (validator allowlist). |
| office2 `/home/kgale/second-brain/notes/04-Growth/` | VERIFY | Re-confirm `_private` absent before deploy (NFR-002). |

## Invariants

- **INV-1 (ordering)**: no surface guard is removed before the folder's absence is verified (already
  true; re-checked at IC-08).
- **INV-2 (scope)**: `SecondBrainRepoBoundary` and `GeneralVaultHygiene` survive; only
  `PrivacyBoundaryToken` enforcement is removed.
- **INV-3 (behavior)**: no change to any path except the removed folder guard (C-004); `VikunjaIsPrivate`
  untouched.
- **INV-4 (coverage)**: retained-guard tests keep ≥ the prior count of leak/refusal assertions.
