# TOOLS.md

## Vault

- **Path on office2**: `/home/kgale/second-brain/notes/`
- **Inbox**: `/home/kgale/second-brain/notes/01-Inbox/`
- **Processing logs**: `/home/kgale/second-brain/agents/logs/`
- **Access**: claude user via secondbrain group

## Note finalize — `route_and_finalize`

The ONE deterministic command capture runs per note (AGENTS.md Step 3c). The
agent classifies the note's blocks, assembles a routing plan, and invokes this
once; the helper routes every block, verifies each artifact, writes each block's
routing-log entry, and marks the note processed ONCE — atomic, fail-loud,
retry-safe. There is **no** standalone `mark_processed` or `append_routing_entry`
in the agent toolkit; only a successful finalize can stamp `processed`.

```bash
cd /home/claude/kg-automation && python3 -m scripts.inbox.route_and_finalize \
  --source-path <abs-path-of-source-note> --plan-file <abs-path-of-plan.json>
```

**RoutingPlan** (`--plan-file`): `{"blocks": [ <block>, … ]}`, one entry per
routable block, in `block_index` order. Each block:

- `block_index` (int), `kind` (`calendar`|`someday`|`vikunja_task`|`journal`|`github_issue`|`empty`),
  `content` (**verbatim** classify_content block text — the idempotency key; never paraphrase), plus a
  kind-specific `payload`:
  - `calendar` → `{"title","start",["end"],["location"],["description"]}` (ET-resolved times)
  - `someday` → `{"title","body"}` (title = first sentence ≤100 chars; body = full block)
  - `journal` → `{"content","datetime"}` (datetime = note `created` or mtime, ISO-8601)
  - `vikunja_task` → `{"title","body"}` in-line; **or** omit `payload`, set `"task_id":<int>` (tasker-delegated; must belong to this note)
  - `github_issue` → `{"type","title","problem_statement",…}` in-line; **or** omit `payload`, set `"issue_number":<int>` (already filed)
- Empty note body → empty `blocks` list (or one `{"block_index":0,"kind":"empty"}`); finalize refuses a non-empty body.

**Result JSON** (stdout, ONE object): `status` is `finalized` (exit 0; `marked_processed:true`),
`needs_clarification` (exit 0; calendar only; note left unprocessed), or `error`
(non-zero; note NOT marked, retries next tick). Branch per AGENTS.md Step 3c.

On `needs_clarification`, the calendar block in `blocks[]` carries `missing` (the
raw missing list) and — **when the date resolved** — a `clarification_signal`
object `{"title","start_date","missing_fields"}`. This signal is built
**deterministically in code** (`route_and_finalize` runs `validate_calendar_event`
on the block, resolving `start_date` against the note's capture-time anchor — the
correct week). Step 3c copies it **byte-for-byte** into the pending record's
`--partial-payload`; the agent never runs the validator or computes the date. An
un-dateable block carries **no** `clarification_signal` (fail-closed → the record
stays ineligible for the all-day fallback).

## Calendar clarification sweep-finalize — `clarification_sweep_finalize`

The deterministic per-tick command AGENTS.md **Step 1a** runs. It replaces the
old bare `handle_clarification_state sweep` (which only deleted aged-out
records). No LLM/agent judgment is involved — the agent only invokes it.

```bash
cd /home/claude/kg-automation && python3 -m scripts.inbox.clarification_sweep_finalize \
  [--state-file <path>] [--account personal] [--inbox-root <dir>]
```

- **8h window (#780 / C-006).** The whole clarification lifecycle now ages out at
  **8h** (reduced from 24h): a pending record is "aged out" once `now − created_at ≥ 8h`.
- **All-day fallback.** When an **eligible** aged-out start-time clarification is
  found, the command creates an **all-day** calendar event from the record's
  `partial_payload` (via the #746 `route_and_finalize` transaction — atomic,
  idempotent), marks the source note processed, removes the record, and writes a
  distinct `calendar_all_day_fallback` routing-log marker. The unanswered
  appointment lands on the calendar instead of being dropped and re-asked forever.
- **Eligibility rule (deterministic).** A record is eligible **iff** its
  `partial_payload` has a non-empty `title`, a well-formed `start_date`
  (`YYYY-MM-DD`), a `missing_fields` list that **contains** `start_time`, and whose
  `missing_fields` is a subset of the timing fields `{start_time, end_or_duration}`.
  Anything else (missing title, non-timing gap, legacy record with no
  `missing_fields`/`start_date`) is **ineligible** → today's delete-and-release
  (drop the record so the note re-scans / re-asks). This is why Step 3c copies the
  finalize block's `clarification_signal` (`title` + `start_date` + `missing_fields`,
  built in code) verbatim into the pending record.
- **Output.** A one-line JSON counts summary on stdout
  (`{"aged_out","finalized","reconciled","released","retained"}`); exit 0 even when
  records are `retained` for a later retry (fail-closed). Continue regardless.

Canonical end-to-end flow (ask → 8h age-out → all-day fallback, with the
reconciliation/idempotency detail): **`docs/design/process-flows/calendar-clarification.md`**.
Do not duplicate that flow here.

## Vikunja API

- Use the vikunja_api skill for task creation
- Run `openclaw skills info vikunja_api` for details

## Date handling

All dates must be resolved in Kent's timezone (America/New_York), not UTC.
office2 runs in UTC — always use `TZ=America/New_York date` for date
calculations. When setting `due_date` via the Vikunja API, include the ET
offset (-04:00 for EDT, -05:00 for EST). Never use the `Z` (UTC) suffix
for due dates.

## GitHub

- **CLI**: `gh` (authenticated as kentonium3)
- **Skill**: `github` (OpenClaw bundled)
- **Default repo**: `kentonium3/kg-automation`
- **Multi-repo**: NOT supported yet -- only kg-automation

### Available Labels

Authoritative label set for `github_issue` blocks (AGENTS.md Step 3b).

**Priority + type** (pick one):
`P1-feature`, `P2-feature`, `P3-candidate`, `P1-infra`, `P2-infra`, `P1-bug`, `P2-bug`, `P1-rfc`, `P2-debt`

**Area** (pick at most one):
`area/infrastructure`, `area/security`, `area/felix-core`, `area/ea`, `area/task-intel`, `area/content`, `area/docs`, `area/biz-ops`

**Always apply**: `spec: brief`

