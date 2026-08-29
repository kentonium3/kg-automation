# Research: Register office4 in the Architecture

**Phase**: 0 | **Date**: 2026-08-29 | **Mission**: `office4-architecture-registration-01M15RW2`
**Revised**: 2026-08-29 after the post-plan adversarial review (see R-11)

Every finding below was taken from the working tree or the live host, not from issue
#909's description of them. That distinction mattered twice: #909 carried a false premise
(R-1), and this document's own first draft carried one (R-4).

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

**Corroboration**: `docs/design/architecture/change-control.md:20` already states the rule
directly — `| New hardware or host | hardware-inventory.json | physical-topology.md |`.

**Alternatives considered**: (a) honour #909 literally — rejected, it rests on a verified
false premise and produces the outcome the issue argues against; (b) give office4 a rich
office2-class entry — rejected, it visually equates office4 with the managed host and
commits us to maintaining host detail for a machine deliberately outside the substrate.

**Approval**: raised with Kent during specify discovery; correction approved. Recorded as
FR-007, with FR-012 correcting the issue thread.

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

**Decision**: cite all five in ADR 0008, using **repo-root-relative paths**, not #909's
shorthand.

| Claim | Verified |
|---|---|
| `deploys/schema/manifest-v1.schema.json` has no `host` field | ✅ zero occurrences of `"host"` |
| `scripts/deploy/lib/deploylock.py:41` | ✅ `DEFAULT_LOCK_PATH = Path("/data/services/deploy/locks/office2-checkout.lock")` |
| `scripts/deploy/felix-deployer/_tick.py:59` | ✅ `DEFAULT_REPO_ROOT = pathlib.Path("/home/claude/kg-automation")` |
| `scripts/deploy/felix-deployer/rebaseline.py:49` | ✅ "felix-deployer runs ON office2, so the SSH wrapper … must be stripped" |
| `scripts/deploy/lib/tier.py:73` | ✅ `summary="Tier 0 deploys must be manual via ssh office2-kgale"` |

**Refinement 1 — wording.** `_tick.py:59` is a *default* with an override at line 404
(`repo_root = pathlib.Path(repo_root) if repo_root else DEFAULT_REPO_ROOT`, documented as
"override the canonical checkout (test fixtures)"). The ADR must say "defaults to office2's
path", not "hardcodes". The claim survives — nothing in the pipeline supplies another value —
but an ADR read as settled truth should not overstate.

**Refinement 2 — the schema claim is stronger than stated.**
`deploys/schema/manifest-v1.schema.json:7` sets `"additionalProperties": false` at the top
level. A manifest naming a host is not merely unsupported; it is **rejected by the schema**.
The ADR should say so — it is a materially stronger argument for the same conclusion at the
cost of one clause.

**Refinement 3 — citation location.** The `rebaseline.py:49` citation lands inside the
module docstring, not executable code. Worth stating, so a reader is not confused by finding
prose where they expected a statement.

---

## R-4 — office4's live identity  ⚠️ CORRECTED

**Decision**: record hostname `office4`, `tailscale_ip` `100.112.83.28`, network-topology
`os` `linux`, hardware-inventory `os` **`Linux Mint 22.3 (Ubuntu 24.04 noble base)`**, and
`hardware` **`Framework Desktop (AMD Ryzen AI Max 300 Series)`**.

**Correction.** This section's first draft recorded the OS as "Ubuntu 24.04 LTS", citing
`uname -a`. That was wrong. `uname -a` returns `#28~24.04.1-Ubuntu`, which is the *kernel
build's* Ubuntu provenance, not the distribution. The actual distro:

```
$ lsb_release -ds        → Linux Mint 22.3
$ cat /etc/os-release    → NAME="Linux Mint"  VERSION="22.3 (Zena)"  ID=linuxmint
```

Mint 22.3 is noble-based, so the original string was not a lie — it simply was not the
answer to the question asked. **Standard of proof going forward: `/etc/os-release`, never
`uname -a`, for a distribution claim.** This is the repo's recurring defect class — a check
whose output cannot distinguish the thing measured from the thing wanted — and it is
recorded here rather than quietly fixed, because it occurred inside the very Phase 0 whose
stated objective is to verify claims before they become ADR assertions.

**Hardware model.** Readable without sudo, contrary to the first draft's assumption that
`dmidecode` and therefore escalation would be needed:

```
/sys/devices/virtual/dmi/id/sys_vendor   → Framework
/sys/devices/virtual/dmi/id/product_name → Desktop (AMD Ryzen AI Max 300 Series)
```

Sibling entries all carry a real model (`Dell XPS 8700`, `MacBook Pro`,
`iPhone 14 Pro Max`), so writing the hostname into that field would break the file's only
convention for it. There is no deferral: the value is known.

**Naming.** The *Tailscale device name* (`office4`, lowercase) is the identifier, not the
system hostname (`Office4`, capitalised). This follows the `kents-macbook-pro` precedent.

**Structural note**: `devices` is nested at `network.devices`, not at the top level.

---

## R-5 — no rebaseline obligation

**Decision**: the change records `Rebaseline: not required — documentation and architecture
metadata only`. Which *commit* carries that line is settled in R-10.

**Rationale**: `audited-surfaces.json` was inspected directly. It contains no reference to
`architecture/data`, `network-topology`, or `hardware-inventory`. Its audited surfaces are
host-state baselines — brew packages and taps, hosts hash, crontabs, listening ports, docker
images, openclaw config and agent prompts, systemd units, deploy scripts, Python dependency
manifests, committed SSH key material. #909's claim is confirmed.

---

## R-6 — ADR conventions to follow

**Decision**: ADR 0008, matching the established shape of 0001–0007.

`docs/design/architecture/adr/` ends at `0007-retire-vikunja-felix-bot.md`. Sibling
frontmatter:

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

then an H1 repeating the title, `**Status**: Accepted`, `**Date**:`,
`**Deciders**: Kent Gale`, then `## Context`. `validate_docs.py` enforces the frontmatter.

---

## R-7 — where an ADR actually gets registered  ⚠️ CORRECTS THE PLAN

**Decision**: the required registration target is
`docs/design/architecture/adr/README.md` — the canonical **ADR Index**, carrying a table of
0001–0007 with title, status, and date. It was named in neither #909 nor the first draft of
this mission's FR-010, nor in `signal-to-doc-map.json`.

Measured ADR references per file:

| File | occurrences of "adr" | Reality |
|---|---|---|
| `docs/design/architecture/adr/README.md` | 5 | **The ADR index.** Must be updated or it shows 0001–0007 forever |
| `docs/INDEX.md` | 14 | Genuinely lists ADRs (lines 63–74) |
| `docs/DEVELOPER_PORTAL.md` | 0 | No ADR surface at all |
| `docs/design/architecture/README.md` | 0 | Has Documents / Data Files / Schema Contracts tables; no ADR list |

FR-010 as first drafted would have bolted an ADR mention onto two files that index no ADRs
while leaving the actual index stale. The two zero-hit files remain targets — they are named
by the signal-to-doc map — but "register" must mean something concrete and modest for them
(a pointer), not "add to the ADR list they do not have".

---

## R-8 — three adjacent surfaces this mission breaks or fails to fix

Approved for inclusion by Kent during plan (decision `01M15TBPHB2JRXFD5ZZCQC0PHN`).

**R-8a — `signal-to-doc-map.json` omits `hardware-inventory.json`.** No change class lists
it in `doc_targets`; `network-topology-changed` names only `network-topology.json`,
`physical-topology.md`, `security-posture.md`, `adr/0004`, `phone-termius-setup.md`. Yet
`change-control.md:20` states the rule plainly (R-1). The narrative doc knows and the
machine-readable map does not — and repo doctrine says the machine-readable version wins, so
the map is **authoritative and wrong**. CLAUDE.md instructs every spec/plan agent to derive
doc targets from that map, so the omission reproduces this mission's own near-miss on the
next device addition. Fixing it converts a one-off correction into a durable one.

**R-8b — `glossary.md` will contradict the ADR.** Line 15 defines Tailscale as connecting
"office2, Mac, and iPhone" — three devices, stale on merge. It also carries no entry for any
of the four terms the spec's Domain Language section declares canonical (*managed host*,
*unmanaged peer*, *attended/unattended*, *thin entry*), which would leave them canonical for
the mission's duration and no longer.

**R-8c — `CLAUDE.md` will contradict the ADR.** Its Platform table (line 39) lists
`| MacBook Pro | Primary authoring and interaction |` with no office4 row, while this
mission's own `purpose_context` calls office4 Kent's primary development machine. Every
session loads CLAUDE.md at startup; almost none opens an ADR unprompted. Leaving the
highest-traffic surface asserting the opposite defeats the mission's stated purpose.

---

## R-9 — what the validators actually check  ⚠️ CORRECTS THE SPEC

Load-bearing, because two spec thresholds were written against capabilities that do not exist.

**`tooling/scripts/validate_docs.py` does not check links.** Its docstring: *"Lightweight:
only checks frontmatter and secrets."* Zero occurrences of "link" in the file. It validates
required frontmatter keys, four enums, `owners`/`revision` formats, and runs a secret scan.
There is no lychee, no markdown-link-check, and no link step in `.github/workflows/docs-ci.yml`.
NFR-004's "0 broken links reported by the docs validator" was therefore satisfiable by a
tool structurally incapable of reporting one. The same applies to the "heading hierarchy"
quality gate.

**`validate_architecture_data.py` is warn-only by default.** Its docstring: *"Findings are
reported but the process exits 0, so wiring this into CI cannot turn the build red."* The
real gates both pass `--strict` — `.githooks/pre-commit:40` and `docs-ci.yml:31`
(`--strict --github`). NFR-001's threshold omitted `--strict`, making it another check that
cannot fail. #909's post-change verification has the identical defect and is corrected in
the same comment FR-012 requires.

**What the validators *do* catch, verified**: `front_matter()` calls
`err('Missing YAML front-matter', p)` when the fence is absent, so NFR-003 is not vacuous.

**What no validator catches**: a wrong *value* in a correctly-shaped field. The C-1/C-2
payloads were applied verbatim to a copy of the data store and
`validate_architecture_data.py --strict` returned `OK (0 findings)`, exit 0 — which is both
the proof that the payloads are valid and the proof that R-4's original wrong OS string
would have landed silently.

---

## R-10 — merge mechanics: which commit carries what

**`spec-kitty merge` cannot set a commit message.** Its options are `--strategy`
(default squash), `--target`, `--delete-branch`, `--remove-worktree`, `--push`, `--dry-run`,
`--json`. The message is composed by spec-kitty.

**The mission's merge target is the feature branch**, not main (`topology: single_branch`,
`target_branch: feat/office4-architecture-registration`). Kent takes `feat → main`
separately with his own message.

**Therefore**: the `Rebaseline:` line (R-5) rides **Kent's `feat → main` merge commit**, not
the mission's internal merge. Amending a spec-kitty merge commit would be a prohibited
manual git workaround; putting the line on a work-package commit would leave it undiscoverable
by a `git log -1` check. This must be stated in the plan and the verification moved out of
the mission's own gate, rather than left implicit.

**Docs CI likewise does not fire on the mission merge.** `.github/workflows/docs-ci.yml`
triggers on `push`/`pull_request` to `main` only. The substance is still covered at commit
time by `.githooks/pre-commit:40-41`, which runs both validators on every commit; but
"Docs CI green" is satisfied at Kent's `feat → main` push, not at mission close.

---

## R-11 — provenance of these corrections

R-3 (refinements), R-4 (the OS correction), R-7, R-8, R-9, R-10, and the `hosts[0]`
invariant in data-model.md all originate in the **mandatory post-plan adversarial review**.
Codex was unauthenticated on office4 at the time (kg-automation#923), so the standing Opus
fallback ran instead; Codex was authorised afterwards and re-reviewed the corrected
artifacts. Every claim above was independently re-verified against the working tree or the
live host before being folded in — the review was treated as a lead, not as authority.

---

## R-12 — four-device reconciliation, verified today

`tailscale status` returns exactly four devices, and all four IPs match both JSON files
after this mission's edits:

| Tailscale IP | device | os |
|---|---|---|
| `100.92.197.90` | office2 | linux |
| `100.71.19.66` | kents-macbook-pro | macOS |
| `100.109.208.6` | iphone-14-pro-max | iOS |
| `100.112.83.28` | office4 | linux |

**Tailscale SSH on office4 is off** — `tailscale debug prefs` → `"RunSSH": false`. This is
the fact that makes the ADR-0004 "no change" affirmation correct rather than assumed:
office4 joining as a member device does widen the accept ACL's nominal scope
(`autogroup:member` → `autogroup:self` → `autogroup:nonroot, root`), and only RunSSH being
false makes that immaterial. `network-topology.json`'s own `tailscale_ssh.verified_via`
field names this exact command as the standard of proof for office2, so the same standard
is now met for office4.

---

## Supply chain

No dependency is added, upgraded, or removed. PyYAML and jsonschema already appear in
`requirements.txt` and are used only by the pre-existing validators. The
`051-supply-chain-install-safety` directive has no surface to act on here. No adversarial
challenge pass is required, because no security-impacting dependency decision is made.

## Adversarial evidence

No contested finding was dropped. Dispositions from the post-plan review: B1, B2, B3, B4,
B5, B6, H1, H3, H6, H7, H8 and A1–A5 **accepted and folded in**; H2, H4, H5 **accepted after
a scope decision by Kent** (decision `01M15TBPHB2JRXFD5ZZCQC0PHN`); the reviewer's
"verified sound" list is recorded in R-9 and R-12 so it is not re-litigated. The one place
this mission departs from its source issue (R-1) is recorded with evidence, rejected
alternatives, and approval rather than applied quietly.
