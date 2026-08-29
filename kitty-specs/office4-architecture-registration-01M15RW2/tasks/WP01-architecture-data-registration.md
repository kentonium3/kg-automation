---
work_package_id: WP01
title: Architecture data registration
dependencies: []
requirement_refs:
- FR-006
- FR-007
- FR-008
planning_base_branch: feat/office4-architecture-registration
merge_target_branch: feat/office4-architecture-registration
branch_strategy: Planning artifacts for this mission were generated on feat/office4-architecture-registration. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/office4-architecture-registration unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-office4-architecture-registration-01M15RW2
base_commit: dd3fe303e578cdfb61bcc2d0aa250a3eb6dcafab
created_at: '2026-08-29T04:18:17.582476+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Authoritative data
history:
- at: '2026-08-29T04:10:34Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: docs/design/architecture/data/
create_intent: []
execution_mode: code_change
model: ''
owned_files:
- docs/design/architecture/data/network-topology.json
- docs/design/architecture/data/hardware-inventory.json
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – Architecture data registration

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `implementer-ivan`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objectives & Success Criteria

Register office4 in both authoritative architecture-data JSON files, at the correct detail
level, without touching the service inventory.

Done when:

- `network-topology.json` → `network.devices` has **four** entries, including office4.
- `hardware-inventory.json` → `hosts` has **four** entries, office4 **appended last** in
  the thin form.
- office2 is still `hosts[0]` and still the only rich entry.
- `service-inventory.json` is unchanged and still all-office2, proven by an assertion.
- `validate_architecture_data.py --strict` exits 0.

## Context & Constraints

- **Exact payloads**: [contracts/architecture-data-payloads.md](../contracts/architecture-data-payloads.md) C-1, C-2, C-3. **Copy the values verbatim — do not re-derive them.**
- **Record shapes and invariants**: [data-model.md](../data-model.md).
- **Why these values**: [research.md](../research.md) R-4.
- Tier 4 (Auto-Commit). No host, service, credential, or network change.
- JSON is authoritative; the markdown views that describe it are WP03's job, not yours.

⚠️ **The validator cannot protect you here.** Both payloads pass
`validate_architecture_data.py --strict` with `OK (0 findings)` whether `os` and
`hardware` are correct or nonsense. An earlier draft of this mission carried a
verified-false OS string that would have shipped silently. These two values get human eyes,
not just a green check.

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: `feat/office4-architecture-registration`
- **Merge target branch**: `feat/office4-architecture-registration`

## Subtasks & Detailed Guidance

### Subtask T001 – Add office4 to `network.devices`

- **Purpose**: record office4 as a tailnet device. Presence here means "exists on the
  network" and implies nothing about managed status.
- **File**: `docs/design/architecture/data/network-topology.json`
- **Steps**: append contract C-1's object to `network.devices` (currently 3 → 4):

  ```json
  {
    "hostname": "office4",
    "tailscale_ip": "100.112.83.28",
    "os": "linux"
  }
  ```

- **Notes**: `hostname` is the **Tailscale device name** (lowercase `office4`), not the
  system hostname (`Office4`). `os` is the coarse family `linux` here — the specific
  release goes in the hardware inventory. This mirrors how office2 is recorded in both files.
- **Do not touch**: `schema_version` (stays `1.2`), `tailscale_ssh`, `port_assignments`,
  `access_rules`. office4 enables no Tailscale SSH (`RunSSH: false`, research.md R-12) and
  exposes no port.

### Subtask T002 – Append office4 thin entry to `hosts`

- **Purpose**: record office4 in the device record. Every other tailnet device is already
  there; omitting office4 would make it the only one missing.
- **File**: `docs/design/architecture/data/hardware-inventory.json`
- **Steps**: **append** contract C-2's object to `hosts` (currently 3 → 4):

  ```json
  {
    "hostname": "office4",
    "role": "primary development machine",
    "hardware": "Framework Desktop (AMD Ryzen AI Max 300 Series)",
    "os": "Linux Mint 22.3 (Ubuntu 24.04 noble base)",
    "network": {
      "tailscale_ip": "100.112.83.28",
      "tailscale_hostname": "office4"
    }
  }
  ```

- **APPEND, do not insert.** `docs/runbooks/ollama-ops.md:30` reads `hosts[0].gpu`, so
  office2 must stay at index 0 (data-model.md invariant H-3). Nothing validates this.
- **Do not add** `cpu`, `ram_gb`, `kernel`, `gpu`, `bios`, `disks`, or `local_ip`.
  Those belong to the rich form, which is office2's alone. Adding them here would suggest
  office4 is a second managed host — the opposite of what this mission records.
- **Where the values came from** (do not re-derive, but know the provenance): `os` from
  `/etc/os-release`; `hardware` from `/sys/devices/virtual/dmi/id/{sys_vendor,product_name}`.
  **Never `uname -a`** — its `#28~24.04.1-Ubuntu` is the kernel build's provenance, and
  reading it as the distro is exactly the error research.md R-4 records.

### Subtask T003 – Bump metadata on both files

- **Purpose**: keep the files' own convention of recording when and why they changed.
- **Steps**: set `last_updated` to today's date on both; append a clause to `updated_by`
  naming `#909`, matching the existing descriptive style (read the current value first —
  it describes what changed and why, not just an issue number).
- **Do not** change `schema_version` on either file. Adding an array element uses the
  existing shape; no schema change occurs.

### Subtask T004 – Assert the service inventory is untouched

- **Purpose**: office4's absence from `service-inventory.json` is a **deliverable**, not an
  omission. Prove it rather than assuming it.
- **Steps**: run contract C-3's assertion:

  ```bash
  python3 -c "
  import json
  d = json.load(open('docs/design/architecture/data/service-inventory.json'))
  hosts = {s.get('host') for s in d['services']}
  assert hosts == {'office2'}, hosts
  print('OK: all', len(d['services']), 'services on office2 only')
  "
  ```

- **Validation**: must print `OK: all 47 services on office2 only`. Also confirm
  `git status` shows the file unmodified.

### Subtask T005 – Run the architecture validator (NFR-001)

- **Steps**: `python3 tooling/scripts/validate_architecture_data.py --strict`
- **`--strict` is required.** Without it the validator is warn-only and exits 0
  unconditionally, so the check could not fail. Expect `OK (0 findings)`.
- Note `--strict` still excludes rollout-advisory rules such as `max-age-missing` from
  exit status, so a clean run does not mean zero findings of every class.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Wrong `os` or `hardware` value ships silently | Values are fixed in contract C-2; copy verbatim. Do not consult `uname -a` |
| Inserting rather than appending breaks `hosts[0].gpu` | Append; verify `hosts[0].hostname == "office2"` after editing |
| Accidentally adding rich fields to office4 | Thin form only — five keys, no more |
| Editing the service inventory "for consistency" | It is explicitly out of scope; T004 proves it untouched |

## Review Guidance

- Confirm office4's `os` reads `Linux Mint 22.3 (Ubuntu 24.04 noble base)`, **not** Ubuntu
  24.04 — this is the specific error a prior draft made.
- Confirm `hardware` is a real model, not the hostname.
- Confirm office2 is still `hosts[0]` and still the only entry with `disks`/`bios`/`cpu`.
- Confirm both `schema_version` values are unchanged.
- Confirm the diff touches exactly two files.

## Activity Log

- 2026-08-29T04:10:34Z – system – Prompt created.
