# Quickstart / Verification: Felix exec host=gateway directive

## What changed

An identical `## Tool use — exec host` hard-rule section was added to each of the
four Felix sub-agent standing-orders files, pinning the OpenClaw `exec` tool to
`host=gateway`:

- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
- `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
- `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`

## Static verification (in-repo, pre/post merge)

All four files carry the directive, with identical wording:

```bash
grep -l "host=gateway" scripts/openclaw/agents/felix-admin-*/AGENTS.md | wc -l   # expect 4
grep -A6 "## Tool use — exec host" scripts/openclaw/agents/felix-admin-capture/AGENTS.md
```

## Deploy verification (office2, after agent-prompt-sync runs)

The 5-minute `agent-prompt-sync.service` copies the prompts to
`/data/services/openclaw/<workspace>/`. Confirm the directive landed:

```bash
ssh office2-claude 'grep -c "host=gateway" /data/services/openclaw/*/AGENTS.md'
```

## Rebaseline verification (office2, after felix-deployer reconciles)

`AGENTS.md` is an audited surface (`affected_baselines: openclaw-config.txt`).
This mission is PR-bound: it merges into `fix/felix-exec-host-gateway-directive`,
then a PR `fix → main`. The #618 felix-deployer observe→reconcile fires when the
change lands on `main` (the PR merge), so the **PR-merge commit** must record the
outcome (`Rebaseline: completed at <ts>` or `not required — <reason>`). If the
automation did not fire, the daily security audit will surface drift; reset per
`docs/runbooks/security-baseline-ops.md`.

## Behavioral verification (7-day observational window — closes #603)

No `exec host=node` errors in the gateway journal after deploy:

```bash
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "<deploy-date>" | grep -c "host=node requires a paired node"'   # expect 0
```

Baseline before fix (for reference): 3 such errors total in the journal
(2026-06-09, 2026-06-10, 2026-06-13), last on 2026-06-13. A clean 7-day window
after deploy satisfies NFR-002 / SC-003 and is the close condition for #603.
