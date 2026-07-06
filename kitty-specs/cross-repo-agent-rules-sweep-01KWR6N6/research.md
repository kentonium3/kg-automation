# Research: Cross-Repo Standing Rules Sweep

## Decision 1: Promote Only Universal Short Rules

**Decision**: A candidate belongs in `.agents/rules/cross-repo-standing-rules.md`
only when it applies in every repository, is short enough for always-on context,
and would create real behavioral risk if absent from another repo session.

**Rationale**: The original #649 failure was an agent missing global behavioral
rules in another repository. The fix should target that failure mode without
turning global context into a copy of kg-automation runbooks.

**Alternatives considered**:

- Copy whole runbook sections into the global file. Rejected because it bloats
  always-on context and creates drift against canonical runbooks.
- Keep all rules local and rely on agents to discover them. Rejected because it
  preserves the cross-repo invisibility failure.

## Decision 2: Use Explicit Candidate Classifications

**Decision**: Each high-signal candidate should be classified as one of:

- `promote`: universal, short, and not already represented
- `link-only`: universal but procedural or long
- `already-represented`: existing standing-rule coverage is sufficient
- `repo-specific`: applies only to kg-automation or office2
- `agent-specific`: applies only to one deployed agent or role
- `unclear`: needs Kent judgment; do not promote silently

**Rationale**: Classification makes non-promotions reviewable and keeps the
implementation from becoming subjective prose cleanup.

**Alternatives considered**:

- Edit directly from grep findings. Rejected because it makes review harder and
  risks promoting local operational assumptions globally.

## Decision 3: Stale Spec-Kitty Bug-Reporting Wording Is In Scope

**Decision**: The standing-rules file should be checked against
`docs/runbooks/spec-kitty-bug-reporting.md`, especially the v1.3 flow that embeds
the upstream draft in the internal issue instead of generating a separate paste
file.

**Rationale**: The current standing-rules file links the runbook but still says
to generate a slim external upstream report. If that wording implies the
deprecated paste-file flow, it undermines the global rule.

**Alternatives considered**:

- Leave the detail to the runbook. Rejected if the standing-rule summary is
  misleading; short summaries must still point agents in the right direction.

## Candidate Source Surfaces

Minimum sweep surfaces:

- `CLAUDE.md`
- `CODEX.md`
- `AGENTS.md`
- `.agents/rules/`
- `docs/runbooks/spec-kitty-bug-reporting.md`
- `docs/constitution/FELIX-CONSTITUTION.md`
- `scripts/openclaw/agents/**/{AGENTS.md,SOUL.md,TOOLS.md}`

Optional bounded surfaces when findings point there:

- `docs/diagnostics/*spec-kitty*`
- `.github/ISSUE_TEMPLATE/spec-kitty-bug.md`

Forbidden or excluded surfaces:

- `~/second-brain/notes/04-Growth/_private/`
- `.kittify/` and unrelated existing `kitty-specs/` mission state
- Global `~/.claude/CLAUDE.md` unless explicitly approved

## Suggested Search Patterns

Use focused, bounded searches:

```bash
rg -n "public post|copy approval|@mentions|dual-track|upstream|standing rules|universal|never .*CLAUDE|private|community skill|approval" CLAUDE.md CODEX.md AGENTS.md .agents docs scripts/openclaw/agents -g '*.md'
```

Then use line-range reads for each candidate rather than rereading whole files.
