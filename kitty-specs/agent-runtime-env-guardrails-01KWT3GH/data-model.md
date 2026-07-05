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
- `BARE_M_SCRIPTS` — `python3 -m scripts.…` with no `${PYTHONPATH…}` assertion.
- `HARDCODED_CD` — `cd /home/claude/kg-automation` (or any hardcoded checkout) before an
  invocation.
- `HARDCODED_ABS_PATH` — `python3 /home/claude/kg-automation/scripts/…py` (hardcoded
  checkout in an absolute script path).
- `HOME_RELATIVE_WRITE` — a write (`>`, `>>`, `tee`, `--out/--output/--path` sink, redirect)
  to a `~`- or `$HOME`-relative destination. Reads of `~/.openclaw/…` are NOT this kind.

### CheckResult (validate_workspace.py contract — existing)
Reused unchanged so the fold matches the existing validator shape:

```python
@dataclass
class CheckResult:
    name: str          # "runtime_env_assumptions"
    passed: bool
    detail: str        # human summary; enumerates Findings when failed
```

## Canonical (compliant) forms — what the checker PASSES

```bash
# -m scripts. form (non-cd, fail-loud; preferred)
PYTHONPATH="${PYTHONPATH:?<msg>}" python3 -m scripts.<pkg>.<mod> [args]
# -m scripts. form (cd variant; also accepted)
cd "${PYTHONPATH:?<msg>}" && python3 -m scripts.<pkg>.<mod> [args]
# absolute-path form
python3 "${PYTHONPATH:?<msg>}/scripts/<path>.py" [args]
```

Compliance predicate: an in-scope invocation is compliant iff its repo-root reference is
`${PYTHONPATH...}` guarded with `:?` (fail-loud) and it contains no hardcoded
`/home/claude/kg-automation` (or sibling checkout) literal.

## Recognizer (what is an "invocation" vs prose) — R-03

A line is evaluated as an invocation candidate when EITHER:
1. it lies inside a fenced code block (```/```bash/```sh), OR
2. its first non-whitespace token is `cd`, `python3`, or `python` AND the line contains
   `-m scripts.` or a `scripts/….py` path.

Excluded (never flagged):
- inline single-backtick spans embedded in a prose sentence (documentation of the pattern),
- HTML comments (`<!-- … -->`),
- lines whose invocation contains an unresolved `<placeholder>` in the module/path position
  (illustrative template text, e.g. `python3 -m scripts.inbox.<helper>`).

Fixtures (IC-02) pin: each ViolationKind true-positive; each canonical form true-negative;
and the must-not-flag set (capture line 74 prose, the `<!-- helper at … -->` comment, the
`<helper>` placeholder line).

## State transitions

None. The checker is pure: `(file bytes) → list[Finding]`. Idempotent, deterministic
(NFR-001).
