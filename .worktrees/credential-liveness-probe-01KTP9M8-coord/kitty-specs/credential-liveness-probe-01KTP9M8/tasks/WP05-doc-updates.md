---
work_package_id: WP05
title: Architecture + runbook doc updates
dependencies:
- WP04
requirement_refs:
- C-007
- FR-021
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T023
- T024
- T025
agent: claude
history: []
agent_profile: curator-carla
authoritative_surface: docs/
execution_mode: code_change
mission_id: 01KTP9M86VF89TQM5SX7JVA83Z
mission_slug: credential-liveness-probe-01KTP9M8
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/runbooks/google-workspace-ops.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

Documentation curator posture: machine-readable first (JSON), narrative second (markdown). Cross-references must stay consistent. Per CLAUDE.md "architecture-docs-first" rule, every service/credential/runbook change updates the relevant architecture surface in the same diff.

## Objective

Update the architecture machine-readable layer (`service-inventory.json`) and the operator runbook (`google-workspace-ops.md`) to reflect the new automatic-detection surface introduced by this mission. Consult `signal-to-doc-map.json` for any additional doc targets it flags.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Lane worktree: allocated per `lanes.json` after `finalize-tasks` runs. WP04 dependency means the lane base has the systemd unit files (so doc references point at real, in-repo paths).

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) | Architecture Impact section enumerates affected change classes |
| [../plan.md](../plan.md) § IC-05 | Concern map |
| `docs/design/architecture/data/service-inventory.json` | Canonical machine-readable service inventory |
| `docs/design/architecture/data/signal-to-doc-map.json` | Lookup: what docs need updating per change class |
| `docs/runbooks/google-workspace-ops.md` | Workspace operator runbook (already updated in this session at commits `6b0ed765` + `00805ef7`) |
| CLAUDE.md "Standing requirement" + "Discovery aid" | The architecture-data update obligation |

## Subtask Guidance

### T023 — Update `service-inventory.json`

**Probe first**:

```bash
python3 -c "import json; d = json.load(open('docs/design/architecture/data/service-inventory.json')); print(type(d), list(d.keys()) if isinstance(d, dict) else 'list-shape')"
grep -n "credential-health-check\|credential_health_check" docs/design/architecture/data/service-inventory.json
```

Find an existing entry for `credential-health-check.service` (the existing daily timer) — use it as the template for the new entry.

**Steps**:

1. Locate the existing `credential-health-check` service entry.
2. Add a new entry for the liveness probe. Keep the same field shape as the existing entry. Example (adapt to the inventory's actual schema):

   ```json
   {
     "name": "credential-liveness-probe.service",
     "type": "systemd-user-oneshot",
     "host": "office2",
     "owner": "claude:claude",
     "triggered_by": "credential-liveness-probe.timer",
     "cadence": "every 6 hours (00,06,12,18:00:00 UTC)",
     "purpose": "OAuth credential liveness probe — issues a cheap `gog calendar list` call per monitored credential and files a GitHub issue on `invalid_grant`. Surfaces dead refresh tokens within ≤6h instead of waiting for user-facing failure (kentonium3/kg-automation#572).",
     "source_unit_file": "scripts/office2/credential-liveness-probe.service",
     "source_timer_file": "scripts/office2/credential-liveness-probe.timer",
     "deploy_script": "scripts/office2/deploy/credential-liveness-probe.sh",
     "deployed_by": "#572-credential-liveness-probe",
     "status": "active",
     "depends_on": ["openclaw-gateway.service", "network-online.target"],
     "consumes_credentials": ["gog-credentials-keyring"],
     "emits_signals": ["credential_alive", "credential_dead", "credential_probe_error"],
     "output_channel": "github-issue"
   }
   ```

3. The exact schema may differ from the example above — match the existing entries' field names. Use `python3 -c "import json; d = json.load(open('docs/design/architecture/data/service-inventory.json')); print(json.dumps(d.get('services', d)[0] if d else {}, indent=2))"` to see one existing entry's full shape.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (+~20 lines)

**Validation**:
- `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0 (JSON validity).
- A grep for `credential-liveness-probe` finds the new entry.

---

### T024 — Update `docs/runbooks/google-workspace-ops.md`

The runbook already references the new automatic surface in the broad sense (after this session's commits `6b0ed765` + `00805ef7` added `gog-reauth.sh` references). T024 adds the specific "the liveness probe will file a GH issue" detail.

**Probe first**:

```bash
grep -n "Testing-app 7-day cycle\|Common issues\|liveness" docs/runbooks/google-workspace-ops.md
```

**Steps**:

1. Locate the §Common Issues entry titled "Refresh token expired (Testing-app 7-day cycle — DOMINANT cause for current setup)".
2. Add a callout (after the existing routine-remediation paragraph) explaining the automatic detection:

   ```markdown
   > **Automatic detection** (post-#572): the `credential-liveness-probe`
   > systemd timer probes the gog token every 6 hours. When the token dies,
   > a GitHub issue is filed within ≤6h titled
   > `credential-liveness-routine-7day: gog-credentials-keyring (<date>)` (or
   > `credential-liveness-unexpected: …` for non-cycle deaths). The issue body
   > carries the exact `gog-reauth.sh` recovery command. You don't need to
   > manually monitor for expiration — the probe surfaces it.
   >
   > Force a probe manually:
   > `systemctl --user start credential-liveness-probe.service` (then
   > `journalctl --user -u credential-liveness-probe.service --since '1 minute ago'`).
   ```

3. The existing "Refresh token revoked (other causes)" paragraph below should reference the `credential-liveness-unexpected:` issue title (so operators know which prefix matches what cause).

**Files**:
- `docs/runbooks/google-workspace-ops.md` (+~15 lines)

**Validation**:
- `grep -n "credential-liveness-probe\|liveness-routine-7day" docs/runbooks/google-workspace-ops.md` finds the new references.
- Markdown renders cleanly (no broken block-quotes or unclosed code fences).
- Runbook frontmatter `last_updated` bumped to today's date; `updated_by` set to `#572-credential-liveness-probe`.

---

### T025 — Consult `signal-to-doc-map.json` for additional doc targets

**Probe first**:

```bash
python3 -c "import json; m = json.load(open('docs/design/architecture/data/signal-to-doc-map.json')); print(json.dumps(m, indent=2)[:3000])"
```

Per CLAUDE.md "Discovery aid for spec/plan agents", filter entries by:

- `match.source == "mission-architecture-impact"`
- `change_class` in `["service-added-or-modified", "systemd-unit-added-or-modified", "credential-added-or-modified", "runbook-modified"]`

**Steps**:

1. Run the probe and review each matching entry's `doc_targets` array.
2. For each `doc_target` NOT already touched by T023/T024 (and not by the runbook updates already shipped in this session), update it to reference the new surface.
3. Likely candidates (verify in the live JSON):
   - `docs/INDEX.md` — may need a new index entry under "Runbooks" or "Architecture".
   - `docs/DEVELOPER_PORTAL.md` — guided onboarding may need a reference.
   - `docs/design/architecture/data/credential-manifest.json` — already updated by WP01 (T004), no further action.
4. If a doc target is named but the update is non-obvious, document a brief one-liner in the file's relevant section pointing at `kitty-specs/credential-liveness-probe-01KTP9M8/spec.md`.
5. If `signal-to-doc-map.json` itself needs an update (e.g., adding a new `change_class` entry for "liveness probe added") — out of scope for this WP. Mention in the mission close commentary.

**Files**:
- Variable, depending on map output. Most likely:
- `docs/INDEX.md` (+1-3 lines for the new runbook + tracking issue)
- `docs/DEVELOPER_PORTAL.md` (+1-3 lines if applicable)

**Validation**:
- For each doc target listed by the map, either: (a) it's already updated as part of T023/T024, OR (b) it gains the new reference in this WP, OR (c) the WP commentary explains why no change was needed.
- No doc target named by the map is silently skipped.

---

## Test Strategy

No automated tests. Validation by:

1. JSON validity check on `service-inventory.json` after edits.
2. Manual visual review of `google-workspace-ops.md` — markdown renders cleanly.
3. Cross-reference check: every doc that mentions `credential-liveness-probe` references the same canonical path (`scripts/office2/credential-liveness-probe.{service,timer}` and the deploy script).
4. Frontmatter consistency: `last_updated` bumped on each modified doc.

## Definition of Done

- [ ] `service-inventory.json` has a new entry for `credential-liveness-probe.service` with the documented fields.
- [ ] JSON validity holds after the edit.
- [ ] `google-workspace-ops.md` §Common Issues gains the "automatic detection" callout in the Testing-app-7-day-cycle entry.
- [ ] `google-workspace-ops.md` frontmatter `last_updated` bumped; `updated_by` set.
- [ ] `signal-to-doc-map.json` consulted; all flagged `doc_targets` for our change classes are addressed or explicitly noted as no-action.
- [ ] No silent doc surface skipped per the CLAUDE.md "Discovery aid" directive.

## Risks

- **Stale references**: if WP04's unit-file names change after this WP's docs are written, references break. The single-mission merge convention + the WP04 dependency mitigate this.
- **JSON schema drift**: `service-inventory.json` may have evolving fields; check the most recent entries (newest by `deployed_by` issue number) to mirror the current shape.
- **Markdown link integrity**: links to `kitty-specs/credential-liveness-probe-01KTP9M8/spec.md` must resolve. Per `[[reference_obsidian_better_markdown_links]]` — the Better Markdown Links plugin in Obsidian may auto-wrap `(#anchor)` → `(<#anchor>)`. Don't fight the transform.
- **signal-to-doc-map gaps**: if the map is silent on "liveness probe added" as a sub-class, the WP-author should still be checking the broader `systemd-unit-added-or-modified` and `service-added-or-modified` entries.

## Reviewer Guidance

- Skim `service-inventory.json` for the new entry; verify field shape matches existing entries.
- Read the workspace runbook's §Common Issues "Refresh token expired" entry end-to-end; the new callout should fit naturally.
- Check that the recovery command in the runbook callout (`systemctl --user start credential-liveness-probe.service`) matches the actual unit name from WP04.
- For T025, verify the WP author actually ran the `signal-to-doc-map.json` query (per the CLAUDE.md mandate) — the WP commentary in the merge commit should list which doc targets were considered and why each was updated or skipped.
