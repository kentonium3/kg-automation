# WP04 Review Feedback — Cycle 1

**Reviewer**: claude:opus-4-7:reviewer-renata:reviewer
**Commit reviewed**: `5a300103`
**Verdict**: REJECT — material defect in data-flows.json

## Summary

The three new mission flow entries were appended to the wrong top-level array in
`docs/design/architecture/data/data-flows.json`. They landed in `planned_flows`
instead of `flows`, despite each entry carrying `"status": "active"` and being
narratively placed in the "Active Flows" section of `data-flows.md`. The
remaining four owned files (service-inventory.json, data-flows.md,
signal-to-doc-map.json) and the validator (`validate_docs.py exit 0`) are clean.
This is a one-file, one-array surgery — no other rework required.

## Required fix (single change)

In `docs/design/architecture/data/data-flows.json`:

1. **Move** the three new entries from the `planned_flows` array to the `flows`
   array:
   - `inbox-calendar-create`
   - `inbox-calendar-clarification-loop`
   - `inbox-aspiration-to-journal`

2. Place them at the end of `.flows` (after `heartbeat-gate-to-main-agent`),
   preserving the existing schema shape (no new top-level keys per entry).

3. Leave the `planned_flows` array untouched aside from removing those three
   entries.

4. Re-run `python3 tooling/scripts/validate_docs.py` — must exit 0.

5. Sanity check the topology:
   ```bash
   jq '.flows | length' docs/design/architecture/data/data-flows.json        # expect 36
   jq '.planned_flows | length' docs/design/architecture/data/data-flows.json # expect 5
   jq '.flows | map(select(.deployed_by == "inbox-calendar-and-aspiration-routing-01KTHHXS")) | length' docs/design/architecture/data/data-flows.json  # expect 3
   ```

## Diagnostic detail

After applying commit `5a300103`, the worktree shows:

```
.flows          length: 33 (UNCHANGED from parent)
.planned_flows  length: 8  (was 5; 3 new entries appended here)
```

This matches the diff hunk header `@@ -1286,6 +1286,117 @@`, which lands inside
`planned_flows` (which closes at parent line 1290, not `flows` which closes at
parent line 1187). The new entries are visually correct as JSON but placed in
the wrong array.

## Why this is material (not cosmetic)

- Each new entry self-declares `"status": "active"`. The `flows` array is
  active-flow canonical; `planned_flows` is for not-yet-implemented designs (the
  array's docstring counterpart in `data-flows.md` is literally `## Planned Flows
  (Not Yet Implemented)`). Inside-out classification: the JSON is internally
  inconsistent (active flag, planned bucket).
- `data-flows.md` places the narrative section in `## Active Flows` (line 562,
  before the `## Planned Flows` divider at line 594). Narrative says active, JSON
  says planned — these drift.
- Downstream consumers that iterate over `.flows` (graph builders, change-class
  consumers in the signal-to-doc-map pipeline, any future mission's diff
  detection) will not see the mission's new flows. The whole point of WP04 is
  doc-sync — landing the wrong bucket defeats it.

## Implementer self-report cross-check (other claims verified)

The implementer reported "Three notable deviations from prompt's literal text
(all justified)". I verified the three named deviations and find them
acceptable:

1. **service-inventory.json uses `purpose` + `notes` rather than a new
   `capabilities` array** — the prompt explicitly says "or equivalent field" and
   the prose in `purpose` + `notes` covers all four required concepts for
   `felix-admin-capture` (calendar via main delegation, aspirations → 08-Journal,
   Someday by name, pending-clarifications + 24h sweep) and both required
   concepts for `main` (calendar-create delegation receiver, WhatsApp
   clarification resolver). Acceptable.

2. **gog entry got a `notes` field** — `notes` already exists on other entries
   (e.g., vikunja). Not a new top-level key for the file. Acceptable.

3. **`feature: F<XXX>` omitted** — per the WP04 prompt, this is optional and
   deferred to merge time. Acceptable.

## Other checks (all PASS)

- **Schema validity**: `python3 tooling/scripts/validate_docs.py` exits 0
  (validator does not enforce the active-vs-planned distinction here; it is
  satisfied by the JSON being well-formed against the schema).
- **Scope**: `git show 5a300103 --stat` lists exactly the 4 owned files. No
  drift beyond scope.
- **T020 service-inventory.json**:
  - `felix-admin-capture` `purpose` + `notes` cover all four new capabilities.
  - `main` `purpose` covers both new capabilities.
  - `gog` `notes` names `felix-admin-capture (via main delegation)`.
  - `last_updated` / `updated_by` bumped to credit the mission.
  - The -13 deletions are a date+attribution rewrite of `last_updated` /
    `updated_by` on three entries; no field shapes removed.
- **T022 data-flows.md**:
  - Section "Inbox classification and calendar routing" present at line 562.
  - In `## Active Flows`, before `## Planned Flows`.
  - References each of Flow A / B / C with their JSON ids.
  - Covers classifier vocabulary, capture → main delegation, 24h clarification
    timeout, aspiration → journal, Someday-by-name.
  - Frontmatter `last_updated` / `updated_by` bumped.
- **T023 signal-to-doc-map.json**:
  - `last_updated` / `updated_by` bumped.
  - No new mapping additions needed — existing entries already cover the
    touched docs.
  - No stale `agent-inventory.json` or `agents.md` references introduced.
- **No `agent-inventory.json` or `architecture/agents.md` references** anywhere
  under `docs/design/architecture/` (grep confirms zero hits).
- **INDEX.md cross-refs** still point at real files (service-inventory.md,
  data-flows.md/.view.md, data/service-inventory.json, data/data-flows.json).

## What "fix" looks like in practice

This should be a small, surgical edit:

1. Cut the three new flow entries (parent lines 1290–1399 in the WP04 commit's
   `data-flows.json`) out of `planned_flows`.
2. Paste them into `.flows` after the last entry (`heartbeat-gate-to-main-agent`).
3. Validate, sanity-check counts, commit.

No other files need to change. service-inventory.json, data-flows.md, and
signal-to-doc-map.json are accepted as-is.
