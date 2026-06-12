# Contract: Deploy Library API v1

**Package**: `scripts/deploy/lib/`
**Stability**: v1 — additions allowed, removals require a deprecation cycle and library version bump.
**Importer pattern**: Both Python callers (the applier) and bash callers (one-shot deploy wrappers) MUST use the library. Bash callers invoke via `python3 -m scripts.deploy.lib.<module> <args>` (per memory: helper -m invocation form is required because the module package depends on `scripts.*`).

## Public surface — by module

### `lib.cron` — OpenClaw cron primitives (never touches system crontab)

```python
def openclaw_cron_disable(cron_name: str) -> LibResult
    """Disable a named openclaw cron. Idempotent: no-op if already disabled."""

def openclaw_cron_enable(cron_name: str) -> LibResult
    """Enable a named openclaw cron. Idempotent: no-op if already enabled."""

def openclaw_cron_edit(cron_name: str, payload_path: str | None = None,
                       schedule: str | None = None) -> LibResult
    """Edit a cron's payload-file or schedule (or both). One or both must be set.
    Refuses to touch a cron not registered with openclaw."""

def openclaw_cron_list() -> LibResult
    """Return current openclaw crons in LibResult.details['crons'] as list of dicts.
    Read-only."""
```

**Invariants:**
- Every call shells out to `openclaw cron <subcommand>`. The library never reads `/etc/crontab` or `crontab -l`.
- CI greps the module for the literal `crontab` token; any hit must be in a comment explaining why (e.g., "DO NOT use crontab here — see #162").

### `lib.snapshot` — Backup verification

```python
def verify_restic_recent(max_age_hours: int = 24) -> LibResult
    """Confirm the most recent Restic snapshot is within max_age_hours.
    Falls back to reading /data/services/backup/logs/backup-YYYY-MM-DD.log
    if the claude user cannot query the repository directly (per current
    permissions limitation; see charter Deployment Constraints)."""
```

### `lib.verify` — File / content / secret checks

```python
def verify_file_present(path: str, executable: bool = False) -> LibResult
    """Confirm path exists; optionally also check that it is executable."""

def verify_no_stale_literal(path: str, literal: str) -> LibResult
    """Confirm path does NOT contain literal anywhere in its text content.
    Used to verify that a stale-version string was successfully replaced."""

def redact_secrets(text: str) -> str
    """Best-effort regex pass to strip token/password-looking substrings from text.
    Used before including stderr in DM payloads."""
```

### `lib.tier` — Tier guard (CI + runtime)

```python
def tier_guard(manifest: dict, mode: str) -> LibResult
    """Validate a manifest against the tier policy.

    mode='ci': used by CI before merge.
        - Reject Tier 0 manifests (LibResult.ok=False with specific error code).
        - Reject Tier 1/2 manifests missing a verification block.
        - Allow Tier 3/4 manifests with required fields present.

    mode='runtime': used by the applier at execute time.
        - Re-runs all CI checks for defense in depth.
        - Additionally: rejects if the manifest references an entrypoint that
          doesn't exist on disk.
    """
```

### `lib.apply` — Orchestrator (the applier's main loop calls this)

```python
def dry_run_then_apply_gate(manifest: dict, manifest_path: str) -> LibResult
    """Canonical apply sequence per data-model.md state-transitions:

        1. tier_guard(manifest, mode='runtime')
        2. snapshot.verify_restic_recent (if tier==2)
        3. verification.pre commands
        4. entrypoint --dry-run (mandatory; aborts on failure)
        5. entrypoint --apply (only on dry-run success)
        6. verification.post commands

    Returns LibResult with .details['phase'] set to the lifecycle phase
    where execution stopped (success or failure).
    """
```

## Return type: `LibResult`

All public primitives return `LibResult`:

```python
@dataclass(frozen=True)
class LibResult:
    ok: bool
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)
```

- **`ok`** — the only signal callers should check for branching logic.
- **`summary`** — one-line human-readable description (≤120 chars; for logs).
- **`details`** — structured detail; well-known keys per primitive:
  - `phase` (set by `apply.dry_run_then_apply_gate`)
  - `error_code` (e.g., `TIER_0_REJECTED`, `RESTIC_TOO_OLD`)
  - `stderr_excerpt`
  - `head_sha`

## Invocation contract

**From Python (applier):**
```python
from scripts.deploy.lib import apply, tier
res = apply.dry_run_then_apply_gate(manifest, manifest_path)
if not res.ok:
    # record failure
```

**From bash (one-shot wrappers, future deploys):**
```bash
python3 -m scripts.deploy.lib.cron openclaw_cron_disable felix-vikunja-sync-driver
# Exits 0 on LibResult.ok=True; non-zero otherwise.
# Prints LibResult.summary to stdout; LibResult.details as JSON to fd 3 when --json passed.
```

The module-as-CLI surface is generated by a thin `__main__.py` per module; each maps `argv[1]` → function, `argv[2:]` → positional args, and serializes the `LibResult`.

## Non-goals

- No async API (the applier is single-threaded oneshot).
- No retry decorators (callers decide retry semantics).
- No transactional rollback (per spec — rollback is manual).
- No first-class types for `tier` or `phase` beyond strings + integers (kept thin to keep bash-callable shape clean).

## Versioning policy

- `v1` is the published contract for this mission.
- Adding a new primitive is non-breaking.
- Changing an existing primitive's signature requires a deprecation cycle: the old signature stays for one mission cycle with a `DeprecationWarning`.
- Removing a primitive requires a major version bump (`v2`) AND charter coordination.
