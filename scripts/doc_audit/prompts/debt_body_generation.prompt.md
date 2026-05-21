---
name: debt_body_generation
version: 0.1.0
last_updated: 2026-05-20
inherits_classification_from: scripts/openclaw/skills/doc-audit/SKILL.md §8
---

# Docs-Debt Body Generation — Boilerplate (cached)

[CACHE_PREFIX_START]

You compose the **body** of a docs-debt GitHub issue. The driver
opens the issue with the title and labels; you produce only the body
markdown.

## SKILL.md §8 — Docs-Debt Issue Template

For each judgment gap and missing artifact, create one issue using
`.github/ISSUE_TEMPLATE/docs-debt.md`. Populate **all six** sections:

1. **Artifact** — repo-relative path to the doc (existing or proposed).
2. **Gap description** — what's missing/outdated/incorrect, specifically.
3. **Area** — checked items match the audit issue's `area/*` labels.
4. **Cross-references** — `Refs #<audit-issue-number>` plus links to
   related docs and commits.
5. **Draft outline** — **the load-bearing field**. Specific enough that a
   downstream Claude Code session can act on it without further research.
   This is the FR-003 success criterion (SC-003): if a downstream session
   needs a separate research pass before writing the fix, the outline was
   not specific enough.
6. **Success criteria** — 2–4 verifiable bullet points.

Apply labels: `P2-debt`, the matching `area/*` label(s), and `type/debt`.

**Special case `area/biz-ops`** (per spec C-006): the driver prefixes
the title with `Docs (biz-ops): ` and adds a body line:
> ⚠ Human confirmation required before action — biz-ops docs may be
> intentionally private or informal.

**One issue per gap** — never bundle. Bundling dilutes the draft outline.

## Output schema

Return structured markdown with **exactly these six H2 headers** in order:

```markdown
## Artifact
<repo-relative path>

## Gap description
<2-4 sentences explaining what is missing/outdated/incorrect>

## Area
- [x] area/<label>

## Cross-references
- Refs #<audit-issue-number> (originating audit)
- <any additional refs>

## Draft outline
<the LOAD-BEARING section — specific enough that a downstream Claude Code
session can act on it without further research. SKILL.md §8 SC-003.>

## Success criteria
- [ ] <verifiable bullet 1>
- [ ] <verifiable bullet 2>
- [ ] <verifiable bullet 3>
```

No prose before the first H2. No content outside these six sections.

## Worked example (SKILL.md §11 Example C)

**Inputs:**
- artifact_path: docs/runbooks/openclaw-agent-setup.md
- gap_description: The runbook's "Choosing a Model" section pre-dates
  model tiering and does not reflect the new Pinned/Optimizable
  distinction.
- evidence_source: mission 021 plan + AGENT-REGISTRY.md Model
  Assignment Policy
- area_labels: ["area/felix-core"]
- originating_audit_number: 320
- cross_references: ["#135", "#225"]

**Output:**

```markdown
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
The "Choosing a Model" section pre-dates the model-tiering work
delivered in mission 021. It lacks the Pinned vs Optimizable
distinction, the rationale for each, and a worked example showing how
to pick a tier for a new agent. New agent authors hitting this section
today will not have enough guidance to make the right call.

## Area
- [x] area/felix-core

## Cross-references
- Refs #320 (originating audit)
- #135, #225

## Draft outline
Insert a new subsection "Choosing a Model Tier" between "Choosing an
Agent Name" and the verification checklist. Cover:
1. Pinned vs Optimizable definitions (1-2 sentences each, cite the
   Model Assignment Policy in AGENT-REGISTRY.md).
2. When to choose Pinned: judgment-heavy work where regression risk
   from model swaps is unacceptable. Example: felix-doc-auditor (this
   agent itself).
3. When to choose Optimizable: routine work where cost matters more
   than per-call consistency. Example: felix-admin-inbox capture.
4. Cross-link to the policy section in AGENT-REGISTRY.md.

## Success criteria
- [ ] New "Choosing a Model Tier" subsection appears in the runbook
- [ ] Both Pinned and Optimizable have at least one named example
- [ ] AGENT-REGISTRY.md Model Assignment Policy is cross-linked
```

Notice how the Draft outline is **specific** — a downstream session
can write the new subsection without a separate research pass. This is
the load-bearing field.

[CACHE_PREFIX_END]

# Per-call inputs

## Artifact path
{{artifact_path}}

## Gap description (2-4 sentences)
{{gap_description}}

## Evidence source
{{evidence_source}}

## Area labels (apply to ## Area section)
{{area_labels}}

## Originating audit number (use in Cross-references)
{{originating_audit_number}}

## Additional cross-references (beyond the audit)
{{cross_references}}

---

Produce the issue body in markdown. Include all 6 H2 sections. The
"Draft outline" section is the most important — make it specific
enough that a downstream Claude Code session can act without further
research.
