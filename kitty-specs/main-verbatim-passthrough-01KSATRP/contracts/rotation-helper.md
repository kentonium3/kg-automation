# Contract: rotate_main_session.py

**Mission**: `main-verbatim-passthrough-01KSATRP`
**Module**: `scripts/openclaw/helpers/rotate_main_session.py`

## CLI

```bash
python3 scripts/openclaw/helpers/rotate_main_session.py [--dry-run] [--force]
```

## Behavior

1. Read marker directory `~/.config/openclaw/`. Idempotent unless `--force`.
2. List active `*.jsonl` files in `/home/claude/.openclaw/agents/main/sessions/` (exclude existing `.reset.*` files).
3. For each active session: rename `<uuid>.jsonl` → `<uuid>.jsonl.reset.<ISO timestamp>` (timestamp format `2026-05-23T16-30-45.000Z` — matches existing pattern observed on office2; uses hyphens instead of colons to be cross-platform-safe).
4. Write marker file `~/.config/openclaw/main-rotation-<ISO timestamp>.done` listing the rotated sessions.
5. Print summary (count rotated, marker path).

## Flags

| Flag | Purpose |
|---|---|
| `--dry-run` | Print what would happen; no renames; no marker |
| `--force` | (Reserved for future use — current behavior is naturally idempotent since each call produces a new timestamped reset file) |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (or dry-run completed) |
| 1 | Filesystem error (rename failed, marker write failed) |
| 3 | Invalid argument (via `_StructuredArgumentParser` mirroring #362's pattern) |

## Pre/post-conditions

**Pre**:
- `/home/claude/.openclaw/agents/main/sessions/` exists
- `~/.config/openclaw/` is writable (or can be created)

**Post**:
- All previously-active `*.jsonl` files have been renamed to `*.jsonl.reset.*`
- A marker file at `~/.config/openclaw/main-rotation-<timestamp>.done`
- Next `openclaw agent --agent main --message ...` invocation will start a fresh session that loads the current `/data/services/openclaw/data/AGENTS.md`

## Examples

```bash
$ python3 scripts/openclaw/helpers/rotate_main_session.py --dry-run
[dry-run] would rotate 6 main session(s):
  29146776-d8b1-...-df2981aa6ba4.jsonl → .jsonl.reset.2026-05-23T16-30-45.000Z
  ...
[dry-run] would write marker: ~/.config/openclaw/main-rotation-2026-05-23T16-30-45.000Z.done

$ python3 scripts/openclaw/helpers/rotate_main_session.py
Rotated 6 main session(s). Marker: ~/.config/openclaw/main-rotation-2026-05-23T16-30-45.000Z.done
```
