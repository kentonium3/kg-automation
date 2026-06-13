---
title: ntfy-notification-v1 — Felix-deployer failure notification wire shape
doc_type: reference
status: approved
audience: agents_and_humans
owners: [kgale]
last_validated: '2026-06-13'
last_updated: '2026-06-13'
---

# ntfy-notification-v1 — Felix-deployer Failure Notification Wire Shape

This contract defines the HTTPS POST request shape sent from the felix-deployer applier on office2 to `https://ntfy.sh/<topic>` whenever a queued deploy manifest fails apply.

This contract **supersedes** `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/dm-payload-v1.md` for the felix-deployer notification path. The earlier contract remains as the historical record of the broken-dispatch design; it is not re-used.

## Scope

In scope:
- The HTTP request shape (method, URL, headers, body).
- The title and body rendering algorithm from `(manifest, phase, error_summary, head_sha, failed_at)`.
- The redact-then-truncate invariant on `error_summary`.
- The closed enum of `error_code` values returned by `dispatch_failure_notification` on failure.

Out of scope:
- ntfy.sh's own API (refer to ntfy.sh docs).
- Topic provisioning, env-file management, and subscriber-app configuration (operator runbook responsibility).
- Notification dedup, batching, or rate-limiting (none implemented; not in scope per spec).

## Request

| Aspect | Value |
|---|---|
| Method | `POST` |
| URL | `https://ntfy.sh/${FELIX_DEPLOYER_NTFY_TOPIC}` |
| `Title:` header | `felix-deployer failed: <manifest_name>` |
| `Priority:` header | `high` (ntfy.sh priority 4 — high; reserved 5 for emergency) |
| `Tags:` header | `warning,rotating_light` |
| Content-Type | (curl default for `--data-binary @-`; ntfy.sh accepts text/plain) |
| Body | Plain text, UTF-8. See "Body template" below. |
| Timeout | Client side: `curl --max-time 10` (10 seconds wall-clock). |

`<manifest_name>` is the manifest's `name` field (e.g. `bootstrap-felix-deployer-v2`). It is single-line, kebab-case, ≤80 chars; the title is safe to render on a phone lock screen without truncation.

If `$FELIX_DEPLOYER_NTFY_TOPIC` is unset or empty, the dispatcher MUST return `LibResult(ok=False, details={"error_code": "NTFY_MISSING_TOPIC", ...})` without invoking curl.

## Body template

The body is plain UTF-8 text rendered from this template (newlines are literal `\n`):

```
Phase: ${phase}
Tier: ${tier}
Head: ${head_sha_prefix}
Failed at: ${failed_at_iso}

Error:
${redacted_error_summary}
```

| Variable | Source | Constraint |
|---|---|---|
| `${phase}` | `phase` arg | One of `tier_guard`, `verification_pre`, `entrypoint`, `verification_post`. Pass-through verbatim. |
| `${tier}` | `manifest.tier` | Integer 1–4. Stringified. |
| `${head_sha_prefix}` | `head_sha` arg | First 8 chars of `head_sha`. If `head_sha` is empty, the literal `(unknown)`. |
| `${failed_at_iso}` | `failed_at` arg, or `_utc_now_iso()` if empty | RFC 3339 / ISO-8601 UTC with seconds, no fractional. |
| `${redacted_error_summary}` | `error_summary` arg, processed | See "Redact-then-truncate invariant" below. |

If `${redacted_error_summary}` is empty (the upstream caller passed an empty `error_summary` and there's nothing left after redaction), the literal text `(no error summary)` is substituted to avoid an empty Error: section.

## Redact-then-truncate invariant

The order of operations on `error_summary` is FIXED and MUST be respected by any future modification:

1. **Redact first**: call `scripts.deploy.lib.verify.redact_secrets(error_summary)`. This strips known secret patterns (API keys, JWT-shaped strings, SSH key fragments, HTTP basic-auth blobs) and replaces them with `<REDACTED>`.
2. **Truncate second**: if the redacted result exceeds 500 characters, truncate to exactly 500 characters. No ellipsis or marker is appended (per existing v1 DM payload convention — preserved for consistency).

**Why redact before truncate**: truncation can split a secret across the boundary, partially exposing it. Redacting first guarantees no recognizable secret pattern survives, regardless of truncation point.

## Curl invocation shape

The dispatcher invokes curl with this exact argv shape (subject to argument substitution):

```bash
curl --silent --show-error --fail --max-time 10 \
    -H "Title: ${TITLE}" \
    -H "Priority: high" \
    -H "Tags: warning,rotating_light" \
    -X POST \
    --data-binary @- \
    "https://ntfy.sh/${NTFY_TOPIC}"
```

- `--silent` and `--show-error` together suppress progress meter but preserve error messages.
- `--fail` returns non-zero exit on HTTP 4xx/5xx (avoids treating "POST accepted but server returned 500" as success).
- `--max-time 10` caps wall-clock at 10 seconds; covers DNS + connect + send + receive.
- `--data-binary @-` reads the body from stdin (avoids shell quoting issues with multi-line redacted summaries).

The body is piped via `subprocess.run(..., input=body, text=True)`.

## Response handling

| Outcome | dispatcher result |
|---|---|
| curl exit 0 | `LibResult(ok=True, summary="ntfy notification sent", details={"title": ..., "topic": ...})` |
| curl exit 6 (DNS) or 7 (connect refused) | `LibResult(ok=False, details={"error_code": "NTFY_NETWORK_UNREACHABLE", "returncode": <code>, "stderr_excerpt": ...})` |
| curl exit 22 (HTTP error caught by `--fail`) | `LibResult(ok=False, details={"error_code": "NTFY_HTTP_ERROR", ...})` |
| curl exit 28 (timeout) | `LibResult(ok=False, details={"error_code": "NTFY_TIMEOUT", ...})` |
| curl exit other non-zero | `LibResult(ok=False, details={"error_code": "NTFY_UNKNOWN", ...})` |
| `FileNotFoundError` raised | `LibResult(ok=False, details={"error_code": "NTFY_CURL_MISSING"})` |
| Other `OSError` raised | `LibResult(ok=False, details={"error_code": "NTFY_SPAWN_FAILED"})` |
| `$FELIX_DEPLOYER_NTFY_TOPIC` unset/empty | `LibResult(ok=False, details={"error_code": "NTFY_MISSING_TOPIC"})` — does NOT invoke curl |

In ALL failure modes, the dispatcher returns normally (no exception escapes the public function). The applier tick treats `ok=False` as a non-fatal warning, logs the result, and continues.

## Worked example

Input:
```python
manifest = {"name": "vikunja-image-bump", "tier": 2}
phase = "verification_post"
error_summary = "vikunja smoke check failed: expected 200 from /api/v1/info, got 502\napi-token=ntfy_BadSecretValueExampleHere1234567890 leak shown to demonstrate redact"
head_sha = "31f63d6070bf5377fa20be921feb9f0e7f69a608"
failed_at = "2026-06-13T15:30:42Z"
```

Rendered title:
```
felix-deployer failed: vikunja-image-bump
```

Rendered body (after redaction, no truncation needed):
```
Phase: verification_post
Tier: 2
Head: 31f63d60
Failed at: 2026-06-13T15:30:42Z

Error:
vikunja smoke check failed: expected 200 from /api/v1/info, got 502
api-token=<REDACTED> leak shown to demonstrate redact
```

(The exact `<REDACTED>` placeholder text depends on what `redact_secrets` is configured to emit; the contract requires only that the recognizable secret pattern is gone, not that the substitution text is a specific literal.)

## Backward compatibility

`ntfy-notification-v1` is a NEW contract; no v0 exists. `dm-payload-v1` (the predecessor for the same purpose, on a different substrate) is retired entirely; no fields are carried forward. Future versions of THIS contract (`v2`, ...) MUST bump the file name (`ntfy-notification-v2.md`) and the implementing module's documented version constant.

## Validation

This contract carries valid YAML frontmatter so `tooling/scripts/validate_docs.py` accepts it. The fields are required by `validator-policy.json`'s blocker rules; the optional `last_validated` and `version` semantics follow existing reference docs in the repo.

The rendered title is asserted byte-for-byte in `tests/deploy/test_notify.py`. The body is asserted structurally (per-line, after redaction) with a tolerance for the `<REDACTED>` placeholder.
