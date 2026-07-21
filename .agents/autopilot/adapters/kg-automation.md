# Autopilot Adapter — kg-automation

Repo-specific mechanics for `felix-dev-autopilot` when the target `repo` is
**kg-automation** (Kent Gale's personal AI OS / Felix on office2). The
repo-agnostic rules live in `../felix-dev-autopilot-contract.md`; this file
supplies only what is specific to this repo.

## Queue source

- Backlog is the GitHub issue queue on `kentonium3/kg-automation`.
- Candidate query (highest-priority open features in the active milestone):
  ```
  gh issue list --repo kentonium3/kg-automation --label P1-feature \
    --state open --limit 5 --json number,title,body,labels,milestone
  ```
- Spec-readiness: full spec-kitty missions need the `spec: ready` label; the
  lighter autopilot vehicles (quick-direct / kitty-light) do not, but the issue
  must still carry symptom/observer/cost (Directive 8). Read the full issue body
  — it is the spec.

## Gate (must all pass locally AND in CI before merge — never merge red)

```
make test                                   # non-live pytest suite (ignores docs/archive)
python3 tooling/scripts/validate_docs.py
python3 tooling/scripts/validate_architecture_data.py
```

- The pre-commit hook (`.githooks/`) runs the two validators whole-tree on
  every commit; `make test` is what CI (`test-ci.yml`) runs. CI checks on a PR:
  `pytest`, `pr-validate`, `remind` — wait for all green.
- Helpers importing `scripts.common.*` must be invoked `python3 -m scripts.X.Y`
  (module form), never the script-path form (ModuleNotFoundError).

## Adversarial review

- Default reviewer is **reviewer-renata** (Opus subagent) for non-trivial diffs.
- Codex (`codex exec -p spec-kitty-review`) is the historical default but has
  been unreliable as a reviewer recently (under investigation) — prefer renata
  until that is resolved. Never `--full-auto` (breaks `.git/` writes).

## Deploy motion (office2)

office2 = Ubuntu hub; agent SSH alias `ssh office2-claude` (never `office2-kgale`
— that's human-only; claude user has no sudo). Two deploy paths by change type:

- **Helper / library / script change (`scripts/**`, most fixes):** the office2
  checkout self-pulls. felix-deployer pulls `origin/main` ~every 5 min; to
  deploy immediately, fast-forward the checkout:
  ```
  ssh office2-claude 'cd ~/kg-automation && git pull --ff-only && git log --oneline -1'
  ```
- **Agent-prompt change (`AGENTS.md` / `IDENTITY.md` / `SOUL.md` / `TOOLS.md` /
  `USER.md`):** deploy via agent-prompt-sync (systemd), which copies prompts to
  `/data/services/openclaw/<deploy-dir>/` (excludes `.tmpl`). A **main-prompt**
  change additionally needs a rotate + `openclaw gateway restart`; sub-agents
  (fresh session per tick) do not. Verify the agent slug → deploy-dir mapping
  with `find` before assuming (slug ≠ deploy dir). AGENTS.md has a 12,000-byte
  cap on at-cap agents (main, felix-admin-calendar) — check size after editing.

## Live-verify

- **Helper/script:** run the deployed script on office2 with a representative
  input and assert the observable behavior (e.g. pipe a block through
  `python3 -m scripts.calendar_routing.validate_calendar_event` and check the
  payload). Confirm the checkout HEAD matches the merged commit first.
- **Prompt:** confirm the deployed file under `/data/services/openclaw/...`
  matches the repo, and (for a main-prompt change) that the gateway restarted.

## Rebaseline rule (#621 / change-control)

- Rebaseline the security-monitor baselines only when the change touches an
  **audited surface** (`docs/design/architecture/data/audited-surfaces.json` —
  openclaw agent prompts, openclaw config, systemd user units + deploy scripts,
  Python dependency manifests, Docker stack files, committed SSH key material).
- Most `scripts/**` + test changes are **not** audited surfaces →
  `Rebaseline: not required — <reason>` in the merge/commit.
- Pipeline-driven deploys (`deploys/queued/` manifests) rebaseline
  automatically via felix-deployer. Out-of-band office2 changes need a manual
  reset (see `docs/runbooks/security-baseline-ops.md`).

## Change-control tiers (kg-automation taxonomy)

`docs/design/architecture/data/change-risk-taxonomy.json`. Tier 0 (host: UFW,
sshd, sudoers, kernel) = **off-limits autonomously**, generate + surface only.
Tier 1 (connectivity/fabric) = verify dependents before+after. Tier 2
(app/state: DB, env, compose) = confirm recent Restic backup first. Tier 3
(logic/workflow: Python, prompts, cron) = standard, dry-run where available.
Tier 4 (schema/metadata: CLAUDE.md, READMEs, comments) = auto-commit.

## Architecture-docs obligation

Any change that deploys/modifies/removes a service, credential, port, or data
flow MUST update `docs/design/architecture/data/*.json` + their markdown
counterparts in the same PR. Use `signal-to-doc-map.json` to find affected docs.

## Deploy-to-office2 discipline

Every office2 deploy that adds/changes a service or cron flows through a
`deploys/queued/<name>.yaml` manifest consumed by felix-deployer. Pure
script/prompt updates that ride the self-pull / agent-prompt-sync do not need a
manifest; a new service/cron/systemd unit does.
