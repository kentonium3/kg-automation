---
title: ADR-0005 — Vikunja client standardization (base URL, token, timeout, error policy)
doc_type: reference
status: approved
owners: ["@kentonium3"]
last_updated: '2026-06-10'
version: v1.0
audience: agents_and_humans
tags: [541, 542, 520, 281, 531, 543]
---

# ADR-0005 — Vikunja client standardization (base URL, token, timeout, error policy)

**Status**: Approved
**Date**: 2026-06-10 (retroactive — the shipped client at `scripts/common/vikunja_client.py` already embodies these decisions; this ADR codifies them so future migrations and new helpers have a single source of truth)
**Deciders**: Kent Gale
**Closes**: kentonium3/kg-automation#541 (child of Epic #531)
**Codifies**: the design decisions shipped in #542 (mission `vikunja-client-and-habits-weekly-report-01KTKSFT`, merged 2026-06-08)
**Builds on**: #520 (URL config foundation), #281 (Directive 6 helper conventions)

## Context

Before this epic, five separate Python scripts under `scripts/{sync,habits,escalation,enrichment,vikunja}/` each implemented their own Vikunja HTTP wrapper — base URL composition, token loading, timeout handling, error semantics, and redaction logic were copy-pasted with subtle drift. The 2026-06-05 architecture review surfaced this as finding **F-004** (High / boundary design / maintainability / integration reliability) and named **Principle 3** ("Integration Clients Are Shared Boundaries") as the governing constraint.

Issue #542 (the refactor child of Epic #531) consolidated the runtime HTTP surface into `scripts/common/vikunja_client.py`. The client is currently consumed by 14+ helpers (verified via `grep -l 'from scripts.common.vikunja_client' scripts/`); migration of remaining ~10 un-migrated helpers is tracked separately as #543 (opportunistic, no deadline).

This ADR captures the **decisions embodied in the shipped client** so future migrations, new helpers, and reviewers have an explicit standards reference rather than having to re-derive intent from code.

## Decisions

### 1. Module location: `scripts/common/vikunja_client.py`

The shared client lives under `scripts/common/` alongside `vikunja_config.py` (the URL helper from #520). Both modules are imported via the `scripts.common.*` package path.

**Rationale**: Per Directive 6 helper conventions (#281), shared deterministic infrastructure lives under `scripts/common/`. Co-locating the client with the URL config helper keeps the Vikunja integration boundary obvious at the file-system level. The `from scripts.common.vikunja_client import ...` import shape is also what the rest of the codebase already uses for cross-cutting helpers.

### 2. Base URL: hostname via Tailscale Serve, not Tailscale IP

The canonical base URL is the hostname-based form (`https://office2.tail0f5f56.ts.net/api/v1/`), resolved via `scripts.common.vikunja_config.get_vikunja_base_url()`. The client accepts an explicit `base_url` override at construct time for testing or unusual contexts.

Resolution order (per `vikunja_config.py`):

1. `VIKUNJA_BASE_URL` environment variable, if set and non-empty
2. Contents of `/data/services/openclaw/config/vikunja-base-url.txt` (whitespace-stripped)

The client validates the resolved URL against the pattern `^https?://[^/]+/api/v1$` and rejects anything else at construct time.

**Rationale**: Settled by #520. The hostname form is fronted by Tailscale Serve which terminates TLS with auto-provisioned Let's Encrypt certs. The Tailscale IP form (`https://100.92.197.90:3456/api/v1/`) bypasses TLS termination — fine for some agent paths but creates the two-URL-bases gotcha that bit us pre-#520. Centralizing the choice eliminates the drift.

### 3. Token loading: file-based at `/data/services/openclaw/secrets/vikunja-api`

The default token path is `/data/services/openclaw/secrets/vikunja-api`. The client reads the file at construct time, strips whitespace, and rejects empty strings.

Override semantics: callers may pass `token=<explicit-string>` to bypass the file (used in tests + the rare credential-rotation tools that hold the token in-memory).

**Rationale**: File-based + override matches the existing `scripts/common/vikunja_config.py` pattern from #520. Putting the token on the filesystem (vs in env vars) means:

- No risk of leaking into a child process's environment
- Permissions are filesystem-level (`0600 claude:claude`), which the existing security-posture model already audits
- Rotation = one file write + service restart (no env-var refresh dance)

Tradeoff considered + rejected: keyring-style storage (gog-style encrypted file). Vikunja token is a single value with no scope, so the encryption layer adds complexity without proportional security gain — the threat model already assumes filesystem access = SSH access.

### 4. Timeout policy: 30s default, per-request override

Default timeout is **30 seconds** (DEFAULT_TIMEOUT = 30.0). Per-request overrides are accepted on every public method (`get`, `post`, `put`, `delete`).

Timeout failures raise `VikunjaTimeoutError` (subclass of `VikunjaError`, NOT `VikunjaHttpError` — there is no HTTP status). Both `socket.timeout` and `urllib.error.URLError` with a wrapped `socket.timeout` reason are mapped to this exception.

**Rationale**: 30s is generous for Vikunja's typical p95 (under 500ms on the office2 tailnet) but tolerates one slow round-trip without false-positive timeouts. Per-request override is needed for the few paths where Vikunja's bulk operations can take 2-5s under load.

### 5. Implementation: stdlib-only, stateless per-instance

The client uses `urllib.request` from the standard library, NOT `requests` or `httpx`. Each `VikunjaClient(...)` instantiation captures `base_url`, `token`, `timeout` at construct time. There is:

- No retry logic
- No connection pooling
- No response caching
- No pagination iterator helpers
- No global state

**Rationale**:

- **Stdlib only**: avoids dependency drift and removes a class of supply-chain risk. The Vikunja API is simple enough that `urllib.request` is genuinely sufficient.
- **Stateless**: each consumer constructs and discards a client per logical scope. Coupling instances across modules creates exactly the dependency-injection complexity Directive 6 deliberately avoids.
- **No retries**: retry policy is a domain concern (idempotency, backoff, jitter). Embedding it in the client commits all callers to one policy. Today's policy is "no retry"; if a domain needs retries, it wraps the client at the call site.
- **No caching**: same argument — caching is a domain concern that depends on the freshness contract of the specific data being read.
- **No paginate helpers**: pagination semantics differ per endpoint; helpers belong with the endpoint-specific wrappers.

### 6. Typed exception hierarchy with HTTP-status mapping

The client maps HTTP responses to a small typed hierarchy:

```text
VikunjaError
├── VikunjaHttpError              (any non-2xx that doesn't match a subclass)
│   ├── VikunjaAuthError          (401)
│   ├── VikunjaNotFoundError      (404)
│   ├── VikunjaBadRequestError    (400)
│   └── VikunjaServerError        (5xx, network errors, non-JSON body)
└── VikunjaTimeoutError           (socket.timeout, URLError(timeout))
```

Callers branch on `isinstance(exc, VikunjaAuthError)` etc. — they do NOT inspect status codes directly.

**Rationale**: Typed exceptions are the integration-boundary contract. Callers should react to "auth expired" or "task not found" semantically, not by scraping a status code field. The class hierarchy reflects which failures are likely recoverable per domain (e.g., habit completers should retry on transient 5xx but escalate auth errors).

Tradeoff: there is no rich error-data attached (no response body, no parsed error JSON). That's deliberate — see Decision 7 (Redaction).

### 7. Redaction-safe error messages by default

Default `str(exc)` returns only `"<ExceptionClass>: <path>"` — never response body content. A separate `exc.verbose_message()` method returns the longer representation including the status code, intended for ad-hoc operator debugging.

**Rationale**: Vikunja's error responses can echo back substrings of the request (e.g., filter syntax in 400 bodies). Auth tokens in headers don't go into bodies, but defense-in-depth: assume the body can contain anything sensitive and never log it by default. `verbose_message()` is the explicit opt-in for the rare debugging case.

This addresses spec.md FR-011 + FR-012 of the shipped contract.

### 8. URL composition: safely merge embedded query strings

The `_compose_url()` helper handles paths that already contain a query string (e.g., `"/projects/13/tasks?filter=done=true"`) by splitting via `urllib.parse`, merging caller-supplied `params`, and re-encoding.

**Rationale**: Naive `?` appending produces broken URLs (`...?filter=done=true?per_page=200`). Caller-supplied `params` take precedence over same-keyed values embedded in the path, which makes the merge predictable.

### 9. Content-Type discipline: POST/PUT always advertise `application/json`

POST and PUT requests always advertise `Content-Type: application/json` even when the caller sends no body (e.g., bulk-toggle endpoints that take only query parameters).

**Rationale**: Server-side content negotiation is unambiguous. Some Vikunja endpoints return 415 when the Content-Type is missing on a POST.

### 10. Empty-body responses parse to `{}`, not `None`

Successful responses with empty bodies (typical for DELETE 204) parse to an empty dict, not `None`. Callers that key into the result then get a uniform mapping type and `result.get(...)` works without a guard.

**Rationale**: Tiny ergonomics win that removes a common foot-gun.

## Alternatives Considered

| Alternative | Why rejected |
| --- | --- |
| `requests` library | Adds a third-party dependency for a small API surface; Directive 6 prefers stdlib-only where practical |
| `httpx` with async support | Same dependency cost + we have no async call sites yet; would over-engineer for current needs |
| Token loaded from env var (`VIKUNJA_TOKEN`) | Env vars leak into child processes; file + permissions is the cleaner posture |
| Token loaded from keyring (gog-style encrypted) | Vikunja token is unscoped; encryption adds complexity without proportional gain |
| Tailscale IP base URL (bypass Tailscale Serve) | Bypasses TLS termination; creates the two-URL-bases drift that #520 closed |
| Untyped `VikunjaError` for everything (status code field only) | Forces callers to scrape status codes; subclassing makes the integration contract explicit |
| Built-in retry with backoff | Retry policy is domain-specific; embedding one commits all callers to it. Today nobody retries; future retriers wrap at the call site |
| Built-in pagination iterator | Endpoint-specific; belongs with endpoint wrappers, not the generic client |
| Response body in default `str(exc)` | Risk of leaking sensitive request echoes into logs; `verbose_message()` is the opt-in |

## Consequences

- **For new Vikunja-touching code**: import from `scripts.common.vikunja_client`. Don't write a new HTTP wrapper. Construct a `VikunjaClient(...)` per logical scope; pass overrides only when truly needed.
- **For migration work (#543)**: each helper that still holds a local HTTP wrapper replaces it with `VikunjaClient` per this ADR. Tests should branch on the typed exception hierarchy.
- **For tests**: the keyword-only constructor allows clean override of `base_url`, `token`, `timeout` in unit tests. Pass an explicit `token="test-token"` and a `base_url="https://test.example.com/api/v1"` to avoid touching the real config helper.
- **For monitoring/observability**: log `exc.path` and the exception class name; never log `exc.verbose_message()` automatically.
- **For future changes**: any decision in this ADR can be amended (e.g., adding retry support) — but the amendment must be explicit, recorded here as a §"Decision changes" addendum, and the shipped client updated in a coordinated PR.

## References

- [`scripts/common/vikunja_client.py`](../../../scripts/common/vikunja_client.py) — the shipped client (314 lines)
- [`scripts/common/vikunja_config.py`](../../../scripts/common/vikunja_config.py) — the URL helper (95 lines)
- [Architecture review F-004](https://github.com/kentonium3/kg-automation/blob/main/docs/research/kg-automation-architecture-review/findings.md#f-004--vikunja-integration-lacks-a-shared-client-and-urltoken-configuration-boundary) — finding that triggered the epic
- kentonium3/kg-automation#531 — Epic
- kentonium3/kg-automation#541 — this ADR's tracking issue (closes via this ADR)
- kentonium3/kg-automation#542 — the refactor that shipped the client (closed 2026-06-08)
- kentonium3/kg-automation#543 — opportunistic migration of remaining helpers (open)
- kentonium3/kg-automation#520 — URL config foundation (closed)
- kentonium3/kg-automation#281 — Directive 6 helper conventions

## Decision changes

(Future amendments record here.)
