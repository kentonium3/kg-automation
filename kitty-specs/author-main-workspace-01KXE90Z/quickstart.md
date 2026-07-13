# Quickstart: Author main agent workspace

Author → validate → merge → verify-sync → smoke → rollback. Steps 1–3 are the
implementation WP; steps 4–9 are **post-merge operator acceptance** (run from the
repo root after `feat → main`), documented here because planning_artifact WPs
cannot own `kitty-specs/` paths (#584 lesson).

## 1. Author the five files (WP)

Author against `docs/design/openclaw-workspace-authoring-standard.md`, applying
the content-conservation move-table in `data-model.md`:
- `SOUL.md` → voice-only + one-line privacy stance
- `USER.md` → filtered Kent-context + Felix "why"
- `TOOLS.md` → real surface (paths, delegation mechanics, `felix-file-issue.py`, timelog helper, state files, enforceable privacy path)
- `IDENTITY.md` → Felix + vibe
- `AGENTS.md` → role statement (EA-orchestrator), Output Discipline block (mirror capture), enforceable privacy rule, consolidated red lines + delegation, de-hardcoded identity line, tightened verbatim / cron-vs-ask rules

Add the one-line GOVERNANCE.md roster note to the #587 standard (FR-010).

## 2. Validate (deterministic gate)

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```

`main` must report `ok: true` (INV-1 + INV-2). Also run the existing suite:

```bash
python3 -m pytest scripts/openclaw/agents/tests/ -q
```

## 3. Conservation self-check

Confirm no content block was lost and none is duplicated across files (INV-3,
INV-5): grep the moved blocks landed in their destinations and were removed from
their sources; confirm the verbatim-passthrough and cron-vs-ask rules still exist
exactly once.

## 4. Baseline BEFORE merge (rebaseline caveat)

Rebaseline is **not required** (agent prompt files not hashed by `audit.sh`,
#621). The merge commit records: `Rebaseline: not required — agent prompt files
are not hashed by audit.sh (#621)`.

## 5. Merge feat → main

Agent-prompt-sync deploys on merge-to-main. There is **no** `deploys/queued/`
manifest for this change.

## 6. Verify agent-prompt-sync deployed

Wait one tick past the sync's `git pull` (the pulling tick runs old code; the
next tick writes the files). Then confirm the sync ran and copied `main`'s files:

```bash
ssh office2-claude 'tail -20 /data/services/openclaw/logs/agent-prompt-sync.jsonl 2>/dev/null || tail -20 /data/services/.../agent-prompt-sync.jsonl'
```

(Exact log path per `scripts/openclaw/deploy/deploy_agent_prompts.py`; plan
phase confirms the destination directory for `main`.)

## 7. Parity check (INV-6)

Confirm repo ↔ office2 md5 match for each authored file:

```bash
for f in IDENTITY.md SOUL.md USER.md TOOLS.md AGENTS.md; do
  echo "== $f =="
  md5 -q scripts/openclaw/agents/main/$f
  ssh office2-claude "md5sum /data/services/openclaw/<main-dest>/$f"
done
```

All five must match.

## 8. Smoke test on the live agent (INV-4 runtime, NFR-004)

- **Direct exchange**: send Felix a direct WhatsApp message; confirm the reply is
  in Kent's voice and leads with the **model-agnostic** identity line.
- **Delegation route**: send one message that belongs to a specialist (e.g. a
  habit completion); confirm main relays it verbatim and returns the specialist's
  result, with no double-relay of cron-driven output.
- **Privacy**: confirm no `04-Growth/_private/` access in any path.

## 9. Rollback

If any check fails: revert the prompt commit on main (`git revert <sha>`), push,
and let agent-prompt-sync restore the prior files on the next tick. Tier 3 change,
fully reversible; no state to unwind.

## Definition of done

- Validator `main` ok:true; suite green (steps 2–3)
- Merged feat → main with the rebaseline record (steps 4–5)
- Sync deployed + parity matches (steps 6–7)
- Smoke passes: direct exchange + one delegation route + privacy hold (step 8)
- Issue #583 closed with the merge SHA + smoke evidence
