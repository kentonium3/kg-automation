# Research: Register office4 in the Architecture

**Phase**: 0 | **Date**: 2026-08-29 | **Mission**: `office4-architecture-registration-01M15RW2`

Every finding below was taken from the working tree or the live host, not from issue
#909's description of them. That distinction mattered: one of #909's premises was false.

---

## R-1 — `hardware-inventory.json` is a device record, not a managed-host record

**Decision**: register office4 in `hardware-inventory.json` as a thin entry, contradicting
issue #909's explicit success criterion that office4 be **absent** from it.

**Rationale**: #909 asserts the file is "the managed-host record" from which the MacBook Pro
is absent. Direct inspection disproves this — its `hosts` array holds all three devices:

| hostname | role | field count |
|---|---|---|
| `office2` | always-on hub | 11 |
| `kents-macbook-pro` | authoring and interaction endpoint | 5 |
| `iphone-14-pro-max` | mobile capture and task monitoring | 5 |

The file records *devices* at two detail levels — rich for the managed host, thin for
unmanaged peers. Excluding office4 would make it the only tailnet device missing from the
device record, which is precisely the undocumented-infrastructure drift #909 exists to
prevent (its own stated cost-of-doing-nothing).

**Alternatives considered**: (a) honour #909 literally — rejected, it rests on a verified
false premise and produces the outcome the issue argues against; (b) give office4 a rich
office2-class entry — rejected, it visually equates office4 with the managed host and
commits us to maintaining host detail for a machine deliberately outside the substrate.

**Approval**: raised with Kent during specify discovery; correction approved. Recorded as
FR-007, with FR-012 correcting the issue thread so the next reader of #909 is not misled.

---

## R-2 — the `service-inventory.json` half of #909's claim is correct

**Decision**: keep office4 out of `service-inventory.json`, and treat that absence as a
verified positive outcome rather than an omission.

**Rationale**: all **47** service entries name `host: office2`. There is no precedent for a
non-office2 service row, and office4 runs no registered service. This is the file that
actually carries the managed/unmanaged boundary — which is what makes R-1 safe. Registering
office4 as a *device* implies nothing about managed status, exactly as it implies nothing
for the Mac.

---

## R-3 — the single-host evidence in #909 is accurate, 5 of 5

**Decision**: cite all five in ADR 0008.

**Rationale**: each was checked against the working tree before being made a requirement.

| Claim | Verified |
|---|---|
| `manifest-v1.schema.json` has no `host` field | ✅ zero occurrences of `"host"` in `deploys/schema/manifest-v1.schema.json` |
| `lib/deploylock.py:41` names the lock `office2-checkout.lock` | ✅ exact line: `DEFAULT_LOCK_PATH = Path("/data/services/deploy/locks/office2-checkout.lock")` |
| `felix-deployer/_tick.py:59` hardcodes `DEFAULT_REPO_ROOT` | ✅ exact line: `DEFAULT_REPO_ROOT = pathlib.Path("/home/claude/kg-automation")` — note it is a *default* with an override at line 404, so the ADR should say "defaults to office2's path", not "hardcodes with no override" |
| `rebaseline.py:49` strips `ssh office2-claude` | ✅ `scripts/deploy/felix-deployer/rebaseline.py` documents it: "felix-deployer runs ON office2, so the SSH wrapper … must be stripped" |
| `lib/tier.py:73` embeds `ssh office2-kgale` | ✅ exact line: `summary="Tier 0 deploys must be manual via ssh office2-kgale"` |

**Refinement**: the `_tick.py` wording is tightened in the ADR. The substance of the claim
holds — the default is office2's path and nothing in the pipeline supplies another — but
"hardcodes" overstates it, and an ADR read as settled truth should not overstate.

---

## R-4 — office4's live identity

**Decision**: record hostname `office4`, `tailscale_ip` `100.112.83.28`, `os` `linux`.

**Rationale**: taken from the host itself:

- `tailscale ip -4` → `100.112.83.28` (matches #909)
- `tailscale status` → `100.112.83.28  office4  kentgale@  linux`
- `hostname` → `Office4`; `uname -a` → Linux 7.0.0-28-generic, Ubuntu 24.04

**Naming**: the *Tailscale device name* (`office4`, lowercase) is the identifier, not the
system hostname (`Office4`, capitalised). This follows the `kents-macbook-pro` precedent —
that entry uses the Tailscale device name too. `os` is recorded as `linux` lowercase,
matching how office2 is recorded in `network.devices`.

**Structural note**: `devices` is nested at `network.devices`, not at the top level.
#909's shorthand ("add office4 to `devices`") could be misread as a top-level key.

---

## R-5 — no rebaseline obligation

**Decision**: the merge commit records `Rebaseline: not required — documentation and
architecture metadata only`.

**Rationale**: `audited-surfaces.json` was inspected directly rather than trusting #909's
assertion. It contains no reference to `architecture/data`, `network-topology`, or
`hardware-inventory`. Its audited surfaces are host-state baselines — brew packages and
taps, hosts hash, crontabs, listening ports, docker images, openclaw config and agent
prompts, systemd units, deploy scripts, Python dependency manifests, committed SSH key
material. Architecture-data JSON is not among them. #909's claim is confirmed.

---

## R-6 — ADR conventions to follow

**Decision**: ADR 0008, matching the established shape of 0001–0007.

**Rationale**: `docs/design/architecture/adr/` ends at `0007-retire-vikunja-felix-bot.md`,
so 0008 is the next free number. Sibling ADRs carry this frontmatter:

```yaml
---
title: ADR-000N — <title>
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: 'YYYY-MM-DD'
version: v1.0
audience: agents_and_humans
tags: [<issue numbers>]
---
```

followed by an H1 repeating the title, then `**Status**: Accepted`, `**Date**:`,
`**Deciders**: Kent Gale`, then `## Context`. `validate_docs.py` enforces the frontmatter,
so a missing or unknown enum value fails the pre-commit gate.

**Note on `owners`**: the sibling convention uses `["@kentonium3"]`. The repo's
no-`@mentions` rule targets prose that would notify a person; this is a structured
frontmatter field following existing convention, and deviating from it would break the
pattern the validator and readers expect.

---

## R-7 — environment, and why it delayed this mission

**Finding**: not a spec-kitty fault and not a mission concern, but recorded because it cost
real time and is a precondition for anyone else running this mission on office4.

office4 was missing three documented setup steps, which together blocked every commit:
`core.hooksPath` unset (so the legacy `tooling/hooks/pre-commit` was active instead of the
`.githooks` #678 doc-validation gate); that legacy hook hardcodes bare `python3` with no
`${PYTHON:-}` seam; and direnv was installed but never hooked into bash, so `python3`
resolved to system 3.13.15 without PyYAML rather than the repo `.venv` (3.12.3, PyYAML
6.0.3). Fixed canonically and tracked as kg-automation#923.

Separately, spec-kitty's specify runbook is internally contradictory on this build — its
Decision Moment Protocol needs a mission handle that its own Discovery Gate runs before
creating. Fixed upstream (#3619) but not in 3.2.6rc2; tracked as kg-automation#922, and the
pre-known workaround from upstream #3434 was applied rather than improvising.

---

## Supply chain

No dependency is added, upgraded, or removed. PyYAML and jsonschema already appear in
`requirements.txt` and are used only by the pre-existing validators. The
`051-supply-chain-install-safety` directive has no surface to act on here. No adversarial
challenge pass is required, because no security-impacting dependency decision is made.

## Adversarial evidence

No contested findings were dropped. R-1 is the one place this mission departs from its
source issue, and it is recorded with its evidence, its rejected alternatives, and its
approval rather than being applied quietly.
