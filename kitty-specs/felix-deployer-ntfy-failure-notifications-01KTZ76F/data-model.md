# Data Model: Felix-deployer ntfy Failure Notifications

The mission introduces no new persistent data entities. The pieces of state that change identity or shape are listed here for plan-→tasks traceability.

---

## Notification (ephemeral)

The HTTPS POST body + headers sent to `ntfy.sh`. Constructed in memory, dispatched, and forgotten. No persistence.

| Field | Type | Source | Notes |
|---|---|---|---|
| `title` | str (≤80 chars, ASCII-safe) | rendered from `manifest.name` | `Title:` header |
| `priority` | enum (literal "high") | constant | `Priority:` header |
| `tags` | str | constant `"warning,rotating_light"` | `Tags:` header |
| `body` | UTF-8 text (≤ ~600 bytes after truncation) | rendered per `contracts/ntfy-notification-v1.md` | HTTP body |
| `topic` | str (private, ≤64 chars) | env var `FELIX_DEPLOYER_NTFY_TOPIC` | URL path segment |

Invariants:
- `body` is the result of `redact_secrets(error_summary)` THEN truncate-to-500. Redact first; truncate second.
- `topic` is never logged at info level. Debug-level logging is permissible for troubleshooting.

## LibResult shape returned by `dispatch_failure_notification`

Reuses the existing `scripts.deploy.lib.LibResult` dataclass — no schema change. The only new convention is the closed enum of `error_code` values in `details`:

```
LibResult(
    ok: bool,
    summary: str,                  # human-readable one-liner
    details: dict[str, Any],       # keys below
)
```

`details` keys (present only on `ok=False`):

| Key | Type | Value space |
|---|---|---|
| `error_code` | str | `NTFY_MISSING_TOPIC` \| `NTFY_CURL_MISSING` \| `NTFY_SPAWN_FAILED` \| `NTFY_TIMEOUT` \| `NTFY_NETWORK_UNREACHABLE` \| `NTFY_HTTP_ERROR` \| `NTFY_UNKNOWN` |
| `returncode` | int | curl exit code (absent when no subprocess invoked, e.g. NTFY_MISSING_TOPIC or NTFY_CURL_MISSING) |
| `stderr_excerpt` | str | First 200 chars of curl stderr (absent when no subprocess invoked) |

`details` keys (present on `ok=True`):

| Key | Type | Notes |
|---|---|---|
| `title` | str | The rendered title (for audit logging) |
| `topic_redacted` | str | Topic name with middle redacted (e.g. `felix-***-abc`) so logs don't leak the full topic |

---

## Environment file (filesystem entity)

| Path | Owner | Mode | Source |
|---|---|---|---|
| `/home/claude/.config/felix-deployer/env` | claude:claude | `0640` | created by operator post-merge; NOT in repo |

Content shape:
```
# Felix-deployer notification topic. Private; do not commit.
FELIX_DEPLOYER_NTFY_TOPIC=felix-deployer-<random-suffix-12-chars>
```

The repo contains `scripts/deploy/felix-deployer/env.sample` with the placeholder. The operator runs a documented one-liner during post-merge redeploy to mint a random suffix and write the real file.

---

## Bootstrap applied entry — `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml`

NEW manifest entry written by the post-merge `--apply` run. Existing `0001-bootstrap-felix-deployer.yaml` is preserved verbatim.

Required fields (per `deploys/schema/manifest-v1.schema.json`):

| Field | Value | Source |
|---|---|---|
| `schema_version` | `v1` | constant |
| `name` | `bootstrap-felix-deployer-v2` | constant in bootstrap script |
| `issue` | `kentonium3/kg-automation#595` | constant |
| `tier` | `1` | inherited from `0001`'s classification |
| `entrypoint` | `scripts/deploy/deploy-felix-deployer-bootstrap.sh` | unchanged |
| `audited_surface` | `true` | unchanged |
| `verification.pre` | (same shape as `0001`) | unchanged |
| `verification.post` | `["systemctl --user is-active felix-deployer.timer", "test -f ${REMOTE_SYSTEMD_USER_DIR}/felix-deployer.service"]` | unchanged |
| `apply_mode` | `bootstrap` | constant |
| `applied_at` | RFC 3339 UTC | timestamp at run time |
| `created_at` | RFC 3339 UTC | timestamp at run time |
| `created_by` | `operator-bootstrap` | constant |
| `notes` | multi-line | NEW — references `0001` as superseded; describes the substrate swap; references this mission's merge commit |

The `notes` block carries the cross-reference text that makes `0001` and `0002` legible as a migration pair.

---

## Architecture data changes

The following JSONs gain or modify entries. Schemas are validated by existing pre-push and CI hooks; no schema changes.

### `docs/design/architecture/data/data-flows.json`

NEW entry (shape consistent with existing entries):

```json
{
  "id": "felix-deployer-ntfy-egress",
  "source": "felix-deployer (office2)",
  "destination": "ntfy.sh (public internet)",
  "protocol": "HTTPS POST",
  "trigger": "deploy manifest fails apply",
  "data_classification": "operational alert; private topic; no PII",
  "trust_boundary_crossing": true,
  "notes": "Best-effort; dispatcher does not crash applier on failure. See kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/contracts/ntfy-notification-v1.md."
}
```

(Exact field set will be confirmed at code time against the live schema.)

### `docs/design/architecture/data/service-inventory.json`

UPDATE `felix-deployer` entry:
- Add to `environment_files` (or equivalent field): `/home/claude/.config/felix-deployer/env` (per claude user).
- Add to `outbound_dependencies` (or equivalent): `ntfy.sh:443/tcp`.

### `docs/design/architecture/data/credential-manifest.json`

NEW entry:

```json
{
  "id": "felix-deployer-ntfy-topic",
  "name": "FELIX_DEPLOYER_NTFY_TOPIC",
  "kind": "private-topic-identifier",
  "storage": "systemd EnvironmentFile on office2 (/home/claude/.config/felix-deployer/env, mode 0640)",
  "in_repo": false,
  "rotation_policy": "manual, on suspicion of leak only (read-only secrecy — knowledge enables passive listening, not impersonation)",
  "used_by": ["felix-deployer"]
}
```

(Schema fit confirmed at code time against the live schema.)

### `docs/design/architecture/data/audited-surfaces.json`

No change. The surfaces touched (`scripts/deploy/deploy-felix-deployer-bootstrap.sh`, `scripts/deploy/felix-deployer/*`) are ALREADY entries; the rebaseline obligation applies to the existing entries, not to a new entry.

---

## Markdown counterparts to JSON updates

Each JSON change has a narrative counterpart in:
- `docs/design/architecture/data-flows.md` (and `data-flows.view.md` if a diagram exists)
- `docs/design/architecture/service-inventory.md`
- `docs/design/architecture/credentials-and-secrets.md`
- possibly `docs/design/architecture/identity-model.md`
- possibly `docs/design/felix-capability-roadmap.md` (felix-deployer capability row)

Tasks WPs will enumerate exact section edits per file when authored. The principle from `CLAUDE.md`: machine-readable JSON is authoritative; narrative markdown supports it.
