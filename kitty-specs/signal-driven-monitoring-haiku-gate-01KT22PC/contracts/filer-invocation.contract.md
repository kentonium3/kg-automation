# Contract: Deterministic filer → `felix-file-issue.py` invocation

**Caller**: `scripts/openclaw/observation/filer.py`
**Callee**: `scripts/openclaw/agents/main/felix-file-issue.py` (existing, unchanged in this mission)
**Mechanism**: `subprocess.run()` shelling out to `python3`.

## Why this contract exists

The deterministic filer and the existing LLM-authored filing path (used by the main agent and other agents) must produce **structurally identical issue bodies**. The single source of truth for body construction is `felix-file-issue.py`. This contract pins the argument-construction expectations so changes to one side don't silently break the other.

## Required arguments

The deterministic filer constructs and passes:

| `felix-file-issue.py` arg | Source | Notes |
|---|---|---|
| `--type` | Signal config (today always `bug`) | Future: signals may map to `infra` or `feature`. |
| `--title` | Templated from signal context | E.g., `"WhatsApp creds.json corruption detected (12 events in 15-min cycle, 35 in rolling hour)"`. Title must NOT include type prefix; helper adds it. |
| `--problem-statement-file` | Tempfile written by filer | Paragraph describing the signal, cycle, ground-truth counts, and impact. |
| `--observed-context-file` | Tempfile written by filer | Concatenation of `excerpt_lines` representative log lines from the source. |
| `--tier-hypothesis` | Signal config `tier_hypothesis` | |
| `--area` | Signal config `area_label` | |
| `--priority` | Signal config `priority` | |
| `--spec-ready-eval` | Hard-coded `brief` | Deterministic filings are always `spec: brief`; operator promotes to ready manually. |
| `--related-issues` | Optional | If a sibling signal recently filed an issue, reference it. |

The filer must NOT pass `--dry-run` in production.

## Tempfile lifecycle

The filer:
1. Creates two tempfiles via `tempfile.NamedTemporaryFile(delete=False)` for the problem statement and observed context.
2. Writes content (UTF-8, no trailing newline issues).
3. `flush()` and `close()` the file handles BEFORE invoking the subprocess.
4. Passes their paths to `--problem-statement-file` and `--observed-context-file`.
5. After the subprocess exits (success or failure), the filer deletes both tempfiles in a `finally` block.

## Subprocess invocation

```python
subprocess.run(
    [
        "python3",
        "/home/claude/repos/kg-automation/scripts/openclaw/agents/main/felix-file-issue.py",
        "--type", "bug",
        "--title", title,
        "--problem-statement-file", str(ps_path),
        "--observed-context-file", str(ctx_path),
        "--tier-hypothesis", tier,
        "--area", area,
        "--priority", priority,
        "--spec-ready-eval", "brief",
    ],
    capture_output=True,
    text=True,
    timeout=60,
    check=False,  # filer inspects rc explicitly
)
```

## Output parsing

`felix-file-issue.py` writes a single JSON line to stdout on success:

```json
{"issue_number": 491, "issue_url": "https://github.com/kentonium3/kg-automation/issues/491", "title": "...", "labels": [...]}
```

followed by a `SUMMARY:` line. The filer parses the JSON line (last line that starts with `{`) and uses `issue_number` to update `E2.last_filed_issue_ref` for the signal.

## Error handling

| Failure mode | Filer behavior |
|---|---|
| Subprocess returncode ≠ 0 | Record error in `E3.errors[]` with `error_type = "filer_subprocess_failed"`. Do NOT mark the cycle as failure (other signals may still file). Do NOT update `last_filed_issue_ref` for this signal. |
| Subprocess timeout (60s) | Same as above; `error_type = "filer_timeout"`. |
| stdout doesn't contain parseable JSON | Same; `error_type = "filer_output_unparseable"`. |
| `kg-felix-bot` identity mismatch (helper exits 1) | Same; `error_type = "filer_identity_mismatch"`. **Operator attention required** — surfaced in `last-tick.json.errors`. |

The filer never raises into the cycle orchestrator's main path — all errors are recorded and the cycle continues. This matches the `felix-doc-auditor` pattern.

## Identity verification (delegated)

`felix-file-issue.py` performs its own `gh auth status` check and refuses to file unless the active identity is `kg-felix-bot`. The deterministic filer does not duplicate this check.

## Change-control implications

Modifying `felix-file-issue.py`'s argument schema is a coordinated change: both the existing main-agent callers AND this mission's filer must be updated. The mission tests include an integration test that invokes `felix-file-issue.py --dry-run` with the filer's argument construction to catch schema drift.
