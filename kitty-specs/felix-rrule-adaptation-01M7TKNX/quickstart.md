# Quickstart: Felix RRULE recurrence adaptation

## Local verification (every WP)

```bash
make test
```

```bash
python3 tooling/scripts/validate_architecture_data.py --strict
```

```bash
git grep -nE "repeat_after|repeat_mode" -- scripts ':!scripts/deploy/vikunja_release' ':!scripts/vikunja/rollback_release.py'
```

The last command must print nothing except the frozen `operations:` block in `phase3-schedule.yaml` (NFR-001). No GitHub Actions are triggered (C-003).

## Before merge (Kent)

1. Re-issue the `vikunja-api-kent` token. In the Vikunja UI (Settings → API Tokens), create a token with the current permissions plus `tasks.occurrences` and `tasks.occurrences_preview`.
2. Write it to `/data/services/openclaw/secrets/vikunja-api-kent` on office2 with `read -rs`. Never echo it. Keep the old token valid for now.
3. Verify the new token read-only, **before** deleting the old one. The probe below uses only code that is already deployed (the existing client loads the token; `urllib` makes the calls) and prints only status codes for both endpoints (post-plan review finding 8):

Run the inline snippet in `research.md` R-004 ("Pre-merge permission probe") as `claude` on office2. It needs nothing undeployed. It prints only HTTP status codes for `GET /api/v2/tasks/14/occurrences?count=1` and `POST /api/v2/tasks/occurrences/preview`. Expect both to be 200 with the new token; the current token gives 401 on both.

4. Only after both return 200, delete the old token in the Vikunja UI. If either fails, put the old token back in the secrets file and stop.

## Rollout window: helpers and agent docs (post-plan review finding 7)

Helpers go live when the office2 checkout advances. Agent docs are copied by a separate 5-minute sync, and OpenClaw sessions can keep their session-init prompt. The risky interleaving is new helper plus old escalation doc: the old doc's bare POST strips the rule, then the working helper closes the task. The reverse (new doc, old helper) is safe, because the old helper's v1 PATCH 405s and writes nothing.

1. **Pause `N done`:** from the merge until step 4, Kent does not reply `N done` or reschedule to the escalation digest. If Kent prefers a mechanical pause, the `escalation-daily` cron can be disabled for the window instead. That is a cron change and needs Kent's go.
2. Confirm the checkout HEAD equals the merge SHA:

```bash
ssh office2-claude 'git -C /home/claude/kg-automation rev-parse HEAD'
```

3. Confirm the synced copies match the repo. MD5 of `/data/services/openclaw/escalation-agent/{AGENTS,TOOLS}.md` and `~/.openclaw/skills/escalation/SKILL.md` must equal the repo files; the `agent-prompt-sync.jsonl` record shows the copy.
4. Confirm no live escalation session still holds the old prompt (the session-init prompt cache; see the OpenClaw gotchas). The next `escalation-daily` run is an isolated session, so verify against its `systemPromptReport`. Then lift the pause.

## Post-merge operator canary (integration verification; record the results on #1111)

1. Complete the rollout window above.

2. Run the schedule drift check, which is read-only. Expect 7 `match` rows and no `missing` or `differs`:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.schedule_loader --check-live'
```

3. Wait for at least one sync cycle (its summary shows `baseline_seeded=N`). Then run the rule inventory against a read-only copy of the 2026-10-30 snapshot, with `--seed-ledger` pointing at the sync's `seed-ledger.jsonl`, and post the summary on #1111.
4. If the inventory is not empty, run `rule_repair --dry-run`, then `--apply`, then post the `--emit-issue-markdown` output on #1111.
5. Kent's go: re-enable the sweeper.

```bash
ssh office2-claude 'systemctl --user enable --now felix-habit-sweeper.timer'
```

6. After the next tick, check the sweeper ledger for 0 errors, and confirm the drift check still shows 7 `match` rows.
7. Over the first week after deploy, run one Felix-recorded habit completion. Verify that the rule survives via v2 GET and that the escalation JSONL records the next `N done`.
