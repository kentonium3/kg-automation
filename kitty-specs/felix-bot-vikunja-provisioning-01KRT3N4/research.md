# Research: felix-bot Vikunja provisioning

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`

This document records research conclusions that resolve uncertainties in the spec and plan. Each entry is a discrete decision with rationale and alternatives considered.

The spec has zero `[NEEDS CLARIFICATION]` markers — discovery resolved all open questions during `/spec-kitty.specify`. This research file captures the supporting decisions for technical details established during plan phase.

---

## R-001 — Vikunja API capabilities verification

**Question**: Does the office2 Vikunja v0.24.6 instance support the API operations this mission requires (user registration, project sharing, token management)?

**Decision**: Yes. Live probe on 2026-05-17 verified:

- `POST /api/v1/register` accepts `{username, email, password}` and creates a user (verified by trying with empty payload and receiving `"Please specify a username and a password"`)
- `GET /api/v1/projects` returns the 12 real projects + 5 pseudo-projects
- `PUT /api/v1/projects/{id}/users` is the documented sharing endpoint
- `GET /api/v1/projects/{id}/users` returns the share list (empty for all 12 projects today)
- Labels (`personal`, `intentional`, `metalcasework`) are global, not per-user — confirmed by reading via the kent token
- `registration_enabled: true` per `GET /api/v1/info`

**Rationale**: Direct verification removes the largest unknown — that the API surface assumed by the spec actually exists on the target instance.

**Alternatives considered**: Trust the Vikunja docs alone. Rejected because the live probe is cheap and gives stronger ground truth.

**Source**: `docs/design/research/vikunja-task-model-research.md` §1.

---

## R-002 — Helper language and dependencies

**Question**: What language and dependencies should the four Vikunja helpers use?

**Decision**: Python 3.10+ with standard library only (`argparse`, `json`, `subprocess`, `urllib.request`). No third-party packages.

**Rationale**:

- Python 3.10+ is the kg-automation standard (per `CLAUDE.md` and the existing helpers in `scripts/habits/`, `scripts/openclaw/agents/main/`).
- Standard library covers everything needed: HTTP via `urllib.request` (matches the simplicity of one-shot scripts; `requests` is not currently a project dependency that I want to introduce just for this mission).
- Avoiding new dependencies keeps the change footprint minimal and avoids supply-chain review (per the spec-ready criteria's "Supply-chain review" check).

**Alternatives considered**:

- `requests` library — more ergonomic but introduces a dependency. Rejected; `urllib.request` is sufficient for our four endpoints.
- Bash with `curl` + `jq` — simpler but less testable, inconsistent with the rest of the codebase.

---

## R-003 — Testing pattern

**Question**: How should the helpers be tested without coupling tests to the live Vikunja instance?

**Decision**: Pytest with subprocess invocation + mocked HTTP responses via `unittest.mock.patch` of `urllib.request.urlopen`. No live Vikunja calls in pytest. Live integration is the operator-driven `validate_felix_bot.py` execution during pre-swap validation (FR-004).

**Rationale**:

- Matches the existing pattern in `tests/openclaw/agents/main/test_felix_file_issue.py` (21 subprocess tests that exercise `--dry-run` mode).
- Fast tests, CI-friendly, no Tailscale dependency.
- The live integration test happens naturally as part of the operator flow — the validation script IS the integration test, executed against the real instance during execution.

**Alternatives considered**:

- Pytest with live Vikunja calls. Rejected — requires Tailscale + live credentials for CI; test pollution if a test fails mid-flow.
- Manual smoke test only. Rejected — Phase 6 + Phase 7 of ADR-0002 will likely reuse the helper patterns; tests give regression coverage when those phases come.

---

## R-004 — Validation comment target

**Question**: Where does `validate_felix_bot.py` write its sample comment when verifying attribution?

**Decision**: Throwaway task created at validation start, deleted entirely after the validation completes. Default target project is Habits (ID 13); configurable via `--target-project-id` flag.

**Rationale**:

- Throwaway task means zero pollution risk to any real task's comment history.
- Habits as the default target project matches Felix's primary surface — most relevant for validating that felix-bot can write to the project Felix exercises most.
- Configurable flag enables validation against other projects if needed (e.g., during Phase 6 or 7).

**Alternatives considered**:

- Existing real task with a `[Felix-Validation]` prefixed comment + delete after. Rejected — the delete might fail, leaving pollution.
- Dedicated permanent "Felix Validation" project. Rejected — overkill for a one-shot mission; creates persistent infrastructure with no clear long-term use case.

---

## R-005 — Atomic secrets-file rotation

**Question**: How does `swap_vikunja_secrets.py` make the secrets rotation atomic and recoverable?

**Decision**: Standard "write-temp + rename" pattern within the `swap_vikunja_secrets.py` helper:

1. Validate the new token argument is well-formed (non-empty string, reasonable length)
2. Read existing contents of `/data/services/openclaw/secrets/vikunja-api` into memory
3. Write a `.bak` file (`vikunja-api.kent-pre-felix-bot.bak`) atomically (write to `.bak.tmp`, then rename to `.bak`, with explicit `chmod 600` and ownership check)
4. Write the new token to `vikunja-api.tmp` atomically (`os.write` with `O_WRONLY|O_CREAT|O_TRUNC`, set mode 600 before close, fsync)
5. `os.rename(vikunja-api.tmp, vikunja-api)` — atomic on the same filesystem
6. `systemctl --user restart openclaw-gateway` and wait for it to come up healthy
7. Post-rotation verification — if it fails, automatically restore from `.bak` and exit nonzero

**Rationale**:

- The write-temp-then-rename pattern guarantees the secrets file is never partially written. Either old contents or new contents — never something in between.
- The `.bak` file is written before the rotation, so rollback is local-only (no network needed).
- The systemctl restart is a deterministic operation; gateway health is verifiable.

**Alternatives considered**:

- Direct overwrite of the secrets file. Rejected — risk of partial-write corruption on system crash.
- Use of `flock` for concurrency. Rejected — only one operator runs the swap at a time; lock not needed.

---

## R-006 — Operator-driven vs auto-orchestrated

**Question**: Should the four helpers be invoked individually by the operator, or chained by a single orchestrator script?

**Decision**: Operator-driven. Each helper is invoked separately; the operator confirms SUMMARY output and decides whether to proceed to the next phase. No orchestrator script.

**Rationale**:

- Aligns with Felix Constitution Directive 6 (deterministic detection in scripts; judgment / interpretation by the human).
- Each phase boundary is a meaningful decision point (pre-flight check, validation success, post-swap soak entry, post-soak cleanup). Forcing the operator to engage at each boundary surfaces problems early.
- An orchestrator becomes a single point of judgment that could mask validation failures or skip rollback opportunities.

**Alternatives considered**:

- Single `provision_felix_bot.py --phase {pre-validate,swap,post-verify,rollback}` orchestrator. Rejected per D6 framing.
- Bash wrapper that invokes each phase sequentially with confirmation prompts. Rejected — adds a layer with no clear benefit over the operator running commands directly from the runbook.

---

## R-007 — Doc update commit timing

**Question**: When in the mission flow are `credential-manifest.json`, `credentials-and-secrets.md`, `identity-model.md`, and `service-inventory.json` updated and committed?

**Decision**: Commit immediately after `swap_vikunja_secrets.py` verifies the post-swap attribution (FR-008). Before the 7-day soak begins. All four files in a single commit.

**Rationale**:

- The swap is the moment-of-truth. Once attribution is verified, the new identity IS the system's state — docs should reflect that immediately.
- Waiting for the full 7-day soak would leave the authoritative JSON manifest stale for a week.
- If rollback is needed during soak, the doc commit is reverted as part of the rollback path (single commit revert).
- Bundling all 4 files in one commit per Constraint C-003 (JSON authoritative + narrative view must not drift).

**Alternatives considered**:

- Commit docs before the swap (claim intent). Rejected — creates a window where the manifest disagrees with reality.
- Commit docs after the soak passes. Rejected — leaves the manifest stale for a week; the audit trail value is lost during the period when problems are most likely to arise.

---

## R-008 — felix-bot password generation and storage

**Question**: How is felix-bot's Vikunja password generated and stored?

**Decision**: Operator-driven generation via 1Password's password generator (24-char minimum, mixed case + digits + symbols). Stored as a new 1Password entry titled "felix-bot — Vikunja office2" with the email `kentgale+felix-bot@gmail.com` and the URL of the office2 Vikunja instance. No on-disk copy.

**Rationale**:

- 1Password is Kent's stated password manager (Q5 of discovery).
- Per the discovery decision (Q5b option A), the password lives only in the password manager. The API token in the secrets file is the operational credential; the password is for the rare emergency UI login scenario.
- Keeping the password out of any on-disk file or env-var reduces the attack surface — even if `/data/services/openclaw/secrets/` is exfiltrated, the password is not in it.

**Alternatives considered**:

- On-disk in `/data/services/openclaw/secrets/felix-bot-vikunja-password`. Rejected per Q5b decision (option A only, not option B).
- TOTP enabled. Rejected per Q5c (skip TOTP — service account, Tailscale-gated, lockout risk on recovery).

---

## R-009 — Sequencing of kent token revocation

**Question**: When in the mission does `revoke_kent_tokens.py` run?

**Decision**: After the 7-day soak passes. Not before.

**Rationale**:

- The `.bak` file preserves the old kent token for rollback. Revoking kent's tokens before the soak completes would orphan the rollback path.
- The 7-day soak window is the empirical confidence interval — if no issues during 7 days, the rotation is stable enough that the kent token rollback is no longer needed.
- Revoking before soak also burns the kent UI access if Kent's UI session happens to depend on the same auth secret (Vikunja JWT sessions vs API tokens are independent but separating them in time avoids any edge case interaction).

**Alternatives considered**:

- Revoke immediately after swap. Rejected — kills the rollback path.
- Never revoke. Rejected — leaves a kent-attributed credential active forever, defeating the audit-trail purpose of this mission.

---

## R-010 — Permission level on the kent UI session post-rotation

**Question**: Does Kent's existing UI session at the Vikunja web UI continue to work after his API token is revoked?

**Decision**: Yes. Vikunja JWT sessions (from `POST /api/v1/login`) and long-lived API tokens are independent. Revoking the API token does not invalidate active UI sessions.

**Rationale**:

- Per the Vikunja v0.24.6 architecture, UI logins issue JWTs with their own expiration. API tokens are a separate credential class.
- Verified by reading Vikunja's auth source / docs (and consistent with all standard token-vs-session models).

**Risk**: If Kent's UI session expires and he needs to re-authenticate, his password is required. That password is for kent (his original Vikunja user), not felix-bot. Kent retains his kent password — out of scope to touch.

**Alternatives considered**: None — this is a verification of an assumption (A-001 from the spec), not a design choice.
