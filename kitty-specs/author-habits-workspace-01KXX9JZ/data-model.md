# Data Model: Author felix-admin-habits workspace

This mission has no runtime data schema. The "data model" is the **content-block conservation model**: every existing block in the three edited files is accounted for as keep / move / reduce-to-stance / delete. NFR-003 asserts this table row-by-row after implementation.

## Entities

- **Content block** — a titled section or discrete instruction unit in a workspace file.
- **Owner file** — the #587-canonical destination for a block's concern (SOUL=voice/stance, USER=filtered person-view, TOOLS=environment/setup, AGENTS=operating rules/role).
- **Enforceable privacy token** — the `04-Growth/_private/` "never access" rule. Invariant: present in AGENTS **and** TOOLS, **absent** from SOUL after the refactor.
- **Weekly-out-of-scope statement** — the "do not generate weekly reports" rule. Invariant: present in AGENTS, **absent** from SOUL after the refactor.

## Move-table — SOUL.md

| Block (current) | Action | Destination / Result |
|---|---|---|
| `## Purpose` (role: "manage Kent's daily habit check-ins…") | **delete** | Role already owned by AGENTS `## Authority`/`## Scope`. No role text remains in SOUL. (FR-002) |
| `## Weekly report — out of scope` (full block, #723/#796 detail) | **delete** | Duplicate of AGENTS `## Weekly report — out of scope`. Single authoritative copy stays in AGENTS. (FR-003, FR-011) |
| `## Voice — write as Kent` (principles, words to avoid, words that are Kent) | **keep** | The keeper — SOUL's core concern. (FR-001) |
| — "Kent has ADD and processes best…" justification inside the "Structured and chunked" bullet | **trim justification, keep rule** | Style rule ("use headers and short sections") stays; the ADD justification is trimmed (the #584/#585 precedent). (FR-001) |
| `## Privacy boundary` (full enforceable rule + path + mission-026/#152 changelog) | **reduce to one-line stance** | SOUL keeps only a behavioral stance ("I work only where I'm invited"). Enforceable rule + path + changelog removed from SOUL; enforceable copy stays in AGENTS + TOOLS. (FR-004) |

## Move-table — USER.md

| Block (current) | Action | Destination / Result |
|---|---|---|
| Name / what-to-call / timezone / Notes ("63, entrepreneur…; ADD (managed)…") | **keep** | Filtered person-view — USER's concern. "ADD (managed)" retained as a neutral fact. (FR-005) |
| `## Context` — "…deliver daily check-ins, record completions, **and report on patterns over time**." | **correct** | Remove the "report on patterns over time" claim (false since #723). Corrected block: deliver daily habit check-ins via WhatsApp and record completions; keep-messages-concise guidance retained. (FR-006) |
| `## Date handling` (America/New_York, `TZ=… date`, ET offset, no-Z rule) | **move** | → TOOLS.md, preserved in substance. (FR-005 → FR-007) |

## Move-table — TOOLS.md

| Block (current) | Action | Destination / Result |
|---|---|---|
| `## Vikunja API` — "use the vikunja_api skill", "run `openclaw skills info vikunja_api`" | **keep** | Environment/setup — TOOLS's concern. |
| — "**Habits project**: resolve by name 'Habits' at runtime **(id=13)**" | **de-inline** | **Remove the `(id=13)`** parenthetical; point to `scripts/common/vikunja_refs.json` as the canonical project-id source. Name-based `vikunja_api` resolution is the agent's ad-hoc path only. (FR-008) |
| — "**Habit task IDs**: 14-20 (7 habits, all personal label)" | **delete** | Volatile inlined IDs (staleness trap), consumed by neither the helpers (which use sync-cache + `phase3-schedule.yaml` + morning artifact) nor the agent as authority. Deleting is behavior-preserving. (FR-008) |
| `## Habit completion storage` (one task per habit; comment format; idempotent search-before-create) | **keep** | The completion-comment storage contract — retained. (FR-008) |
| `## Privacy` — "NEVER access: `/home/kgale/second-brain/notes/04-Growth/_private/` …" | **keep (byte-unchanged)** | Enforceable privacy token stays in TOOLS (Invariant A home). Path already canonical (C-005). |
| *(new)* date-handling section | **receive from USER** | The America/New_York / ET-offset / no-Z content lands here. (FR-007) |

## Move-table — AGENTS.md

| Block (current) | Action | Destination / Result |
|---|---|---|
| `## Authority`, `## Scope`, `## Weekly report — out of scope`, `## Output discipline`, `## Privacy — absolute rule`, tick/reply workflows | **keep (unchanged)** | AGENTS is the operating-rules home; already healthy. |
| A sentence (if any) naming SOUL as a privacy-**enforcement** home | **correct only if present** | If AGENTS says privacy is "enforced in SOUL.md, AGENTS.md, TOOLS.md" (or similar), correct it to reflect SOUL now carries only a stance. If no such sentence exists, AGENTS is untouched. (FR-009) |

## Invariants (post-refactor assertions — the conservation check)

1. `validate_workspace.py --json` → `felix-admin-habits` object `ok: true` (all four checks). (NFR-001)
2. Enforceable privacy token (`04-Growth/_private/`) present in **AGENTS.md** and **TOOLS.md**, **absent** in **SOUL.md**. (NFR-003)
3. Weekly-out-of-scope statement present in **AGENTS.md**, **absent** in **SOUL.md**. (NFR-003)
4. Date-handling content present in **TOOLS.md**, **absent** in **USER.md**. (NFR-003)
5. No `id=13` / `14-20` literal in **TOOLS.md**. (FR-008)
6. No "report on patterns over time" (or equivalent reporting claim) in **USER.md**. (FR-006)
7. `## Voice` section still present in **SOUL.md**; no `## Purpose` / role text in **SOUL.md**. (FR-001, FR-002)
8. Behavior preservation is TWO checks (Finding 2): (a) before/after morning-list helper output identical = a *no-helper/config-change* scope guard (NOT a prompt-behavior gate); (b) static-diff that the AGENTS tick/reply commands, relay-verbatim rule, Output Discipline, completion flow, and habit-management rules are unchanged, + the live smoke as the real prompt-behavior check. (NFR-004)
9. `service-inventory.md` weekly-report rows match `service-inventory.json` (no residual "weekly cron via felix-admin-habits"). (FR-012)
