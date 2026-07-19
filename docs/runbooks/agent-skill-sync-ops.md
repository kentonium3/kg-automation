---
id: agent-skill-sync-ops
doc_type: runbook
title: Agent skill sync — operator runbook
audience: agents_and_humans
status: approved
level: howto
owners: ["kgale"]
last_validated: '2026-07-19'
last_updated: '2026-07-19'
version: v1.0
tags: [775, 567, 563, 714]
---

# Agent skill sync — operator runbook

Operator-facing runbook for the OpenClaw skill deploy pipeline (`agent-skill-sync`).
Mission: `openclaw-skills-sync-01KXW1DQ` (closes #775). Sibling to the agent-prompt
deploy pipeline ([`agent-prompt-sync-ops.md`](<./agent-prompt-sync-ops.md>), #567);
this one keeps the OpenClaw **skills** (`SKILL.md`) faithful from repo → office2.

**Scope**: deploy/sync **mechanism** only. Skill **content** refresh is #714.

## What this pipeline does

Every ~5 minutes on office2, a user-level systemd timer fires a Python helper
that:

1. Advances the shared checkout `/home/claude/kg-automation` to `origin/main`
   (git fetch + `merge --ff-only`, via `scripts/deploy/lib/gitsync`, under the
   shared `deploylock` advisory lock)
2. For each of the six skills, MD5-compares the repo
   `scripts/openclaw/skills/<skill>/SKILL.md` against the deployed
   `/home/claude/.openclaw/skills/<skill>/SKILL.md`
3. Atomically copies any drifted `SKILL.md` (destination dir created first)
4. Appends structured audit records to
   `/data/services/openclaw/deploy/agent-skill-sync.jsonl`
5. Overwrites the flat `/data/services/openclaw/deploy/skills-last-tick.json`
   freshness pointer (timer-liveness anchor; `exit_code` always 0) every real tick

The six skills: `doc-audit`, `escalation`, `skill-author`, `task-intelligence`,
`vikunja-api`, `whisper`.

**Copy-only discipline**: it **never prunes**. A deployed skill with no repo
counterpart (an **orphan**) is left in place and surfaced as an alert (never
deleted). `*.backup*` sidecars are ignored. A repo skill dir carrying files
beyond `SKILL.md` emits a **warning-audit** — the copied payload stays
`SKILL.md` only.

No openclaw restart is triggered. Running agents pick up a new `SKILL.md` at
their next session-init (next cron tick).

**Third actor on the shared checkout**: `agent-skill-sync` joins `felix-deployer`
and `agent-prompt-sync` on the single office2 checkout, reusing the same
race-immune advance + advisory `deploylock`. A lock-unavailable tick **defers
cleanly** to the next interval — a benign, non-failing event. See
[`deployment.md` §Shared-checkout lock](<./deployment.md>).

## The units

| Unit | Role | Source in repo |
|---|---|---|
| `agent-skill-sync.timer` | User timer — `OnUnitInactiveSec=300s` + `OnBootSec=120s` + `Persistent=true` | `scripts/openclaw/deploy/agent-skill-sync.timer` |
| `agent-skill-sync.service` | User oneshot — `ExecStart=/usr/bin/python3 -m scripts.openclaw.deploy.deploy_agent_skills` (WorkingDirectory `/home/claude/kg-automation`) | `scripts/openclaw/deploy/agent-skill-sync.service` |

Both are **user** units (run as `claude`), installed under
`~/.config/systemd/user/`.

## Deploy (manifest pipeline + hard verify-before-enable gate)

The pipeline deploys through the standard manifest discipline:
`deploys/queued/skills-sync.yaml` (tier 3, `audited_surface: true`) →
entrypoint `scripts/deploy/deploy-skills-sync.sh`. felix-deployer applies it
within ~5 min of the merge landing on `main`: it advances the checkout (so the
helper, units, and entrypoint are present), then runs the entrypoint.

felix-deployer invokes the entrypoint **twice** — `--dry-run` (non-mutating:
validate + print the plan) then `--apply` (does the work). The `--apply` path is a
**HARD verify-before-enable gate** — a failed smoke or enable fails the deploy
**loudly** rather than leaving a half-enabled timer:

1. Place the unit files into `~/.config/systemd/user/`
2. `systemctl --user daemon-reload`
3. **Lock-free real-copy smoke**: run `python3 -m scripts.openclaw.deploy.deploy_agent_skills --smoke`
   **in-process** and assert it wrote `skills-last-tick.json` with `status=smoke`.
   This does REAL `SKILL.md` copies without acquiring the shared checkout
   `deploylock` (which felix-deployer already holds around the whole apply) and
   without a git advance (the checkout is already current). A `systemctl start`
   smoke would run in a separate process, contend the held lock, defer, and pass on
   a no-op — so the smoke uses `--smoke` to prove a *real* sync ran (Codex #2 HIGH-1).
4. `systemctl --user enable --now agent-skill-sync.timer` (schedules the timer; its
   first real, lock-held tick runs after felix-deployer releases the lock)
5. Assert `is-enabled` and that the timer shows in `list-timers`

`XDG_RUNTIME_DIR` is exported so the `systemctl --user` calls reach the user bus.
**No sudo** is used (Tier-0 discipline).

Because the units + deploy script are an **audited surface**, the felix-deployer
happy path auto-rebaselines (#685 watermark) and the merge records the rebaseline
outcome.

## Operator: manual enable / validation

If you ever need to install or re-validate by hand (the deploy entrypoint is the
supported path; this is the manual fallback):

```bash
ssh office2-claude
cd ~/kg-automation
git pull --ff-only origin main
git log -1 --oneline   # should match the merge commit on Mac

export XDG_RUNTIME_DIR=/run/user/$(id -u)

mkdir -p ~/.config/systemd/user
cp scripts/openclaw/deploy/agent-skill-sync.service ~/.config/systemd/user/
cp scripts/openclaw/deploy/agent-skill-sync.timer   ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now agent-skill-sync.timer
systemctl --user list-timers | grep agent-skill-sync
```

Verify the first tick (within ~5 minutes):

```bash
journalctl --user -u agent-skill-sync.service --since "10 min ago" --no-pager
tail -50 /data/services/openclaw/deploy/agent-skill-sync.jsonl
cat /data/services/openclaw/deploy/skills-last-tick.json
```

Spot-check a deployed skill matches repo:

```bash
md5sum /home/claude/kg-automation/scripts/openclaw/skills/vikunja-api/SKILL.md \
       /home/claude/.openclaw/skills/vikunja-api/SKILL.md
```

Both md5s should match. If they differ, run the drift check (below).

### Manual trigger, dry-run, single-skill

```bash
cd /home/claude/kg-automation

# Manual full tick (functionally identical to the timer firing):
python3 -m scripts.openclaw.deploy.deploy_agent_skills

# Preview drift without modifying anything (read-only: no fetch/merge, no copy,
# no lock, audit log NOT written):
python3 -m scripts.openclaw.deploy.deploy_agent_skills --dry-run

# Force-sync a single skill (incident response):
python3 -m scripts.openclaw.deploy.deploy_agent_skills --skill vikunja-api
```

Or trigger via systemd (equivalent to a full tick):

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user start agent-skill-sync.service
```

**Invocation form is mandatory** — the module imports `scripts.*` siblings, so a
script-path invocation fails `ModuleNotFoundError`. Always use the `-m` form from
the checkout root (`cd /home/claude/kg-automation && python3 -m …`).

**Sync helper exit codes**: `0` success (no drift OR all copies succeeded; also a
benign lock defer; also `--dry-run`) · `1` partial failure (advance ok, one or
more copies failed) · `2` git advance failed (fetch/merge/diverged — no copies
attempted) · `3` validation error (missing `.git/`, missing skills dir, unknown
`--skill`).

## Independent drift check (and how it's canary-probed)

`scripts/openclaw/enforcement/skills_drift_check.py` is a **standalone
comparator** — deliberately **NOT** the sync's own code path. It MD5-compares
each repo `SKILL.md` against its deployed copy and reports drift **plus orphans**
(deployed skills with no repo counterpart; alert-only, never pruned), ignoring
`*.backup*`:

```bash
cd /home/claude/kg-automation
python3 -m scripts.openclaw.enforcement.skills_drift_check          # human-readable
python3 -m scripts.openclaw.enforcement.skills_drift_check --json   # per-skill rows
```

**Drift-check exit codes**: `0` clean (all repo `SKILL.md` match deployed, no
orphans) · `1` drift and/or orphan · `2` a skills dir was unreadable.

This comparator is wired as the service's **canary `health_check`** (method
`self-check-command`, endpoint
`cd /home/claude/kg-automation && python3 -m scripts.openclaw.enforcement.skills_drift_check`).
The felix-canary turns a non-zero exit into a deduped alert. A separate
comparator is used **on purpose**: the sync overwrites office2 every tick, so a
dry-run of the sync itself would be circular and maskable by the next remediating
tick — an independent observer is the only trustworthy drift signal.

## Observability

| Surface | Path | What it tells you |
|---|---|---|
| Audit log | `/data/services/openclaw/deploy/agent-skill-sync.jsonl` | Per-file `copy`/`skip`/`warning`/`error` records + per-tick summary |
| Freshness pointer | `/data/services/openclaw/deploy/skills-last-tick.json` | Timer liveness (`completed_at_utc`, `exit_code` always 0). The canary's freshness anchor |
| Git-advance health | `/data/services/openclaw/deploy/agent-skill-sync-git-health.json` | Confirmed git-advance failure streak; fires ≤1 ntfy alert per streak via the felix-alert bus |
| Copy health | `/data/services/openclaw/deploy/agent-skill-sync-copy-health.json` | Confirmed per-file copy failure streak; fires ≤1 ntfy alert per streak |
| Independent drift check | `python3 -m scripts.openclaw.enforcement.skills_drift_check` | Repo↔deployed drift + orphans (canary `health_check`) |

`lock_unavailable` defers do **not** count as failures — they are logged and the
tick retries on its next interval.

## Troubleshooting

### `systemctl --user list-timers` does not show agent-skill-sync

The timer was not enabled. Re-run
`systemctl --user enable --now agent-skill-sync.timer` (with
`XDG_RUNTIME_DIR` exported).

### Audit log has git-advance failures / `agent-skill-sync-git-health.json` is escalating

The shared-checkout advance failed (`fetch`/`merge`/`diverged`). This is shared
with felix-deployer + agent-prompt-sync — inspect
`cd ~/kg-automation && git status`. A transient network blip self-heals on the
next tick; a genuine divergence (e.g. a manual commit on the office2 clone) must
be reconciled by hand (the helper does NOT auto-resolve divergence).

### Audit log has copy `error` entries / `agent-skill-sync-copy-health.json` is escalating

An atomic copy raised. Common cases: `PermissionError` (deploy dir not writable
by `claude` — confirm `/home/claude/.openclaw/skills/<skill>/` is writable) or
`OSError [Errno 28]` (disk full on the target volume).

### Drift check reports an orphan

A deployed skill exists under `/home/claude/.openclaw/skills/` with **no** repo
counterpart. This is **alert-only by design** — the pipeline never prunes. Decide
deliberately: add the skill to `scripts/openclaw/skills/<skill>/` in the repo (so
it becomes managed), or remove the deployed dir by hand if it is genuinely stale.

### A `SKILL.md` changed in repo but the agent's behavior hasn't

Agents read their skills at openclaw session-init only (no hot-reload). The next
agent session (next cron tick) picks up the new `SKILL.md`. The helper does NOT
force-restart openclaw.

## Rollback

If the pipeline itself misbehaves (regression in `deploy_agent_skills.py`, or a
bad `SKILL.md` needs to stop propagating), disable and remove the units:

```bash
ssh office2-claude
export XDG_RUNTIME_DIR=/run/user/$(id -u)

systemctl --user disable --now agent-skill-sync.timer
rm ~/.config/systemd/user/agent-skill-sync.{service,timer}
systemctl --user daemon-reload
```

To roll back a **bad skill content** change (rather than the mechanism), revert
the offending commit on Mac and push — the next tick picks up the revert via the
normal pull-and-sync flow:

```bash
cd ~/repos/kg-automation
git revert <bad-sha>
git push origin main
# wait <=5 min for the next tick, OR force one:
ssh office2-claude 'cd ~/kg-automation && python3 -m scripts.openclaw.deploy.deploy_agent_skills'
```

## References

- Mission spec: `kitty-specs/openclaw-skills-sync-01KXW1DQ/spec.md`
- Helper source: `scripts/openclaw/deploy/deploy_agent_skills.py`
- Independent drift check: `scripts/openclaw/enforcement/skills_drift_check.py`
- Systemd units: `scripts/openclaw/deploy/agent-skill-sync.{service,timer}`
- Deploy manifest + entrypoint: `deploys/queued/skills-sync.yaml`, `scripts/deploy/deploy-skills-sync.sh`
- Service inventory entry: `docs/design/architecture/data/service-inventory.json` → `services[name=agent-skill-sync]`; narrative in `docs/design/architecture/service-inventory.md` §OpenClaw Skill Deploy Pipeline (#775)
- Data flow: `docs/design/architecture/data/data-flows.json` → `flows[name=openclaw-skill-sync]`
- Sibling pipeline: [`agent-prompt-sync-ops.md`](<./agent-prompt-sync-ops.md>) (#567)
