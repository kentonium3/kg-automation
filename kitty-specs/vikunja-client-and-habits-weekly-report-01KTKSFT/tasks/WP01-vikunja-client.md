---
work_package_id: WP01
title: Shared Vikunja client + tests
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-011
tracker_refs: []
planning_base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
merge_target_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
base_commit: 1e2532b8fb82ff48a1789288c7b8a1da082ef098
created_at: '2026-06-08T15:11:03.600067+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
agent: "codex:gpt-5:reviewer-renata:reviewer"
shell_pid: "8342"
history: []
authoritative_surface: scripts/common/
execution_mode: code_change
owned_files:
- scripts/common/vikunja_client.py
- tests/common/**
tags: []
---

# WP01: Shared Vikunja client + tests

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Deliver `scripts/common/vikunja_client.py` — the shared HTTP wrapper for Vikunja API consumers. Encapsulates base URL composition + token loading + request execution + timeout policy + typed error semantics. First consumer is the new weekly helper in WP02; future migrations of `scripts/sync/fetch.py` and `scripts/vikunja/*` are deferred follow-ups.

Per Felix Constitution Directive 6, this is the deterministic infrastructure layer. The client is pure: no LLM, no global state, no caching. Each method is a pure function of inputs → (parsed JSON OR typed exception).

## Context

- **Authority docs**: `spec.md` FR-001 / FR-002 / FR-011 / FR-012; `contracts/vikunja_client.md` (full API surface); `data-model.md` (entity definitions).
- **Existing patterns to follow**:
  - `scripts/inbox/` helpers — stdin/stdout JSON convention, exit codes, atomic state writes.
  - `scripts/calendar_routing/validate_calendar_event.py` (mission #558) — most recent stdlib-only helper precedent.
  - `tests/inbox/` and `tests/calendar/` — pytest layout including `--cov-branch` usage; `urlopen` mocking via the global guard in `tests/conftest.py`.
- **Standard library only**: no `requests`, no `httpx`. Use `urllib.request`, `urllib.parse`, `urllib.error`, `json`. This matches the mission #558 precedent.
- **Token storage**: `/data/services/openclaw/secrets/vikunja-api` (read directly; no token-helper function exists in the repo).
- **Base URL helper**: `scripts/common/vikunja_config.get_vikunja_base_url()` exists; the client strips trailing slash before composing request paths (the canonical config file has a trailing slash; Vikunja's API rejects `//` paths).
- **Vikunja API base URL**: `https://office2.tail0f5f56.ts.net/api/v1` (no trailing slash, per phase-0 R-005).
- **Test-first per DIRECTIVE_034**: author T004's fixtures + T005's tests BEFORE finalizing the implementation. Red → Green → Refactor.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent <name>`
- No dependencies — this WP starts immediately.

---

## Subtask T001: Scaffold module + exception hierarchy

**Purpose**: Establish the module file and exception classes. Sets up the import boundary so later subtasks can write tests that import from `scripts.common.vikunja_client`.

**Steps**:
1. Create `scripts/common/vikunja_client.py`. Module docstring summarizing purpose + reference to `kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/vikunja_client.md`.
2. Imports: `json`, `urllib.parse`, `urllib.request`, `urllib.error`, `socket`, `dataclasses`, `typing` (Optional, Any).
3. Define the exception hierarchy:
   ```python
   class VikunjaError(Exception):
       """Base exception for all Vikunja-client failures."""
       def __init__(self, path: str, status: int | None = None):
           self.path = path
           self.status = status
           super().__init__(f"{type(self).__name__}: {path}")

       def verbose_message(self) -> str:
           """Detailed message for ad-hoc debugging. Not used by default."""
           return f"{type(self).__name__}(path={self.path!r}, status={self.status!r})"

   class VikunjaHttpError(VikunjaError): ...
   class VikunjaAuthError(VikunjaHttpError): ...
   class VikunjaNotFoundError(VikunjaHttpError): ...
   class VikunjaBadRequestError(VikunjaHttpError): ...
   class VikunjaServerError(VikunjaHttpError): ...
   class VikunjaTimeoutError(VikunjaError): ...
   ```
4. No top-level code; just imports + class definitions.

**Files**:
- `scripts/common/vikunja_client.py` (new — initial scaffold ~50 lines)

**Validation**:
- [ ] Module imports cleanly: `python3 -c "from scripts.common.vikunja_client import VikunjaError, VikunjaClient" ` (will fail until T002; that's expected for now)
- [ ] Exception classes can be raised and caught: `raise VikunjaAuthError(path="/test", status=401)`
- [ ] `str(exc)` returns `"VikunjaAuthError: /test"` — no status, no body

---

## Subtask T002: Implement `VikunjaClient` class

**Purpose**: The core HTTP wrapper. Stateless per-instance configuration; pure-function methods.

**Steps**:
1. Append to `scripts/common/vikunja_client.py`:
   ```python
   DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"
   DEFAULT_TIMEOUT = 30.0

   class VikunjaClient:
       def __init__(self, *, base_url: str | None = None,
                    token: str | None = None,
                    timeout: float = DEFAULT_TIMEOUT) -> None:
           # Resolve + validate
           ...
   ```
2. Constructor logic:
   - If `base_url is None`: call `from scripts.common.vikunja_config import get_vikunja_base_url; base_url = get_vikunja_base_url()`. Strip trailing slash via `.rstrip("/")`.
   - Validate `base_url` matches `^https?://[^/]+/api/v1$` regex. Raise `ValueError` if not.
   - If `token is None`: open `DEFAULT_TOKEN_PATH`, read, strip whitespace. Raise `ValueError` if empty.
   - Validate `timeout > 0`. Raise `ValueError` if not.
   - Store on `self.base_url`, `self.token`, `self.timeout`.
3. Implement private `_request(method, path, params, json_body, timeout)`:
   - Compose full URL: `f"{self.base_url}{path}"` + querystring from `params` if any.
   - Build `Authorization: Bearer {token}` header. Add `Content-Type: application/json` for POST/PUT.
   - For POST/PUT with `json_body`: `data = json.dumps(json_body).encode("utf-8")`.
   - Use `urllib.request.Request(url, data=data, headers=headers, method=method)`.
   - Execute via `urllib.request.urlopen(req, timeout=effective_timeout)`.
   - Parse response body via `json.loads(response.read())`. Return parsed object.
   - Wrap network/HTTP errors in the typed exceptions per T003.
4. Implement public methods `get(path, *, params=None, timeout=None)`, `post(path, *, json=None, params=None, timeout=None)`, `put(...)`, `delete(...)` as thin wrappers calling `_request`.

**Files**:
- `scripts/common/vikunja_client.py` (extends scaffold to ~150 lines)

**Validation**:
- [ ] `VikunjaClient(base_url="https://x.test/api/v1", token="t")` constructs without error
- [ ] `VikunjaClient(base_url="https://x.test/api/v1/", token="t")` — trailing slash stripped
- [ ] `VikunjaClient(base_url="invalid", token="t")` raises `ValueError`
- [ ] `VikunjaClient(base_url="https://x.test/api/v1", token="")` raises `ValueError`
- [ ] `VikunjaClient(base_url="https://x.test/api/v1", token="t", timeout=0)` raises `ValueError`

---

## Subtask T003: Error mapping + redaction-safe `__str__` + verbose mode

**Purpose**: Map HTTP status codes / network conditions to typed exceptions. Default error messages are redaction-safe (path only). Opt-in verbose mode for debugging.

**Steps**:
1. In `_request`, catch errors and map them:
   ```python
   try:
       response = urllib.request.urlopen(req, timeout=effective_timeout)
       body = response.read()
       return json.loads(body) if body else {}
   except socket.timeout:
       raise VikunjaTimeoutError(path=path, status=None) from None
   except urllib.error.HTTPError as exc:
       status = exc.code
       if status == 401:
           raise VikunjaAuthError(path=path, status=status) from None
       elif status == 404:
           raise VikunjaNotFoundError(path=path, status=status) from None
       elif status == 400:
           raise VikunjaBadRequestError(path=path, status=status) from None
       elif 500 <= status < 600:
           raise VikunjaServerError(path=path, status=status) from None
       else:
           raise VikunjaHttpError(path=path, status=status) from None
   except urllib.error.URLError as exc:
       if isinstance(exc.reason, socket.timeout):
           raise VikunjaTimeoutError(path=path, status=None) from None
       raise VikunjaServerError(path=path, status=None) from None
   except json.JSONDecodeError:
       raise VikunjaServerError(path=path, status=200) from None
   ```
2. Confirm exception `__str__` is `f"{type(self).__name__}: {self.path}"` (set in T001's `VikunjaError.__init__`). NO body content.
3. `verbose_message()` exists from T001 — returns the dataclass-like rep. Tests cover that default str is short; verbose is longer.

**Files**:
- `scripts/common/vikunja_client.py` (extends to ~180 lines total)

**Validation**:
- [ ] All 6 HTTP status codes (401, 404, 400, 500, 502, 503) map to the expected exception class
- [ ] `socket.timeout` maps to `VikunjaTimeoutError`
- [ ] `urllib.error.URLError(socket.timeout)` also maps to `VikunjaTimeoutError`
- [ ] Server returning non-JSON body maps to `VikunjaServerError`
- [ ] `str(exc)` for any exception returns only `{class}: {path}` — no body, no status detail
- [ ] `exc.verbose_message()` returns the longer representation

---

## Subtask T004 [P]: Curate test fixtures

**Purpose**: Author the 8 mock-response scenarios per `contracts/vikunja_client.md` § Test fixtures. Can be done in parallel with T002/T003 — fixtures are stand-alone JSON files.

**Steps**:
1. Create `tests/common/fixtures/vikunja_client_responses.json` with the 8 named scenarios:
   ```json
   {
     "mock_response_200_json": {
       "status": 200,
       "body": [{"id": 1, "title": "Sample habit", "done": false}]
     },
     "mock_response_401": {"status": 401, "body": {"code": 401, "message": "Invalid token"}},
     "mock_response_404": {"status": 404, "body": {"code": 404, "message": "Not found"}},
     "mock_response_400": {"status": 400, "body": {"code": 400, "message": "Invalid filter"}},
     "mock_response_500": {"status": 500, "body": "Internal Server Error"},
     "mock_response_timeout": {"raise_on_request": "socket.timeout"},
     "mock_response_non_json": {"status": 200, "body": "<html>not json</html>"},
     "mock_response_empty_body": {"status": 204, "body": ""}
   }
   ```
2. Helper functions in `tests/common/conftest.py` (NEW) to translate each scenario into a mocked `urlopen` callable.

**Files**:
- `tests/common/__init__.py` (NEW, empty)
- `tests/common/conftest.py` (NEW, ~80 lines — mock helpers)
- `tests/common/fixtures/vikunja_client_responses.json` (NEW)

**Validation**:
- [ ] JSON file parses cleanly
- [ ] Each of the 8 scenarios has a corresponding helper-function or fixture in `conftest.py`
- [ ] Helpers can be imported by the test file in T005

---

## Subtask T005: Write unit tests

**Purpose**: Cover every code path in `vikunja_client.py`. Red → Green → Refactor with T002/T003.

**Steps**:
1. Create `tests/common/test_vikunja_client.py`. Tests organized by area:
   - Construction (5+ tests): default base_url, explicit base_url, trailing-slash strip, token resolution from file, validation errors.
   - URL normalization (3+ tests): with/without trailing slash, embedded query string, path encoding.
   - HTTP method coverage (4+ tests): GET, POST, PUT, DELETE — each makes the expected `urllib.request.Request` call.
   - Param encoding (3+ tests): single param, multiple params, special characters.
   - Error mapping (8+ tests): one per status code + timeout + URL error + JSON decode error.
   - Redaction (3+ tests): `str(exc)` short for each error class; `verbose_message()` longer; no body leaks.
2. Use `monkeypatch.setattr("urllib.request.urlopen", mock_callable)` to inject the fixture responses.
3. Aim for ~50 tests total.

**Files**:
- `tests/common/test_vikunja_client.py` (NEW, ~250 lines)

**Validation**:
- [ ] `pytest tests/common/test_vikunja_client.py -v` runs all tests
- [ ] All tests pass against the T002/T003 implementation
- [ ] No flaky behavior on repeat run

---

## Subtask T006: Pytest coverage gate

**Purpose**: Enforce ≥90% line + ≥85% branch coverage on `scripts/common/vikunja_client.py`.

**Steps**:
1. Locate existing pytest config — likely `pyproject.toml` (under `[tool.pytest.ini_options]`) or `pytest.ini`. Match the convention from mission #558's calendar gate.
2. Add coverage config block targeting `scripts/common/vikunja_client`:
   - Under `[tool.coverage.run]`: extend `source` list to include `scripts/common/vikunja_client`.
   - Under `[tool.coverage.report]`: ensure `fail_under = 90`, `show_missing = true`.
3. Document the canonical invocation in `tests/common/README.md` (NEW, optional, ~20 lines): `pytest tests/common/test_vikunja_client.py --cov=scripts/common/vikunja_client --cov-branch --cov-fail-under=90`.
4. Verify gate passes against the T002/T003/T005 deliverables.

**Files**:
- `pyproject.toml` OR `pytest.ini` (existing — modified)
- `tests/common/README.md` (NEW, optional)

**Validation**:
- [ ] Coverage config includes `scripts/common/vikunja_client` in measured source
- [ ] `pytest tests/common/ --cov=scripts/common/vikunja_client --cov-branch --cov-fail-under=90` succeeds (line ≥90%, branch ≥85%)
- [ ] Removing one branch in `vikunja_client.py` temporarily causes the gate to fail (smoke check)

---

## Definition of Done

- [ ] All 6 subtasks complete with their per-subtask validation items checked.
- [ ] `pytest tests/common/test_vikunja_client.py --cov=scripts/common/vikunja_client --cov-branch --cov-fail-under=90` passes from a clean checkout.
- [ ] Helper has zero external dependencies beyond stdlib.
- [ ] No uncommitted changes outside this WP's `owned_files`.

## Risks

1. **Vikunja's `urllib.error.URLError` wrapping inconsistency** — some versions of Python wrap `socket.timeout` differently. Tests should cover both paths (the `urllib.error.URLError(reason=socket.timeout)` AND the bare `socket.timeout`). T003's error-mapping logic catches both.
2. **Coverage thresholds in CI** — if `pyproject.toml` already has a different coverage convention, T006 may need to adapt. Mitigation: T006 step 1 reads existing config before modifying.

## Reviewer guidance

- Reviewer runs `pytest tests/common/ --cov=scripts/common/vikunja_client --cov-branch` independently and verifies actual coverage numbers.
- Reviewer checks: are exception messages ACTUALLY redaction-safe? Grep the test file for any test that asserts a response body's content survives into `str(exc)` — if so, the redaction is broken.
- Reviewer verifies the 6 HTTP error classes have distinct exception types (not all the same class).
- Reviewer scans for any `requests` import or third-party dependency — must be stdlib only.

## Activity Log

- 2026-06-08T15:11:37Z – claude:sonnet:python-pedro:implementer – shell_pid=93140 – Started implementation via action command
- 2026-06-08T15:21:46Z – claude:sonnet:python-pedro:implementer – shell_pid=93140 – Ready for review: stdlib-only impl, 40 tests, 100% coverage, no callers yet (WP02 first)
- 2026-06-08T15:22:04Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=96400 – Started review via action command
- 2026-06-08T15:28:06Z – user – shell_pid=96400 – Moved to planned
- 2026-06-08T15:48:02Z – claude:sonnet:python-pedro:implementer – shell_pid=3202 – Started implementation via action command
- 2026-06-08T15:54:16Z – claude:sonnet:python-pedro:implementer – shell_pid=3202 – Cycle 2: fixed URL merge (#2), Content-Type bodyless POST/PUT (#4), {} empty body (#3), Consumers docstring (#1). FR-012 over-claim (#5) handled by orchestrator via map-requirements --replace. 45 tests, 100% line/branch coverage.
- 2026-06-08T15:54:25Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=5251 – Started review via action command
- 2026-06-08T15:59:56Z – user – shell_pid=5251 – Moved to planned
- 2026-06-08T16:01:22Z – claude:sonnet:python-pedro:implementer – shell_pid=7578 – Started implementation via action command
- 2026-06-08T16:03:44Z – claude:sonnet:python-pedro:implementer – shell_pid=7578 – Cycle 3: docstring uses dotted module form (--cov=scripts.common.vikunja_client) so pytest-cov actually collects coverage. Verified path-form fails at 0% and dotted-form succeeds at 100%/100%.
- 2026-06-08T16:03:56Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=8342 – Started review via action command
- 2026-06-08T16:16:16Z – user – shell_pid=8342 – Arbiter override: codex cycle-3 review verdict PASS (all 4 cycle-1 substantive issues fixed). 45 tests, 100% line+branch coverage. Issue-matrix verdicts now have explicit Follow-up handles.
