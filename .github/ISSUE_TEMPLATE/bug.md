---
name: Bug
about: Something is broken or behaving incorrectly
title: "Bug: "
labels: P3-candidate
assignees: ''
---

## Summary

<!--
One sentence: what breaks and under what condition.
-->

---

## Environment

- **spec-kitty version** (if relevant):
- **office2 service/agent**:
- **Date/time observed**:

---

## Reproduction

**Prerequisites:**

**Steps:**
1. 
2. 
3. 

---

## Expected behavior

---

## Actual behavior

---

## Evidence

<!--
Paste relevant log output, error messages, or API responses.
Use code blocks.
-->

```
[log output here]
```

---

## Workaround applied

<!--
If you worked around it, describe what you did.
This helps spec-kitty understand constraints on the fix.
-->

---

## Root cause hypothesis

<!--
Optional — your best guess at what's wrong.
If the root cause is already confirmed, state it here.
-->

---

## Suggested fix

<!--
Optional. State the fix at the requirements level, not implementation.
"Option A: harmonize the two conflicting formats" not "edit line 47 of parser.py"
-->

---

## Impact

- **Severity**: Blocking / Degraded / Cosmetic
- **Frequency**: Always / Intermittent / Once observed
- **Affected workflow**:

---

## Success criteria

- [ ] Original reproduction steps no longer produce the bug
- [ ] No regression in [related functionality]
- [ ] Root cause documented in commit message or postmortem if Tier 0/1

---

## Spec-ready criteria

<!--
Self-check before this bug is ready for /spec-kitty.specify. Phone-filed
issues are not expected to meet this bar at capture time.
-->

This issue is ready for spec-kitty when:

- [ ] **Summary** is a single sentence stating what breaks and under what condition
- [ ] **Environment** captures version/service/timing
- [ ] **Reproduction** steps are deterministic (anyone could follow them)
- [ ] **Expected behavior** and **Actual behavior** are both stated
- [ ] **Evidence** includes the relevant log/error output (or explicitly affirms unavailable)
- [ ] **Root cause hypothesis** is present (even if speculative) OR explicitly marked "unknown — investigation needed"
- [ ] **Impact** severity and frequency are set
- [ ] HTML comment guidance blocks have been removed
