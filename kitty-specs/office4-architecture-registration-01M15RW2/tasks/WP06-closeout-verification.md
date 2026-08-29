---
work_package_id: WP06
title: Closeout — issue correction and verification
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
requirement_refs:
- FR-012
planning_base_branch: feat/office4-architecture-registration
merge_target_branch: feat/office4-architecture-registration
branch_strategy: Planning artifacts for this mission were generated on feat/office4-architecture-registration. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/office4-architecture-registration unless the human explicitly redirects the landing branch.
subtasks:
- T025
- T026
- T027
- T028
- T029
- T030
- T031
phase: Phase 3 - Closeout
history:
- at: '2026-08-29T04:13:36Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: reviewer-renata
authoritative_surface: kitty-specs/office4-architecture-registration-01M15RW2/
create_intent:
- kitty-specs/office4-architecture-registration-01M15RW2/verification-report.md
execution_mode: planning_artifact
model: ''
owned_files:
- kitty-specs/office4-architecture-registration-01M15RW2/verification-report.md
role: reviewer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP06 – Closeout

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `reviewer-renata`
- **Role**: `reviewer`
- **Agent/tool**: `claude`

---

## Objectives & Success Criteria

Execute every acceptance check, record a concrete result for each, correct #909 so it stops
misleading, and hand off the one obligation this mission cannot satisfy itself.

Done when `verification-report.md` records **pass or fail for every quickstart step**, with
no step left as "not run", and #909 carries the correcting comment.

## Context & Constraints

- **This WP edits no repo source files.** It performs an external action (a GitHub comment)
  and read-only verification, and writes only its own report into the mission directory. Do
  not modify files owned by WP01–WP05; if you find a defect, report it and let the owning WP
  fix it.
- **Depends on all five preceding WPs.**
- Full procedure: [quickstart.md](../quickstart.md).
- **The distinction this repo cares about**: a check that cannot tell "verified false" from
  "couldn't check" is a defect. If you cannot run something, record it as **not run** with
  the reason — never as passing.

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: `feat/office4-architecture-registration`
- **Merge target branch**: `feat/office4-architecture-registration`

## Subtasks & Detailed Guidance

### Subtask T025 – Comment on issue #909

- **Purpose**: #909 contains a verified-false premise and a verification step that cannot
  fail. Left uncorrected, the next reader is misled by both.
- **Two corrections**:
  1. **The `hardware-inventory.json` premise.** #909 calls it "the managed-host record" from
     which the Mac is absent, and sets a success criterion requiring office4 to be absent
     too. In fact its `hosts` array already held all three devices — office2 rich (11
     fields), Mac and iPhone thin (5). Following #909 literally would have made office4 the
     only tailnet device missing from the device record, the exact drift the issue exists to
     prevent. office4 was therefore registered, at the thin detail level. The
     `service-inventory.json` half of the claim was correct and was honoured.
  2. **The verification step.** #909's post-change verification runs
     `validate_architecture_data.py` **without `--strict`**. That validator is warn-only by
     default and exits 0 unconditionally, so as written the check cannot fail. It needs
     `--strict`, which is what the pre-commit gate and Docs CI actually use.
- **Copy approval**: not required. The cross-repo public-post gate carries a repo-scoped
  exception for `kentonium3/kg-automation` internal tracking, and #909 is in that repo.
- **Steps**: `gh issue comment 909 --repo kentonium3/kg-automation --body "..."`. Record the
  returned comment URL in the report.

### Subtask T026 – Run both validators at their real postures

- `python3 tooling/scripts/validate_architecture_data.py --strict` → expect `OK (0 findings)`
- `python3 tooling/scripts/validate_docs.py` → expect `validate_docs: OK`
- Record the exact output of each. `--strict` is not optional; without it the first cannot fail.

### Subtask T027 – Reconcile all four devices against the live tailnet

- Run quickstart step 4 — it compares `tailscale status` against `network-topology.json` for
  **all four** devices, not office4 alone.
- Expect `office2 100.92.197.90`, `kents-macbook-pro 100.71.19.66`,
  `iphone-14-pro-max 100.109.208.6`, `office4 100.112.83.28`.

### Subtask T028 – Assert zero office4 service records

- Run quickstart step 3. This is the one check in the mission that fails correctly in both
  directions — it would catch a violation rather than merely not-finding one.
- Also run quickstart step 2 (four devices, four hosts, only office2 rich, hostnames agree).

### Subtask T029 – Human review of links and heading hierarchy

- **Nothing in this repo validates links or heading hierarchy** — `validate_docs.py` checks
  frontmatter, secrets, and the portal drift block only. These are genuinely manual.
- **Steps**: open every relative link introduced or edited by WP01–WP05 and confirm it
  resolves. Check heading hierarchy (H1 → H2 → H3, no skips) in the new ADR and every edited
  markdown file.
- **Record the count checked**, not just "passed" — an unquantified pass is indistinguishable
  from a skipped check.

### Subtask T030 – Attest office4's `os` and `hardware` sources

- **Run on office4**:
  ```bash
  grep -E '^(NAME|VERSION)=' /etc/os-release
  ```
  ```bash
  cat /sys/devices/virtual/dmi/id/sys_vendor /sys/devices/virtual/dmi/id/product_name
  ```
- Must match `hardware-inventory.json`'s office4 `os` and `hardware`.
- **Never `uname -a`.** Its `#28~24.04.1-Ubuntu` is the kernel build's provenance, not the
  distro — reading it as the distro is the error research.md R-4 records, and no validator
  would catch the result.
- If you are not on office4, record this as **not run**, with the reason.

### Subtask T031 – Write the report and hand off the merge obligation

- **Create** `kitty-specs/office4-architecture-registration-01M15RW2/verification-report.md`
  with: one row per quickstart step (1, 2, 3, 4, 4b, 5, 5b, 5c, 6), its result (pass / fail /
  not run + reason), and the evidence — exact command output where there is any.
- Include the #909 comment URL from T025.
- Include the SC-005 accounting: all 8 signal-map targets (6 updated, 2 affirmed) plus the 5
  the map does not name, each marked done.
- **Hand off C-004 explicitly.** The line
  `Rebaseline: not required — documentation and architecture metadata only` must ride the
  `feat → main` **integration commit**, which must be created with `git merge --no-ff` —
  a fast-forward creates no commit to annotate. `spec-kitty merge` has no commit-message
  option, and amending its commit would be a prohibited manual git workaround. State clearly
  that this is **outside the mission's gate** and is Kent's step, and that verification checks
  both the message and that `HEAD` has two parents.
- Note that **Docs CI does not fire on the mission merge** (it triggers only on `main`), so
  SC-006 is satisfied at commit time by the `.githooks` gate and at Kent's push by CI.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Recording "passed" for something not actually run | T029/T030 require counts and explicit not-run entries |
| Fixing a defect found during verification | Out of scope for this WP — report it to the owning WP |
| The `Rebaseline:` obligation being silently dropped | T031 makes the handoff an explicit deliverable |
| The #909 comment diverging from what shipped | This WP runs last, after the payload is settled |

## Review Guidance

- Confirm the report has an entry for **every** quickstart step, none blank.
- Confirm any "not run" carries a reason.
- Confirm the #909 comment covers **both** corrections, and the URL is recorded.
- Confirm the `--no-ff` handoff is stated unambiguously.
- Confirm no repo source file outside the mission directory was modified by this WP.

## Activity Log

- 2026-08-29T04:13:36Z – system – Prompt created.
