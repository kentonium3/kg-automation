---
tags: [162]
---

# Project Charter

<!-- Authoritative policy document for spec-kitty workflow governance. Edit directly, run `spec-kitty charter sync` to regenerate derived files. -->

Generated: 2026-03-26T04:46:08Z (original)
Last amended: 2026-04-11 (mission 027 close-out merge + comprehensive restoration from mission-026/027 lessons)

## Intent

Drive accountable action on Kent's personal and business goals through always-on automation, frictionless capture, and proactive follow-up. Minimize context-switching cost; maximize time spent on high-value work; surface what needs attention before it's forgotten.

Deliver highly leveraged automation around business outcomes and operations acting as an extensible team of specialists to manage research, systems development, business development, administration, marketing, sales, service, communications, networking, accounting, and other business functions so Kent may focus time and attention on the highest value thinking and tasks.

Felix (this system) is not general-purpose automation. It is a personal operating system with a specific architecture centered on office2 (Ubuntu 24.04 LTS, Tailscale-accessible), OpenClaw as orchestration engine, Vikunja as task store and UI, and an Obsidian vault as the knowledge store. Every design decision should measurably support that operating model.

## Design Principle: Self-Documenting and Self-Discoverable

This system is built by a solo operator who sets direction and makes judgment calls but is not a system architect or software developer. Professional-grade design comes from AI systems with access to relevant models — Claude Code, Claude Desktop, and other AI agents that read the repo, reason about it, and implement what Kent directs. This development model only works if the system can explain itself.

**Self-documenting** means every design choice, operational constraint, and past decision is captured in the repo in a form that is both human-readable and machine-parseable. When an AI agent starts a fresh session with nothing but `git clone` and `CLAUDE.md`, it must be able to understand the system's architecture, current state, constraints, and open decisions within minutes — not hours of conversation. This is not optional polish; it is a hard prerequisite for the development model to function at all.

**Self-discoverable** means the system's structure actively guides exploration. An agent should not need to be told where to look — the documentation map (`docs/INDEX.md`), the architecture JSON store (`docs/design/architecture/data/`), the issue queue, the charter, the Felix Constitution, and `CLAUDE.md` itself form a network of cross-references that an unfamiliar agent can navigate to find what it needs. Dead-end paths (undocumented services, unregistered agents, config files with no rationale) are system defects, not acceptable shortcuts. If a component exists but can't be found by reading the repo, it effectively doesn't exist for development purposes.

**Why this matters:**

1. **Blind-spot compensation.** Kent sets direction but is not a system architect or software developer. The system must be clear enough that AI agents can identify design risks, catch inconsistencies, and propose improvements without being told what to look for. Complete docs with current rationale are how a non-expert operator gets expert-quality reasoning from AI partners.

2. **Continuity across sessions.** Every Claude Code session starts cold. There is no persistent memory beyond what the repo, `CLAUDE.md`, agent memory files, and the issue queue contain. Self-documentation turns disconnected sessions into a coherent, cumulative engineering effort.

3. **Leverage through delegation.** The business intent (see Intent above) is to build an extensible team of AI specialists. That team can only function if each specialist can orient itself quickly — finding the relevant architecture docs, service inventory, change-risk tier, deploy pattern, agent workspace layout, and Felix Constitution constraints without being hand-walked through it.

4. **Design quality by proxy.** When the system's docs are complete and accurate, AI agents can apply solid design principles (separation of concerns, defense in depth, fail-loud-not-silent, idempotency) because they have the context to reason about tradeoffs. When docs are incomplete or stale, agents make assumptions — and assumptions become integration bugs.

**All existing doc-sync rules, architecture JSON conventions, change-control protocols, and runbooks exist to serve this principle.** They are not bureaucratic overhead. They are the mechanism by which a non-architect operator gets architect-quality reasoning from AI partners.

**Rationale belongs in docs; decision history belongs in ADRs.** Current state and *why it works this way* must be visible in the repo. *How we got here* (which missions motivated a rule, what alternatives were considered) belongs in GitHub issues and Architecture Decision Records, referenced by number but not inlined. Keep the docs optimized for a cold-start reader who needs to act, not a historian who needs to reconstruct.

**Standing obligation:** Any work that creates a new service, agent, script, cron job, data flow, or operational pattern MUST leave behind enough documentation for a cold-start AI session to discover, understand, and safely modify it. "It works" is not sufficient; "it works and the next agent can find it, understand why, and change it safely" is the bar.

## Two Constitutions — Don't Conflate

This project has two distinct governance artifacts. Both exist intentionally:

| Artifact | Purpose | Location |
|---|---|---|
| **This charter** (`.kittify/charter/charter.md`) | spec-kitty workflow governance: testing, quality gates, branching, deploy constraints, change-risk tiers. Injected into agent prompts at every workflow step. | `.kittify/charter/charter.md` |
| **Felix Constitution** (`docs/constitution/FELIX-CONSTITUTION.md`) | Felix agent governance: autonomy levels, privacy boundaries, agent registry, "Constitutional Compliance" directives in func-specs. | `docs/constitution/FELIX-CONSTITUTION.md` |

Neither replaces the other. Spec-kitty cares about the charter; Felix agents care about the Felix Constitution. Changes to one do not automatically propagate to the other — verify both when a change touches both layers.

## Testing Standards

- **Doc validation (mandatory in CI)**: every push to `main` runs `python tooling/scripts/validate_docs.py` which enforces YAML frontmatter compliance + secret scan. Violations fail the build.
- **Python unit tests (pytest, scope-dependent)**: any non-trivial Python helper or script MUST ship with pytest coverage for its core behaviors before merge. Trivial one-shot scripts may ship without tests if their contract fits on one screen.
- **Test fixtures must mirror real inputs**: fixtures must be sampled from real file structures, not invented. If the code processes Obsidian vault files, the fixtures should come from actual vault files (e.g., with real frontmatter shapes, encoding, and whitespace patterns).
- **No formal coverage target yet**: pragma-driven. Add tests where the cost of a regression is high; skip where the behavior is obvious and one-shot.
- **Integration verification is mandatory before `for_review`**: a module with passing unit tests but no live callers is NOT implemented. Grep for callers. Verify dead code does not ship.

## Quality Gates

- **CI validation passes** (`validate_docs.py`: frontmatter compliance + secret scan) on every push to `main`.
- **Self-review of diff** before push. Diff review catches accidental inclusion of unrelated changes, secrets, or scope creep.
- **Spec-kitty review phase** is the in-workflow quality gate for missions; use it rigorously, do not rubber-stamp.
- **Integration gate (WP05-equivalent)**: any mission that touches deployed services MUST have an explicit integration verification work package that exercises the real environment. Unit tests and dry-runs are necessary but not sufficient; live smoke tests against real service state catch a class of bugs that nothing else does.

## Performance Benchmarks

- Inbox processing completes within 60 seconds of cron trigger.
- WhatsApp command responses within 10 seconds of inbound message.
- CI validation under 30 seconds end-to-end.
- Heartbeat schedules fire on time (no silent cron skips).
- **Empty-run inbox cost**: ≤500 agent `output_tokens` per cron run when the inbox has zero unprocessed files. The pre-scan helper pattern is authoritative; deviation requires a new mission.

## Branch Strategy

- **Solo maintainer project.** Push directly to `main` for routine changes. Use feature branches when genuinely useful (complex multi-step work, experiments, long-running parallel efforts).
- **No PR requirement.** Spec-kitty's review phase serves as the quality gate. When a change would benefit from a second perspective, use Claude Code or Claude Desktop as the architectural review partner before merging.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `refactor:`. Append `[doc-audit]` to maintenance commits that change behavior without going through the issue queue.
- **Merge commits, not PRs, for spec-kitty missions**: spec-kitty merges go directly to `main` as merge commits. Any GitHub Action that triggers on `pull_request` will not fire on these merges. Design automation triggers accordingly.
- **Sparse-checkout staleness recovery is mandatory after every `spec-kitty merge`**: phantom staged deletions appear after merge due to a known spec-kitty bug (Priivacy-ai/spec-kitty#588). Always run `git status` immediately after merge and apply the recovery recipe (unstage + checkout from HEAD) before any follow-up commits.

## Deployment Constraints

- **Production services run on office2** (Ubuntu 24.04 LTS). Mac is authoring only.
- **Target Linux by default.** All scripts and configs assume Linux unless explicitly noted. No Windows support. No Dropbox coordination.
- **Tailscale-only service exposure.** Vikunja, OpenClaw, and any other management port is Tailscale-internal. Never expose to the public internet.
- **Every feature that deploys code, agents, skills, or scheduled services to office2 must include a deploy script** at `scripts/deploy/deploy-f{NNN}.sh` (or mission-slug equivalent). See `docs/runbooks/deployment.md` for the established pattern.
- **Deploy scripts follow the strict-order-of-operations safe-deploy pattern**: pre-flight (Restic age, reachability, source presence) → copy artifacts → verify artifacts → edit config (e.g., `openclaw cron edit`) → post-flight smoke test. Each step halts on error. Rollback is manual, not automatic; the wrapper prints recovery instructions.
- **No cron pause/resume required** if the deploy order is strict: artifacts first, then config. The worst-case mid-deploy cron fire runs legacy behavior harmlessly.
- **System crontab is never used** for openclaw-managed cron jobs. All cron operations go through `openclaw cron list/edit/run/runs`. Mixing the two causes silent failures (see kentonium3/kg-automation#162).
- **Deploy targets must match the real service paths**, not inferred paths. Always read `/home/claude/.openclaw/openclaw.json` for `workspace` and `agentDir` before committing to a target path. Repo-side `.tmpl` paths and office2-side workspace paths are often different.
- **Tier 2 pre-flight requires a Restic backup ≤24h old**. The `claude` user currently cannot query snapshots directly due to file permissions; operators can confirm via the backup log at `/data/services/backup/logs/backup-YYYY-MM-DD.log` and deploy wrappers should accept a `--backup-confirmed` operator-ack flag as an explicit attestation path.

## Change-Risk Taxonomy (Tier Protocol)

Every change is classified by a 5-tier risk model. Before editing or deploying, identify the tier and follow the protocol. Full definitions in `docs/design/architecture/data/change-risk-taxonomy.json` and `docs/runbooks/governance/pre-flight-checklist.md`.

| Tier | Scope | Required Protocol |
|---|---|---|
| **Tier 0** — Hard Lock | Host-level (UFW, iptables, sshd, sudoers, kernel params, chmod/chown on system files) | **Claude Code never executes directly.** Generate the script, present to Kent for manual `ssh office2-kgale` run. Absolute. Cannot be overridden. |
| **Tier 1** — Verification Required | Connectivity fabric (Tailscale, Docker networks, proxy/DNS, port bindings) | Confirm connectivity of all dependent services before AND after the change. Follow pre-flight + post-flight checklists. |
| **Tier 2** — Snapshot Required | Application state (DB schemas, service env files, Docker Compose, application config, openclaw cron payloads) | Confirm recent Restic snapshot ≤24h. Trigger one if missing. Follow Tier 2 checklist. |
| **Tier 3** — Standard | Logic/workflow (Python scripts, agent prompts, cron schedules) | Proceed with dry-run or sandbox validation. No pre-flight checklist. |
| **Tier 4** — Auto-Commit | Schema/metadata (CLAUDE.md, READMEs, comments, frontmatter, logging) | Full autonomy. No pre-flight or verification required. |

## Rebaseline Obligation (Audited Surfaces, #557)

Separate from the tier-based protocol above, **any** change that touches an **audited surface** triggers a rebaseline obligation: the security-monitor baselines on office2 must be reset after the change deploys, otherwise the daily 3 AM audit alerts as drift. This applies regardless of tier — a Tier 4 prompt edit that touches an OpenClaw agent's `AGENTS.md` triggers the same obligation as a Tier 2 docker-compose change.

**Authoritative list of audited surfaces**: `docs/design/architecture/data/audited-surfaces.json` (6 surface classes as of 2026-06-10: openclaw agent prompts, openclaw config, systemd user units + deploy scripts, Python dependency manifests, Docker stack files, committed SSH key material).

**Reset procedure**: `docs/runbooks/security-baseline-ops.md` (canonical command + verification).

**Mission-end obligation**: For any spec-kitty mission whose Architecture Impact section includes a change class that maps to an audited surface, the merge commit message (or a comment on the closing issue) must record one of:

- `Rebaseline: completed at <ISO-8601 UTC>` (with verification output if practical), OR
- `Rebaseline: not required — <one-line justification>` (e.g., "change is doc-only, no deployed-state effect")

Missing or vague rebaseline notes are a spec-kitty review-cycle defect. The reviewer should reject with `--review-feedback-file` citing the missing record. The acceptance gate (`spec-kitty accept`) is a soft-reminder surface that flags this concern; the merge commit is the authoritative record.

**Pre-merge reminder surfaces** (informational, not a hard gate):

- `.github/workflows/audited-surface-reminder.yml` annotates PRs/pushes touching audited-surface paths with `::warning::`
- `tooling/scripts/check_audited_surface_drift.py` can be run locally before push or merge to preview the same warnings

The operator is responsible for actually running the reset command on office2. Neither CI nor the charter can perform the reset itself.

## Governance Activation

```yaml
mission: software-dev
selected_paradigms: [c4-incremental-detail-modeling]
selected_directives:
  - DIRECTIVE_001   # Architectural Integrity Standard — separation of concerns, well-defined boundaries
  - DIRECTIVE_003   # Decision Documentation Requirement — capture decisions with rationale (→ ADRs)
  - DIRECTIVE_010   # Specification Fidelity Requirement — implementation faithful to approved specs
  - DIRECTIVE_024   # Locality of Change — changes stay close to the problem, reduce blast radius
  - DIRECTIVE_031   # Context-Aware Design — explicit bounded-context awareness, probe real state
  - DIRECTIVE_033   # Targeted Staging Policy — only stage/commit what the current WP owns
  - DIRECTIVE_034   # Test-First Development — test-first across acceptance and implementation layers
# available_tools is constrained to spec-kitty's built-in registry (spec-kitty, git, python, pytest,
# ruff, mypy, uv). The project also uses bash, docker, docker-compose, ssh, systemctl, gh, curl,
# tailscale, mermaid, openclaw, restic, rsync, and jq — but listing them here causes a governance
# resolution failure because they aren't in spec-kitty's DEFAULT_TOOL_REGISTRY. The full tool list
# is documented in the Policy Summary section instead.
available_tools: [git, python, spec-kitty, pytest]
template_set: software-dev-default
```

## Policy Summary

- **Intent**: Drive accountable action on personal and business goals through always-on automation, frictionless capture, and proactive follow-up.
- **Languages/Frameworks**: Python 3.11+, Bash, Docker, YAML/Markdown docs. Vikunja REST API, Anthropic Claude API direct (no proxies), OpenClaw skills. Obsidian for knowledge store.
- **Testing**: doc validation via `validate_docs.py` in CI (mandatory); pytest for non-trivial Python helpers (encouraged, not enforced); integration verification before `for_review` (mandatory). Fixtures must mirror real inputs.
- **Quality Gates**: CI validation on every push; self-review of diff; spec-kitty review phase; mandatory integration gate for deployed services.
- **Review Policy**: solo maintainer, push directly to main. Use Claude Code or Claude Desktop as architectural partner for cross-cutting changes. No PR requirement.
- **Performance Targets**: inbox 60s, WhatsApp 10s, CI 30s, heartbeats on time, empty-run inbox ≤500 output tokens.
- **Deployment Constraints**: office2-only, Tailscale-only, deploy script required, strict-order-of-operations safe-deploy pattern, no system crontab, Tier 2 requires Restic ≤24h.
- **Documentation Policy**: YAML frontmatter required on all markdown; architecture decisions in `docs/design/`; feature specs via GitHub issues + spec-kitty missions (historical archive in `docs/func-spec/`); conventional commits; update docs when behavior changes; JSON files are authoritative, markdown views follow.
- **Risk Boundaries**: `~/second-brain/notes/04-Growth/_private/` is the constitutional hard limit — never read, written, referenced, or logged by any agent or script. No credentials in code or committed files. Anthropic API called direct. No community OpenClaw skills without source review. All services Tailscale-only. No untrusted code runs near credentials or personal data.
- **Amendment Process**: edit `charter.md` directly, run `spec-kitty charter sync`, commit and push. Review the diff to confirm derived files reflect intent.
- **Exception Policy**: exceptions documented with rationale, scope, and expiration. Hard boundaries (privacy, credentials, agent traceability) cannot be excepted.

## Project Directives

1. **Apply the `DIRECTIVE_034` doctrine directive** (c4-incremental-detail-modeling) to planning and implementation. Stage spec → plan → research → data-model → tasks → implementation, each layer adding concrete detail to the layer above. Avoid premature detail; avoid terminal vagueness.

2. **Respect privacy and security hard boundaries.**
   - `~/second-brain/notes/04-Growth/_private/` is never read, written, referenced, or logged by any agent or script. No exceptions.
   - No credentials in code or committed files. Anthropic API called direct — no third-party proxies.
   - No community OpenClaw skills without source review.
   - All services Tailscale-only — never exposed to public internet.
   - No untrusted code executes near credentials or personal data.
   - The `claude` user on office2 does not have sudo. Tier 0 actions are operator-only.

3. **Keep documentation synchronized with workflow and behavior changes.**
   - Any feature that changes deployed services, credentials, data flows, or network topology MUST update the relevant files in `docs/design/architecture/` and `docs/design/architecture/data/` in the SAME commit.
   - This is not optional and not a separate task — it is a mandatory deliverable of every such mission.

4. **Follow documentation standards.**
   - Machine-readable files (JSON) are the authoritative record for operational data.
   - Narrative markdown documents provide context and rationale.
   - Diagrams (Mermaid `.view.md` files) are the preferred format for system structure, service dependencies, data flows, and network topology.
   - When machine-readable and narrative conflict, JSON wins.

5. **Every mission specification must include an explicit documentation-synchronization requirement** covering architecture JSON, markdown views, runbooks, INDEX, and roadmap status as applicable.

6. **Probe the real environment during design phase.**
   - During `/spec-kitty.specify` and `/spec-kitty.plan`, when an assumption touches "how office2 / OpenClaw / the vault actually behaves", run a cheap live probe before committing the assumption to the spec.
   - Load-bearing assumptions must be verified, not inferred from repo state or docs.
   - Budget design-phase research as real planning activity, not overhead.
   - Probe checklist: `openclaw cron list/edit --help`, `cat openclaw.json`, `ls -la <target>`, `touch <target>/.probe` for writability, `head <real-file> | od -c` for real byte patterns.
   - When probes reveal gaps in repo docs, flag them — file a fix in the same mission.

## Reference Index

| Reference ID | Kind | Summary | Local Doc |
|---|---|---|---|
| `USER:PROJECT_PROFILE` | user_profile | Project-specific interview answers captured for charter compilation. | `library/user-project-profile.md` |
| `PARADIGM:c4-incremental-detail-modeling` | paradigm | Stage design from high-level intent to concrete implementation, each layer adding detail to the previous. | `library/paradigm-c4-incremental-detail-modeling.md` |
| `DIRECTIVE:DIRECTIVE_034` | directive | Apply c4-incremental-detail-modeling to planning and implementation decisions. | `library/directive-034.md` |
| `TEMPLATE_SET:software-dev-default` | template_set | Build high-quality software with structured workflows and staged design detail. | `library/template-set-software-dev-default.md` |
| `STYLEGUIDE:python-implementation` | styleguide | Python implementation style for this project. | `library/styleguide-python-implementation.md` |
| `RUNBOOK:deployment` | runbook | Deploy script pattern, SSH host alias setup, per-resource deployment procedures for office2. | `docs/runbooks/deployment.md` |
| `RUNBOOK:pre-flight-checklist` | runbook | Tier-aware pre-flight checklist for all change-risk tiers. | `docs/runbooks/governance/pre-flight-checklist.md` |
| `RUNBOOK:post-change-verification` | runbook | Post-change verification steps by tier. | `docs/runbooks/governance/post-change-verification.md` |
| `DATA:change-risk-taxonomy` | data | Authoritative JSON definition of the 5-tier risk model. | `docs/design/architecture/data/change-risk-taxonomy.json` |
| `DOC:FELIX-CONSTITUTION` | companion_governance | Separate governance doc for Felix agent autonomy levels, privacy, directives. Not managed by spec-kitty. | `docs/constitution/FELIX-CONSTITUTION.md` |

## Amendment Process

1. Edit `.kittify/charter/charter.md` directly.
2. Run `spec-kitty charter sync` to regenerate derived YAML files (`governance.yaml`, `directives.yaml`, `metadata.yaml`, `references.yaml`).
3. Review the resulting diff to confirm derived files reflect intent.
4. Commit and push.
5. Verify new content is picked up by running `spec-kitty charter context --action specify --json` and inspecting the returned text.

If spec-kitty's sync step rejects the edit (schema violation, missing section), diagnose against the charter command's error message rather than fighting the tool. Prefer fixing the charter content over bypassing sync.

## Exception Policy

Exceptions to architecture and security policies must be documented with rationale, scope, and expiration. Record exceptions in `docs/design/architecture/security-posture.md` under "Policy Exceptions" and in the feature spec (or GitHub issue) that introduces them.

**Required fields for each exception:**
- **Constraint**: Which policy is being excepted.
- **Rationale**: Why the exception is necessary.
- **Scope**: What the exception covers and its boundaries.
- **Expiration**: When the exception expires, or "no expiration" with explicit justification.
- **Feature / Issue**: Which mission or issue introduced the exception.
- **Review trigger**: What condition should cause the exception to be re-evaluated.

**Hard boundaries (no exceptions):**
- Privacy boundary: `~/second-brain/notes/04-Growth/_private/` inviolable.
- Credential-in-code prohibition.
- Agent traceability: all agent actions must be traceable to the `claude` user on office2.
- Tier 0 host-level changes: never executed directly by Claude Code regardless of urgency or explicit instruction.
