# Data Model: Register office4 in the Architecture

**Phase**: 1 | **Date**: 2026-08-29

This mission adds no database and no runtime entity. The "data model" is the record
shape of the two architecture-data JSON files it edits. Both are authoritative over
their narrative Markdown views (charter policy), so their shapes are contracts.

---

## Entity: Tailnet Device (`network-topology.json` → `network.devices[]`)

A device reachable on the tailnet. Presence here means "exists on the network", nothing more.

| Field | Type | Required | Notes |
|---|---|---|---|
| `hostname` | string | yes | The **Tailscale device name**, lowercase. Not the OS hostname. |
| `tailscale_ip` | string (IPv4) | yes | From `tailscale ip -4` on the device. |
| `os` | string | yes | Existing values: `linux`, `macOS`, `iOS`. office4 is `linux`. |

**Invariant D-1**: every device on the tailnet appears exactly once. After this mission
the array has four entries.

**Invariant D-2**: presence in this array implies nothing about managed status. Three of
the four entries are unmanaged peers.

---

## Entity: Hardware Host (`hardware-inventory.json` → `hosts[]`)

A physical device, recorded at one of two detail levels.

### Thin form — unmanaged peers (the shape office4 takes)

| Field | Type | Required | Notes |
|---|---|---|---|
| `hostname` | string | yes | Tailscale device name, matching the topology entry. |
| `role` | string | yes | Short human phrase, e.g. "authoring and interaction endpoint". |
| `hardware` | string | yes | Real model, from `/sys/devices/virtual/dmi/id/{sys_vendor,product_name}` (world-readable, no sudo). Never the hostname. |
| `os` | string | yes | Specific release, e.g. `Ubuntu 24.04 LTS`, `Linux Mint 22.3 (Ubuntu 24.04 noble base)`. Source of truth is `/etc/os-release` — **not** `uname -a`, whose kernel build string names Ubuntu even on a Mint host. |
| `network` | object | yes | `{ tailscale_ip, tailscale_hostname }` for peers. |

### Rich form — the managed host (office2 only; office4 does NOT take this shape)

Adds `cpu`, `ram_gb`, `kernel`, `gpu`, `bios`, `disks`, and a `network` that also carries
`local_ip`. Reserved for the machine whose host state Felix actually manages and audits.

**Invariant H-1**: exactly one host uses the rich form. Adding a second would assert a
second managed host, which is the decision this mission records *against*.

**Invariant H-2**: `hosts[].hostname` and `network.devices[].hostname` agree for every
device present in both.

**Invariant H-3 — the array is positionally consumed.** `docs/runbooks/ollama-ops.md:30`
references `hosts[0].gpu`. office2 must remain `hosts[0]` for as long as any positional
reference exists, so new entries are **appended**, never inserted. Nothing validates this;
it is a convention a reordering edit would silently break.

**Note on `os` divergence**: `network.devices[].os` uses a coarse family (`linux`) while
`hosts[].os` uses a specific release (`Ubuntu 24.04 LTS`). This is existing convention —
office2 is `linux` in one and `Ubuntu 24.04 LTS` in the other. office4 follows it rather
than normalising, since normalising would be an unrelated change to a file this mission
should touch minimally.

---

## Entity: Registered Service (`service-inventory.json` → `services[]`)

**Not modified by this mission.** Documented here only to state the invariant.

**Invariant S-1**: every entry has `host: office2`. All 47 currently do. This file, not
the device record, is what carries the managed/unmanaged boundary — which is what makes
registering office4 in the hardware inventory safe.

---

## Entity: Architecture Decision Record

| Field | Constraint |
|---|---|
| Number | `0008` — next free; `adr/` ends at 0007 |
| Filename | `docs/design/architecture/adr/0008-<kebab-slug>.md` |
| Frontmatter | `title`, `doc_type: reference`, `status: approved`, `owners`, `last_updated`, `version`, `audience: agents_and_humans`, `tags` |
| Body | H1 repeating title, then `**Status**: Accepted`, `**Date**`, `**Deciders**`, then `## Context` |

**Invariant A-1**: frontmatter enum values must already exist in
`docs/design/standards/allowed-values.json`, or `validate_docs.py` fails the commit.

**Invariant A-2**: ADR numbers are never reused and never renumbered.

---

## Shared metadata fields

Both edited JSON files carry `schema_version`, `last_updated`, `updated_by`.

**Invariant M-1**: any content edit updates `last_updated` (ISO date) and appends the
driving issue to `updated_by`, matching the existing convention of naming the issue that
caused the change.

**Invariant M-2**: `schema_version` is **not** bumped. Adding an array element uses the
existing shape; no schema change occurs.
