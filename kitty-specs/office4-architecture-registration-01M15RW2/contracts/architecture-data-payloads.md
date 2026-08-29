# Contract: architecture-data payloads

**Phase**: 1 | **Date**: 2026-08-29

The exact content to be added, so implementation is mechanical and review is a diff
comparison rather than a judgement call. Values are from the live host (research.md R-4).

---

## C-1 — `docs/design/architecture/data/network-topology.json`

Append to `network.devices` (currently 3 entries → 4):

```json
{
  "hostname": "office4",
  "tailscale_ip": "100.112.83.28",
  "os": "linux"
}
```

Also update the file's metadata:

- `last_updated` → the merge date
- `updated_by` → append a clause naming #909, matching the existing style of describing
  what changed and why

Do **not** change `schema_version` (currently `1.2`), `tailscale_ssh`, `port_assignments`,
or `access_rules`. office4 enables no Tailscale SSH and exposes no port.

---

## C-2 — `docs/design/architecture/data/hardware-inventory.json`

Append to `hosts` (currently 3 entries → 4), in the **thin** form:

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

Both values are settled — there is **no deferral and no judgement call here**:

- `os` comes from `/etc/os-release` (`NAME="Linux Mint"`, `VERSION="22.3 (Zena)"`,
  `ID=linuxmint`). Do **not** derive it from `uname -a`: that string
  (`#28~24.04.1-Ubuntu`) is the kernel build's Ubuntu provenance, and reading it as the
  distro is exactly the error an earlier draft of this contract made (research.md R-4).
- `hardware` comes from `/sys/devices/virtual/dmi/id/sys_vendor` and `product_name`.
  World-readable; **no sudo, no `dmidecode`, no escalation to Kent.** Every sibling entry
  holds a real model (`Dell XPS 8700`, `MacBook Pro`, `iPhone 14 Pro Max`), so putting the
  hostname in this field would break the file's only convention for it.

Other rules for the implementer:

- Do **not** add `cpu`, `ram_gb`, `kernel`, `gpu`, `bios`, or `disks`. Those belong to
  the rich form, reserved for the managed host (data-model.md invariant H-1).
- Do **not** add `local_ip`. Peer entries carry only Tailscale networking.
- **Append**, do not insert. `docs/runbooks/ollama-ops.md:30` references `hosts[0].gpu`,
  so office2 must stay at index 0 (data-model.md invariant H-3).
- Update `last_updated` / `updated_by`; leave `schema_version` at `1.0`.

⚠️ **No validator catches a wrong value in a correctly-shaped field.** Both payloads here
were applied verbatim to a copy of the data store and `validate_architecture_data.py
--strict` returned `OK (0 findings)`, exit 0. That proves the shapes are valid *and* that a
wrong `os` or `hardware` string would land silently. These two values get human eyes.

## C-3 — `docs/design/architecture/data/service-inventory.json`

**No change.** This is a contract of omission, and it is verifiable:

```bash
python3 -c "
import json
d = json.load(open('docs/design/architecture/data/service-inventory.json'))
hosts = {s.get('host') for s in d['services']}
assert hosts == {'office2'}, hosts
print('OK: all', len(d['services']), 'services on office2 only')
"
```

Must pass before and after the mission.

---

## C-4 — Post-conditions (all must hold at merge)

| # | Condition | Check |
|---|---|---|
| 1 | Four devices in the topology | `len(network.devices) == 4`, hostnames include `office4` |
| 2 | Four hosts in the hardware inventory | `len(hosts) == 4`, office4 present in thin form |
| 3 | Exactly one rich host entry | only `office2` carries `disks`/`bios`/`cpu` |
| 4 | Zero office4 services | C-3 assertion passes |
| 5 | Recorded IP matches the live host | equals `tailscale ip -4` on office4 |
| 6 | Hostnames agree across both files | `hosts[].hostname` ⊇ `network.devices[].hostname` |
| 7 | Neither `schema_version` changed | `1.2` and `1.0` respectively |
| 8 | Both validators pass | `validate_architecture_data.py --strict`, `validate_docs.py` |

---

## C-5 — ADR 0008 content contract

The ADR must let a reader answer all five questions without leaving the document:

1. What are the three machines, and which is managed?
2. What is the rule for deciding where a workload goes? *(the attended/unattended test,
   with both worked cases)*
3. Why is office4 not a managed host? *(five citations, R-3)*
4. What must office4 never do? *(no `kg-automation` checkout at a felix-deployer-recognisable
   path, and why — `self-pull` makes "which checkout is the deploy" ambiguous)*
5. Why are there no `claude`/`codex` Unix users on office4? *(the office2 `claude` user
   exists because the agent is a remote actor on a host it does not live on — attribution
   plus blast radius; office4 inverts that, and a separate user would firewall the agent
   from the repos, git identity, and config trees it needs)*

Per R-3, phrase the `_tick.py` citation as "defaults to office2's path" rather than
"hardcodes" — the default is overridable at line 404, and nothing in the pipeline supplies
another value. The claim survives; the overstatement does not belong in an ADR.

---

## C-6 — Documentation registration targets (corrects the original FR-010)

Measured ADR references per file, so "register" means something different in each:

| File | "adr" hits | What "register" means here |
|---|---|---|
| `docs/design/architecture/adr/README.md` | 5 | **Required.** This is the ADR Index — a table of 0001–0007 with title, status, date. Add a 0008 row. Omitting this leaves the index permanently stale. |
| `docs/INDEX.md` | 14 | Add 0008 to the ADR list (lines 63–74). |
| `docs/DEVELOPER_PORTAL.md` | 0 | **No ADR surface exists.** Add a single pointer to the ADR index — do not invent an ADR list. |
| `docs/design/architecture/README.md` | 0 | **No ADR surface exists.** Its tables are Documents / Data Files / Schema Contracts. Add a single pointer to the ADR index. |

## C-7 — Adjacent-surface edits (approved scope addition)

Decision `01M15TBPHB2JRXFD5ZZCQC0PHN`.

**`docs/design/architecture/glossary.md`**

- Line 15's `Tailscale` entry currently reads "…between office2, Mac, and iPhone."
  Change to name four devices including office4.
- Add entries for the four canonical terms: **managed host**, **unmanaged peer**,
  **attended / unattended**, **thin entry**. Definitions come from spec.md's Domain
  Language table; keep the file's existing `| **Term** | definition |` shape.
- Consider whether the `office2` entry ("Always-on hub for all services") now needs the
  managed-host framing so it does not read as "the only machine". Affirm either way.

**`CLAUDE.md`**

- Platform table (line 39 area): add a row for office4. It must not read as a managed
  host — office2 remains "always-on hub"; office4 is the attended development machine.
- Add a one-line pointer to ADR 0008 near that table.
- ⚠️ `CLAUDE.md` is repo-root, not under `docs/`, so `validate_docs.py` frontmatter rules
  may not apply to it. Do not add frontmatter it does not already have.

**`docs/design/architecture/data/signal-to-doc-map.json`**

- Add `docs/design/architecture/data/hardware-inventory.json` to the `doc_targets` array
  of the `network-topology-changed` change class (`match.source == "mission-architecture-impact"`).
- This aligns the machine-readable map with `change-control.md:20`, which already says new
  hardware or host → `hardware-inventory.json`. Repo doctrine makes the JSON authoritative,
  so today the authoritative file is the wrong one.
- Re-run `validate_architecture_data.py --strict` afterwards — this file is itself
  architecture data.

## C-8 — Where the `Rebaseline:` line goes

`spec-kitty merge` has **no commit-message option** (`--strategy`, `--target`,
`--delete-branch`, `--remove-worktree`, `--push`, `--dry-run`, `--json` only), and the
mission merges to `feat/office4-architecture-registration`, not `main`.

So the line

```
Rebaseline: not required — documentation and architecture metadata only
```

rides **Kent's `feat → main` merge commit**. Do not amend the spec-kitty merge commit —
that is a prohibited manual git workaround. Do not put it on a work-package commit — a
`git log -1` check would not find it. This is outside the mission's own gate by design;
say so in the handoff rather than leaving it implicit.
