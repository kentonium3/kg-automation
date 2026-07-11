---
work_package_id: WP04
title: main prompt integration (option A, no sub-agent)
dependencies:
- WP03
requirement_refs:
- FR-001
- FR-003
- FR-004
tracker_refs: []
planning_base_branch: feat/felix-time-logging
merge_target_branch: feat/felix-time-logging
branch_strategy: Planning artifacts for this mission were generated on feat/felix-time-logging. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-time-logging unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
phase: Phase 3 - Dialog
assignee: ''
agent: claude
agent_profile: "curator-carla"
history:
- at: '2026-07-10T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/
create_intent:
- scripts/openclaw/agents/tests/test_timelog_prompt.py
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/AGENTS.md
- scripts/openclaw/agents/tests/test_timelog_prompt.py
role: implementer
tags: []
---

# WP04 — `main` prompt integration (option A, no sub-agent)

## ⚡ Do This First: Load Agent Profile

Before touching any file, load your implementer profile so identity, governance
scope, and boundaries are in force for this session:

- Invoke the **`spk-doctrine-profile-load`** skill (or `ad-hoc-profile-load`) and
  adopt the **implementer** role for this work package.
- Confirm the initialization declaration (identity, scope, boundaries) before
  proceeding. If the profile cannot be loaded, STOP and surface it — do not
  improvise around the workflow.

You are implementing on branch `feat/felix-time-logging`. Do not open a mission,
do not run other slash commands, do not touch `kitty-specs/` or `.kittify/`.

## Branch Strategy

- **Current branch at workflow start:** `feat/felix-time-logging`.
- **Planning/base branch for this feature:** `feat/felix-time-logging`.
- **Completed changes must merge into:** `feat/felix-time-logging`.

**This WP DEPENDS on WP03.** WP03 lands the `timelog` main-facing entrypoint
(`scripts/google/timelog.py`) and settles the **structured-args + typed-signal
contract** (`contracts/timelog-cli.md` C1, `data-model.md` `TimelogResult`). The
`main` prose you author here references the **real** flag shapes and status union
from that contract — so WP03's CLI surface must be settled before this prose is
written. If WP03's shipped flags or status names differ from what `contracts/timelog-cli.md`
records, STOP and surface the mismatch rather than guessing.

## Objectives & Success Criteria

Implement **option A** of the plan (IC-04, operator-locked in `research.md` D4):
`main` (sonnet) itself conducts the time-logging dialog. There is **NO sub-agent
delegation** — `main` calls the `timelog` helper **directly** via its OpenClaw
`exec` form and relays the helper's typed results. This designs out the #679
delegation failure class.

Success = all of:

- **FR-001** — `main` recognizes the "log time" intent shape from a WhatsApp DM
  and **extracts** the candidate fields (`client`, `hours`, `description`,
  `date` — default "today", `billable` — default yes); a non-time-log message is
  **not** misinterpreted as a log (`main` simply does not call the helper).
- **FR-003** — on an unknown/ambiguous client the helper returns a typed
  clarification signal and `main` **asks** Kent to confirm/add — it does not
  write and does not guess.
- **FR-004** — on Kent confirming a new client, `main` re-invokes the helper to
  create the tab + log the pending entry, and reports truthfully if the tab was
  created but the append failed (`client_created_entry_failed` → **not** a
  "logged" claim).
- `main` calls `timelog` with **structured args** (C1) and **conducts the
  clarifying dialog off the typed signals** — no sub-agent, no LLM in the write
  path.
- The fleet-guard size test stays green: `main/AGENTS.md` stays **< 12,000 bytes**
  after both the compression pass and the time-log addition.

## Context & Constraints

**CRITICAL BUDGET (Codex F1).** `main/AGENTS.md` is **~11,960 / 12,000 bytes**
today (measured). There is **~40 bytes** of headroom — nowhere near enough to add
a time-logging section. Therefore the implementer **MUST first run a
meaning-preserving compression pass** on the existing prompt to reclaim
**≥ ~600 bytes of headroom** BEFORE adding any time-log prose. Then keep the
addition **minimal by RELAYING the helper's typed-result text** — the helper
(WP03) authors the receipts, questions, and error strings wherever possible;
`main` relays them rather than authoring lots of fixed prose of its own.

Other constraints:

- **No sub-agent delegation (option A).** Unlike the calendar path (which
  delegates to `felix-admin-calendar`), the time-log path has `main` call the
  helper **directly**. Do NOT add a delegation section, do NOT invoke
  `openclaw agent --agent ...` for time-logging.
- **Anchored `-m` invocation.** The helper is invoked as
  `cd /home/claude/kg-automation && python3 -m scripts.google.timelog …` (the
  `-m` module form — script-path form fails `ModuleNotFoundError`; the `cd` is
  the env-assumptions guard).
- **Truthful reporting (#683).** `main` reports **only** what the helper's typed
  result says landed. `logged`/`corrected`/`deleted` mean a mutation was
  API-confirmed; `error` and `client_created_entry_failed` are **never** relayed
  as success. This section RE-USES the existing "Truthful Reporting & Mechanism
  Fidelity (ABSOLUTE)" block — do not weaken or duplicate it.
- **Audited-but-unmonitored surface (gap #621).** `scripts/openclaw/agents/main/AGENTS.md`
  is an audited surface but felix-deployer does **not** auto-rebaseline agent
  prompts. No rebaseline action is owed by this WP; the deploy WP (IC-05) handles
  prompt-sync + any manual rebaseline. Just note it in the merge record.
- **Do NOT lose load-bearing instruction in compression.** The compression pass
  is meaning-preserving. Every existing behavioral rule must survive verbatim in
  effect (see T011 spot-check list).

## Subtasks & Detailed Guidance

### T011 — PRE-WORK: meaning-preserving compression pass (MANDATORY, F1)

Before writing a single byte of time-log prose, tighten the existing
`scripts/openclaw/agents/main/AGENTS.md` to reclaim **≥ ~600 bytes** of headroom.

- **Record before/after byte counts** in your commit message and the WP
  completion note (e.g. `before: 11960 B → after: 11310 B → reclaimed 650 B`).
  Measure with `wc -c scripts/openclaw/agents/main/AGENTS.md`.
- **Meaning-preserving only.** Tighten wording, collapse redundancy, drop filler —
  never drop a behavioral instruction. Consider invoking the
  **`spk-doctrine-semantic-compression`** skill (Randy Reducer) for a
  behavior-preserving reduction pass.
- **Spot-check that these load-bearing instructions survive in effect** (do NOT
  drop or dilute any):
  - the **Message identity** header (`Sent by main:sonnet` first line);
  - the **Truthful Reporting & Mechanism Fidelity (ABSOLUTE)** block;
  - the **Verbatim pass-through (ABSOLUTE)** block (+ its example);
  - the **Governance / read GOVERNANCE.md** tier discipline (all five tiers +
    "state the tier" rule + "file, don't apply" reflex);
  - the **No Unrequested Infrastructure** rule;
  - the **felix-file-issue.py** filing block (helper invocation intact);
  - the existing **delegation** sections (inbox / habits / calendar) and the
    **cron-driven output — don't relay** rule.
- **Update the `.tmpl` ONLY IF it exists.** Check for
  `scripts/openclaw/agents/main/AGENTS.md.tmpl`. It is NOT in `owned_files`
  (it does not exist as of planning); if present, apply the same
  compression + addition there as a small out-of-map edit and note it. If absent,
  do nothing — do not create it.

### T012 — add a terse "Time-logging" section to `main/AGENTS.md`

After T011 reclaims headroom, add ONE tight section. Keep it minimal — relay the
helper's typed text, do not re-author reply strings.

- **Recognize the intent:** a WhatsApp DM shaped like
  `log N hrs for <client> [today|yesterday|<date>] doing <desc>` (and the
  `non-billable` variant). A message that is not a time-log → do **nothing**
  special (do not call the helper).
- **Extract the fields** (`client`, `hours`, `description`, `date` default
  today, `billable` default yes) and **call the helper directly** (anchored
  `-m` form):

  ```bash
  cd /home/claude/kg-automation && python3 -m scripts.google.timelog \
      --client <client> --hours <hours> --date <date> --description "<desc>" [--non-billable] \
      --channel whatsapp --conversation <cid> --source-msg-id <mid>
  ```

  Pass the conversation correlation (`--channel whatsapp --conversation <cid>
  --source-msg-id <mid>`) so the helper keys its pending + ledger state correctly.

- **RELAY the returned `TimelogResult`** (exactly one status; the helper exits `0`
  for any handled status, so read the JSON, don't branch on exit code):
  - `logged` / `corrected` / `deleted` → relay the helper's `receipt` verbatim
    (a mutation landed, API-confirmed).
  - `unknown_client` → ask Kent to confirm the `closest` match or add the client.
  - `need_field` → ask Kent for the named `missing` field.
  - `ambiguous` → ask Kent to disambiguate.
  - `client_created_entry_failed` → report **truthfully**: the tab was created but
    the time was **NOT** logged (never a "logged" claim). Ties #683.
  - `correction_ambiguous` / `no_pending` / `stale_pending` / `no_last_write` →
    report/ask per the status (nothing was mutated).
  - `not_timelog` → do nothing special.
  - `error` → report the failure **honestly** ("couldn't log that"), never a
    fabricated "logged" (ties #683 truthful-reporting; the helper also alerts via
    #701).
- **Follow-ups re-invoke `timelog`** with the same conversation correlation:
  - confirm-client → `--confirm-client "<name>"`
  - add-client → `--add-client "<name>"`
  - supply a field → `--field <name>=<value>`
  - correct → `--correct --hours <n>` (or the amended field)
  - delete-last → `--delete-last`
- **Keep it TIGHT.** No delegation. No re-authored receipt/question prose — relay
  the helper's text. This is the whole point of the byte budget.

### T013 — `scripts/openclaw/agents/tests/test_timelog_prompt.py` (fleet-guard)

Create the prompt test (in `create_intent`). Reuse the `test_agents_md_size.py`
size approach and the `conftest.py` `repo_root` fixture (session-scoped, resolves
the repo root; import it implicitly via the fixture arg — do NOT hard-code paths).

Assert, against `repo_root / "scripts/openclaw/agents/main/AGENTS.md"`:

- **Recognizer present** — the prompt contains a time-logging section that
  recognizes the `log … hrs for …` intent (assert on stable marker text you add
  in T012, e.g. a `Time-logging` heading and the `scripts.google.timelog`
  invocation string).
- **Direct helper call, no delegation** — assert the anchored
  `python3 -m scripts.google.timelog` invocation appears AND that the time-log
  section does **not** route via `openclaw agent --agent` (guard option A).
- **Key typed-signal handling present** — assert the prose names the load-bearing
  statuses main must handle: at least `unknown_client`, `need_field`,
  `client_created_entry_failed`, and `error` (the truthful-reporting-critical
  ones).
- **Size still under cap** — assert `main/AGENTS.md` `st_size < 12_000` (mirror
  `test_agents_md_size.py`'s `CAP`). This is the budget guard for the addition.

Also **run the existing** `scripts/openclaw/agents/tests/test_agents_md_size.py`
in the same suite so both size assertions gate this WP.

## Test Strategy

Run the two prompt-test files and confirm green:

```bash
python3 -m pytest scripts/openclaw/agents/tests/test_timelog_prompt.py scripts/openclaw/agents/tests/test_agents_md_size.py -v
```

- `test_agents_md_size.py::test_main_agents_md_under_12k` must stay **GREEN**
  after both the compression pass (T011) and the addition (T012) — this is the
  budget forcing function.
- `test_timelog_prompt.py` asserts the recognizer, the direct (non-delegated)
  helper call, the key typed-signal handling, and the size guard.
- No mock/network needed — these are static-content assertions on the prompt file.

## Definition of Done

- [ ] **Compression reclaimed ≥ ~600 bytes** of headroom on `main/AGENTS.md`,
      with before/after byte counts recorded in the commit + completion note.
- [ ] **No load-bearing instruction lost** — every rule in the T011 spot-check
      list survives in effect (meaning-preserving compression).
- [ ] The terse **Time-logging** section is added: recognizer + field extraction
      + anchored `-m` direct helper call + relay of the full typed-signal union
      (`logged`/`corrected`/`deleted`/`unknown_client`/`need_field`/`ambiguous`/
      `client_created_entry_failed`/`correction_ambiguous`/`no_pending`/
      `stale_pending`/`no_last_write`/`not_timelog`/`error`) + the follow-up
      re-invocations.
- [ ] **No sub-agent delegation** in the time-log path — the helper is called
      directly.
- [ ] `main/AGENTS.md.tmpl` updated **iff** it exists (else untouched, not
      created).
- [ ] `scripts/openclaw/agents/tests/test_timelog_prompt.py` created and **GREEN**.
- [ ] `main/AGENTS.md` is **< 12,000 bytes**; both prompt tests pass.
- [ ] Merge record notes the audited-but-unmonitored surface (gap #621 → no
      auto-rebaseline; deploy WP owns prompt-sync).

## Risks

- **Byte budget (the whole reason for the compression pass).** `main/AGENTS.md`
  starts at ~11,960/12,000 B — the addition cannot land without first reclaiming
  headroom. Mitigation: T011 compression FIRST; relay the helper's typed text
  instead of authoring reply prose; the size test is the forcing function.
- **Losing a load-bearing instruction during compression.** Meaning-preserving
  only; spot-check the T011 list; prefer the semantic-compression skill over
  ad-hoc deletion.
- **Accidental delegation.** Option A calls the helper **directly** — do not copy
  the calendar path's `openclaw agent --agent` delegation. The prompt test guards
  this.
- **Wrong invocation form.** Use the anchored `-m` module form
  (`cd /home/claude/kg-automation && python3 -m scripts.google.timelog …`); the
  script-path form fails `ModuleNotFoundError` and bare `python` is exit-127 on
  office2.
- **Contract drift from WP03.** If the shipped `timelog` flags/statuses differ
  from `contracts/timelog-cli.md` C1, STOP and surface — do not guess shapes into
  the prompt.

## Reviewer Guidance

- **Budget with real headroom.** Confirm `main/AGENTS.md` is genuinely under
  12,000 bytes with headroom, not scraping the cap — verify the recorded
  before/after byte counts and that the compression reclaimed **≥ ~600 B**.
- **No load-bearing instruction lost.** Diff the compression pass and confirm
  every rule in the T011 spot-check list survives in effect (Message identity,
  Truthful Reporting ABSOLUTE, Verbatim pass-through ABSOLUTE, Governance tiers,
  No Unrequested Infrastructure, felix-file-issue, existing delegations,
  cron-don't-relay).
- **Dialog covers the full typed-signal union.** Confirm the Time-logging section
  handles every status from `contracts/timelog-cli.md` C1 — especially the
  truthful-reporting-critical `client_created_entry_failed` and `error`
  (must never be relayed as success, #683).
- **Direct helper call, no delegation.** Confirm the anchored
  `python3 -m scripts.google.timelog` call is present and that the time-log path
  does NOT route through `openclaw agent --agent` (option A integrity).
- **Tests gate the budget.** Confirm `test_timelog_prompt.py` and
  `test_agents_md_size.py` both pass and that the size assertion is present in the
  new test.
