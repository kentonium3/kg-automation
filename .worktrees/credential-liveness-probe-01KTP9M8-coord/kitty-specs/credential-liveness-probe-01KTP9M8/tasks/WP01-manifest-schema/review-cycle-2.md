---
affected_files: []
cycle_number: 2
mission_slug: credential-liveness-probe-01KTP9M8
reproduction_command:
reviewed_at: '2026-06-09T14:39:06Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
review_artifact_override_at: "2026-06-09T14:46:45Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP01"
review_artifact_override_reason: "Cycle 2 approval: cycle 1 rejected only on issue-matrix.md #572 placeholder; matrix now reads 'in-mission' (verified on coord). Lane code unchanged from cycle 1 (single feat commit ccf17b17 + coord merges); 18/18 manifest tests pass including 7 new liveness_probe tests."
---

# WP01 review feedback — cycle 1

## Verdict

Code, tests, and JSON changes are all correct. The acceptance criteria for
WP01 are technically met; however, **the accept gate refuses to move WP01 to
`approved`** because `kitty-specs/credential-liveness-probe-01KTP9M8/issue-matrix.md`
still has the placeholder row for #572 in the `unknown` state (row 7,
`<fill at WP-implementation time>` placeholder, `unknown` verdict, `<link or commit>`
placeholder). This is a planning-artifact omission that blocks the workflow
state transition.

Concrete error from `spec-kitty agent tasks move-task WP01 --to approved`:

```
ERROR: issue-matrix.md has unresolved entries. Fill in verdicts before
approving.
Unknown: #572
```

## Issue 1 — Resolve the #572 row in `issue-matrix.md`

**File**: `kitty-specs/credential-liveness-probe-01KTP9M8/issue-matrix.md` (line 7)

**What's there now**:
```
| #572 | <fill at WP-implementation time> | unknown | <link or commit> |
```

**Why it blocks**: spec.md and plan.md both name `closes #572` for the mission
as a whole, and the matrix table requires a verdict before any WP can be
approved. The "fill at WP-implementation time" cue was the hand-off marker
for whichever WP first touches credential-manifest.json (WP01).

**How to fix**: pick the verdict that matches reality. Most likely candidate:

- **Title** column: copy the GitHub issue title for #572 (e.g.
  `Add liveness probe for gog OAuth refresh tokens` — pull the actual title
  via `gh issue view 572 --repo kentonium3/kg-automation --json title -q .title`).
- **Verdict** column: `in-mission` (the mission's later WPs — WP03 wires the
  probe, WP04 ships the systemd timer — are what actually close the issue;
  WP01 lays the schema groundwork). The legend at the bottom of the matrix
  explicitly allows `in-mission` so long as a terminal verdict is reached
  before mission `done`.
- **Evidence ref** column: the merge commit for WP01 once it lands — for now,
  reference the WP01 lane commit hash from this lane
  (`git log kitty/mission-credential-liveness-probe-01KTP9M8..HEAD --format=%H -n 1`
  from the lane-a worktree) or simply `WP01 lane commit`.

**Suggested final row**:
```
| #572 | <real GH title for #572> | in-mission | <WP01 lane commit hash, e.g. ccf17b17> |
```

## Notes on the actual code review (everything else passes)

For the implementer's reference — the implementation work is solid and does
NOT need a second pass once the matrix row is filled:

- `LivenessProbeConfig` dataclass: `frozen=True`, 4 fields, correct
  `Optional[str]` defaults. ✅
- `Credential.liveness_probe: Optional[LivenessProbeConfig] = None` appended
  without reordering existing fields. ✅
- Parser handles all four cases (absent → `None`, enabled-complete → config,
  enabled-missing → `ManifestQualityError`, disabled → config with `None`
  fields). ✅
- Unknown subkeys raise `ManifestQualityError` with a clear message. ✅
- `credential-manifest.json` `gog-credentials-keyring` block populated with
  the exact paths/commands from spec.md FR-006. JSON validity holds. ✅
- 7 new tests added; all 18 tests in `test_manifest.py` pass; all 133 tests
  in `tests/security/` pass with no regressions. ✅

### One observation worth recording (no action required)

The WP01 prompt (line 167) and spec/contract referred to `ManifestQualityError`
as "an existing exception in this module — DO NOT create a new one." It was
not. The base `manifest.py` only had `ManifestUnreadableError` and
`ManifestQualityIssue` (the latter is the collected-not-raised pattern).
The implementer made the right call by adding `ManifestQualityError` as a
new exception that matches the spec's raise-not-collect contract — the
alternative (degrading to `ManifestQualityIssue` collection) would have
silently violated FR-013. This is correct and intentional; logging it here
in case a future reviewer or mission-review sees the new exception and
wonders why the prompt said "existing."

## Definition-of-Done after this cycle

- [ ] Row 7 of `issue-matrix.md` filled with a real title, a non-`unknown`
      verdict, and a real evidence reference.
- [ ] `spec-kitty agent tasks move-task WP01 --to approved …` succeeds.
- No code changes required.
