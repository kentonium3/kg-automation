# Research: Felix-admin cron path robustness fix

Phase 0 findings. All conclusions are grounded in live codebase probes of
`/Users/kentgale/repos/kg-automation` (not the issue text alone).

## R1 — FR1 guardrail mechanism: environment vs. prompt

**Decision**: Set `Environment=PYTHONPATH=/home/claude/kg-automation` in
`scripts/openclaw/openclaw-gateway.service`. Do **not** add per-invocation
`PYTHONPATH` prefixes or a wrapper script to the prompts. (Decision
`DM 01KWR0CRKY6G91P715GD375YKC`.)

**Rationale**: The invariant "`scripts` is importable" must live in the
deterministic layer. Inline prefixes and wrapper calls are *improved
instructions* — correctness still depends on an LLM emitting a specific string
on every invocation and every improvised fallback/error branch, the same
fragility class as today's prose. The systemd unit already exports
`Environment=HOME=/home/claude` (line 14), which is inherited by agent
subprocesses — and that inheritance is precisely what makes `~` resolve to
`/home/claude` (the root cause of the stray-dir defect). So the inheritance path
is proven; `PYTHONPATH` set on the same unit reaches every agent subprocess
identically, from any cwd, for all agents present and future. `KillMode=control-group`
confirms tool-call subprocesses live in the gateway's cgroup.

**Alternatives considered**:
- *Inline `PYTHONPATH=…` prefix per invocation* — matches the credential-probe
  precedent (`scripts/office2/deploy/credential-*.sh`), but is stochastic, touches
  ~26 invocation sites across 4 prompts, and doesn't cover novel code paths.
- *Thin wrapper `scripts/bin/…` called by absolute path* — centralizes the constant
  but adds a new executable to deploy/chmod and a second convention ("use the
  wrapper, by absolute path") the agent can drift from. No reliability gain over inline.
- *`openclaw.json` agent env* — also environment-level, but there is **no source
  `openclaw.json` in the repo** (it lives on office2), so it would be an out-of-repo
  change outside the prompt-sync/deploy path. The gateway `.service` is the in-repo,
  deploy-governed equivalent.
- *Install `scripts` as a package (`pip install -e`)* — the repo has **no
  `setup.py`/`pyproject.toml` packaging**, so this is a larger change for no extra
  benefit over the env var.

**Fleet-wide consequence**: because the fix is a single inherited env var, it
resolves the cwd/`ModuleNotFoundError` class for the whole agent fleet, not just
felix-admin. The broader audit of the same *runtime-environment-assumption class*
(other cwd/HOME/checkout-path cases) is extracted to **#658**, sequenced after
this mission.

## R2 — Complete reader/writer set for the relocated state (issue was incomplete)

**Decision**: Relocate **two** state files, not one, both to
`/data/services/openclaw/state/`:
- `inbox-routing.jsonl` — `scripts/inbox/routing_log.py:22`
  (`DEFAULT_ROUTING_LOG_PATH = Path.home()/second-brain/agents/state/inbox-routing.jsonl`).
- `pending-calendar-clarifications.json` — `scripts/inbox/handle_clarification_state.py:47`
  (`STATE_PATH_DEFAULT = Path.home()/second-brain/agents/state/pending-calendar-clarifications.json`).

**Rationale**: FR-008/SC-5 require that *no writer* recreates
`/home/claude/second-brain`. Grep found a second live writer the issue never
named; leaving it pointed at the stray dir would resurrect it on the next
calendar clarification. Both modules resolve their default **at call time**
(via `sys.modules[__name__].DEFAULT_…`), which is friendly to monkeypatch-based
tests. No other reader hardcodes the old state path (grep confirmed only these
two writers + a prescan docstring reference).

**Alternatives considered**: ledger-only relocation (issue's literal text) —
rejected; leaves SC-5 unsatisfiable and defers a known defect to a follow-up.

## R3 — Forensic-log canonical location

**Decision**: `/home/kgale/second-brain/agents/logs/` (absolute, never `~`).
Fix `scripts/inbox/prescan.py:56` `DEFAULT_LOG_DIR` (+ the docstring at line 27)
and the `~/second-brain` reference in
`scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl` (~line 565);
reconcile the `AGENTS.md`/`TOOLS.md`/`TOOLS.md.tmpl` copies.

**Rationale**: `service-inventory.json` shows the `obsidian-sync` service syncs
`/home/kgale/second-brain/notes`; only `/home/kgale/second-brain` reaches Kent's
devices. `~` resolves to `/home/claude` for the claude-run agent (same root cause
as R1). `scripts/inbox/file_inbox_quality_issue.py:37` already uses the correct
absolute path — it is the reference pattern; the two drifted outliers are prescan
and the capture template.

## R4 — Prose that becomes inert under the guardrail

**Decision**: After R1 deploys, remove the redundant cwd instructions:
habits `AGENTS.md` `cd /home/claude/kg-automation && …` prefixes + the line-90
"cwd matters / ModuleNotFoundError" warning; capture `AGENTS.md` line-74
"Working dir: /home/claude/kg-automation"; and fix escalation `AGENTS.md` line-265
stale `~/repos/kg-automation/…/log_action.py` → `/home/claude/kg-automation`.

**Rationale**: The guardrail makes these unnecessary; leaving them misleads future
readers and re-legitimizes the fragile pattern. **Sequencing**: removal must
follow the R1 deploy — deleting "you must cd" before the env var is live would
reintroduce the failure with no safety net.

**Note on tasker**: the tasker agent invokes `scripts.enrichment.*` (not
`scripts.tasker.*` as the issue assumed) and has no `cd` prefix today — it simply
benefits from R1. Calendar has **zero** `-m scripts.*` invocations and is out of
the prompt sweep.

## R5 — Office2 migration & cutover ordering

**Decision**: Perform the one-time data move as a Tier-2 deploy manifest
(`deploys/queued/000N-migrate-inbox-state-and-logs.yaml`) with a Python entrypoint
built on `scripts/deploy/lib/` (`snapshot`, `verify`, `tier`). Order: snapshot-verify
→ copy the two state files to `/data/services/openclaw/state/` → preserve historical
forensic logs into `/home/kgale/second-brain/agents/logs/` → assert new-path files
present (`post`) → decommission `/home/claude/second-brain/`.

**Rationale**: `deploys/applied/0003-*` establishes the manifest schema (v1:
entrypoint + pre/post verification + tier + snapshot). C-003 makes this Tier-2
(state mutation on a service data dir) → snapshot-required. The
**migration/cutover window** (code reads new path before the copy exists) is
bounded by two existing safeguards: routing_log's reader is fail-safe (missing
file → empty set) and notes carry `status: processed` frontmatter enforced by
`mark_processed`, so already-routed notes are skipped even against an empty ledger.
Worst case is re-evaluation, not duplicate routing.

**Alternatives considered**: a transitional new→old read-fallback in both state
modules — deferred to the tasks phase as an option only if IC-05's copy-first +
fail-safe reasoning proves insufficient; if adopted it needs an explicit removal
forcing function (no-vestiges rule).

## R6 — Audited-surface / rebaseline determination

**Decision**: This mission touches two audited surfaces — the systemd unit
(`openclaw-gateway.service`) and agent prompts (`AGENTS.md`). The merge must
carry a rebaseline line. **Open item for the plan-to-tasks boundary**: per the
#621 gap, `audit.sh` hashes `openclaw.json` into `openclaw-config.txt` but does
**not** hash agent `AGENTS.md` files — so agent-prompt changes are effectively an
*unmonitored* audited surface, while the systemd-unit change **is** monitored and
does require a rebaseline. Tasks/merge must state which applies (expected:
`Rebaseline: completed …` for the unit change; note the AGENTS.md gap).
