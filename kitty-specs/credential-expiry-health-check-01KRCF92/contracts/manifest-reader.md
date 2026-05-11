# Contract: Manifest Reader

**Surface**: read `credential-manifest.json` and yield well-formed `Credential` records.

## Inputs

- `manifest_path: str` — absolute path. Default `/home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json`.

## Outputs

- `well_formed: list[Credential]` — credentials whose required fields validate (per `data-model.md` §Credential validation).
- `malformed: list[ManifestQualityIssue]` — entries that fail validation, with the specific failure reason.

## Behaviour

1. Open and parse the file. On any I/O or JSON parse error: raise `ManifestUnreadableError` (caller exits non-zero per FR-011).
2. Validate top-level shape: must be a dict with a `credentials` key whose value is a list. Otherwise raise `ManifestUnreadableError`.
3. For each entry in `credentials`:
   - Validate required fields per `data-model.md` §Credential validation.
   - If well-formed, parse `last_reviewed` into a `datetime.date`. Yield as a `Credential` named tuple / dataclass.
   - If malformed, emit a `ManifestQualityIssue` with `credential_name` (or `<index N>` if `name` itself is missing) and `reason` (e.g., `"missing last_reviewed"`, `"unrecognised review_cadence value: weekly"`).

## Failure modes

- File missing → `ManifestUnreadableError` → check exits 1.
- File present but not valid JSON → `ManifestUnreadableError` → check exits 1.
- Top-level shape wrong → `ManifestUnreadableError` → check exits 1.
- Per-credential malformation → captured in `malformed` list; processing continues.

## Test coverage

- Fixture: `tests/fixtures/manifest-valid.json` (copy of live manifest at the time of test writing) → expect N well-formed, 0 malformed.
- Fixture: `tests/fixtures/manifest-missing-last-reviewed.json` → expect that credential in `malformed` with `reason` matching.
- Fixture: `tests/fixtures/manifest-bad-review-cadence.json` → expect that credential in `malformed`.
- Fixture: `tests/fixtures/manifest-invalid-json.txt` → expect `ManifestUnreadableError`.
- Fixture: `tests/fixtures/manifest-not-a-dict.json` (root is a list) → expect `ManifestUnreadableError`.
