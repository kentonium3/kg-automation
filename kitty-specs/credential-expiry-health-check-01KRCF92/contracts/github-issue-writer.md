# Contract: GitHub Issue Writer

**Surface**: file alerts as GitHub issues on `kentonium3/kg-automation`.

## Identity

All `gh` invocations run as the `claude` user. The `gh` CLI is preconfigured with the `kg-felix-bot-pat` (per `credential-manifest.json` and AGENT-REGISTRY.md §Service Accounts). Issues authored by the check appear as `kg-felix-bot` in the GitHub timeline.

## Inputs (cadence-based alert)

- `credential: Credential`
- `boundary: datetime.date`
- `vikunja_task_id: int` — must exist before the issue is filed (cross-ref in body)

## Inputs (activity-staleness alert)

- `credential: Credential`
- `signal_failure: ActivitySignalFailure` — captures which signal threshold was crossed

## Inputs (manifest-quality batch)

- `issues: list[ManifestQualityIssue]`
- `cycle_date: datetime.date`

## Outputs

- `issue_number: int` on success
- raises `GitHubWriteError` on failure (caller logs and continues; partial state acceptable per spec §6 edge case)

## Title formats (stable — used for dedup; do NOT change without coordinating dedup logic)

| Variant | Title |
|---|---|
| Cadence-based | `Credential review: <credential.name> due <boundary.isoformat()>` |
| Activity-staleness | `Credential staleness: <credential.name>` |
| Manifest-quality batch | `Credential manifest quality: <N> entries with issues — <cycle_date.isoformat()>` |

## Body templates

### Cadence-based body

```markdown
**Credential**: `<credential.name>` (`<credential.type>`)
**Scope**: <credential.scope>
**Stored at**: `<credential.storage>`
**Used by**: <credential.used_by joined with ', '>

**Review cadence**: `<credential.review_cadence>` — last reviewed **<credential.last_reviewed.isoformat()>**
**Cadence boundary**: **<boundary.isoformat()>** (in <days_remaining> days)
**Vikunja task**: #<vikunja_task_id> (due <boundary - 7 days>)

---

### Rotation procedure

<credential.expiry_notes>

---

*Filed by `credential-health-check.service` on office2 on <cycle_date.isoformat()>. Filed via `kg-felix-bot`.*

*Close this issue after rotating + updating `last_reviewed` in `docs/design/architecture/data/credential-manifest.json`.*
```

### Activity-staleness body

```markdown
**Credential**: `<credential.name>` (`<credential.type>`)
**Scope**: <credential.scope>
**Stored at**: `<credential.storage>`
**Used by**: <credential.used_by joined with ', '>

**Review cadence**: `<credential.review_cadence>`

---

### Signal that triggered this alert

<signal_failure.summary>  — for example: "openclaw channels status reported in:14d 3h ago, exceeding the 14-day session expiry threshold documented in expiry_notes."

---

### What to do

<credential.expiry_notes>

---

*Filed by `credential-health-check.service` on office2 on <cycle_date.isoformat()>. No Vikunja task is created for activity-staleness alerts (one-way notification).*

*Close this issue after acting on it.*
```

### Manifest-quality batch body

```markdown
The credential-health-check cycle on <cycle_date.isoformat()> found <N> entries in `credential-manifest.json` with field-quality issues. These entries were skipped for cadence-based processing.

| Entry | Issue |
|---|---|
| `<name or index>` | `<reason>` |
| ... | ... |

Fix these entries and bump `last_updated` in `credential-manifest.json`.

*Filed by `credential-health-check.service` on office2.*
```

## Dedup check (called before writing)

```
gh issue list \
  --repo kentonium3/kg-automation \
  --search 'in:title "<title-prefix>"' \
  --state open \
  --json number,title \
  --limit 50
```

Where `<title-prefix>` is one of:

- `Credential review: <credential.name>` (cadence)
- `Credential staleness: <credential.name>` (activity)
- `Credential manifest quality` (batch)

Returns the list of open issues whose title starts with the prefix. If non-empty, the check skips filing for that variant on this cycle.

**Note**: GitHub `in:title` search is case-insensitive and supports phrase matching with quotes; the prefixes above are designed to be unambiguous and unique to this auditor.

## Labels

Apply the existing repo label `area/security` to all issues. No new labels are created by this contract.

## Assignees

Set `assignees: ['kentonium3']` on all issues (matches Kent's manual default).

## Test coverage

- Unit: title generation for each variant, with edge cases (credential names with hyphens, dots, etc.).
- Unit: body templating for each variant against fixture inputs.
- Contract: stub `gh` invocation; verify the constructed `gh issue create` command line matches expected shape.
- Integration smoke (canary): fire one cycle against a fixture manifest pointing the auditor at a side-channel; manually inspect the resulting issue, then close it before live runs resume.
