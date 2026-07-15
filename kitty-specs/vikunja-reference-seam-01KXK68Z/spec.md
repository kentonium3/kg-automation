# Feature Specification: Felix Vikunja reference-resolution seam

**Mission**: vikunja-reference-seam-01KXK68Z
**Branch**: feat/vikunja-reference-seam
**Status**: Draft
**Issue**: kentonium3/kg-automation#748 (epic #747)

## Overview

Felix resolves Vikunja projects and labels ad-hoc today — by title in some
places, by hardcoded id in others — with no single source of truth. That
fragility silently broke inbox routing when the #714 Vikunja reset deleted a
project: a by-title lookup for a now-deleted project failed, and captured items
were lost without a visible error (#743). This feature consolidates every Felix
project/label reference into one declared, validated registry that resolves
against the locked post-reset names and **fails loud** when a reference cannot be
resolved, so Felix stays correct across Vikunja structure changes and the
downstream routing / atomicity / validation work (#745 / #746 / #749) can build
on a stable foundation.

## User Scenarios & Testing

**Primary actor:** a Felix helper or agent that needs to act on a Vikunja
project or label (e.g. file a captured item into "Inbox", label a task
`q:schedule`, scope a habits query).

- **Happy path:** the helper asks the registry for the identity of a logical
  name ("Inbox"); the registry returns the correct owner-scoped identity; the
  helper proceeds. No live project/label listing is required on this path.
- **Missing reference (exception):** the logical name is not declared, or its
  declared identity no longer exists in Vikunja. The helper receives a typed,
  descriptive failure and stops — it never silently writes to a wrong project or
  returns an empty result. (This is the #743 regression guard.)
- **Structure drift (exception):** a Vikunja reorg renames or deletes a
  referenced project/label. The next validation run reports the broken reference
  by name, loudly, so the operator updates the registry in one place.

## Requirements

### Functional

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | A single declared registry maps every logical Vikunja project and label name Felix uses to its Vikunja identity (id and/or selector). | Planned |
| FR-002 | All Felix code resolves Vikunja projects and labels exclusively through the registry; no code resolves a project/label by ad-hoc title match or by a literal hardcoded id. | Planned |
| FR-003 | Resolving a logical name that is undeclared, or whose declared identity is absent in Vikunja, raises a typed descriptive error; the system never silently returns an empty result or acts on a wrong target. | Planned |
| FR-004 | A validation routine checks the declared registry against live Vikunja and reports, loudly, any declared name that is missing or whose recorded identity no longer matches (drift). | Planned |
| FR-005 | The existing resolution call sites — someday routing, inbox-project lookup, habit-project scoping, and the sync private-project set — are migrated onto the registry, and their prior by-title / hardcoded-id lookups are removed. | Planned |
| FR-006 | Label resolution accounts for per-user (per-token) label ownership, so a label is resolved within the correct owning user's namespace (#715 two-token model). | Planned |
| FR-007 | The registry resolves against the locked post-#714-reset project and label names, and treats the felix-bot token's own native Inbox as out of scope (never a resolution target). | Planned |

### Non-Functional

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-001 | Resolution on the routing hot path performs zero per-call network requests to Vikunja (identities are available without a live fetch on each resolution). | Planned |
| NFR-002 | The validation routine completes within at most two Vikunja listing round trips (projects + labels) and is safe to run on demand. | Planned |
| NFR-003 | No new third-party dependencies are introduced; the standard library plus the existing Vikunja client only. | Planned |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | This feature changes only Felix-side resolution code. It does not create, rename, or delete any Vikunja project, label, or filter — that is the domain of #714. | Active |
| C-002 | Resolution is owner-scoped to kent-owned projects; the felix-bot user's own native Inbox (id 14) is never a resolution target. | Active |
| C-003 | Proceed as if native is-null date filtering (#725) is unavailable indefinitely; nothing in this seam depends on it. | Active |
| C-004 | The locked post-reset names are those defined in `docs/design/vikunja-configuration-design.md`; the registry must not diverge from that document. | Active |

## Success Criteria

- **SC-001:** 100% of Felix's Vikunja project/label resolutions go through the single registry — zero remaining by-title or hardcoded-id lookups anywhere in the codebase.
- **SC-002:** A deleted or renamed referenced project/label produces a loud, actionable failure within one validation run, rather than a silent mis-route or empty result (regression guard for the #743 class).
- **SC-003:** Changing a project/label identity requires editing only the registry (a single location), with no other code changes.
- **SC-004:** No increase in the number of Vikunja API calls made on the routing hot path relative to today.

## Key Entities

- **Project reference** — a logical project name (e.g. "Inbox", "Personal") bound to a Vikunja project identity.
- **Label reference** — a logical label name (e.g. `q:schedule`) bound to a label identity within an owning token's namespace.
- **Registry** — the declared collection of project and label references (the single source of truth).
- **Validation report** — the set of missing / drifted references produced by checking the registry against live Vikunja.

## Assumptions

- **Representation (confirmed with operator 2026-07-15):** the registry is a committed machine-readable data file (source of truth) fronted by a thin typed accessor, matching the project's "machine-readable data authoritative, code is a view" convention. *(Design detail — recorded here so it is not lost; the concrete form is finalized in plan.)*
- **Identity strategy (confirmed 2026-07-15):** project/label identities are committed into the registry for a network-free hot path, with a separate validation routine that asserts committed identity ↔ name still agree against live Vikunja and fails loud on drift.
- The locked names and structure are taken from `docs/design/vikunja-configuration-design.md` (Inbox, Felix / kg-automation, Clients › {PointerHealth, spec-kitty}, Personal, Metal Casework, CT-90day, Habits; labels `f:`, `q:`, `t:`, `loe:`).
- Two Vikunja tokens exist (felix-bot and kent) per #715; label namespaces are per-token.

## Scope

**In scope:** a declared project/label registry; migration of all existing Felix resolution call sites onto it; fail-loud resolution; a drift/missing validation routine.

**Out of scope:** any change to Vikunja's own configuration (projects, labels, filters — #714); the capture routing-model change (#745); routing atomicity (#746); the task-intake validation loop (#749); native is-null date filtering (#725).

## Edge Cases

- **Duplicate project titles** (e.g. two "Inbox" projects across users): the registry pins the correct owner-scoped identity; the felix-bot token's own Inbox is excluded.
- **Declared name absent in Vikunja:** fail loud (FR-003).
- **Identity drift** (name still present but id changed): flagged by validation (FR-004).
- **Label present under one token but not another:** resolved in the correct namespace, or fail loud (FR-006).

## Dependencies

- `docs/design/vikunja-configuration-design.md` — the locked post-reset names.
- Existing `scripts/common/vikunja_client.py` and `scripts/common/vikunja_config.py`.
- Consumed by #745 / #746 / #749; relates to #714 (reset), #715 (per-user labels), #725 (is-null primitive).
