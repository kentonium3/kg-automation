# Quickstart: felix-doc-auditor driver (post-#343 architecture)

**Mission**: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
**Audience**: operator (Kent); future Claude Code sessions

This quickstart covers the new scripts-first driver that replaces the openclaw-agent-based auditor. Use after #343 ships; before that, see the prior `reference_felix_doc_auditor_ops.md` memory.

---

## The five things to know

1. **The auditor is now a Python script, not an LLM agent.**
   `python3 /home/claude/kg-automation/scripts/doc_audit/run.py` on office2.
   The systemd timer `felix-doc-auditor.timer` fires it hourly.

2. **Tick health lives in one file.**
   `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` — current state of the most recent tick. `cat | jq` answers "is the auditor healthy?"

3. **LLM is called only at 3 judgment moments.**
   `tier_classification`, `debt_body_generation`, `cross_file_implication`. Each prompt is a checked-in file in `scripts/doc_audit/prompts/`. Reviewing the prompts tells you everything the LLM sees.

4. **The old openclaw agent is GONE.**
   `/data/services/openclaw/felix-doc-auditor/` no longer exists. No SKILL.md is loaded at runtime. No conversation session is persisted. The auditor is stateless between ticks.

5. **Fail-forward.**
   If a tick fails, the next tick retries. No automatic rollback. If something breaks badly, patch forward — don't revert.

---

## Health check (30 seconds)

```bash
# 1. Latest tick result
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq'

# Look for:
#   status: "success"
#   timestamp_utc: within the last ~60 minutes
#   exit_code: 0
#   errors: []
```

Expected output shape (per `contracts/tick-signal.contract.md`):
```json
{
  "status": "success",
  "exit_code": 0,
  "timestamp_utc": "2026-05-20T16:00:00Z",
  "duration_seconds": 7.3,
  "tick": { "signals_seen": 0, "signals_processed": 0, ... },
  "judgment": { ..., "input_tokens": 0, ... },
  "errors": []
}
```

If `timestamp_utc` is older than 2 hours OR `status != "success"` → investigate.

---

## Forcing a manual tick

```bash
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'
```

`--wait` blocks until the oneshot completes. Then check `last-tick.json`.

---

## Dry-run preview

```bash
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/run.py --dry-run'
```

Prints what the next tick would do without filing issues, committing, or labeling. Useful when investigating an unexpected backlog.

---

## Inspecting recent tick history

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "24 hours ago" --no-pager'
```

Each tick logs a one-line `SUMMARY:` to the journal:
```
SUMMARY: status=success audits=2 debt=1 tier_a=1 drift=0 dur=7.3s tokens=in:6420(cache:4180)/out:540
```

Grep journal for patterns:
```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "24 hours ago" | grep "^SUMMARY:"'
```

---

## Reading the prompt artifacts

The three LLM judgment prompts are at:
```
scripts/doc_audit/prompts/
├── tier_classification.prompt.md
├── debt_body_generation.prompt.md
└── cross_file_implication.prompt.md
```

Each file shows:
- Cached boilerplate (rule recap + output schema) — the part the LLM "remembers" across calls within a tick
- Variable inputs — what gets injected per call
- Expected response schema — what the driver validates against

To review what the LLM is actually being asked:
```bash
less scripts/doc_audit/prompts/tier_classification.prompt.md
```

To see the driver's invocation surface:
```bash
less scripts/doc_audit/judgment/tier_classification.py
```

---

## Backlog recovery

When the queue is unexpectedly deep (e.g., post-outage):

```bash
# 1. Confirm signals exist
ssh office2-claude 'gh issue list --label "Doc audit:" --state open --limit 20 --json number,title'

# 2. Force a tick — the driver processes the FULL queue per tick (per Q3=B)
ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'

# 3. Verify drain
ssh office2-claude 'gh issue list --label "Doc audit:" --state open'

# 4. Check tick result for any errors
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq .errors'
```

If the queue doesn't drain in one tick, check `last-tick.json` for partial state (`status: "partial"`, errors list) and investigate.

---

## Stuck `status:in-progress` lock recovery

Pre-#343 the operator had to manually clear stuck locks. Post-#343 the driver recovers them automatically per spec FR-014. If you see a stuck lock that the driver hasn't cleared after a tick:

```bash
# Verify the auditor saw it (look in last-tick.json errors)
ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq .errors'

# If still stuck and confirmed orphan, manual clear:
gh issue edit <number> --repo kentonium3/kg-automation --remove-label "status:in-progress"
```

Note: the driver's stale-lock detection follows SKILL.md §8.7 rules (an issue with a referenced pending-approval issue + no decision label is the expected Level-1 wait state, not a stuck lock).

---

## Pending-approval workflow (unchanged from operator's perspective)

The driver still surfaces Tier-B proposed edits as `audit-pending-approval` issues. Operator decides asynchronously by applying ONE of:

- `audit-approve` → driver applies edits + closes both audit and pending-approval on the next tick
- `audit-reject` → driver demotes proposals to docs-debt issues + closes both
- `audit-skip` → driver closes both with a skip note

The actor-verification check (per SKILL.md §8.6) still applies: the driver refuses to process a decision label applied by `kg-felix-bot` itself.

---

## Cost / token usage

Each tick records token usage in `last-tick.json`:
```json
"judgment": {
  "tier_classification_calls": 3,
  "debt_body_generation_calls": 1,
  "cross_file_implication_calls": 0,
  "input_tokens": 6420,
  "cache_hit_input_tokens": 4180,
  "output_tokens": 540
}
```

For monthly cost estimation: aggregate `input_tokens + output_tokens` per tick × 24 ticks/day × 30 days. With prompt caching, `cache_hit_input_tokens` is billed at 10% of the standard input rate.

Baseline measurement (per spec NFR-001) is recorded in `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json`. Post-rework measurement in `…/-post-rework.json`. Reduction target: ≥80%.

---

## When something looks wrong — escalation flow

1. **Tick failed**: `cat last-tick.json | jq .errors`. Identify failure class.
2. **Stale signal**: `last-tick.json` timestamp older than 2 hours. Check timer + journal.
3. **Unexpected behavior**: review the relevant prompt artifact + the corresponding judgment module (e.g., `scripts/doc_audit/judgment/tier_classification.py`). The driver's behavior at each judgment moment is determined by the checked-in prompt + the structured response parser.
4. **Cost spike**: token usage suddenly higher. Likely cache invalidation (boilerplate changed) or queue size spike. Inspect `last-tick.json` `judgment` field.
5. **API outage**: errors list mentions Anthropic SDK rate-limit or 5xx. Next tick retries automatically.

For any failure mode the driver can't recover from, **file a P2-bug** rather than patching the running system unilaterally. Fail-forward is by-design.

---

## Configuration

Default config: `scripts/doc_audit/config.toml`. Holds:
- Adapter list (which signal sources are enabled)
- Anthropic model (default `claude-haiku-4-5`)
- Anthropic API key path (default `/data/services/openclaw/secrets/anthropic`)
- Cursor file paths
- Activity log directory
- `last-tick.json` path

Override via `--config` for testing. Production uses the default.

---

## What changed vs the old openclaw-agent auditor

| Aspect | Pre-#343 | Post-#343 |
|---|---|---|
| Entry point | `openclaw agent --agent felix-doc-auditor ...` | `python3 scripts/doc_audit/run.py` |
| State per tick | Persistent openclaw session (accumulated until context overflow per #342) | Stateless; each tick a fresh process |
| Procedure source | `AGENTS.md` + `SKILL.md` (~57 KB) interpreted by LLM | Python code in `scripts/doc_audit/` |
| LLM model | claude-haiku-4-5 via openclaw | claude-haiku-4-5 via anthropic SDK directly |
| LLM calls per tick | 1 huge call interpreting full procedure | 0-N small calls per judgment moment |
| Per-tick cost | ~20 K input tokens baseline regardless of work | ~1-2 K input per judgment moment, only when needed |
| Health signal | Free-text in journal + activity log | Structured `last-tick.json` + journal SUMMARY line |
| Failure mode | Silent (per #342, 52+ hours undetected) | Structured signal; 95% NFR-002 floor; #327 alerting consumes signal |
| Workspace files | `/data/services/openclaw/felix-doc-auditor/` (deleted at cutover) | Removed; driver has no workspace |

---

## Cross-references

- **Mission spec**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/spec.md`
- **Research decisions**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md`
- **Data model**: `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/data-model.md`
- **Tick signal contract**: `contracts/tick-signal.contract.md`
- **Signal-source contract**: `contracts/signal-source.contract.md`
- **Judgment-prompt contract**: `contracts/judgment-prompts.contract.md`
- **Driver invocation contract**: `contracts/driver-invocation.contract.md`
- **Inherited classifications**: `scripts/openclaw/skills/doc-audit/SKILL.md` (still informative; the rules continue to apply, just from Python now)
- **Future consumer**: [#327](https://github.com/kentonium3/kg-automation/issues/327)
