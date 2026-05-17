---
affected_files: []
cycle_number: 1
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
reproduction_command:
reviewed_at: '2026-05-17T05:57:03Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP05
---

**Issue 1: Phase 2 rollback smoke-test command is not runnable as documented.**

`docs/runbooks/felix-bot-vikunja-provisioning.md:211` documents:

```bash
python3 scripts/vikunja/validate_felix_bot.py \
    --rollback-smoke-test \
    --secrets-path /data/services/openclaw/secrets/vikunja-api \
    --bak-path /data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak
```

The approved `validate_felix_bot.py` argparse requires `--token-file` even in
`--rollback-smoke-test` mode. Running the documented command exits with code 2:

```text
validate_felix_bot.py: error: the following arguments are required: --token-file
```

Fix the runbook invocation by including
`--token-file /run/user/$(id -u)/felix-bot-token` in the rollback smoke-test
command, or change the helper interface before this WP is re-reviewed. The
runbook must match the approved helper interface exactly.

**Issue 2: Phase 2 expected SUMMARY lines do not match the validator's actual output.**

`docs/runbooks/felix-bot-vikunja-provisioning.md:228` expects:

```text
SUMMARY: validated felix-bot - 12 projects readable, write attribution confirmed, cleanup complete
```

The approved validator emits a parseable key/value line instead:

```text
SUMMARY: mode=validate projects_ok=12 target_project_id=13 task_id=<id> comment_id=<id> attribution=ok cleanup_comment=<bool> cleanup_task=<bool> elapsed_seconds=<seconds>
```

`docs/runbooks/felix-bot-vikunja-provisioning.md:235` expects:

```text
SUMMARY: rollback-smoke-test simulated total=<seconds>s budget=300s
```

The helper emits:

```text
SUMMARY: mode=rollback-smoke-test simulated_seconds=<seconds> budget_seconds=300.0 within_budget=True elapsed_real_seconds=<seconds>
```

Update the runbook expected output and GO criteria to match the actual helper
output fields.

**Issue 3: Phase 3 expected SUMMARY and GO/NO-GO checks do not match `swap_vikunja_secrets.py`.**

`docs/runbooks/felix-bot-vikunja-provisioning.md:314` and `:333` require
`phase=post-verify result=ok attribution=felix-bot`, but the approved swap
helper emits:

```text
SUMMARY: phase=verify result=ok created_by=felix-bot
```

`docs/runbooks/felix-bot-vikunja-provisioning.md:325` and `:346` expect
auto-rollback as `phase=rollback result=ok attribution=kent`, but the helper
emits:

```text
SUMMARY: phase=auto_rollback result=ok attribution=kent
```

Update the Phase 3 expected output, GO criteria, and NO-GO branches to use the
helper's actual `phase` and field names. This matters because the runbook tells
the operator exactly which line to verify before proceeding.

**Issue 4: SC-002 checklist wording does not mirror the spec's verification method.**

The spec says SC-002 is verified when reads succeed on all 12 projects and
"write probe succeeds on one per project." The runbook checklist at
`docs/runbooks/felix-bot-vikunja-provisioning.md:589` says "a per-project write
probe succeeded," but Phase 2 only documents a single write probe against
project 13. Either update the runbook to include one write probe per project,
or adjust the checklist text so it does not claim the spec's per-project write
verification was performed.

**Validation notes from this review**

- `credential-manifest.json` parses with `python3 -c "import json; json.load(open(...))"`.
- `service-inventory.json` parses with `python3 -c "import json; json.load(open(...))"`.
- `markdownlint` is not installed in this environment, so markdown lint could not be executed locally.
- `service-inventory.json` no-op is acceptable because the `vikunja` entry has no accounts/users/identities field, and the WP05 commit message documents that.
