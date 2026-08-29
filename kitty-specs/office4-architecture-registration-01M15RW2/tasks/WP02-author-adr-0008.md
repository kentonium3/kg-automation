---
work_package_id: WP02
title: Author ADR 0008 — the three-machine model
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-011
planning_base_branch: feat/office4-architecture-registration
merge_target_branch: feat/office4-architecture-registration
branch_strategy: Planning artifacts for this mission were generated on feat/office4-architecture-registration. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/office4-architecture-registration unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
phase: Phase 1 - Decision record
history:
- at: '2026-08-29T04:11:23Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: architect-alphonso
authoritative_surface: docs/design/architecture/adr/
create_intent:
- docs/design/architecture/adr/0008-three-machine-model.md
execution_mode: code_change
model: ''
owned_files:
- docs/design/architecture/adr/0008-three-machine-model.md
role: architect
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Author ADR 0008

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `architect-alphonso`
- **Role**: `architect`
- **Agent/tool**: `claude`

---

## Objectives & Success Criteria

Write the decision record that makes the office2/office4 boundary answerable from the
architecture store instead of from a local plan file and issue comments.

Done when a reader with no prior context can answer all five of contract C-5's questions
**without leaving the document**:

1. Which of the three machines is managed?
2. Where does a given workload belong?
3. Why is office4 not a managed host?
4. What must office4 never hold, and why?
5. Why are there no `claude`/`codex` Unix users on office4?

And: `validate_docs.py` exits 0 (frontmatter is enforced), and every citation resolves.

## Context & Constraints

- **Content contract**: [contracts/architecture-data-payloads.md](../contracts/architecture-data-payloads.md) C-5.
- **Verified evidence**: [research.md](../research.md) R-3 (citations), R-12 (RunSSH), R-6 (conventions).
- **This is the largest unit of judgement in the mission.** An ADR is read as settled truth
  for years; a wrong citation in it is costlier than a wrong line of code, because code
  fails loudly and a bad ADR quietly misinforms.
- **ADRs are immutable once approved.** `docs/design/architecture/adr/README.md`: superseded
  decisions get a **new** ADR referencing the prior one. Write the Consequences section in
  that language — never instruct a future reader to "amend this ADR".

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: `feat/office4-architecture-registration`
- **Merge target branch**: `feat/office4-architecture-registration`

## Subtasks & Detailed Guidance

### Subtask T006 – Create the file with sibling-matching frontmatter

- **File**: `docs/design/architecture/adr/0008-three-machine-model.md` (new)
- **Steps**: read `0007-retire-vikunja-felix-bot.md` and `0006-*.md` first and match their
  shape exactly. Frontmatter:

  ```yaml
  ---
  title: ADR-0008 — Three-machine model: office2 managed, office4 and Mac unmanaged peers
  doc_type: reference
  status: approved
  owners: ["@kentonium3"]
  last_updated: 'YYYY-MM-DD'
  version: v1.0
  audience: agents_and_humans
  tags: [909, 908, 910, 917]
  ---
  ```

- Then an H1 repeating the title, `**Status**: Accepted`, `**Date**:`,
  `**Deciders**: Kent Gale`, then `## Context`.
- **Validation**: enum values must already exist in
  `docs/design/standards/allowed-values.json` or `validate_docs.py` fails the commit.

### Subtask T007 – Context and Decision

- **Context**: office4 arrived as Kent's primary development machine and is live on the
  tailnet, but appeared in no architecture document. The decisions that shaped the migration
  lived only in a local plan file and GitHub issue comments — the same drift class that
  produced the undocumented `codex` account (#917), found live before it was found in docs.
- **Decision**: three machines. **office2 = managed host.** **MacBook Pro and office4 =
  unmanaged peers.** office4 joins as a second peer.
- **State plainly what defines managed status**: this ADR and the deploy/audit mechanisms.
  **Not** the contents of `service-inventory.json`, and **not** how detailed a machine's
  hardware record is. Those are corroborating facts. A managed host could temporarily run
  zero registered services without ceasing to be managed; documenting a peer's hardware in
  detail would not make it managed. Say this explicitly — otherwise a later documentation
  edit appears to change architecture.

### Subtask T008 – The governing principle and the placement test

- **Principle**: *"office2 is unattended, office4 is attended."*
- **State the trap explicitly**: office4 **is** always-on, so uptime is **not** the axis that
  separates the machines. Attendedness is. A reader who assumes "always-on ⇒ can host
  services" will place work wrongly.
- **The placement test**, in applicable form: *"If this is down for ten minutes while nobody
  is watching, is the cost annoyance or data loss?"* → annoyance means office4; data loss
  means office2.
- **Work both cases.** Give one concrete example that resolves to office2 and one that
  resolves to office4, so the test is demonstrated rather than merely asserted.

### Subtask T009 – The five single-host citations

Use **repo-root-relative paths**. All five were verified (research.md R-3):

1. `deploys/schema/manifest-v1.schema.json` — has **no** `host` field, **and** sets
   `"additionalProperties": false` at the top level (line 7). So a manifest naming a host is
   **rejected by the schema**, not merely unsupported. State it this way; it is materially
   stronger than "unsupported" for the same conclusion.
2. `scripts/deploy/lib/deploylock.py:41` — the lock is named `office2-checkout.lock`.
3. `scripts/deploy/felix-deployer/_tick.py:59` — `DEFAULT_REPO_ROOT` **defaults to**
   office2's path. Say "defaults to", **not** "hardcodes": an override exists at line 404,
   though nothing in the pipeline supplies one. An ADR should not overstate.
4. `scripts/deploy/felix-deployer/rebaseline.py:49` — documents stripping the
   `ssh office2-claude` wrapper *because felix-deployer runs on office2*. Note this citation
   lands in the module docstring, not executable code, so a reader is not confused.
5. `scripts/deploy/lib/tier.py:73` — embeds `ssh office2-kgale`.

- **Framing**: these show Felix's substrate is single-host **in code, not by convention**.
  Making office4 managed is a design change across five subsystems, and nothing in this
  migration required it.
- **Cite file and behaviour together**, never a bare line number — line numbers drift, and a
  moved line should still leave a findable claim.

### Subtask T010 – The two constraints

- **No recognisable checkout.** office4 must not hold a `kg-automation` checkout at any path
  felix-deployer would recognise, because `self-pull` means "merging to `main` **is** the
  deploy" — two recognisable checkouts make "which checkout is the deploy" ambiguous.
  Acknowledge that **nothing enforces this mechanically**; it is documentation only, and
  mechanical enforcement would require the felix-deployer changes this mission excludes.
- **No `claude`/`codex` Unix users.** The office2 `claude` user exists because the agent is
  a *remote actor on a host it does not live on* — attribution plus blast radius, hence
  non-sudo. office4 inverts that: the agent lives there and needs Kent's repos, git identity,
  and config trees. A separate Unix user would firewall it from exactly what it needs.

### Subtask T011 – Consequences and the Review-only affirmations

- **Consequences**: what becomes easy, what becomes harder, and what would have to change to
  revisit this. Frame the `service-inventory.json` exclusion as a **revisitable decision** —
  revisiting it means authoring a **superseding ADR**, not editing this one and not quietly
  adding a service row.
- **Add a `### Review-only affirmations` subsection** (this is FR-011 — a reader must be
  able to tell "read and unchanged" from "never opened"):
  - `docs/design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md` — **unchanged**.
    office4 joining as a member device does widen the accept ACL's nominal scope
    (`autogroup:member` → `autogroup:self` → `autogroup:nonroot, root`); what makes that
    immaterial is that **Tailscale SSH is off on office4** — `tailscale debug prefs` →
    `"RunSSH": false`. Cite that evidence. It is the same standard of proof
    `network-topology.json`'s own `tailscale_ssh.verified_via` field names for office2.
  - `docs/runbooks/phone-termius-setup.md` — read and confirmed unaffected (state the
    outcome you actually reach; if it *does* need a change, say so and flag it).

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Citations decay as code moves | Cite file + behaviour together, never a bare line number |
| Overstating a claim into an ADR | Use R-3's settled phrasings ("defaults to", not "hardcodes") |
| Instructing a future amendment | ADRs are immutable; write supersession language |
| Frontmatter enum not in allowed-values.json | Match ADR-0007's values exactly; the commit gate enforces it |
| Implying inventory contents define managed status | T007 states the definition explicitly |

## Review Guidance

- Open all five citations and confirm each resolves to the claimed content.
- Confirm the `additionalProperties: false` point is present — it is the strongest of the five.
- Confirm the placement test appears with **both** worked cases, not just stated.
- Confirm no sentence tells a reader to amend or edit this ADR later.
- Confirm the Review-only affirmations subsection exists and cites `RunSSH: false`.
- Confirm frontmatter matches ADR-0006/0007 field for field.

## Activity Log

- 2026-08-29T04:11:23Z – system – Prompt created.
