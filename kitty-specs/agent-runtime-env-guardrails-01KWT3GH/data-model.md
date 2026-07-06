# Data Model — Agent runtime-env guardrails

The "model" here is the checker's detection model: the entities it produces and the
patterns it recognizes. No persistent storage.

## Entities

### Finding
A single detected issue in an agent prompt.

| Field | Type | Notes |
|---|---|---|
| `path` | str | agent-prompt file (absolute or repo-relative) |
| `line` | int | 1-based line number of the offending invocation |
| `kind` | enum `ViolationKind` | see below |
| `snippet` | str | the offending command text (trimmed) |
| `remediation` | str | the canonical form to use instead |

### ViolationKind (enum)
- `BARE_M_SCRIPTS` — `python3 -m scripts.…` with no `cd "${PYTHONPATH…}"` (or equivalent
  `${PYTHONPATH…}`) assertion in the same logical command.
- `HARDCODED_CD` — `cd /home/claude/kg-automation` (or any hardcoded checkout path) before
  an invocation.
- `HARDCODED_ABS_PATH` — `python3 /home/claude/kg-automation/scripts/…py` **or** `python
  /home/claude/kg-automation/scripts/…py` (hardcoded checkout in an absolute script path).
  **Both `python` and `python3` interpreters are in scope** (MED-1: live lines use bare
  `python …` in calendar/tasker/escalation/`.tmpl`).
- `HOME_RELATIVE_WRITE` — a write (`>`, `>>`, `tee`, `--out/--output/--path` sink, redirect)
  to a `~`- or `$HOME`-relative destination. Reads of `~/.openclaw/…` are NOT this kind.

### CheckResult (validate_workspace.py contract — EXISTING, field name is `ok`)
Reused unchanged so the fold matches the real validator shape. **The dataclass field is
`ok`, NOT `passed`** (verified against `validate_workspace.py:56-61` + its rendering/tests
which consume `.ok`) — an earlier draft said `passed`; corrected per Codex MED-3:

```python
@dataclass
class CheckResult:
    name: str          # "runtime_env_assumptions"
    ok: bool           # NOT `passed` — matches the existing dataclass + _render_human + tests
    detail: str        # human summary; enumerates Findings when not ok
```

## Canonical (compliant) forms — what the checker PASSES (cd form, per Codex HIGH-3)

```bash
# -m scripts. form (cd — fixes BOTH cwd drift AND imports; fail-loud)
cd "${PYTHONPATH:?<msg>}" && python3 -m scripts.<pkg>.<mod> [absolute args]
# absolute-path form (python OR python3)
cd "${PYTHONPATH:?<msg>}" && python3 scripts/<path>.py [absolute args]
# equivalently for abs-path: python "${PYTHONPATH:?<msg>}/scripts/<path>.py"
```

Compliance predicate: an in-scope invocation is compliant iff its repo-root reference is
`${PYTHONPATH...}` guarded with `:?` (fail-loud) AND it contains no hardcoded
`/home/claude/kg-automation` (or sibling checkout) literal. Companion requirement (not
checker-enforced, but a WP-conversion + smoke-test rule): helper path args are absolute, so
the `cd` to repo root never breaks a cwd-relative argument.

## Recognizer (what is a real invocation vs documentation) — R-03, REVISED per Codex HIGH-1/MED-2

Operate on **logical commands**, not raw lines:
1. Join backslash-continued lines and fenced ```bash/```sh blocks into one logical command;
   remember its STARTING line for reporting.
2. Extract concrete invocation candidates from BOTH fenced commands AND inline
   single-backtick spans in prose (capture's real commands are inline imperatives —
   "Invoke `python3 -m scripts.inbox.prescan`").
3. A candidate is an invocation iff it contains a **concrete** `-m scripts.<mod>` or a
   `<abs>/scripts/<file>.py` path with `python`/`python3` (both interpreters).

Excluded (never flagged):
- candidates whose module/path position holds an unresolved `<placeholder>` (e.g.
  `python3 -m scripts.inbox.<helper>`, capture `:74`) — documentation of the pattern;
- HTML comments (`<!-- … -->`).

Fixtures (IC-02) pin: inline-imperative true-positive (capture `:78`), fenced true-positive,
backslash-continuation true-positive (habits `:93-94`), `python` (not `python3`) abs-path
true-positive (calendar `:58`); each canonical-form true-negative; and the must-not-flag set
(capture `:74` `<helper>` placeholder, the `<!-- helper at … -->` comment).

## State transitions

None. The checker is pure: `(file bytes) → list[Finding]`. Idempotent, deterministic
(NFR-001).
