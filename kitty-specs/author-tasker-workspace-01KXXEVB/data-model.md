# Data Model: Author felix-admin-tasker workspace

This mission has no runtime data model. The "model" here is the **content-conservation move-table**: every content block in the three edited files, its #587-canonical owner, and its disposition. The implementer treats this as authoritative; the reviewer checks the diff against it.

Legend: **KEEP** (stays in this file, unchanged) · **TRIM** (stays, but a specific sub-part is removed) · **REDUCE** (collapsed to a one-line stance) · **DELETE** (removed from this file; canonical copy lives in the owner named) · **RECEIVE** (n/a this mission — no cross-file moves land in a new file).

## SOUL.md — reduce to voice + one-line stance

| Block (current) | Disposition | Canonical owner / destination | Notes |
|---|---|---|---|
| `## Purpose` (role: "sole purpose is task intelligence…" **plus a restatement of the confirmation rule: "propose structured tasks and wait for Kent's confirmation before creating them"**) | **DELETE** | role → `AGENTS.md` `## Authority` + `## Scope`; the embedded confirmation clause → `AGENTS.md` `## Operating Mode` (already present) | SOUL is explicitly NOT role/purpose (#587). No role text remains in SOUL. The confirmation clause is separately owned by `## Operating Mode` (conservation invariant #3) — Purpose is not a pure role block (post-plan review, renata #4). |
| `## Voice — write as Kent` (Principles; Words/phrases to avoid; Words/phrases that are Kent) | **KEEP** verbatim | SOUL (owner) | The keeper. Includes the "Structured and chunked … Kent has ADD" style bullet — kept as-is (it is a voice rule, and the operator chose SOUL → voice-only, keeping the Voice section intact). |
| `## Behavioral principles` (never-create-without-confirmation; minimize questions; one-question-at-a-time; respect-time/batch-concise; propose-confidently) | **DELETE** | `AGENTS.md` (`## Operating Mode`, `enrich_task` Steps 1 & 3, `retroactive_enrichment`) + SOUL `## Voice` (confidence stance) | Every item is already owned elsewhere; the block drops no unique instruction. **Note (post-plan review, renata #3):** "minimize questions — infer what you can, ask what you must" is the one item owned by *subsumption-by-mechanism* (the enrich_task ≥90%-include/<90%-clarify threshold operationalizes it) rather than co-located verbatim — defensible (nothing lost at runtime), but the implementer should explicitly confirm this in the conservation review rather than treat it as a clean co-located move. |
| `## Privacy boundary` (full never-touch policy + path + mission-026/#152 changelog parenthetical) | **REDUCE** → one-line stance | Stance stays in SOUL; enforceable rule already in `AGENTS.md` + `TOOLS.md` | e.g. "I work only where I'm invited." Policy body, filesystem path, and changelog parenthetical are removed from SOUL. |

## USER.md — filtered person-view, no enforceable rules

| Block (current) | Disposition | Canonical owner / destination | Notes |
|---|---|---|---|
| Person block (Name / What to call / Timezone / Notes incl. "ADD (managed)") | **KEEP** | USER (owner) | Filtered person-view. "ADD (managed)" retained as a neutral person-fact (#583 precedent). |
| `## Identities` (personal / intentional / metalcasework) | **KEEP** unchanged | USER (owner) | Genuine task-intelligence context — tasker assigns identity labels from these. Principle-4 filtered view. |
| `## Context` (Kent solo entrepreneur; task sources; **"Your job is to take raw…structure them into fully enriched Vikunja entries"**) | **TRIM** | Keep Kent-context in USER; role re-statement → `AGENTS.md` (already present) | Remove the embedded role re-statement (bolded); keep "Kent is a solo entrepreneur managing multiple business and personal initiatives. Tasks arrive from … Obsidian inbox …, direct Vikunja creation, and agent actions." |
| `## Communication preferences` (**"Concise, direct. No pleasantries or filler"**; proposals over open-ended questions; yes/no confirmations; batch proposals) | **TRIM** | Keep genuine prefs in USER; "concise/direct" voice line → SOUL `## Voice` (already present) | Remove the bolded voice-rule line (owned by SOUL Voice); keep the genuine interaction preferences. |
| `## Privacy boundary` (enforceable rule + path + mission-026/#152 changelog parenthetical) | **DELETE** | `AGENTS.md` + `TOOLS.md` (already present) | Duplication banned by #587 Principle 2. USER carries no enforceable privacy rule after this. |

## TOOLS.md — environment surface, corrected + de-behavioralized

| Block (current) | Disposition | Canonical owner / destination | Notes |
|---|---|---|---|
| `## Skills` (vikunja-api, task-intelligence) | **KEEP** | TOOLS (owner) | Environment/tool surface. |
| `### WhatsApp` | **KEEP** | TOOLS (owner) | Interaction channel surface. |
| `### Vikunja API` (base URL, auth secrets path, skill pointer) | **KEEP** | TOOLS (owner) | Environment surface; no volatile IDs inlined (resolves by name at runtime). |
| `### Action log` — **`Format: task-intelligence-YYYY-MM-DD.md`** | **CORRECT** (FR-008) | TOOLS (owner) | Replace with the real `log_action.py` shape: `/home/kgale/second-brain/agents/logs/felix-admin-tasker/YYYY-MM-DD.jsonl` (per-agent subdir, `.jsonl`). Preserve the Directive-3 required-fields substance. |
| `## Restrictions` → "NEVER read/write/reference `…/04-Growth/_private/`" | **KEEP** | TOOLS (Invariant A env home) + `AGENTS.md` | Byte-unchanged (already canonical, C-005). |
| `## Restrictions` → "NEVER log API tokens or credentials" | **KEEP** | TOOLS (owner) | Tool-use constraint, TOOLS-appropriate. |
| `## Restrictions` → "NEVER create tasks without Kent's confirmation (while at Assisted level)" | **DELETE** | `AGENTS.md` `## Operating Mode` (already present) | Behavioral operating rule — not TOOLS' concern per #587. |

## AGENTS.md / IDENTITY.md — not edited

- **AGENTS.md**: byte-unchanged. It already owns role (`## Authority`/`## Scope`), the confirmation rule (`## Operating Mode`), and enforceable privacy (`## Privacy — absolute rule`), and does NOT reference SOUL as a privacy home. FR-010 re-verifies by grep.
- **IDENTITY.md**: byte-unchanged (out of scope; operator decision).

## Conservation invariants (the reviewer's checklist)

After the edits, ALL of these must hold:

1. **Enforceable privacy rule**: present in `AGENTS.md` AND `TOOLS.md`; ABSENT from `SOUL.md` (stance only) AND `USER.md` (removed). → also gives `validate_workspace` Invariant A `ok`.
2. **Privacy path form**: the retained copies (AGENTS, TOOLS) keep the canonical physical path `/home/kgale/second-brain/notes/04-Growth/_private/` (validator `privacy_path_canonical: ok`), byte-unchanged.
3. **Confirmation-while-Assisted rule**: present in `AGENTS.md`; ABSENT from `SOUL.md` AND `TOOLS.md`.
4. **Role statement**: present in `AGENTS.md` (`## Authority`/`## Scope`); ABSENT from `SOUL.md` AND `USER.md`.
5. **Voice section**: present in `SOUL.md` only; unchanged.
6. **Identities block**: present in `USER.md` only; unchanged.
7. **Output Discipline block**: present in `AGENTS.md` (Invariant B `ok`); unchanged.
8. **Action-log format**: `TOOLS.md` matches `log_action.py` (`…/felix-admin-tasker/YYYY-MM-DD.jsonl`); no `task-intelligence-*.md` string remains.
9. **Action-log required-fields substance** (post-plan review, Codex MEDIUM / renata #2): after the FR-008 correction, the TOOLS `## Action log` block STILL enumerates the Directive-3 required fields — agent name, action type, target, outcome, timestamp, autonomy level. The correction rewrites only the filename/path shape; it must NOT drop the required-fields line. (Invariant #8 alone would pass even if the whole block were replaced by just the new path — this invariant closes that gap.)
10. **Scope**: `git diff --name-only` lists only `scripts/openclaw/agents/felix-admin-tasker/{SOUL,USER,TOOLS}.md` + mission artifacts. `AGENTS.md` and `IDENTITY.md` are byte-identical.
