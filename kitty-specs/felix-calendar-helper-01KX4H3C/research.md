# Research: Felix Calendar Helper

**Mission**: felix-calendar-helper-01KX4H3C
**Date**: 2026-07-09
**Method**: Repo-convention mapping + live office2 environment probing (per
`[[feedback_design_phase_research]]` / DIR-015). All decisions below are
grounded in committed code and the real runtime, not assumptions.

---

## D1 — Authentication: reuse the proven spike pattern, generalized per-account

**Decision**: Build the helper's auth on `google-api-python-client` +
`google-auth-oauthlib`, reusing the `_load_or_mint()` / `_write_token()`
pattern already proven in `scripts/google/workspace_auth_spike.py`. Generalize
its single `FELIX_GOOGLE_DIR` credential home into a **per-account** store:
`~/.config/felix/google/<account>/{client_secret.json, token.json}`.

**Rationale**: RFC #681 resolved auth deterministically — a personal `@gmail`
account on an "In production" OAuth app mints a durable refresh token
(connectivity green 2026-07-09). The spike already demonstrates the exact
load → refresh → persist(0600) flow against the real Calendar API. Scope stays
least-privilege: `https://www.googleapis.com/auth/calendar` (read+write; the
spike used `calendar.events` — the helper needs `list` on calendars too, so the
broader `calendar` scope or `calendar.events` + `calendar.readonly` is used;
finalized in data-model).

**Alternatives rejected**:
- A broad Google Workspace MCP server — same trust class as `gog`, reintroduces
  the F0/#675 unbounded-surface problem. RFC #681 Q3 already rejected it.
- Service-account/domain-wide delegation — overkill for one personal account;
  not available for a consumer `@gmail` account anyway.

---

## D2 — Helper location and invocation

**Decision**: `scripts/google/calendar_helper.py` (the `scripts/google/`
package already exists, holding the spike). Auth logic factors into a small
sibling module `scripts/google/calendar_auth.py` so it is unit-testable and
reusable by later Google helpers (mail/drive). Logical invocation:
`python3 -m scripts.google.calendar_helper <subcommand> …` from the checkout
root — **but see D3**: on office2 the interpreter is the helper's venv python,
not bare `python3`.

**Rationale**: Matches `scripts/<domain>/` convention and the existing Google
namespace. A separate auth module keeps the CRUD helper thin and the auth
fail-safe path independently testable (NFR-003).

---

## D3 — office2 dependency provisioning: a dedicated uv venv (LOAD-BEARING)

**Decision**: The helper runs on office2 under a **dedicated uv-provisioned
virtualenv** at `/data/services/openclaw/felix-calendar/venv`, holding pinned
`google-api-python-client`, `google-auth`, and `google-auth-oauthlib`. Agents
invoke it as:
`cd /home/claude/kg-automation && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.calendar_helper …`

**Rationale (grounded in live probing)**:
- office2 system `python3` (3.12.3) **cannot import** `googleapiclient` /
  `google.oauth2` — the libs are absent, and there is **no `pip`/`pip3`** on the
  `claude` PATH (`python3 -m pip` → "No module named pip"). The deterministic
  helpers work today only because they need nothing beyond apt `dist-packages`
  (jsonschema/pyyaml).
- The available package manager is **`uv` 0.11.2** (`~/.local/bin/uv`).
- There is direct precedent for the venv pattern: `felix-doc-auditor-driver`
  and `felix-heartbeat-gate` both run
  `/data/services/openclaw/<svc>/venv/bin/python …/scripts/<x>/run.py` with
  `WorkingDirectory=/home/claude/kg-automation`. The calendar helper follows the
  same established shape.

**Alternatives rejected**:
- System-wide install into `/usr/local/lib/python3.12/dist-packages` — needs
  `pip` (absent) and root/sudo (claude has none; Tier 0). Rejected.
- `uv run --with google-api-python-client …` (ephemeral resolution per call) —
  adds per-invocation latency and a network dependency inside a fail-safe path;
  violates the "no invisible debt / canonical package-managed path" preference
  (`[[feedback_no_workarounds_for_expediency]]`). Rejected.

**Consequence**: this is a small, justified deviation from the bare
`python3 -m scripts.*` convention — captured in Charter Check. The venv is
provisioned as a deploy step (D6).

---

## D4 — Inbox path rewire + felix-admin-calendar reshape (closes #679)

**Decision**: The NL→structured layer is **already deterministic** and stays:
`scripts/calendar_routing/validate_calendar_event.py` parses date/time/duration/
recurrence in pure Python and `scripts/inbox/route_calendar_event.py` assembles
the `create_calendar_event` payload. The **only** thing that changes at the
terminal step is *who executes the create*:

- **Today (broken, #679)**: capture builds the envelope, then invokes
  `felix-admin-calendar` via `openclaw agent --agent felix-admin-calendar …`
  through `exec` (an agent-to-agent hop). Haiku mishandles this hop (the
  #661/#662/#679 fragility class), so inbox→calendar silently fails.
- **New**: capture builds the same envelope, then calls the **new calendar
  helper directly** (a deterministic CLI, no agent hop) →
  `calendar_helper create --payload-file <envelope>`. The event is created; the
  note is marked processed. **No agent-to-agent delegation** → #679 closed.

**`felix-admin-calendar` reshape (judgment-only)**: it keeps the two jobs that
genuinely need an LLM — (a) the **conversational** calendar path (Kent → main →
calendar agent) and (b) **clarification round-trips** for incomplete inbox
captures (matching Kent's async reply to a pending record, extracting the
missing fields). In both, its terminal action becomes
`calendar_helper …` instead of `gog calendar create`. **The `gog` skill is
removed from its openclaw.json registration.**

**Rationale**: Removing the agent hop from the happy path is the minimal,
robust fix. The existing deterministic parsers are reused verbatim (no reason to
re-derive judgment that is already code). This aligns with the spec's explicit
AC: "reaches calendar via a deterministic helper call, not agent-to-agent
delegation."

**Alternatives rejected**:
- A deterministic agent-to-agent delegation mechanism (fix the hop) — this is
  exactly what #679 proved unreliable/blocked (`sessions_send`), and it keeps a
  needless indirection. Rejected.

---

## D5 — Multi-account model

**Decision**: An `--account <name>` selector (default `personal`) chooses the
credential set at `~/.config/felix/google/<account>/`. `calendar_id` defaults to
`primary`. The existing routing helpers' `DEFAULT_ACCOUNT` constant flips from
`kent@intentional.biz` to `personal` (the new happy path targets the personal
calendar). Adding the `intentional.biz` account later = drop its credentials at
`~/.config/felix/google/intentional/` and pass `--account intentional` — **no
code change** (FR-005, SC-005).

**Rationale**: Keys the store by account name so the second account is purely
additive. `personal` is the account RFC #681 proved and Kent chose to develop
against first.

**Note**: `account` in the current payloads was a `gog --account` value
(`kent@intentional.biz`). In the direct-API world it becomes the credential-set
selector. This is a scoped semantic-default change in two helper files +
fixtures, not a global string rename (mission stays `change_mode: normal`).

---

## D6 — Deploy: manifest (Tier 2+3), venv provisioning, manual creds staging, rebaseline

**Decision**: A `deploys/queued/felix-calendar-helper.yaml` manifest
(`tier: 3`, `audited_surface: true`) with an entrypoint deploy script that:
1. **Tier-2 gate**: `snapshot.verify_restic_recent --max-age-hours 24` before
   any state change (credentials/venv).
2. **Provision the venv**: create/refresh `/data/services/openclaw/felix-calendar/venv`
   via uv and install the pinned google deps (idempotent).
3. **Verify creds present**: file-presence check for
   `~/.config/felix/google/personal/{client_secret,token}.json` (0600). The
   helper does **not** copy secrets — staging is a manual operator step.
4. **Smoke self-check**: run `calendar_helper --self-check` (loads creds,
   refreshes token, lists calendars) as a post-flight gate.

Helper **code** reaches office2 via the checkout's `git pull` (felix-deployer's
5-min tick) after `feat → main`. **Agent prompts** reach office2 via the
`agent-prompt-sync` timer (edits to `scripts/openclaw/agents/felix-admin-calendar/
AGENTS.md` + capture's `AGENTS.md.tmpl`). The openclaw.json change (remove `gog`
from felix-admin-calendar `skills`) is a **manual out-of-band** edit + gateway
restart (monitored surface) → **manual rebaseline** (out-of-band exception, per
CLAUDE.md), OR encoded so felix-deployer covers it — finalized in quickstart.
Either way the merge records `Rebaseline: completed at <ts>`.

**Credential staging**: copy Mac `~/.config/felix/google/personal/{client_secret,
token}.json` → office2 same path (0600, dir 0700). Secrets never enter the repo,
never via git. This is an explicit manual step in quickstart; the manifest only
*verifies* presence.

**Rationale**: Honors DIR-004 (manifest discipline), the Tier-2 snapshot gate
(C-005), and the audited-surface rebaseline obligation. Mirrors the doc-auditor/
heartbeat-gate venv provisioning precedent.

---

## D7 — Fail-safe authentication behavior

**Decision**: On any auth failure (missing/invalid token, `invalid_grant`,
refresh failure), the helper writes `ERROR: auth_failed …` to **stderr**, emits
`SUMMARY: op=<op> status=auth_failed`, performs **no** calendar mutation, and
exits with a **dedicated non-zero code (3)** distinct from usage (2) and
operational/API errors (1). The consuming agent surfaces the error verbatim and
never reports a false success (no-silent-fallback, #675/#683; SC-004).

**Rationale**: A distinct exit code lets agents and the deploy self-check
distinguish "credentials need re-staging" from a transient API error, and
guarantees a failed auth can never be misread as a completed action.

---

## D8 — Testing strategy

**Decision**: `tests/google/test_calendar_helper.py` + `tests/google/
test_calendar_auth.py`. Mock the Google client (`googleapiclient.discovery.build`
returns a fake `service` whose `.events()` records calls) and `Credentials`
(valid / expired-refreshable / invalid-grant). Cover: create/list/update/delete
happy paths, the auth-failure fail-safe path (FR-006/SC-004), payload-file
mapping from the `create_calendar_event` envelope, multi-account credential-path
resolution (FR-005), and exit-code contract. The repo's global
`tests/conftest.py` HTTP block already forbids live network; a `live_smoke`
marker (per `pytest.ini`, gated by `LIVE_SMOKE_ENABLED=1`) carries one opt-in
real-calendar round-trip for local verification only (never in CI). Coverage
runs `--cov-branch` at the repo threshold.

**Rationale**: Matches the existing mocking discipline (`tests/common/
test_vikunja_client.py`) and NFR-003 (100% of subcommands + explicit auth-failure
test, no network in CI). The `live_smoke` marker is the sanctioned path for a
real-API check without weakening CI (`[[feedback_live_integration_tests]]`: the
marker documents the quirk; it is not a mock-substitute).

---

## Open items folded into design (no NEEDS CLARIFICATION remain)

- **Scope string** (`calendar` vs `calendar.events`+`calendar.readonly`):
  finalized in data-model.md — helper uses the scope that supports `calendars`
  list + event CRUD; re-consent is a one-time operator action if the staged
  token's scope is narrower.
- **openclaw.json rebaseline path** (manual vs deployer-covered): finalized in
  quickstart.md; default is manual out-of-band + manual rebaseline, matching the
  CLAUDE.md out-of-band exception.
- **Duplicate validators** (`validate_calendar_event.validate` vs
  `route_calendar_event.validate_payload`): left as-is (documented in
  route_calendar_event's own header); this mission does not collapse them —
  out of scope, flagged for a later cleanup.
