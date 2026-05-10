# Contract: Audit Commit Message

**Produced by**: `felix-doc-auditor`
**Used for**: every commit containing high-confidence doc edits derived from an audit
**Format**: Conventional Commits (consistent with kg-automation repo convention)

## Template

```
chore(doc-audit): <one-line summary> (audit: #<N>)

- <doc-relative-path>: <one-line change description>
- <doc-relative-path>: <one-line change description>

Refs #<audit-issue-number>.

Co-Authored-By: felix-doc-auditor <noreply@kg-automation.local>
```

## Rules

- **Subject line**: ≤72 chars when possible. Format `chore(doc-audit): <summary> (audit: #<N>)`.
- **Body**: bullet list of all edits in this commit. One bullet per file edited. If multiple changes to the same file, group as one bullet with sub-bullets.
- **Footer**: `Refs #<audit-issue-number>.` linking back to the audit issue. Plus the `Co-Authored-By` attribution line so commits can be attributed to the agent (not the human running the cron).
- **One commit per audit issue** — atomicity per FR-002. If an audit produces zero approved edits, no commit is made (debt issues are filed instead).
- The `Co-Authored-By` email is a placeholder (`noreply@kg-automation.local`). Implementation phase decides whether to use this or a real noreply address.

## Examples

### Single-file frontmatter update

```
chore(doc-audit): bump service-inventory last_updated (audit: #188)

- docs/design/architecture/data/service-inventory.json: bump last_updated to 2026-05-09; updated_by to issue-80-gpu-install

Refs #188.

Co-Authored-By: felix-doc-auditor <noreply@kg-automation.local>
```

### Multi-file weekly audit

```
chore(doc-audit): refresh frontmatter dates after weekly review (audit: #186)

- docs/design/architecture/data/hardware-inventory.json: bump last_updated to 2026-05-10
- docs/design/architecture/data/service-inventory.json: bump last_updated to 2026-05-10
- docs/design/architecture/physical-topology.md: update kernel reference to 6.8.0-111-generic per hardware-inventory
- docs/design/architecture/service-inventory.md: cross-ref to commit 372bf6e

Refs #186.

Co-Authored-By: felix-doc-auditor <noreply@kg-automation.local>
```
