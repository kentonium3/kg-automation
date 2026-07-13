# Quickstart: Author main agent workspace

Author → validate → merge → verify-sync → **rotate** → smoke → rollback. Steps
1–3 are the implementation WP; steps 4–10 are **post-merge operator acceptance**
(run from the repo root after `feat → main`), documented here because
planning_artifact WPs cannot own `kitty-specs/` paths (#584 lesson).

Real office2 paths (verified against `service-inventory.json`, Codex F7):
- **main deploy dest**: `/data/services/openclaw/data/` (NOT `inbox-agent` — that is capture)
- **agent-prompt-sync log**: `/data/services/openclaw/deploy/agent-prompt-sync.jsonl`

## 1. Author the files (WP)

Author against `docs/design/openclaw-workspace-authoring-standard.md` per the
content-conservation move-table in `data-model.md`. Key rebalance under the 12K
AGENTS cap:
- `SOUL.md` → voice-only + one-line privacy stance
- `USER.md` → filtered Kent-context + Felix "why"
- `TOOLS.md` → real surface **+ delegation/timelog/issue-filing mechanics + the enforceable `04-Growth/_private/` privacy rule (Invariant A home)**
- `IDENTITY.md` → Felix + vibe
- `AGENTS.md` → role statement (EA-orchestrator), adapted Output Discipline block, full routing matrix (all six specialists), consolidated red lines, de-hardcoded identity line `Sent by main:<model>`; delegation **rules** only (mechanics live in TOOLS)

Add the one-line GOVERNANCE.md roster note to the #587 standard (FR-010).

## 2. Validate (deterministic gate — main-scoped, Codex F6)

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```

**Acceptance is `main` `ok: true`** (read main's entry from the JSON). Note: the
full-fleet exit code is currently RED because `felix-admin-calendar` also fails
`output_discipline` — that is the #635 mission's scope, **out of scope here**.
Gate on main's object, not the process exit code.

Byte cap + suite:

```bash
python3 -m pytest scripts/openclaw/agents/tests/test_agents_md_size.py -q   # INV-8: main/AGENTS.md < 12000 B
python3 -m pytest scripts/openclaw/agents/tests/ -q
```

## 3. Conservation self-check (INV-3, INV-5)

Confirm every moved block landed in its destination and was removed from its
source, and that no rule was dropped. Spot-grep the load-bearing rules survive
exactly once:

```bash
grep -c "Verbatim" scripts/openclaw/agents/main/AGENTS.md          # verbatim-passthrough present
grep -o "felix-admin-[a-z]*" scripts/openclaw/agents/main/AGENTS.md | sort -u   # all specialists in routing matrix
grep -c "04-Growth/_private" scripts/openclaw/agents/main/TOOLS.md  # enforceable privacy rule in TOOLS
```

Expect all six specialists (capture, habits, escalation, tasker, calendar) plus the timelog path.

## 4. Baseline / rebaseline record (before merge)

Rebaseline **not required** (agent prompt files not hashed by `audit.sh`, #621).
Merge commit records: `Rebaseline: not required — agent prompt files are not
hashed by audit.sh (#621)`.

## 5. Merge feat → main

Agent-prompt-sync deploys on merge-to-main. **No** `deploys/queued/` manifest.

## 6. Verify agent-prompt-sync deployed

Wait one tick past the sync's `git pull` (the pulling tick runs old code; the
next tick writes the files). Then confirm the copy landed:

```bash
ssh office2-claude 'tail -20 /data/services/openclaw/deploy/agent-prompt-sync.jsonl'
```

Expect a record with the merge SHA and `main` files copied.

## 7. Parity check (INV-6)

```bash
for f in IDENTITY.md SOUL.md USER.md TOOLS.md AGENTS.md; do
  echo "== $f =="
  git show HEAD:scripts/openclaw/agents/main/$f | md5
  ssh office2-claude "md5sum /data/services/openclaw/data/$f"
done
```

All five must match.

## 8. Rotate the live main session (INV-9, Codex F5)

Prompt-sync copies files, but an active `main` session caches its prompt at
session-init (the known systemPromptReport staleness). Rotate before smoke so the
test exercises the NEW prompt:

```bash
ssh office2-claude 'python3 /data/services/openclaw/.../scripts/openclaw/helpers/rotate_main_session.py'
```

(Helper: `scripts/openclaw/helpers/rotate_main_session.py`, present in repo;
resolve its deployed path during implementation.)

## 9. Smoke test — evidence-shaped (NFR-004, Codex F9)

Run a real WhatsApp exchange, then confirm with logs/session evidence — not just
by eyeballing the reply:

- **Direct exchange**: send Felix a direct message. Evidence: main session JSONL
  shows a reply beginning with `Sent by main:<model>` (model-agnostic form, no
  `:sonnet`); gateway send log shows delivery.
- **Delegation route**: send one specialist-bound message (e.g. a habit
  completion). Evidence: the specialist's session JSONL received Kent's text
  **verbatim** (grep the exact phrase); main did not double-relay cron output.
- **Privacy**: grep the main session for any `_private` access — must be absent.

```bash
ssh office2-claude 'grep -h "Sent by main" <main-session-log> | tail -3'
ssh office2-claude 'grep -h "<verbatim phrase>" <specialist-session-log> | tail -3'
ssh office2-claude 'grep -rl "_private" <main-session-logs> || echo "no _private access (good)"'
```

## 10. Rollback

If any check fails: `git revert <sha>` on main, push, let agent-prompt-sync
restore prior files on the next tick, **then run `rotate_main_session.py` again**
(so the live session picks up the reverted prompt). Tier 3, fully reversible.

## Definition of done

- main `ok:true` (main-scoped), `test_agents_md_size.py` green, suite green (steps 2–3)
- Merged feat → main with the rebaseline record (steps 4–5)
- Sync deployed + parity matches (steps 6–7)
- Session rotated (step 8); smoke passes with evidence: direct exchange + one delegation route + privacy hold (step 9)
- Issue #583 closed with the merge SHA + smoke evidence
