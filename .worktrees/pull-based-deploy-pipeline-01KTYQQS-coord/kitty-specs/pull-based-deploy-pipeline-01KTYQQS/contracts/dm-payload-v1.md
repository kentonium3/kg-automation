# Contract: WhatsApp DM Payload v1

**Surface**: openclaw cron `felix-deployer-alert`
**Direction**: applier → openclaw → existing felix-admin DM pathway → operator's WhatsApp
**Versioning**: payload includes `payload_version: "v1"`; future shape changes increment.

## Why openclaw cron and not a direct API call

The applier reuses the existing openclaw WhatsApp surface so it does not introduce a new credential consumer and does not need its own DM client library. See R-03 in [research.md](../research.md).

## openclaw cron registration

The mission registers one new openclaw cron during bootstrap:

| Field | Value |
|---|---|
| `name` | `felix-deployer-alert` |
| `schedule` | manual (no schedule — only invoked by `openclaw cron run`) |
| `payload.kind` | `whatsapp-dm-outbound` |
| `payload.template` | `templates/felix-deployer-alert.txt` (shipped in the deployer's directory) |
| `recipient` | inherits from existing operator-DM configuration in openclaw |

The applier never modifies this cron after bootstrap.

## Payload synthesized by the applier on failure

When the applier needs to dispatch a DM, it constructs a payload as a single JSON object and writes it to a temp file, then invokes:

```bash
openclaw cron run felix-deployer-alert --payload-file <tempfile> --wait --json
```

### JSON payload shape

```json
{
  "payload_version": "v1",
  "manifest_name": "string (the failed manifest's name field)",
  "tier": "integer 1-4",
  "phase": "string — one of: tier_guard, verification_pre, entrypoint, verification_post",
  "error_summary": "string — ≤500 chars, redacted of any path/secret-looking substrings",
  "head_sha": "string — git HEAD SHA at the moment of failure",
  "failed_at": "string — ISO 8601 timestamp",
  "tick_log_excerpt": "string — optional, last N lines of the tick log"
}
```

### Field rules

- **`payload_version`** — always `"v1"`. The receiving openclaw cron knows how to render this version.
- **`manifest_name`** — copied verbatim from the manifest's `name` field; no transformation.
- **`tier`** — copied verbatim from the manifest's `tier` field. Tier 0 cannot reach this path (rejected upstream).
- **`phase`** — the lifecycle phase at which the failure occurred. Used by the operator to triage quickly.
- **`error_summary`** — truncated stderr/error message. The applier passes it through `lib.verify.redact_secrets()` first (a best-effort regex pass to strip anything that looks like a token or password).
- **`head_sha`** — recorded so the operator can reproduce the failure state. Always the post-pull HEAD.
- **`failed_at`** — wall-clock UTC ISO 8601.
- **`tick_log_excerpt`** — optional; included when the failure phase is `entrypoint` (the most opaque failure mode).

## Rendered message (what the operator sees)

The openclaw cron's template renders the payload into a single WhatsApp message:

```
🛑 felix-deployer apply failed

manifest: <manifest_name>
tier:     <tier>
phase:    <phase>
head:     <head_sha[:8]>
when:     <failed_at>

<error_summary>

(Manifest stays in queued/; next applier tick will re-attempt unless you delete it.)
```

This is a single-shot message — no threading, no follow-ups, no acknowledgement required.

## Non-goals

- No success-path messages (per the spec, `WhatsApp DM only on apply failure`).
- No per-tick "alive" pings (the tick log + `health_signal` file cover liveness).
- No template versioning beyond `payload_version` — operational templating is openclaw's responsibility.
- No retry — the applier dispatches once. If openclaw cron returns non-zero, the applier records the dispatch failure in the tick log and proceeds. The operator can re-read the failure record at any time.

## Validation

A unit test confirms:
1. The payload schema matches `payload_version: v1` (no extra fields, no missing required fields).
2. `redact_secrets()` strips token-like patterns from `error_summary`.
3. The rendered template would produce a non-empty message for a minimal payload.
