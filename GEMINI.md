---
title: Gemini / Antigravity Context — kg-automation
doc_type: reference
status: approved
---

<!-- spec-kitty:orientation -->
**Spec Kitty v3.2.0rc45** — project: kg-automation (healthy)

Two usage patterns:
- **Full mission** (spec → plan → tasks → implement → review → merge):
  trigger: "spec out", "create a mission", "write a spec", "plan this"
  → run `/spec-kitty.specify`
- **Lightweight dispatch** (ad-hoc fix, question, or advice — no mission created):
  trigger: "hey spec kitty", "use spec kitty to", "spec kitty, fix/do/ask/advise/dispatch"
  → **ALWAYS run `spec-kitty dispatch "<request verbatim>"` — do NOT answer directly.**
  `spec-kitty do`, `ask`, and `advise` are retained first-class aliases — use whichever fits.
  If you know the right profile, pass it to skip routing:
  `spec-kitty dispatch --profile <profile-id> "<request verbatim>"`
  Reason: `spec-kitty dispatch` (and its aliases) loads governance context, routes to the
  correct agent profile, and opens the Op. Skipping it produces ungoverned, untracked responses.
  After finishing the work, close the Op with the command printed in the capsule
  (`spec-kitty profile-invocation complete --invocation-id <id> --outcome <done|failed|abandoned>`).
<!-- /spec-kitty:orientation -->
