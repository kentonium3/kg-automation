# WP06 Review — Cycle 1 (CHANGES REQUESTED)

Reviewer: independent **opus** fallback (codex hit its usage limit mid-review; re-reviewed with
codex-level rigor per operator decision). Role: reviewer-renata.

## Verdict summary

Most of WP06 is correct and high quality — see "What passed" below. But the architecture store
is left **internally contradictory** about the agent-log location, which is precisely the
"stale `/home/claude/second-brain`" class this WP exists to eliminate. One blocker.

---

## BLOCKER — Issue 1: stale `/home/claude/second-brain` agent-log paths left in the store (self-contradiction)

This mission decommissions the entire stray tree. Deploy manifest `0007-migrate-inbox-state-and-logs.yaml`
sweeps **all** of `agents/logs/**` (the migration script classifies `agents/logs/**` → `log_tree`,
not just `inbox-prescan-*.md`), then **quarantine-renames the whole `/home/claude/second-brain`
tree and asserts `test ! -e /home/claude/second-brain`**. FR-008 / SC-5 additionally require that
**no writer recreate it**.

Yet WP06 leaves three architecture-store surfaces still describing an **active** service that
reads/writes that now-removed tree:

1. `docs/design/architecture/data/service-inventory.json` — `felix-core-digest` service (~L1932-1951):
   - `input_path`: `/home/claude/second-brain/agents/logs/ (summarize.py) ...`
   - `output_path`: `/home/claude/second-brain/notes/Agent-Logs/ (summarize.py) ...`
   - `dependencies[].target`: `/home/claude/second-brain/agents/logs/`
2. `docs/design/architecture/data/data-flows.json` — `observation-digest` flow (~L140-165):
   - `log_action.py` → `/home/claude/second-brain/agents/logs/{agent}/YYYY-MM-DD.jsonl`
   - `summarize.py` → `/home/claude/second-brain/notes/Agent-Logs/`
3. `docs/design/architecture/data-flows.md` — storage-location table (L685-686):
   - `Agent JSONL logs | /home/claude/second-brain/agents/logs/`
   - `Agent digest files | /home/claude/second-brain/notes/Agent-Logs/`
   (Note the same table already lists the doc-auditor log at `/home/kgale/second-brain/agents/logs/`
   two rows down — so the table is now self-inconsistent about the vault convention.)

Net effect: the store simultaneously documents `/home/claude/second-brain` as decommissioned
(migration_note + manifest) AND as the live I/O home of the `felix-core-digest` (F014, status
`active`) service. WP06's stated objective is "keep the live architecture store truthful"; it is
not truthful as written.

### Related integration risk this contradiction is masking (surface to mission owner)

The reason the docs still point at `/home/claude` is that **the observation-digest code was never
repointed by any WP**: `scripts/openclaw/observation/config.py` computes `log_dir =
Path.home()/second-brain/agents/logs` → `/home/claude/second-brain/agents/logs` (gateway runs as
user `claude`); `log_action.py` writes there, `summarize.py` reads there and writes digests to
`/home/claude/second-brain/notes/Agent-Logs/`. After manifest 0007 runs, the next agent action will
`mkdir` and **recreate `/home/claude/second-brain/agents/logs`, violating FR-008/SC-5**, while
`summarize.py` reads the recreated (empty) dir — the historical JSONL was moved to `/home/kgale` —
and targets a now-absent `notes/Agent-Logs/`. This is a genuine mission-level integration gap
(observation digest silently orphaned), not merely cosmetic.

### How to fix (WP06 scope)

Reconcile the three surfaces above with the decommission — do **not** leave them pointing at the
quarantined tree. Pick the branch that matches the mission's actual intent and make the docs match
reality:

- **(A) If the observation digest is meant to follow the same vault convention** (most consistent
  with the mission's premise that agent logs belong in `/home/kgale/second-brain`): update the three
  surfaces to `/home/kgale/second-brain/agents/logs/` and `/home/kgale/second-brain/notes/Agent-Logs/`,
  AND raise the `config.py`/`log_action.py`/`summarize.py` code repoint as a mission blocker / code-WP
  item. Docs must not assert a move the code does not make — so this path requires the code fix to
  land too (or an explicit "code repoint pending, tracked in <ref>" note on the entries).
- **(B) If the observation digest is deliberately out of scope for this mission**: add an explicit
  note on the `felix-core-digest` service entry + `observation-digest` flow recording the known
  contradiction — that manifest 0007 removes `/home/claude/second-brain` while this service still
  writes there, the SC-5 recreation risk, and a tracking follow-up issue ref. Silence is the problem;
  an accurate, sourced caveat is acceptable.

Either way the store must stop simultaneously claiming the tree is gone and in active use.

---

## What passed (no action needed)

- **Validators both green**: `validate_docs: OK`; `validate_architecture_data: OK (0 findings)`.
- **Inbox/calendar path relocation** (service-inventory.json + .md, data-flows.json + .md): accurate
  and internally consistent with the deployed artifacts — `/data/services/openclaw/state/`, owner
  `claude:secondbrain`, dir 0750 / file 0640, and the `/home/kgale/.../agents/logs/` prescan log all
  match manifest 0007's post-checks and the drop-in. JSON is authoritative and the md mirrors it.
- **Gateway PYTHONPATH drop-in** entry (service-inventory.json config_files + .md): matches
  `scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf` and manifest `0006`
  (`PYTHONPATH=/home/claude/kg-automation`).
- **Rebaseline determination (T021) is correct and honest**: verified against audited-surfaces.json —
  `systemd-user-units` → `systemd-user-dropins.txt` baseline, `rebaseline_required: true` (drop-in
  requires `Rebaseline: completed at <ts>` at merge); `openclaw-agent-prompts` →
  `affected_baselines: []`, `rebaseline_required: false` (#621 gap — WP04 AGENTS.md edits correctly
  claim no rebaseline). The audited-surfaces.json pattern extension (`scripts/openclaw/*.service.d/*.conf`)
  is a justified out-of-map edit for the systemd-unit change class.
- **Signal-to-doc doc_targets addressed**: all three change classes' targets updated or justifiably
  skipped (`service-dependencies.view.md`, `data-flows.view.md`, `felix-capability-roadmap.md` skipped
  — path relocation only, no service-graph / capability / diagram-edge change; documented in the WP
  commit body). INDEX.md / DEVELOPER_PORTAL.md are correctly not in these classes' targets.
- **Anti-pattern checklist**: docs-only WP, no new code — items 1-4, 6, 8 N/A; item 5 (frozen surface)
  PASS (no frozen files touched); item 7 (shared-file ownership) PASS (no other WP edits these doc files
  in the merge; out-of-map edits to data-flows.md + audited-surfaces.json are justified, noted in the
  commit body).

Resolve Issue 1 and this is an approve.
