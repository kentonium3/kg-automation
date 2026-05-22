# Contract: LLM output JSON schema

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Surface**: Moment 0 drift_interpretation LLM output

Strict JSON. Three valid output shapes. Any deviation triggers `DriftInterpretationError` and the retry policy (D6).

---

## Shape 1 — PROPOSED_EDIT

```json
{
  "verdict": "PROPOSED_EDIT",
  "confidence": 0.85,
  "rationale": "service-inventory.json doesn't list the new cron entry that audit.sh detected in openclaw.json. Proposing to add it.",
  "proposed_edit": {
    "doc_path": "docs/design/architecture/data/service-inventory.json",
    "current_value": "...existing JSON block...",
    "proposed_value": "...updated JSON block with new cron entry...",
    "rationale_detail": "The drift adds a new systemd dropin file 'foo.conf'. service-inventory.json's openclaw section enumerates active dropins; add an entry mirroring the deployed file."
  }
}
```

### Required keys

- `verdict` (string, exactly `"PROPOSED_EDIT"`)
- `confidence` (float, [0.0, 1.0])
- `rationale` (string, non-empty)
- `proposed_edit` (object) containing:
  - `doc_path` (string, must be in the input `doc_targets[].path` list)
  - `current_value` (string)
  - `proposed_value` (string)

### Optional keys

- `proposed_edit.rationale_detail` (string) — richer context for the operator if escalated

---

## Shape 2 — JUDGMENT_REQUIRED

```json
{
  "verdict": "JUDGMENT_REQUIRED",
  "confidence": 0.55,
  "rationale": "The diff modifies a config field that may or may not be tracked in the target docs. Cannot determine without knowing operator intent.",
  "question": "The openclaw.json drift adds a new top-level field `deliveryMode` on each cron entry. Should this field be added to the schema of service-inventory.json's openclaw section, or is the change in openclaw.json unintentional?"
}
```

### Required keys

- `verdict` (string, exactly `"JUDGMENT_REQUIRED"`)
- `confidence` (float, [0.0, 1.0])
- `rationale` (string, non-empty)
- `question` (string, non-empty, ≤500 chars — should be specific and actionable)

### Optional keys

None.

---

## Shape 3 — NO_CHANGE_NEEDED

```json
{
  "verdict": "NO_CHANGE_NEEDED",
  "confidence": 0.90,
  "rationale": "service-inventory.json does not track the `deliveryMode` field on cron entries. The drift in openclaw.json is correct system state but not within the documentation scope."
}
```

### Required keys

- `verdict` (string, exactly `"NO_CHANGE_NEEDED"`)
- `confidence` (float, [0.0, 1.0])
- `rationale` (string, non-empty — must explain WHY no change is needed)

### Optional keys

None.

---

## Validation rules (caller-side defense-in-depth)

The Python parser in `drift_interpretation.py` MUST enforce all of these BEFORE returning a verdict:

1. **JSON parses** — if not, demote to retry (per D6); after 3 retries, raise `DriftInterpretationError("invalid JSON")`
2. **`verdict` is one of** the three string values above (case-sensitive); otherwise retry
3. **`confidence` is a JSON number** in [0.0, 1.0]; otherwise retry
4. **`rationale` is a non-empty string**; otherwise retry
5. **If `verdict == "PROPOSED_EDIT"`**:
   - `proposed_edit` object MUST be present
   - `proposed_edit.doc_path`, `.current_value`, `.proposed_value` MUST be non-empty strings
   - `proposed_edit.doc_path` MUST appear in the input's `doc_targets[].path` list — if not, raise `DriftInterpretationError("out-of-set proposed doc_path")` (exit code 5; no retry — this is a semantic violation the LLM won't fix by retrying)
6. **If `verdict == "JUDGMENT_REQUIRED"`**: `question` MUST be present, non-empty, ≤500 chars
7. **If `verdict == "NO_CHANGE_NEEDED"`**: no shape-specific extra fields required
8. **Confidence demotion** (FR-005, FR-007 boundary): if `verdict ∈ {PROPOSED_EDIT, NO_CHANGE_NEEDED}` and `confidence < 0.80`, the caller (`interpret()`) returns a synthesized JUDGMENT_REQUIRED verdict with the original payload folded into rationale; this is NOT a retry

### No retry for semantic violations

Out-of-set `doc_path` is a semantic violation, not a transient one. Retrying won't fix it (the LLM keeps choosing the same out-of-set path because the prompt is the same). Exit code 5 propagates; caller files the diagnostic [doc-audit] issue immediately.

---

## Prompt-side enforcement

The system prompt MUST include:

- **Explicit JSON-only directive**: "Return STRICT JSON in one of three shapes. No commentary outside the JSON object. No code fences. No prose."
- **Whitelist of doc_path values**: at prompt assembly time, the user portion of the prompt lists the allowed doc_paths (from `doc_targets`). The system prompt reminds the model: "`proposed_edit.doc_path` MUST be one of the doc_target paths listed in the user message."
- **Examples**: 3 worked examples (one per verdict shape) using realistic but synthetic drift events.

---

## Token budget

Per D7:

| Component | Approx tokens |
|---|---|
| System prompt (cached, includes examples + schema + rules) | ~1,200 |
| User prompt (event + mapping + doc_target contents) | ≤2,000 |
| Output (verdict JSON) | ≤200 |
| **Per-call total** | **≤3,400** |

Average expected: ~1,500-2,000 tokens per call (NFR-003 budget of ≤2,000 is the AVERAGE — peak can exceed slightly without violating the NFR).

---

## Examples (for reference, not for inclusion verbatim)

### Example A: Auto-close (NO_CHANGE_NEEDED)

Input: openclaw-cron drift showing `deliveryMode: "none" → "announce"` on 7 cron entries.
Target: `service-inventory.json` (current contents show cron entries WITHOUT a deliveryMode field).
Expected output:
```json
{
  "verdict": "NO_CHANGE_NEEDED",
  "confidence": 0.92,
  "rationale": "service-inventory.json's cron entries do not include a deliveryMode field. The openclaw.json drift adds this field operationally, but it is not within the documentation scope of service-inventory.json."
}
```

### Example B: Propose edit (PROPOSED_EDIT)

Input: systemd-user-dropins drift showing a new dropin file `claude-cron-watch.conf` added to `/home/claude/.config/systemd/user/openclaw-gateway.service.d/`.
Target: `service-inventory.json` (current contents enumerate dropins for openclaw-gateway).
Expected output:
```json
{
  "verdict": "PROPOSED_EDIT",
  "confidence": 0.88,
  "rationale": "service-inventory.json enumerates active dropins under openclaw-gateway. The new file claude-cron-watch.conf is missing; propose adding it.",
  "proposed_edit": {
    "doc_path": "docs/design/architecture/data/service-inventory.json",
    "current_value": "...existing dropins block...",
    "proposed_value": "...updated dropins block with claude-cron-watch.conf entry..."
  }
}
```

### Example C: Escalate (JUDGMENT_REQUIRED)

Input: openclaw.json hash drift with no obvious correspondence to inventory fields.
Target: `service-inventory.json`.
Expected output:
```json
{
  "verdict": "JUDGMENT_REQUIRED",
  "confidence": 0.40,
  "rationale": "The diff shows internal openclaw.json hash change but the modified fields don't map cleanly to any documented inventory field. Cannot determine intent.",
  "question": "openclaw.json hash drift detected — fields modified include `claude_session_ttl_seconds`. Should this be added to service-inventory.json, or is it operator-only configuration not subject to docs tracking?"
}
```
