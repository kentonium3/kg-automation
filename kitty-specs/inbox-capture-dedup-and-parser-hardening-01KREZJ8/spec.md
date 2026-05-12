# Inbox Capture Dedup and Parser Hardening

**Mission**: `inbox-capture-dedup-and-parser-hardening-01KREZJ8`
**Source**: [`kentonium3/kg-automation#185`](https://github.com/kentonium3/kg-automation/issues/185) — *P1-bug: inbox processing creates duplicate GitHub issues for already-routed notes*
**Mission type**: `software-dev`
**Target branch**: `main`

---

## 1. Why this exists

On 2026-04-17 through 2026-04-19, `felix-admin-capture` filed **9 duplicate GitHub issues** (#177–#184; #176 retained) for a single inbox note over 2 days. Each cron tick treated the same note as unprocessed and routed it again, while the escalation engine amplified the loop by re-escalating the resulting Vikunja tasks. Kent received repeated WhatsApp notifications for the same item.

Two compounding failures caused this:

1. **No duplicate-detection step**: The capture agent does not check whether a GitHub issue already exists for a given inbox note before creating a new one.
2. **Non-defensive frontmatter parsing**: When the source note had a malformation (the original case was a leading `\n` byte before `---`, easy to introduce via WhisperFlow voice-to-text or phone editing), the agent treated "frontmatter not parseable" as "no frontmatter" → "status: unprocessed" → "route the note again."

This mission fixes both failures and adds operator-experience helpers to make parse failures visible and recoverable.

---

## 2. User Scenarios

The system has one user: **Kent**, in his role as the operator of the inbox-processing pipeline.

### Primary scenario — Note routed exactly once

1. Kent captures a note in `~/second-brain/notes/01-Inbox/<filename>.md` via Obsidian, Templater, or WhisperFlow. Frontmatter is well-formed.
2. The next `felix-admin-capture` cron tick reads the note. The agent classifies and routes it: files one GitHub issue (and one Vikunja task per existing flow), records the route in the routing log, writes `status: processed` into the note's frontmatter (atomic mark).
3. On every subsequent cron tick, the agent reads the note's filename, consults the routing log, sees the entry, and skips. No duplicate is filed even if the note's `status:` frontmatter is somehow flipped back to `unprocessed`.

### Secondary scenario — Malformed frontmatter

1. Kent captures a note where the first bytes are `\n---\n...` (leading newline before the opening frontmatter delimiter). Or a UTF-8 BOM precedes the `---`. Or the frontmatter has an invalid YAML value. Or the closing `---` is missing.
2. The next cron tick reads the note. The defensive parser detects the malformation and **halts routing for this note** (does NOT treat as unprocessed).
3. The agent collects the parse-failure record along with any other parse failures observed in the same run. At end-of-run, it files **one batched "Inbox quality" GitHub issue** listing every affected note with its specific parse-failure reason.
4. The agent injects (or refreshes in place) an Obsidian callout error marker at the top of each affected note's body, referencing the batched issue number for traceability.
5. On subsequent cron ticks, the same notes continue to halt (still malformed) and the agent dedupes the "Inbox quality" issue by title prefix — no new batched issue is filed until the current one is closed.
6. Kent fixes the frontmatter manually. The next cron tick reads the note, parses cleanly, strips the error-marker callout as part of the same edit that writes `status: processed`, and routes the note normally.

### Tertiary scenario — First-run safety (post-deploy bridge)

1. Routing log starts empty on deploy.
2. First cron tick after deploy reads `01-Inbox/`. With the current inbox state (5 notes; 4 already marked `status: processed`; 1 fresh unprocessed note from today, not a residual from the bug), the agent routes only the 1 unprocessed note.
3. No retroactive backfill of existing notes' frontmatter. No mass-routing of legitimately-processed notes (their existing `status: processed` mark prevents that).
4. Steady state achieved after the first run.

### Edge cases

- **Routing log file is missing or unreadable** at run start: agent treats this as an empty log. Bug fix is preserved on the next run when the agent writes its first entry. Worst case is one cron tick where dedup is unavailable; in practice the file is append-only and would only go missing under explicit operator action.
- **Routing log entry exists but the referenced GitHub issue was deleted/closed-as-spam**: agent still trusts the log and skips. The orphaned-issue case is fixed by Kent removing the stale log entry; documented in the runbook.
- **GitHub or Vikunja unreachable** during the route step: existing felix-admin-capture failure modes apply. This mission does not change recovery semantics for upstream-outage cases — out of scope.
- **Same note's filename re-used** (Kent renames a different note to a name that previously existed in the routing log): agent dedupes incorrectly (treats the new note as already-routed). Documented in the runbook; mitigation is "don't reuse filenames." Same trade-off as filename-keyed dedup in any system.
- **Note moved out of `01-Inbox/` and back in**: routing log entry persists by filename; subsequent appearances dedupe. Same trade-off as above.
- **Marker auto-cleanup encounters a note that was edited to ADD a `> [!error] felix-capture:` line manually**: the auto-cleanup strips it. Acceptable because the prefix is namespaced to `felix-capture:` (extremely unlikely to be authored by Kent).

---

## 3. Functional Requirements (FR-###)

| ID | Status | Requirement |
|---|---|---|
| **FR-001** | mandatory | The agent maintains a routing log at `~/second-brain/agents/state/inbox-routing.jsonl` (on office2). Each line is a single JSON object. Append-only — every successful route writes one new line; existing lines are never edited. |
| **FR-002** | mandatory | Each routing log entry contains at minimum: `filename` (basename, e.g. `Inbox 2026-04-16 1919.md`), `issue_number` (the GitHub issue number filed for this note), `vikunja_task_id` (the Vikunja task ID, if one was created), `routed_at` (UTC ISO-8601 timestamp), `note_excerpt` (a short string ≤120 chars from the note's body for human cross-reference). |
| **FR-003** | mandatory | Before filing a new GitHub issue for an inbox note, the agent reads the routing log and checks for an entry whose `filename` matches the note's filename. If found, the agent **skips** the note entirely (no GitHub issue, no Vikunja task, no frontmatter write) and logs the dedup decision to the per-run activity log. |
| **FR-004** | mandatory | If the agent's frontmatter-parse step fails for a note (for any of the malformation cases enumerated in FR-005), the agent **halts routing for that note**. It does NOT treat the note as unprocessed. It does NOT file a GitHub issue. It does NOT file a Vikunja task. |
| **FR-005** | mandatory | The defensive parser handles at minimum these malformations: (a) leading whitespace including newlines and `\t` before the opening `---`; (b) UTF-8 BOM (`\xEF\xBB\xBF`) at the very start of the file; (c) missing closing `---` (unterminated frontmatter block); (d) invalid YAML inside the frontmatter block. For each, "malformed" is determined and the note halts. |
| **FR-006** | mandatory | At end of each cron run, if one or more notes halted under FR-004, the agent files **one batched "Inbox quality" GitHub issue** with a stable title prefix `Inbox quality:`. Body: a markdown table of `\| filename \| reason \|` rows. The body also references the per-run activity log path. |
| **FR-007** | mandatory | The "Inbox quality" issue is deduped across cron runs via title-prefix search (matching the doc-auditor §4 pattern). If an open issue with the prefix exists, the agent does NOT file a new one — it logs the dedup decision and continues. |
| **FR-008** | mandatory | When the agent halts a note under FR-004, it injects (or refreshes in place) an Obsidian callout marker at the top of the note body. Format: `> [!error] felix-capture: could not parse frontmatter on <YYYY-MM-DD>. See issue #<N> ("Inbox quality" issue for this run).` Insertion location: after the closing `---` if frontmatter delimiters are detectable; otherwise at the very top of the file. The agent collects all parse failures during a run, files the batched issue at end-of-run, then writes/refreshes markers with the real issue number. |
| **FR-009** | mandatory | Marker writes are **idempotent**: if a `> [!error] felix-capture:` line already exists at the top of the note, the agent updates it in place (refreshes date + issue#) rather than appending. |
| **FR-010** | mandatory | **Auto-cleanup**: when the agent reads a note that (a) parses cleanly (passes FR-005 checks) AND (b) contains a top-of-file `> [!error] felix-capture:` marker, it strips the marker line as part of the same edit that writes `status: processed`. |
| **FR-011** | mandatory | After successfully creating a GitHub issue for a note (and any Vikunja task), the agent **immediately** writes `status: processed` into the note's frontmatter — not at end-of-run, not on a subsequent run. The routing-log entry write and the frontmatter mark are part of the same logical "route" step (FR-001's append happens once per successful route, regardless of whether the frontmatter mark write succeeded). |
| **FR-012** | mandatory | If the frontmatter `status: processed` write in FR-011 fails (e.g., file became read-only, encoding error), the agent logs the failure to the per-run activity log. The routing-log entry from FR-001 already prevents duplicate routes on subsequent ticks; the failed frontmatter mark does NOT trigger a re-route. |

---

## 4. Non-Functional Requirements (NFR-###)

| ID | Status | Requirement | Measurable threshold |
|---|---|---|---|
| **NFR-001** | mandatory | Per-tick runtime overhead introduced by the routing log lookup. | Less than **100 ms** for an inbox of up to 200 routed notes (current scale ~5 notes; 40× growth headroom). |
| **NFR-002** | mandatory | Routing log durability. The log survives process crashes and machine restarts. | Verified by inspecting the file after a `systemctl restart` on office2. |
| **NFR-003** | mandatory | Idempotent operation. Running the same cron tick twice against the same inbox state produces the same set of decisions and (because of FR-003 and FR-007) zero additional GitHub issues. | Manual replay against a fixed-state inbox snapshot in tests. |
| **NFR-004** | mandatory | No silent failures. Every parse-halt, dedup-skip, write-failure, and marker-injection produces a record in the per-run activity log (`/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`). | `grep "<filename>"` against the activity log finds at least one record per note touched during the run. |
| **NFR-005** | mandatory | No false positives in the parse-failure classifier. A well-formed note must never be flagged as malformed. | Validated by unit tests against a corpus of well-formed fixtures plus a representative sample of historical inbox notes. |

---

## 5. Constraints (C-###)

| ID | Status | Constraint |
|---|---|---|
| **C-001** | mandatory | The agent runs on office2 as the `claude` user via OpenClaw cron. It cannot use sudo. |
| **C-002** | mandatory | The routing log path is `~/second-brain/agents/state/inbox-routing.jsonl`. The `state/` subdirectory is created lazily on first route. This path is OUT OF SCOPE for credential-manifest tracking. |
| **C-003** | mandatory | The "Inbox quality" issue is filed against `kentonium3/kg-automation` with label `area/content`. |
| **C-004** | mandatory | The error marker on a malformed note is the ONLY note-body-content mutation the agent performs. All other agent mutations remain confined to frontmatter (`status: processed`). |
| **C-005** | mandatory | The marker format prefix `> [!error] felix-capture:` is a stable contract. Future versions of the agent that change the prefix must include a one-time cleanup migration step. |
| **C-006** | mandatory | The routing log file is NOT committed to git. It lives on office2 only. Backup hygiene is handled by the existing nightly Restic snapshot of `/home/kgale/second-brain/`. |
| **C-007** | mandatory | No retroactive mutation of existing inbox notes during deploy. First-run path is "accept-the-risk" (R); routing log starts empty. |
| **C-008** | mandatory | Architecture documentation (`service-inventory.md` / `service-inventory.json`) must be updated in the same change set to reflect the new state file and the agent's new behavior. |

---

## 6. Success Criteria

| ID | Criterion |
|---|---|
| **SC-001** | A canary scenario in which the same inbox note is presented to the agent across 5 simulated cron ticks produces **exactly one** GitHub issue and exactly one Vikunja task; subsequent ticks are dedup-no-ops with corresponding activity-log entries. |
| **SC-002** | A note with a leading `\n` before `---` (the original bug-trigger pattern) is correctly halted by the defensive parser; an "Inbox quality" issue is filed; a callout marker is injected; the note is NOT routed; on a subsequent run after Kent fixes the frontmatter, the marker is auto-stripped and the note routes normally. |
| **SC-003** | A note with a UTF-8 BOM before `---` is correctly halted and surfaced per SC-002. |
| **SC-004** | A note with valid frontmatter delimiters but invalid YAML inside is correctly halted and surfaced per SC-002. |
| **SC-005** | Across the first **7 days** of live operation post-deploy, **zero duplicate GitHub issues** are filed for any inbox note. |
| **SC-006** | Across the first 7 days post-deploy, NO well-formed note is incorrectly flagged as malformed (zero false positives in NFR-005). |
| **SC-007** | The routing log on office2 contains one entry per successful route after the first 7 days. Manual cross-reference with the GitHub issue queue shows 1:1 mapping. |
| **SC-008** | Architecture docs reference the routing log state file, the batched "Inbox quality" issue pattern, and the callout marker convention. |

---

## 7. Key Entities

| Entity | Source of truth | Notes |
|---|---|---|
| **Inbox note** | `~/second-brain/notes/01-Inbox/<filename>.md` | The source artifact captured by Kent or external tools. Read-mostly by the agent; modified only via frontmatter `status: processed` write and (when halted) the error-marker callout. |
| **Routing log entry** | `~/second-brain/agents/state/inbox-routing.jsonl` (one line per entry) | The dedup substrate. Fields per FR-002. Append-only. |
| **Parse-failure record** | In-memory during the cron run; surfaced via the batched issue and per-run activity log | Captures `filename`, `reason` (specific malformation), `attempted_at`. Not persisted between cron ticks. |
| **"Inbox quality" issue** | A GitHub issue with stable title prefix `Inbox quality:` | The visible queue surface for parse failures. Filed at end-of-run if any halts occurred. Deduped via title-prefix search (FR-007). |
| **Per-run activity log** | `~/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md` | The pre-existing per-run audit trail; this mission adds new event types (dedup-skip, parse-halt, marker-inject, marker-cleanup, inbox-quality-filed). |

---

## 8. Assumptions

| ID | Assumption | Recorded basis |
|---|---|---|
| **A-001** | The felix-admin-capture agent reads notes through a code path that can be safely modified to add the routing-log check. The exact code surface (Python module + agent prompt) is resolved in `/spec-kitty.plan`. | Discovery — current code in `scripts/inbox/prescan.py` and `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` are the likely surfaces. |
| **A-002** | Filename-based dedup is robust enough for the inbox workflow. Inbox filenames are timestamp-based (`Inbox YYYY-MM-DD HHMM.md`) and Kent does not regularly rename or reuse them. | Discovery confirmed. Documented as an operational expectation in the runbook. |
| **A-003** | Mission 027's prescan blank-line-skip fix (`690a370`, 2026-04-11) addressed one specific case but did not cover the broader class of frontmatter malformations. The fact that the original bug occurred 6 days AFTER mission 027 merged suggests that mission 027's parser path is not the one the agent actually uses during routing — or that the bug-trigger was a different malformation than the documented `\n---` case. The plan phase investigates which code path is in scope. | Git log + bug-body chronology. |
| **A-004** | Existing #176 (the retained issue from the bug-cycle) and the 4 already-processed notes in the current inbox state are NOT residual bug-victims that would cause first-run duplicates. The 1 currently-unprocessed note is fresh-from-today per Kent's discovery confirmation. | Discovery — Kent confirmed inbox composition and freshness. |
| **A-005** | The agent has read+write access to `~/second-brain/agents/state/` and the `01-Inbox/` notes themselves. Permission setup is not blocking; the `state/` subdirectory is created lazily on first route. | Existing agent workspace conventions; verified during plan. |

---

## 9. Dependencies

- `~/second-brain/notes/01-Inbox/` — watched directory on office2 (mounted under `kgale` user via Obsidian Sync).
- `~/second-brain/agents/state/` — new subdirectory (created lazily) holding the routing log.
- `~/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md` — pre-existing per-run activity log; extended with new event types.
- `gh` CLI configured for `kg-felix-bot` identity on office2 — for filing the batched "Inbox quality" issue and the per-note issues.
- Vikunja API (existing `vikunja-api` skill) — for the per-note Vikunja task creation (unchanged from current flow).
- Existing OpenClaw cron triggering `felix-admin-capture` — unchanged.

---

## 10. Out of scope (explicit)

| Item | Rationale |
|---|---|
| Backfill of existing inbox notes' frontmatter | First-run safety path (R) per discovery. Inbox is small; one unprocessed note is fresh; manual review of 5 notes is cheaper than build. |
| Backfill of existing notes into the routing log | Same. Log starts empty. |
| Cleanup of pre-existing duplicate GitHub issues (#177–#184) | Already closed per the bug body. |
| Cross-system rename of the `status:` taxonomy or schema changes to the inbox-note format | This mission preserves the existing schema. |
| Changes to upstream-outage recovery semantics (GitHub or Vikunja unreachable mid-route) | Existing felix-admin-capture behavior is unchanged. |
| Adding the routing log to credential-manifest tracking | The log contains no credentials; it's operational state. |
| Promoting the felix-admin-capture agent's autonomy level | Governance decision; out of scope. |

---

## 11. References

- Source issue: [`kentonium3/kg-automation#185`](https://github.com/kentonium3/kg-automation/issues/185)
- Bug evidence: #176 (retained) + #177–#184 (closed duplicates) + Vikunja API task IDs 46–49 (duplicates marked done)
- Prior art for dedup pattern: `scripts/openclaw/skills/doc-audit/SKILL.md` §4 (felix-doc-auditor uses analogous title-prefix dedup against GitHub)
- Prior art for batched-quality-issue pattern: `scripts/openclaw/skills/doc-audit/SKILL.md` §3 step 8.5 / §4.1.b (manifest-quality batching)
- Mission 027 (prescan helper) — earlier work that partially addressed leading-blank-line frontmatter: commit `690a370`
- Felix-admin-capture agent workspace: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- Inbox prescan code: `scripts/inbox/prescan.py`
