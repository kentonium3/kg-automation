# Phase 0 Research: Felix exec host=gateway directive

## R-01 — How do AGENTS.md changes reach office2?

- **Decision**: Rely on the existing `agent-prompt-sync.service` auto-sync; do
  not author a `deploys/queued/` manifest.
- **Rationale**: `docs/design/architecture/data/audited-surfaces.json` (canonical)
  lists surface `openclaw-agent-prompts` with
  `deploy_path: "scripts/openclaw/deploy/deploy_agent_prompts.py + agent-prompt-sync.service (auto)"`
  and patterns covering `scripts/openclaw/agents/*/AGENTS.md`. A 5-minute systemd
  user timer (#567) copies these files to `/data/services/openclaw/<workspace>/`,
  which the running agents read. The `deploys/queued/` manifest discipline applies
  to felix-deployer-applied changes; agent prompts have their own dedicated
  channel, so a manifest would be redundant.
- **Alternatives considered**: (a) `deploys/queued/<name>.yaml` manifest — rejected
  as redundant/incorrect channel for AGENTS.md; (b) manual `scp`/edit on office2 —
  rejected (violates deploy discipline; would be an out-of-band audited-surface
  change requiring manual rebaseline, the very thing #618 removed).

## R-02 — Is the rebaseline automatic or manual for this change?

- **Decision**: Automatic via the #618 felix-deployer observe→reconcile path; the
  merge commit records the automated rebaseline outcome.
- **Rationale**: `AGENTS.md` is an audited surface with
  `affected_baselines: ["openclaw-config.txt"]` and `rebaseline_required: true`.
  Per the #618 happy path, felix-deployer pulls `origin/main`, detects the
  audited-surface change in the merged commit range, sets a pending token, and
  rebaselines `openclaw-config.txt` once the expected drift is confirmed (the
  drift is produced when `agent-prompt-sync.service` copies the new prompts). No
  operator action on the happy path; outcome is recorded as
  `rebaseline: completed`. If the automation fails, felix-deployer emits one ntfy
  alert and a human resets manually per `docs/runbooks/security-baseline-ops.md`.
- **Alternatives considered**: Manual `ssh office2-claude 'rm baselines/* && audit.sh'`
  — this is the documented out-of-band fallback only; not needed for a
  pipeline-observed change.
- **Open verification**: This mission is PR-bound and merges into
  `fix/felix-exec-host-gateway-directive` first, then a PR `fix → main`. The
  felix-deployer observe→reconcile fires when the change lands on `main` (via the
  PR merge), not on the intermediate fix branch. The PR-merge commit must record
  the rebaseline outcome (`Rebaseline: completed at <ts>` or `not required —
  <reason>`).

## R-03 — Is `host=gateway` functionally sufficient for everything the agents do with `exec`?

- **Decision**: Yes — pin to `host=gateway`.
- **Rationale**: The #603 trajectory shows the failed run's retry used
  `host=gateway` and ran the inbox prescan clean (`unprocessed=0`, agent emitted
  `IDLE`); a separate mission-#592 run used `host=gateway` on the first try with
  `status=ok`. `host=node` requires a paired companion/node host, which is not and
  was never paired on office2, so it can only ever error. The agents' `exec` use
  (e.g. running helper scripts, `log_action.py`) is all in-process work that
  `host=gateway` serves.
- **Alternatives considered**: (a) Remove the `host=node` option from the tool
  surface — rejected; that is an OpenClaw runtime/config change, out of scope for
  the operator-selected Option A and broader than needed. (b) Leave as-is and
  filter the false-positive alert downstream — rejected; treats the symptom, not
  the cause, and the alert path is shared infrastructure.

## R-04 — Where should the directive live in each AGENTS.md, and how to keep it consistent?

- **Decision**: Insert an identical `## Tool use — exec host` hard-rule section at
  the same anchor in all four files: immediately after `## Message identity` and
  before `## Output discipline`.
- **Rationale**: All four files share the top structure
  `## Governance` → `## Authority` → `## Message identity` → `## Output discipline`,
  so this anchor exists in every file and yields identical placement. A
  self-contained section (rather than weaving into each file's differently-shaped
  body) guarantees identical wording (NFR-001) and is easy to verify by grep.
  Phrasing as a hard rule matches the existing Felix output-discipline hard-rule
  convention (FR-003).
- **Alternatives considered**: Adding the line into each file's existing "Output
  discipline" or "Action logging" section — rejected; those sections differ across
  agents, risking wording drift and harder verification.
