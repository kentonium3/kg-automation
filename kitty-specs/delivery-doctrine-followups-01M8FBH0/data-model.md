# Data Model: Delivery-doctrine follow-ups (#1146)

## Guard pattern classes (`delivery_doctrine.py`)

| Class | Meaning | Change in this mission |
|---|---|---|
| Canonical block | `DELIVERY_DOCTRINE_BLOCK`. It must appear exactly once in each announce `AGENTS.md`, byte for byte | Retry tail → "…fix the input from the error, or skip it and say so in your final reply." (FR-003) |
| Forbidden pattern | `(name, regex)` in `FORBIDDEN_DELIVERY_PATTERNS`, scanned outside the block | Added or widened for the FR-001 forms: emphasis-insensitive `no_change`, `automations` as a tool reference, `catalog.search("automations")`, `automations.<method>(`, "mark/set … no_change", "recording no_change", "then notify … <channel>" |
| Exemption | A rule that waives a pattern match in a specific **clause** (never a whole line) | Added for FR-002: a negation attached directly to the matched verb ("do not / never / don't record no_change"), the prose form "cron automations (…)", and a mention of a field named `record_result`. The existing `_FINAL_REPLY_EXEMPT` is narrowed from line scope to clause scope (R1-3) |

**Invariants**
- The block is searched on the raw text. Normalisation applies only to the scanned remainder: paired formatting delimiters are removed, identifier underscores are kept, and table pipes and list markers are clause boundaries (R1-4).
- Every exemption has a same-fixture positive control: the same sentence without its exempting context is still flagged.
- The guard is deterministic, with regex and string operations only.

## Announce agent → readable skills (mirror for the FR-005 test)

| Agent | Skills (live `agents.entries.<id>.skills`) | Prompt-referenced |
|---|---|---|
| felix-admin-capture | `vikunja_api`, `github` | — |
| felix-admin-escalation | `escalation`, `vikunja_api` | — |
| felix-admin-habits | `vikunja_api` | task-intelligence |

The canary re-checks this mirror against live config.

## Tool deny entry (office2 `openclaw.json`)

```json5
agents: { entries: {
  "felix-admin-capture":    { tools: { deny: ["conversations_*","sessions_*","message","automations"] } },
  "felix-admin-escalation": { tools: { deny: ["conversations_*","sessions_*","message","automations"] } },
  "felix-admin-habits":     { tools: { deny: ["conversations_*","sessions_*","message","automations"] } },
} }
```

**Invariants**
- `main`, `felix-admin-calendar`, `felix-admin-tasker` and the top-level `tools` stay unchanged; their sorted-JSON sha256 is equal before and after.
- Re-applying is a no-op.
- The entrypoint refuses if any target agent already has `tools.allow` or a different `tools.deny`.

**State transitions:** `absent` → (apply) → `denied`; `denied` → (apply) → `denied` (no-op); `denied` → (rollback) → original. Rollback dequeues the manifest if it is still queued, then applies one Gateway `config patch` restoring each agent's original `tools` value from the recovery receipt. The receipt is written before the first change, kept across retries, and distinguishes an absent key from an empty array. Restoring the whole-file backup is the last resort only (R1-2).

## Manifest `announce-agent-tool-deny` (unnumbered when queued; fields of note)

- `tier: 2`
- `verification.pre`: the applier's mandatory snapshot gate (backup-state file, ≤ 24 h); the live shape matches expected.
- `verification.post`: read back the deny; check the other entries' hashes.
- `audited_surface: true`
- `expected_baselines: [openclaw-config.txt]`
- recovery notes naming the backup file
