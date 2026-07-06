---
title: Cross-Repo Standing Rules Sweep Validation
doc_type: diagnostic
status: draft
owners: [kgale]
last_updated: '2026-07-06'
---

# Cross-Repo Standing Rules Sweep Validation

## Summary

WP03 validated the final `.agents/rules/cross-repo-standing-rules.md` update for #649 after the approved WP02 standing-rules change was integrated onto `feat/cross-repo-standing-rules-sweep`.

The standing-rules file is ready for #649 closeout. It preserves the existing public-post copy approval and local tracking ticket protections, removes the stale separate external paste-file wording, and points agents at the embedded upstream draft flow.

## Validation Results

| Check | Result | Evidence |
| --- | --- | --- |
| Docs validator | Pass | `python tooling/scripts/validate_docs.py` returned `validate_docs: OK`. |
| Stale standing-rules wording | Pass | `rg -n "paste file|paste-buffer|generate.*external" .agents/rules/cross-repo-standing-rules.md` returned no matches. |
| Protected headings | Pass | `rg -n "Public-post copy approval|Local tracking tickets|issue reporting" .agents/rules/cross-repo-standing-rules.md` found all three expected sections at lines 8, 22, and 26. |
| Always-on size | Pass | `.agents/rules/cross-repo-standing-rules.md` has 29 nonblank lines, under the 80-line success criterion. |

## Operator Judgment

No candidate from the WP01 classification remains unresolved for #649. The only promoted candidate was the Spec-Kitty issue-reporting wording correction, and the final standing-rules file now reflects the embedded upstream draft flow.

One non-blocking follow-up surfaced during validation: the linked runbook `docs/runbooks/spec-kitty-bug-reporting.md` still has an introductory sentence saying a slim external paste-buffer doc is generated, while its lifecycle and v1.3/v1.4 notes say the draft is embedded directly in the internal issue with no separate paste file. That residual is outside the #649 standing-rules deliverable and should be handled as separate docs-debt unless the operator wants to expand this mission.

## Closeout Readiness

#649 is ready for closeout after mission review/acceptance, subject to the normal requirement that no GitHub comment or issue closure is posted without exact-copy approval.

Suggested exact copy, if the operator wants to comment on #649 after acceptance:

```text
Implemented via the cross-repo standing rules sweep mission.

Summary:
- Updated the global standing-rules Spec-Kitty issue-reporting guidance to use the embedded upstream draft flow.
- Preserved public-post copy approval and local tracking protections against notification mentions.
- Added validation evidence confirming docs validation passes, stale standing-rules wording is gone, and the standing-rules file remains under the 80-line budget.

No public/upstream issue copy was posted as part of this mission.
```
