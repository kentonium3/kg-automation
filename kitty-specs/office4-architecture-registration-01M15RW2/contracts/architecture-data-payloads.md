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
  "hardware": "office4",
  "os": "Ubuntu 24.04 LTS",
  "network": {
    "tailscale_ip": "100.112.83.28",
    "tailscale_hostname": "office4"
  }
}
```

Notes for the implementer:

- `role` should read as a peer role, parallel to the Mac's "authoring and interaction
  endpoint". "primary development machine" is the intent; adjust wording if a better
  phrase fits the file's voice, but do **not** use language implying managed status
  (avoid "host", "server", "hub").
- `hardware` is a model description. The placeholder above is weak — **the implementer
  should fill in the actual model** (from `sudo dmidecode -s system-product-name`, or
  from Kent). If the real model cannot be determined without escalation, keep it
  descriptive and honest rather than inventing a model string.
- Do **not** add `cpu`, `ram_gb`, `kernel`, `gpu`, `bios`, or `disks`. Those belong to
  the rich form, which is reserved for the managed host (data-model.md invariant H-1).
- Do **not** add `local_ip`. Peer entries carry only Tailscale networking.
- Update `last_updated` / `updated_by`; leave `schema_version` at `1.0`.

---

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
