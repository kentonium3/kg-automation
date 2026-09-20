# Contract: doc-standards generator

`tooling/scripts/generate_doc_standards.py`

## Input

`docs/design/standards/allowed-values.json` — the single enforced source. Read-only to this script.

## Output

| Target | Region written |
|---|---|
| `docs/design/standards/frontmatter.schema.json` | the `status` enum only |
| `docs/design/standards/doc-standards.md` | only between `<!-- GENERATED:status-list START -->` and `<!-- GENERATED:status-list END -->` |

## Behaviour

| Mode | Contract |
|---|---|
| default | write the derived regions; exit 0 |
| `--check` | write nothing; exit non-zero if any derived region differs from what would be generated, naming each stale file |

## Invariants

1. **Idempotent** — a second consecutive run produces byte-identical output and stages no diff (NFR-001).
2. **Sentinel-strict** — if a sentinel pair is missing or malformed, fail loudly with the file and the
   missing marker. Never guess an insertion point, never append.
3. **Region-scoped** — hand-written prose outside the sentinels is never touched. Verified by a test
   that mutates surrounding prose and asserts it survives regeneration.
4. **Source is never written** — `allowed-values.json` is input only.
5. **Deterministic ordering** — status values are emitted in source order, not sorted, so the diff is
   reviewable and stable.

## Consumers

- `.githooks/pre-commit` — informational; the hook may bypass via `--no-verify`.
- `.github/workflows/docs-ci.yml` — `--check` mode is the enforcing gate, on `push` to `main` **and**
  `pull_request` (spec-kitty merges do not fire `pull_request` — see research R-07).
