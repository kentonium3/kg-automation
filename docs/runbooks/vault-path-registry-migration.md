---
title: Vault Path Registry Migration Runbook
doc_type: runbook
status: approved
audience: agents_and_humans
last_updated: '2026-04-10'
revision: v1.0
---

# Vault path registry migration runbook

A reusable playbook for migrating Felix vault folder names through the
`scripts/vault/` registry. First executed by mission 026 (#152), which
extended the registry from a single inbox path (mission 024 / #150 MVP)
to every top-level vault folder, renumbered the folders to a clean
00–09 ordinal sequence, and created the `02-Inbox-Processed/` destination
that the inbox pre-scan helper (#149) depends on.

This runbook is the canonical reference for any future migration that
renames, renumbers, or restructures vault folders. It is reusable: a
future similar migration should be executable from this document
without re-reading the original mission spec.

## Purpose

A vault path registry migration is the controlled replacement of one or
more vault folder names across:

1. The registry data file (`scripts/vault/paths.json`).
2. Every consumer that references those names — agent workspaces,
   Claude instructions, CLAUDE.md, scripts, architecture JSON and
   markdown, and runbooks.
3. The physical vault folders themselves (renamed via the Obsidian UI
   so that wikilinks auto-update).
4. The deployed agent files on office2 (resolved through the registry
   at deploy time).

The runbook exists because vault folder names are referenced from
dozens of places. Without the registry, a folder rename was a
multi-file hunt-and-replace with high risk of missed references that
break silently until the affected agent next runs. With the registry,
the rename becomes a single-file data change followed by a deterministic
deploy.

## When to use this runbook

Use this runbook when any of the following are true:

- A vault folder is being **renamed** (e.g. `00-Inbox` → `01-Inbox`).
- A vault folder is being **renumbered** to fit a new ordinal scheme.
- A new top-level vault folder is being **added** and any code or doc
  needs to reference it by logical name.
- An existing logical name in the registry is being **retired** and
  consumers must be migrated off it.

Do **not** use this runbook for:

- Adding files inside an existing top-level vault folder (no migration
  required — only the top-level names are registered).
- Changing the constitutional `_private/` boundary path. The boundary
  itself does not move; only the parent folder ordinal can change, and
  CLAUDE.md's hardcoded reference is updated by direct edit, not via
  the registry.
- Cross-vault migrations (e.g. moving content from one Obsidian vault
  to another). That is a different operation and requires a separate
  playbook.

## C4 summary (per `c4-incremental-detail-modeling` paradigm)

The migration's structural shape, expressed in progressive C4 detail.
Use this section to orient yourself before reading the procedure.

### Level 1 — System Context

```
+-------------------------+        +-----------------------------+
|                         |        |                             |
|  Operator (Kent)        |───────▶|  Felix system               |
|                         |        |  (kg-automation + office2)  |
+-------------------------+        +-----------------------------+
                                              │
                                              │ resolved at deploy time
                                              ▼
                                   +--------------------------+
                                   |  Knowledge store         |
                                   |  (Obsidian vault on      |
                                   |  office2; synced to Mac  |
                                   |  and iPhone)             |
                                   +--------------------------+
```

The system boundary does not change during a migration. The Felix
system continues to compose the same services. The vault remains the
same logical knowledge store. What changes is the **internal naming**
of folders inside the vault and the corresponding registry entries
that map logical names to physical paths.

### Level 2 — Containers

```
+-------------------------------------------------------------+
|  Felix system                                               |
|                                                             |
|  +------------------+    +------------------------------+   |
|  | OpenClaw agents  |    | scripts/vault/               |   |
|  | (workspaces +    |◀───|  paths.json                  |   |
|  |  deployed files) |    |  targets.json                |   |
|  +------------------+    |  resolver.py                 |   |
|         ▲                |  paths.sh (generated)        |   |
|         │ deploy         |  deploy.py                   |   |
|         │                +------------------------------+   |
|  +------------------+              ▲                        |
|  | Architecture     |              │ resolves               |
|  | docs / runbooks  |              │ markers                |
|  +------------------+    +------------------------------+   |
|                          | scripts/deploy/              |   |
|                          |  deploy-fNNN.sh wrappers     |   |
|                          +------------------------------+   |
+-------------------------------------------------------------+
```

`scripts/vault/` is a deployable container — a shared piece of
infrastructure consumed by every agent and any consumer that needs to
reference a vault path. The container holds the registry data, the
resolver API, and the deploy script. Migrations expand the container's
data files but do not change its public interface.

### Level 3 — Components

```
scripts/vault/
├── paths.json          ← logical name → physical path mapping (data)
├── targets.json        ← .tmpl source → resolved file mapping (data)
├── resolver.py         ← Python API: get_vault_path("inbox") → "01-Inbox"
├── paths.sh            ← shell sourcing helper (generated by deploy.py)
├── deploy.py           ← marker substitution and resolved-file emission
└── README.md           ← human-readable usage examples

scripts/deploy/
└── deploy-f<NNN>.sh    ← thin wrapper for a specific mission's
                          deploy with mode flags and verification
                          orchestration
```

The components have stable interfaces. A migration:

- **Adds rows** to `paths.json` (new logical names).
- **Edits rows** in `paths.json` (renames change the physical path).
- **Adds rows** to `targets.json` (new files to be templatized).
- **May add** a new wrapper under `scripts/deploy/` if the migration
  needs custom orchestration (e.g. pre-rename vs post-rename modes).

The resolver, the generated `paths.sh`, and `deploy.py` itself are
generic and rarely change between migrations.

### Level 4 — Code

```
.tmpl source files
├── scripts/openclaw/agents/<agent>/AGENTS.md.tmpl
│       Hello {{VAULT_INBOX}} — process content from this folder.
│
├── ai-agents/claude-instructions.md.tmpl
│       Read planning notes from {{VAULT_CONSTITUTION}}/Goals-MOC.md.
│
└── docs/_templater-scripts/...
        (rare; most docs are not templatized)

Marker substitution:
  {{VAULT_INBOX}}              → 01-Inbox
  {{VAULT_INBOX_PROCESSED}}    → 02-Inbox-Processed
  {{VAULT_CONSTITUTION}}       → 03-Constitution
  ...
```

The Code level is where individual `.tmpl` files live and where the
deploy script's substitution logic runs. The `_private/` boundary is
deliberately **not** representable as a marker — it stays hardcoded
in the (small) set of files that reference it (CLAUDE.md being the
canonical example) so that no logical resolution path can ever
discover it.

## Prerequisites

Before starting a migration, confirm:

1. **Mission 024 (#150) infrastructure is operational.** The registry,
   resolver, and deploy script must work end-to-end against the
   *current* vault state. Run `python3 scripts/vault/resolver.py inbox`
   and confirm a path is returned.

2. **Workspace is clean.** `git status` shows no uncommitted changes
   on the mission branch.

3. **Inbox is quiescent.** `ssh office2-claude 'ls
   /home/kgale/second-brain/notes/01-Inbox | wc -l'` returns a count
   you are willing to leave unprocessed during the risky window
   (zero is ideal; small counts are acceptable).

4. **Restic backup is current** (≤ 24 hours old). The folder rename
   is a Tier 2 operation per
   `docs/design/architecture/data/change-risk-taxonomy.json`. Confirm
   via `ssh office2-claude 'restic snapshots --last 1'`.

5. **`felix-admin-capture` cron is currently enabled** and you have
   the operator credential to pause it. The migration's risky window
   begins with the cron pause and ends with the cron resume.

6. **You can edit CLAUDE.md and the constitution.** These files
   contain the `_private/` boundary reference; updating that
   reference is a hardcoded edit, not a registry-driven change.

7. **You have the rename table.** Decide the mapping of old folder
   names to new folder names *before* starting. The mission 026
   table is reproduced below as the canonical example:

   | Old | New |
   |---|---|
   | `00-Inbox` | `01-Inbox` |
   | `01-Constitution` | `03-Constitution` |
   | `02-Growth` | `04-Growth` |
   | `03-Health` | `05-Health` |
   | `04-Business` | `06-Business` |
   | `05-Finance` | `07-Finance` |
   | `06-Journal` | `08-Journal` |
   | `07-Resources` | `09-Resources` |

   `00-System` was unchanged. `02-Inbox-Processed` was created new.

## Procedure (10-step sequence)

The mission-026 procedure, generalized so it can be re-applied. Each
step is individually verifiable; halt and roll back at the first
failed verification.

### Step 1 — Extend the registry (no behavior change)

Edit `scripts/vault/paths.json` to add any new logical names. Add
matching entries to `scripts/vault/targets.json` for every file that
will be templatized in step 2. Validate JSON with
`python3 -m json.tool`. Verify resolver behavior:

```bash
python3 scripts/vault/resolver.py inbox_processed   # new name
python3 scripts/vault/resolver.py _private          # MUST raise UnknownPathError
```

The registry now describes the *future* state but no consumer files
have been migrated yet. Commit the registry extension as a discrete
work package (mission 026 used WP01).

### Step 2 — Migrate consumers to template markers

For every file in the audit (agent workspaces, Claude instructions,
scripts, etc.) that contains a hardcoded vault folder literal, create
a `.tmpl` source file with `{{VAULT_*}}` markers and add a
`targets.json` entry mapping the source to the resolved output. Run
`python3 scripts/vault/deploy.py --apply` and verify the resolved
output is byte-equivalent to the pre-migration content.

Acceptance:

```bash
grep -rn "00-Inbox\|01-Constitution\|..." scripts/ ai-agents/ CLAUDE.md \
  | grep -v "_private" \
  | grep -v "\.tmpl:"
# Expect: zero matches
```

Commit as a discrete work package (mission 026 used WP02).

### Step 3 — Synchronize documentation

Update every architecture JSON, markdown view, runbook, INDEX, and
roadmap that references the migrated folder names. Per project
directive #4, JSON is authoritative; markdown narratives must match.
Set `updated_by: "#<issue>"` on every modified JSON file. Run
`validate_docs.py` and confirm zero hits for old folder literals
outside `docs/archive/` and `docs/func-spec/`.

This step exists as a first-class mission deliverable per charter
project directive #5 — documentation synchronization is not a
post-hoc cleanup. Mission 026 used WP03 for this work and it is
the WP that produced this runbook.

### Step 4 — Pre-rename deploy + refactor-fidelity checkpoint

Run the wrapper in pre-rename mode:

```bash
bash scripts/deploy/deploy-f<NNN>.sh --apply --mode pre-rename
```

Capture baseline outputs from any agents whose behavior must remain
unchanged (mission 026 used `felix-admin-capture` and
`felix-admin-tasker`). Re-run after the deploy and `diff` against
baseline. The diff must contain only timestamp / run-ID differences,
nothing semantic.

This is the **DIRECTIVE_034 test-first checkpoint**. Step 4 exists
specifically to prove that the registry extension and consumer
migration are a pure refactor.

Operator authorization gate: Step 5 is the risky window. Do not
proceed past Step 4 without explicit operator approval.

### Step 5 — Pre-flight Tier 2 checks and pause cron

```bash
# Verify Restic snapshot age
ssh office2-claude 'restic snapshots --last 1'
# Pause the inbox-capture cron
ssh office2-claude 'crontab -l'
ssh office2-claude 'crontab -e'   # comment out felix-admin-capture entry
ssh office2-claude 'crontab -l'   # confirm
```

The risky window (NFR-004 budget: 90 minutes) starts here.

### Step 6 — Create new folders directly at their final names

For any new top-level folder, create it at its final target name (do
not create-then-rename — rename adds risk for nothing). Mission 026
created `02-Inbox-Processed/`:

```bash
ssh office2-claude 'mkdir -p /home/kgale/second-brain/notes/02-Inbox-Processed'
ssh office2-claude 'touch /home/kgale/second-brain/notes/02-Inbox-Processed/.gitkeep'
```

The placeholder file ensures Obsidian Sync propagates the empty
directory reliably.

### Step 7 — Rename existing folders via Obsidian UI

This is the only step performed outside of CLI tooling. Open Obsidian
on the Mac and rename folders one at a time, in the order from your
rename table. **Verify wikilink integrity in Obsidian after each
rename** before proceeding to the next.

Mission 026 rename order (canonical example):

1. `00-Inbox` → `01-Inbox`
2. `01-Constitution` → `03-Constitution`
3. `02-Growth` → `04-Growth`
4. `03-Health` → `05-Health`
5. `04-Business` → `06-Business`
6. `05-Finance` → `07-Finance`
7. `06-Journal` → `08-Journal`
8. `07-Resources` → `09-Resources`

Wait for Obsidian Sync to propagate to office2. Verify on office2:

```bash
ssh office2-claude 'ls /home/kgale/second-brain/notes/'
# Expect: every renamed folder visible at its new name
```

If any rename produces unresolved wikilinks in Obsidian, halt. See
the Rollback section.

### Step 8 — Update the registry to point at the new folder names

Edit `scripts/vault/paths.json` so each logical name maps to its new
physical folder. Edit any hardcoded boundary references in CLAUDE.md
(or its `.tmpl`, if templatized) and the constitution to reflect the
new parent folder for `_private/`.

Commit the changes to the mission branch.

### Step 9 — Post-rename deploy + verification + smoke tests

```bash
bash scripts/deploy/deploy-f<NNN>.sh --apply --mode post-rename
```

The wrapper performs (in order):

1. `deploy.py --apply` resolves all markers against the new registry.
2. Repo-wide grep for stale literals (expect zero, NFR-002).
3. Deployed-file grep for unreplaced `{{VAULT_*}}` markers (expect
   zero, NFR-003).
4. Smoke-test invocation of every agent that references vault paths.
   Mission 026 covered `felix-admin-capture` and `felix-admin-tasker`.
5. Obsidian wikilink integrity check (expect zero new unresolved
   links, NFR-005).

Any failure halts the wrapper and leaves the cron paused. See the
Rollback section.

### Step 10 — Resume cron and verify the next tick

```bash
ssh office2-claude 'crontab -e'   # uncomment felix-admin-capture entry
ssh office2-claude 'crontab -l'   # confirm uncommented
```

Wait for the next scheduled cron tick (or trigger a manual run-once)
and confirm the agent succeeds against the new paths. The risky
window (NFR-004) ends here.

## Verification

The acceptance checks above are codified in
`kitty-specs/<mission>/contracts/verification-contract.md` for any
mission that uses this runbook. The pattern, for mission 026, was:

- WP01 — registry resolves every new logical name; `_private` is
  not resolvable.
- WP02 — zero hardcoded literals in production files outside the
  `_private/` boundary; resolved files match pre-migration content.
- WP03 — zero hardcoded literals in `docs/`; all JSON files have
  `updated_by` set; markdown views match JSON sources.
- WP04 — pre-rename deploy produces no behavior change; agent
  baselines diff cleanly.
- WP05 — every step from this runbook's Step 5 through Step 10
  completes successfully; total risky window ≤ 90 minutes.
- WP06 — cross-repo `_private/` gitignore in second-brain works
  (trivial test: place a file under `_private/`, observe `git
  status` remains clean).

A future migration's verification contract should follow this same
shape, adjusted for the specific folders being migrated.

## Rollback

Rollback strategy depends on the step at which failure occurred.

**Step 1 (registry extension)** — `git revert` the registry commit.
No runtime state has been touched.

**Step 2 (consumer migration)** — `git revert` the migration commit.
The `.tmpl` files and resolved outputs are removed; pre-migration
files are restored.

**Step 3 (doc sync)** — `git revert` the doc-sync commit. Documentation
returns to its pre-migration state.

**Step 4 (pre-rename deploy)** — Re-run `deploy.py --apply` against
the reverted registry. Resolved files on office2 return to their
pre-migration content.

**Step 5 (pre-flight)** — Re-enable the cron. Halt the migration.

**Steps 6–7 (folder creation and renames, pre-redeploy)** — In
Obsidian on the Mac, rename each new folder back to its old name.
Verify wikilinks resolve. Re-enable the cron.

**Step 8 (registry update)** — Revert the registry change. No deploy
has happened yet so office2 is still on the old folder names; no
further action required beyond re-enabling the cron.

**Step 9 (post-rename deploy)** — Re-run `deploy.py --apply` against
the registry that points at the *old* folder names. This restores
old-state agent files on office2. Then Obsidian-rename folders back
to their old names per the Steps 6–7 rollback. Re-enable the cron.

**Step 10 (cron resume)** — If the cron resumes but the next agent
run fails, pause the cron again and investigate. Most likely cause
is a missed reference somewhere in the registry, the deploy, or a
runbook command — the verification in Step 9 should have caught it,
but if it slipped through, the cron pause provides another safe
window for diagnosis.

**Catastrophic** — If the vault state itself is corrupted beyond
manual recovery (e.g. Obsidian Sync conflict storms, or wikilinks
pointing into nonexistent folders that cannot be repaired), fall
back to a Restic restore of `/home/kgale/second-brain/notes/` per
the Tier 2 fallback in
`docs/runbooks/governance/post-change-verification.md`. This is the
last-resort option and requires re-running the migration from a
clean state once recovery completes.

## Post-migration

Once the migration is verified end-to-end:

1. **Close the mission's GitHub issue** with a link to the merge
   commit and a one-line summary of what changed.

2. **Update `docs/INDEX.md`** if the migration created any new
   runbooks or doc artifacts (this runbook itself was added by
   mission 026).

3. **Update `docs/design/felix-capability-roadmap.md`** to reflect
   the expanded registry capability state.

4. **Notify any blocked downstream missions** that they are now
   unblocked. Mission 026 unblocked `#149` (the inbox pre-scan
   helper) by creating `02-Inbox-Processed/`.

5. **Refresh the `last_validated` date on every modified runbook**
   if your project follows that convention.

6. **For any cross-repository operations** (e.g. mission 026's
   second-brain `_private/` gitignore step), perform them in their
   own commit on the appropriate repo and reference the kg-automation
   mission in the commit message.

## References

- Mission 024 — Vault path registry MVP: `#150` (introduced the
  registry infrastructure, single inbox path)
- Mission 026 — Vault path registry extension and folder renumber:
  `#152` (extended to all vault folders; first user of this runbook)
- `kitty-specs/026-vault-path-registry-and-folder-renumber/spec.md`
  — canonical example of a vault path registry migration spec
- `kitty-specs/026-vault-path-registry-and-folder-renumber/plan.md`
  — implementation plan with WP-level breakdown
- `kitty-specs/026-vault-path-registry-and-folder-renumber/contracts/verification-contract.md`
  — acceptance test pattern reused by future migrations
- `scripts/vault/README.md` — usage reference for the registry,
  resolver, and deploy script
- `docs/design/architecture/change-control.md` — change-control
  protocol that any migration must follow
- `docs/runbooks/governance/pre-flight-checklist.md` — Tier 2
  pre-flight requirements
- `docs/runbooks/governance/post-change-verification.md` — Tier 2
  post-change verification and Restic fallback
- `docs/design/felix-capability-roadmap.md` — registry capability
  status (full as of mission 026)
- Inbox pre-scan helper: `#149` (downstream consumer of
  `02-Inbox-Processed/`)

---

*This runbook is reusable. A future similar migration should be
executable from this document without re-reading the original
mission 026 spec. If this runbook has drifted from current practice
during a future migration, update it as part of that migration's
documentation-synchronization work package — never as a side
project. Doc sync is a first-class deliverable per charter project
directive #5.*
