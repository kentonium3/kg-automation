# Research: Inbox Processed-At Timestamp

**Mission**: inbox-processed-at-timestamp-01KQZ2Y5
**Created**: 2026-05-06

## Research Items

### R1: ISO 8601 parsing in Python 3.10+

**Decision**: Use `datetime.fromisoformat()` from stdlib
**Rationale**: Available since Python 3.7, handles offset-aware timestamps (e.g. `2026-05-06T12:30:00-04:00`) natively in 3.11+. Python 3.10 handles the common `+HH:MM` offset format. No external dependency needed.
**Alternatives considered**: `dateutil.parser.isoparse()` — more permissive but adds a dependency. Not warranted for a controlled format we define ourselves.

### R2: YAML safe_load behavior with ISO timestamps

**Decision**: Store `processed_at` as a quoted string in YAML frontmatter
**Rationale**: `yaml.safe_load()` auto-parses unquoted ISO timestamps into `datetime` objects, which could cause type inconsistency. Since the agent writes the frontmatter as text (not programmatically), the value will naturally be a string. prescan.py should handle both `str` and `datetime` types defensively.
**Alternatives considered**: Rely on YAML auto-parsing — rejected because it's fragile (depends on exact format) and the existing codebase treats frontmatter values as strings.

### R3: Filesystem mtime reliability

**Decision**: Keep mtime as fallback only, not primary
**Rationale**: Confirmed during discovery — mtime resets on any file edit (Obsidian auto-save, sync operations, manual edits). This is the core motivation for the `processed_at` field. Mtime remains the fallback for legacy files that predate this feature.
