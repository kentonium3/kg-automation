# Quickstart: Capture Directive-6 Helpers

**Mission**: `capture-d6-helpers-extraction-01KTMS5Q`
**Audience**: Operator or follow-on AGENTS.md rewrite author.

## Verify helpers exist post-merge

After mission merge and #567's 5-min deploy tick:

```bash
ssh office2-claude
cd ~/kg-automation
git log -1 --oneline  # should be the merge commit

# Smoke test each helper's --help
python3 -m scripts.inbox.mark_processed --help
python3 -m scripts.inbox.route_journal_entry --help
python3 -m scripts.inbox.route_someday --help
python3 -m scripts.inbox.route_calendar_event --help
python3 -m scripts.inbox.handle_clarification_state --help
python3 -m scripts.inbox.classify_content --help
```

All six should exit 0 with usage text.

## Per-helper invocation examples

### mark_processed

```bash
python3 -m scripts.inbox.mark_processed \
  --path /home/kgale/second-brain/notes/01-Inbox/Inbox\ 2026-06-08\ 0712.md
```

Idempotent. Safe to invoke repeatedly.

### route_journal_entry

```bash
echo "Made progress on Felix this morning." > /tmp/content.txt

python3 -m scripts.inbox.route_journal_entry \
  --content-file /tmp/content.txt \
  --datetime "2026-06-08T07:32:00-04:00"
```

Appends a section to `/home/kgale/second-brain/notes/08-Journal/Journal 2026-06-08 0732.md`.

### route_someday

```bash
python3 -m scripts.inbox.route_someday \
  --title "Look into Rust" \
  --body "Curious about the borrow checker model." \
  --note-filename "Inbox 2026-06-08 0712.md"
```

Stdout: `task_id=<int>`. Creates Vikunja task in the Someday project.

### route_calendar_event

```bash
cat > /tmp/payload.json <<'EOF'
{
  "title": "Meet with Rob",
  "start": "2026-06-12T15:00:00-04:00"
}
EOF

python3 -m scripts.inbox.route_calendar_event --payload-file /tmp/payload.json
```

Stdout: normalized JSON with `end` filled in. Stderr: empty if valid; structured error if missing fields.

The agent prompt then delegates to Felix main for the actual `gog calendar create` call.

### handle_clarification_state

```bash
# Add a pending clarification:
python3 -m scripts.inbox.handle_clarification_state add \
  --note-filename "Inbox 2026-06-08 0712.md" \
  --partial-payload '{"title": "Meet with Rob", "start": "2026-06-12T15:00:00-04:00"}'

# Daily sweep (cron-callable):
python3 -m scripts.inbox.handle_clarification_state sweep

# Match an incoming reply:
python3 -m scripts.inbox.handle_clarification_state match \
  --reply-content "3pm works for the Rob meeting"
```

State file: `/home/kgale/second-brain/agents/state/pending-calendar-clarifications.json`.

### classify_content

```bash
python3 -m scripts.inbox.classify_content \
  --content-file /home/kgale/second-brain/notes/01-Inbox/Inbox\ 2026-06-08\ 0712.md
```

Stdout: JSON `{note_filename, blocks: [...]}`. The follow-on AGENTS.md rewrite parses this and routes per block.

## Running tests locally

From the repo root:

```bash
pytest tests/inbox/ \
  --cov=scripts.inbox \
  --cov-branch \
  --cov-fail-under=90 \
  -v
```

Per-helper:

```bash
pytest tests/inbox/test_mark_processed.py --cov=scripts.inbox.mark_processed --cov-branch
```

## Operator notes

- The 6 new helpers do NOT modify capture's AGENTS.md. That is the follow-on mission's responsibility.
- Until the follow-on AGENTS.md rewrite merges, the helpers exist on disk but are not invoked by the cron tick. The capture agent continues to use its pre-rewrite prompt (which is truncated at openclaw's 12K budget — silent content loss class continues until the follow-on mission lands).
- Coverage gate is enforced per-helper, not globally.
- These helpers all run as the `claude` user on office2. `~/second-brain/` (kgale-owned) is readable + writable by claude per existing inbox-helper precedent.
