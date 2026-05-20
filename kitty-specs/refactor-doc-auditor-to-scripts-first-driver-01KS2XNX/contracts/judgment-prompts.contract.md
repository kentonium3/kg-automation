# Contract: LLM Judgment Prompt I/O

**Mission**: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
**Realizes**: spec FR-002, FR-011, NFR-005; research.md D12
**Applies to**: each of three judgment moments (per Q2=C)

This contract defines the input shape, prompt-template layout, response schema, and audit/reviewability requirements for each LLM judgment call the driver makes.

## Common contract — applies to all three judgment moments

### Template structure (cache-aware)

Every prompt template file in `scripts/doc_audit/prompts/*.prompt.md` has this layout:

```
---
name: <moment_name>
version: 0.1.0
last_updated: 2026-MM-DD
inherits_classification_from: scripts/openclaw/skills/doc-audit/SKILL.md §<section>
---

# <Moment Name> — Boilerplate (cached)

[CACHE_PREFIX_START]

<rule recap — verbatim summary of the relevant SKILL.md section>

<output schema — concrete JSON or markdown shape the LLM must produce>

<illustrative example I/O (1-2 samples)>

[CACHE_PREFIX_END]

# Per-call inputs

{{variable_section}}
```

The `[CACHE_PREFIX_*]` markers delineate the cached portion. At runtime, the driver passes a single `cache_control: {"type": "ephemeral"}` block on the message that contains the cached prefix.

### Driver-side wrapping

For each judgment call:

```python
response = anthropic_client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=...,
    system=[
        {"type": "text", "text": cached_prefix, "cache_control": {"type": "ephemeral"}}
    ],
    messages=[
        {"role": "user", "content": variable_section}
    ],
)
```

The driver reads the prompt template, splits on the cache markers, and constructs the API call accordingly. The cached prefix is invariant across calls within a tick.

### Response parsing

Each moment returns a structured response (JSON for two of three; structured markdown for the third). The driver MUST:
- Parse the response and validate against the documented schema.
- On parse failure or schema violation: log the error, demote the finding to a docs-debt issue (a safe default), and continue.
- NEVER trust LLM output without schema validation.

### Cost accounting

The driver records `input_tokens`, `cache_hit_input_tokens`, and `output_tokens` from each response, summed per tick (per `TickSignal` E-009 / contract).

---

## Moment 1: `tier_classification`

**File**: `scripts/doc_audit/prompts/tier_classification.prompt.md`

**Source of truth**: SKILL.md §4.1 (Tier A categories, Tier B categories), §4.2 (judgment categories), §4.3 (constitutional guardrails).

### Inputs

```json
{
  "proposed_edit": {
    "doc_path": "docs/design/architecture/data/service-inventory.json",
    "change_type": "frontmatter_field_bump",
    "current_value": "2026-05-15",
    "proposed_value": "2026-05-20",
    "evidence_source": "audit issue triggering commit a5d7af05"
  },
  "audit_area_labels": ["area/felix-core"],
  "doc_frontmatter_excerpt": "...up to 50 lines of frontmatter around the edit site...",
  "guardrail_check_result": "not_guardrailed"
}
```

`guardrail_check_result` is determined deterministically by the driver BEFORE the LLM call (path matching against §4.3 list). If guardrailed, the driver short-circuits to JUDGMENT without invoking the LLM.

### Output schema

```json
{
  "tier": "tier_a" | "tier_b" | "judgment",
  "rationale": "<one-line explanation>"
}
```

### Cache-prefix content

- Verbatim text of SKILL.md §4.1.a (Tier A categories 1, 4)
- Verbatim text of SKILL.md §4.1.b (Tier B categories 2, 3, 5, 6, 7)
- Verbatim text of SKILL.md §4.2 (judgment categories)
- One example per tier (per SKILL.md §11 Examples A, D for Tier A and B; one synthesized for judgment)

### Failure modes

- LLM returns invalid JSON → driver treats as `judgment`, files debt.
- LLM returns `tier_a` for a guardrailed path → defense-in-depth check (the driver re-checks guardrail before applying); always demoted.

---

## Moment 2: `debt_body_generation`

**File**: `scripts/doc_audit/prompts/debt_body_generation.prompt.md`

**Source of truth**: SKILL.md §8 (debt-issue template with all 6 sections).

### Inputs

```json
{
  "artifact_path": "docs/runbooks/openclaw-agent-setup.md",
  "gap_description": "Section 'Choosing a Model' pre-dates model-tiering work and lacks the Pinned/Optimizable distinction.",
  "evidence_source": "Mission 021 plan + agent-registry Model Assignment Policy",
  "area_labels": ["area/felix-core"],
  "originating_audit_number": 320,
  "cross_references": ["#135", "#225"]
}
```

### Output schema (markdown, not JSON)

```markdown
## Artifact
docs/runbooks/openclaw-agent-setup.md

## Gap description
<2-4 sentences>

## Area
- [x] area/felix-core

## Cross-references
- Refs #320 (originating audit)
- #135, #225

## Draft outline
<the LOAD-BEARING section — specific enough that a downstream Claude Code
session can act on it without further research. SKILL.md §8 SC-003.>

## Success criteria
- [ ] <verifiable bullet 1>
- [ ] <verifiable bullet 2>
- [ ] <verifiable bullet 3>
```

### Driver-side handling

- Parse the markdown headers to ensure all 6 sections are present.
- On missing section: log error, file the debt issue ANYWAY with a stub for the missing section + a note that the LLM output was incomplete. The empty section becomes a follow-up flag.
- For `area/biz-ops` audits: prefix the title with `Docs (biz-ops):` and inject the SKILL.md §8 confirmation-required line.

### Cache-prefix content

- Verbatim SKILL.md §8 template requirements (the 6 sections explained)
- One worked example from SKILL.md §11 Example C (prose rewrite needed → docs-debt)

---

## Moment 3: `cross_file_implication`

**File**: `scripts/doc_audit/prompts/cross_file_implication.prompt.md`

**Source of truth**: SKILL.md §4.2 #5 (interpretation-of-intent) + §5 (comparison rules) + signal-to-doc-map.json (for drift-event-triggered audits).

### Inputs

```json
{
  "triggering_event": {
    "kind": "commit" | "drift_event",
    "summary": "<one-line summary>",
    "diff_excerpt": "<up to 300 lines of relevant diff>"
  },
  "touched_files": ["docs/design/architecture/data/service-inventory.json"],
  "in_scope_files": [
    "docs/design/architecture/service-inventory.md",
    "docs/design/architecture/data/network-topology.json",
    "docs/runbooks/openclaw-agent-setup.md",
    "..."
  ],
  "domain_labels": ["area/felix-core"]
}
```

The driver pre-resolves `in_scope_files` via the domain map; the LLM receives only the path list (not the file contents), to keep context small.

### Output schema

```json
{
  "implications": [
    {
      "untouched_file": "docs/runbooks/openclaw-agent-setup.md",
      "implication": "<2-3 sentences explaining the likely drift>",
      "evidence": "<which part of the triggering event suggests it>",
      "suggested_action": "judgment"
    }
  ]
}
```

If no implications are detected: `implications: []`. The driver consumes the implications list to file debt issues for any non-empty entries (with `suggested_action == judgment` always — these are not auto-edits).

### Cache-prefix content

- Verbatim SKILL.md §4.2 #5 (interpretation-of-intent rules)
- The signal-to-doc-map.json mappings (for drift-event signals — when one ships, the LLM knows which doc surfaces are typically affected)
- One worked example showing a non-touched doc with implied drift

---

## Reviewability checklist (FR-011, NFR-005)

A reviewer reading the three `.prompt.md` files alone MUST be able to answer:

- [ ] What is the LLM asked at each judgment moment?
- [ ] What information does the LLM receive (and what does it NOT receive)?
- [ ] What response shape is expected?
- [ ] How does the driver handle malformed responses?
- [ ] Which SKILL.md sections inform each prompt?

The driver's source files SHOULD link back to the prompt artifact for each call site.

## Versioning

Each prompt template carries a `version` field in its frontmatter. Bump on any text change. Driver logs the version with each call so post-hoc analysis can correlate behavior with prompt revisions.
