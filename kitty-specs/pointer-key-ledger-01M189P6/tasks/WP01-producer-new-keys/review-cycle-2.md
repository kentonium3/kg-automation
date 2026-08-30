---
affected_files: []
cycle_number: 2
mission_slug: pointer-key-ledger-01M189P6
reproduction_command:
reviewed_at: '2026-08-30T04:45:23Z'
reviewer_agent: user
wp_id: WP01
---

# WP01 Review — Cycle 2 — REJECT

Reviewer: codex (advisory, read-only, tests executed). Verdict recorded by the orchestrator, which
independently reproduced the finding.

**Two of the three cycle-1 findings are fully fixed.** Verified:

- **Carry-forward encoding — PASS.** jq now validates type *and* format and does the encoding. A
  corrupt prior document, a quote-bearing value, and non-string values all fall back to `null` without
  aborting the run.
- **Fourteen-key coverage — PASS.** The assertion is parametrized across happy path, mount failure,
  repo-inaccessible and backup-failure, with `json.loads` parseability on each.
- Tests execute the script, 34 pass. `SOURCE_ROOTS` still defined once and feeding both uses. The EXIT
  trap is unmoved and unconditional. Scope is correct. Bash syntax clean.

One defect remains, and it is the same one — narrowed, not gone.

---

## `source_roots_present` still reports `false` when `paths` is absent or null

`scripts/office2/restic-backup.sh:179`

```bash
(.[0].paths // []) as $p
| if ($p | type) == "array" then ($p | index($r) != null) else empty end
```

The structure is right and the intent is right — the comment above it describes exactly the correct
behaviour. But `// []` is evaluated **before** the type check, so an absent or JSON-`null` `paths`
becomes `[]`, which *is* an array, so the guard passes and the filter emits `false`.

The default defeats the very check that was added to fix this.

**Reproduced directly:**

```
$ echo '[{"paths":null}]' | jq -c '(.[0].paths // []) | index("/data") != null'
false                              # <- claims the root is absent

$ echo '[{"paths":null}]' | jq -c 'if ((.[0].paths // null) | type) == "array" then "evaluable" else "NOT evaluable" end'
"NOT evaluable"                    # <- what it should conclude
```

The reviewer also black-box probed the real script: valid snapshot JSON containing `"paths": null`
exits 0 and emits `"source_roots_present": false`.

**Why this still blocks.** `false` is a positive claim that a configured source root was *proven
absent* — asserted when no paths array was available to compare against. Spec C-004 requires `null`
when the comparison could not be performed. This is the third appearance of the same shape in this WP
("could not check" reported as "checked and bad"), and it is the exact distinction the whole mission
exists to enforce.

**Required fix.** Remove the `// []` default so absent/null `paths` is genuinely unevaluable, e.g.:

```
(.[0].paths) as $p
| if ($p | type) == "array" then ($p | index($r) != null) else empty end
```

`empty` then correctly produces no output, the shell `case` falls to `*`, and `null` is emitted.

**Also decide, and state the decision in a comment:** an array containing non-string entries. The
reviewer flags it; it is a genuine judgement call rather than a clear defect. Either treat a
non-string-bearing `paths` as unevaluable (`null`) on the grounds that the collection is malformed, or
treat it as a normal array and let `index()` decide. Whichever you pick, say why in the comment so the
next reader does not "fix" it back.

**Required tests:**
- snapshot JSON with `"paths": null` → `source_roots_present` is `null`
- snapshot JSON with `paths` absent entirely → `null`
- whichever behaviour you choose for a `paths` array containing non-strings

Keep the existing cases green: a genuinely missing root → `false`; all roots present → `true`;
malformed snapshot JSON → `null`; scalar wrong-shape `paths` → `null`.

---

This is **cycle 2 of 3**. The remaining change is small and localised — one jq default, plus tests.
