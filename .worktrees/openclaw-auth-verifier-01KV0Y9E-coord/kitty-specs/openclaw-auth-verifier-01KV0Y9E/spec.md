# Specification: OpenClaw Auth Verifier

**Mission**: `openclaw-auth-verifier-01KV0Y9E`
**Mission type**: software-dev
**Source issue**: kentonium3/kg-automation#597 (preventive follow-up to #596; references #591, #557, #343, #490)

---

## Intent Summary

Ship a deterministic, read-only-by-default helper script that detects the two silent failure modes of the OpenClaw 2026.6.x Anthropic auth substrate **before** they manifest as cron-call rejections: (a) per-agent SQLite rows that shadow the read-through inheritance from `main`, and (b) drift between the plaintext credential file consumed by non-openclaw Python drivers and `main`'s SQLite auth store. Integrate the verifier into `anthropic-rotate.sh` as a fail-closed gate at the end of every rotation; on failure, emit a copy-pasteable rollback hint and let the operator drive the rollback decision.

- **Primary actor**: solo operator (Kent), invoking from Mac via `ssh office2-claude`. Future agents may also invoke it as part of post-upgrade checklists.
- **Trigger**: post-OpenClaw upgrade, post-Anthropic-key rotation, or ad-hoc when sub-agent cron failures appear in WhatsApp escalations.
- **Success outcome**: `--check` runs in under thirty seconds, reports per-agent auth-row topology, plaintext-vs-SQLite sync status, and Anthropic API acceptance of the canonical key. All-clear exits zero with a green report; any finding exits non-zero with a structured operator-facing summary.
- **Rule that must always hold**: the verifier MUST NOT print key values — only sha256-prefix fingerprints (8 hex chars) and structural verdicts. This rule binds stdout, stderr, log files, error messages, and the lifecycle-integration rollback hint.
- **Most common exception**: shadow row detected on a sub-agent after `openclaw doctor --fix` migration. The verifier emits the finding, the operator runs `--repair` (which backs up the affected SQLite store and clears the per-agent auth rows so inheritance is restored), and re-runs `--check` to confirm green.

---

## Domain Language

Use these canonical terms throughout planning and implementation:

- **canonical key** — the Anthropic API key value currently resident in `main`'s OpenClaw SQLite auth store. The reference value the verifier compares everything else against.
- **per-agent auth row** — a row in either `auth_profile_store` or `auth_profile_state` (key `primary`) of a sub-agent's `~/.openclaw/agents/<id>/agent/openclaw-agent.sqlite`. Healthy state for any sub-agent is **zero** rows.
- **shadow** — the condition where a sub-agent has at least one per-agent auth row, overriding the read-through inheritance from `main`. Detection is row-presence-based, not value-comparison-based.
- **drift** — the condition where `/data/services/openclaw/secrets/anthropic` (the plaintext credential file) and `main`'s SQLite store hold byte-different key values.
- **plaintext file** — `/data/services/openclaw/secrets/anthropic`, mode `0600`, owned by `claude:claude`. The substrate consumed by `felix-doc-auditor-driver` (#343) and `felix-heartbeat-gate` (#490) outside the openclaw-gateway path.
- **verifier** — the helper script `scripts/security/anthropic-verify.sh`. Not "checker", not "validator", not "auditor".
- **rotation script** — `scripts/security/anthropic-rotate.sh`. The pre-existing helper from #591 that this mission integrates with.
- **fingerprint** — sha256 hex digest truncated to the first 8 characters. The only form in which key-derived material may appear in the verifier's output.
- **finding** — a structured verdict object produced by `--check`, naming the failure mode (`shadow` / `drift` / `anthropic_rejected` / `network`), the affected store, and the suggested operator action. One finding per detected condition.
- **fail-closed gate** — the behavior of `anthropic-rotate.sh` when it invokes `--check` at the end of a rotation: any non-zero exit halts rotation as successful, prints the findings, and prints a one-line rollback command for the operator to run.

---

## User Scenarios & Testing

### Primary scenario — Post-upgrade verification

After an OpenClaw upgrade (e.g., 2026.6.5 → 2026.6.6), the operator runs `ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check`. The verifier enumerates `~/.openclaw/agents/*/agent/openclaw-agent.sqlite`, reports per-agent auth-row presence with row counts and last-update timestamps, sha256-prefix-compares the plaintext file against `main`'s SQLite, and pings Anthropic with the plaintext value. All sub-agents are empty, fingerprints match, and Anthropic returns HTTP 200. Verifier exits zero with a green summary in under thirty seconds. The operator has independent confidence that the upgrade did not silently break auth inheritance.

### Secondary scenario — Post-rotation fail-closed gate

The operator runs `ssh -t office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh` to rotate the Anthropic key. After steps 1 through 4 succeed (paste, plaintext write, SQLite update, gateway restart), the rotation script invokes `anthropic-verify.sh --check`. The verifier reports green, the rotation script exits zero, and the operator receives a final "rotation complete" message. Had the verifier reported a finding (e.g., a sub-agent had a pre-existing shadow row the rotation did not touch), the rotation script would have emitted the findings and a one-line rollback command, exiting non-zero. The rotation itself is not auto-undone; the operator decides whether to roll back or remediate forward.

### Exception scenario — Shadow row detected, operator repairs

A `WhatsApp` escalation reports `felix-admin-capture` cron failures with `invalid x-api-key`. The operator runs `--check`, which reports `shadow` finding on `felix-admin-capture` (table `auth_profile_store`, last-update timestamp). The operator inspects the finding and runs `--repair`, which copies the affected SQLite store to a `.pre-repair.<unix-ts>.bak` sibling, deletes rows from `auth_profile_store` and `auth_profile_state`, and instructs the operator to restart `openclaw-gateway.service`. The operator restarts the gateway and re-runs `--check`; the verifier reports green. No key value appears anywhere in this flow.

### Exception scenario — Plaintext drift detected, operator repairs

A future Anthropic key rotation goes through `openclaw models auth paste-api-key` directly (skipping the rotation script). `--check` later reports `drift` between the plaintext file and `main`'s SQLite (fingerprints differ). The operator runs `--repair`, which copies the plaintext file to `.pre-repair.<unix-ts>.bak` and writes `main`'s SQLite key value into the plaintext file at mode `0600`. The operator re-runs `--check`; green.

### Exception scenario — Anthropic rejects the key

`--check` finds clean topology and no drift but the Anthropic API ping returns HTTP 401. The verifier emits `anthropic_rejected` finding with the response status and a hint to rotate the key via the rotation script. Distinct from `network` (HTTP timeout, DNS failure, TLS handshake failure) which is emitted as `network` and instructs the operator to retry. The exit code distinguishes these so a future timer or wrapper can branch on them.

### Edge cases

- **No sub-agents present** (fresh-install office2): verifier reports `main` only, no shadow possible; OK.
- **`main` itself has zero auth rows**: verifier emits a distinct `main_empty` finding because the inheritance source is unconfigured. `--repair` does NOT attempt to fix this; the operator must run the rotation script.
- **Plaintext file missing**: verifier emits `plaintext_missing` finding. `--repair` does NOT create the file from `main`'s SQLite — operator runs the rotation script (the file's existence is a rotation invariant, not a verifier responsibility).
- **`auth_profile_store` populated but `auth_profile_state` empty (or vice versa)**: verifier treats either-populated as shadow; `--repair` clears both tables.
- **`--repair` invoked when `--check` is green**: verifier prints "nothing to repair" and exits zero; no mutation.
- **`--check` invoked on a non-office2 host** (operator typos): verifier detects missing canonical paths and exits with a clear error pointing at the expected invocation form.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The verifier enumerates sub-agent SQLite stores by globbing `~/.openclaw/agents/*/agent/openclaw-agent.sqlite` (excluding `main`); discovery is dynamic, not hardcoded. | required |
| FR-002 | For each sub-agent, the verifier counts rows in `auth_profile_store` and `auth_profile_state` and reports presence (healthy = both zero) along with last-update timestamps when populated. | required |
| FR-003 | The verifier computes sha256[:8] fingerprints of the plaintext file at `/data/services/openclaw/secrets/anthropic` and of `main`'s `auth_profile_store["primary"].store_json["profiles"]["anthropic:default"]["key"]`; reports both fingerprints and a binary `match | drift` verdict. | required |
| FR-004 | The verifier performs an Anthropic API liveness ping using the plaintext file value: `POST /v1/messages` with `model: claude-haiku-4-5`, `max_tokens: 8`, `messages: [{"role":"user","content":"ping"}]`. Reports HTTP status + model echoed. | required |
| FR-005 | The verifier emits at most one structured finding per detected condition. Finding shape: `{ type: shadow|drift|anthropic_rejected|network|main_empty|plaintext_missing, agent|file: <name>, evidence: { …deterministic fields only… }, suggested_action: "<text>" }`. | required |
| FR-006 | The verifier writes no key value to any stream — stdout, stderr, log file, finding evidence, or error text. Verified by a CI test that greps the verifier's output against a known-test sentinel value. | required |
| FR-007 | The verifier supports `--check` (default; read-only; no mutation under any circumstance) and `--repair` (read-write; mutations are gated behind this explicit flag — no interactive prompt). | required |
| FR-008 | In `--repair` mode, the verifier copies each store it intends to mutate to a `.pre-repair.<unix-ts>.bak` sibling at mode `0600` before any deletion or write. | required |
| FR-009 | `--repair` on a shadow finding deletes all rows from the sub-agent's `auth_profile_store` and `auth_profile_state` and prints the systemd command the operator must run next (`systemctl --user restart openclaw-gateway.service`). The verifier does NOT auto-restart the gateway. | required |
| FR-010 | `--repair` on a drift finding writes `main`'s SQLite key value to the plaintext file via an atomic rename (`<file>.tmp` → `<file>`), preserving mode `0600` and owner `claude:claude`. | required |
| FR-011 | The verifier's exit code distinguishes: `0` green; `2` shadow; `3` drift; `4` anthropic_rejected; `5` network; `6` main_empty or plaintext_missing; `1` unexpected error. | required |
| FR-012 | `anthropic-rotate.sh` invokes `anthropic-verify.sh --check` at the end of a successful rotation (after gateway restart and the existing inbox-7am liveness probe). | required |
| FR-013 | If the post-rotation `--check` exits non-zero, `anthropic-rotate.sh` emits the verifier's findings, prints a single-line rollback command (e.g., `anthropic-rotate.sh --rollback <backup-timestamp>`), and exits non-zero. Rotation is NOT auto-undone. | required |
| FR-014 | `anthropic-rotate.sh --rollback <ts>` restores the three rotation artifacts (plaintext file, openclaw.json, the SQLite store-side `auth-profiles.json`-style backup written during rotation) from the timestamped backups created during the rotation it is rolling back. | required |
| FR-015 | `docs/runbooks/openclaw-ops.md` § _Known upgrade gotchas_ documents both failure modes (shadow + drift), describes the verifier as the post-`doctor --fix` and post-rotation gate, and shows the canonical invocation. | required |
| FR-016 | `docs/runbooks/credential-rotation-ops.md` § _anthropic_ references the verifier as part of the rotation success criteria. | required |
| FR-017 | The merge commit records `Rebaseline: completed at <ts>` or `Rebaseline: not required — <reason>` per the audited-surface protocol (#557) — the verifier and rotation-script changes touch `scripts/security/`, an audited surface. | required |

## Non-Functional Requirements

| ID | Requirement | Status | Threshold |
|---|---|---|---|
| NFR-001 | `--check` completes end-to-end (including the Anthropic API ping) within thirty seconds on office2 under normal network conditions. | required | ≤ 30 s wall clock |
| NFR-002 | The verifier produces human-readable summary output on stdout suitable for ssh-attached terminal viewing; lines are individually addressable for grep / awk consumption by future wrappers. | required | One line per finding; one summary line at the end |
| NFR-003 | The verifier writes nothing to disk during `--check` mode. | required | Zero file mutations; verified by a test that snapshots filesystem state before and after |
| NFR-004 | `--repair` mutations are atomic: either the backup AND the mutation both land, or neither does. | required | Backup file exists before mutation begins; failed mutation triggers a clean error message naming the backup path for recovery |
| NFR-005 | The verifier's dependency surface is restricted to the office2 stock environment: `python3` (with stdlib `sqlite3`, `urllib.request`, `pathlib`, `hashlib`, `shutil`, `os`, `json`) and `bash`. No third-party PyPI packages. | required | Zero non-stdlib imports |
| NFR-006 | The rotation-script fail-closed gate adds no more than five seconds to a successful rotation. | required | ≤ 5 s overhead at end of `anthropic-rotate.sh` |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The verifier runs entirely on office2. Mac-side invocation is via `ssh office2-claude`; no key material crosses the SSH wire. | binding |
| C-002 | `--check` is read-only. No filesystem mutation, no openclaw CLI side effects, no gateway restart, no Anthropic API mutation. | binding |
| C-003 | State mutations happen only behind `--repair`. No `--dry-run` flag; `--check` IS the dry-run surface. | binding |
| C-004 | The verifier MUST NOT call `openclaw doctor --fix`. The doctor's auth-import path is what plants shadow rows in the first place; the verifier exists because of that path and must not perpetuate it. | binding |
| C-005 | The verifier prints fingerprints only. Key values never appear in stdout, stderr, log file, error message, finding evidence, or environment variables visible to subsequent process output. | binding |
| C-006 | No systemd timer or scheduled invocation is shipped by this mission. The verifier is operator-triggered and rotation-script-invoked only. | binding |
| C-007 | No JSON output mode is shipped by this mission. Human-readable text is the only output format. | binding |
| C-008 | Per-sub-agent Anthropic API pings are out of scope; only the canonical plaintext key (which is also `main`'s SQLite value when not drifted) is pinged. | binding |
| C-009 | The verifier does not modify any OpenClaw configuration file (`~/.openclaw/openclaw.json` and siblings). | binding |
| C-010 | The verifier's risk tier is **Tier 3** (Logic / Workflow per `docs/design/architecture/data/change-risk-taxonomy.json`). No host-level changes. The `--repair` mode mutates application state (auth stores + plaintext credential file) — pre-flight discipline per Tier 2 is satisfied by the backup-before-mutate invariant in FR-008. | binding |
| C-011 | The verifier does not fix or work around the OpenClaw upstream behavior where `paste-api-key` writes per-agent rows that the runtime rejects. That is upstream behavior; the verifier surfaces the shadow row, the operator clears it. | binding |
| C-012 | The verifier's helper-script tier per Felix Constitution Directive 6 + `docs/design/helper-script-conventions.md` is **helper** (not library, not skill). Deterministic checks; small public surface; reusable from the rotation script and from operator ad-hoc invocation. | binding |

---

## Success Criteria

Measurable, technology-agnostic outcomes that determine mission success at acceptance and post-merge review.

- **SC-001** — A reproduction of the #596 shadow condition (manual paste-api-key into a sub-agent) is detected by `--check` in under thirty seconds with an exit code of `2` and a finding identifying the affected sub-agent and table.
- **SC-002** — A forced drift between the plaintext file and `main`'s SQLite (manual edit of either) is detected by `--check` with an exit code of `3` and a finding showing both sha256[:8] fingerprints.
- **SC-003** — `--repair` on a shadow finding removes the per-agent auth rows, leaves a `.pre-repair.<ts>.bak` sibling, and prints the gateway-restart command; a subsequent `--check` plus gateway restart yields green.
- **SC-004** — `--repair` on a drift finding rewrites the plaintext file atomically from `main`'s SQLite value, leaves a `.pre-repair.<ts>.bak` sibling, and a subsequent `--check` yields green.
- **SC-005** — An Anthropic-rejection scenario (a known-revoked key in place of the canonical key) is detected by `--check` with exit code `4`, distinguishable from a network failure (exit code `5`) injected separately.
- **SC-006** — `anthropic-rotate.sh` invokes the verifier at the end of a real rotation; a deliberately-engineered post-rotation shadow condition triggers the fail-closed gate; the rotation script prints the rollback command and exits non-zero.
- **SC-007** — A `grep` of the verifier's stdout and stderr across all scenarios above reveals zero occurrences of the test-sentinel Anthropic key value.
- **SC-008** — Both runbook touchpoints (`docs/runbooks/openclaw-ops.md`, `docs/runbooks/credential-rotation-ops.md`) document the verifier and the invocation form; CI verifies the runbook section anchors exist.
- **SC-009** — The merge commit records `Rebaseline: completed at <ts>` per the audited-surface protocol (#557); the operator has run the rebaseline reset on office2 within the rotation-script-invoked verification surface.
- **SC-010** — The local tracker issue #597 is closed at merge with a comment naming the merge commit hash; memory entry `reference_openclaw_per_agent_auth_shadow` is updated to cross-link the verifier as the canonical detection path.

---

## Key Entities

- **Anthropic API Key** — The secret being verified. Lives in three places on office2: `main`'s OpenClaw SQLite store, the plaintext file at `/data/services/openclaw/secrets/anthropic`, and (when shadow conditions exist) one or more sub-agent SQLite stores. The verifier never prints its value.
- **Per-Agent Auth Row** — A row in `auth_profile_store` or `auth_profile_state` of a sub-agent's `openclaw-agent.sqlite`, keyed `primary`. Healthy state for a sub-agent: zero rows in both tables.
- **Plaintext Credential File** — `/data/services/openclaw/secrets/anthropic`, mode `0600`, owned `claude:claude`. Consumed by `felix-doc-auditor-driver` (#343) and `felix-heartbeat-gate` (#490) directly via filesystem read; not via the openclaw-gateway.
- **Canonical Key** — The Anthropic API key value resident in `main`'s SQLite `auth_profile_store["primary"].store_json["profiles"]["anthropic:default"]["key"]`. Reference value for the drift comparison.
- **Verifier Helper Script** — `scripts/security/anthropic-verify.sh`. The deliverable. Bash-driven outer shell with a Python core for the SQLite read + sha256 + Anthropic ping.
- **Rotation Script** — `scripts/security/anthropic-rotate.sh`. Pre-existing helper from #591; this mission adds the post-rotation verifier invocation and the `--rollback <ts>` mode.
- **Finding** — A structured verdict object produced by `--check`. Single-purpose: name a failure mode, identify the affected store, suggest the operator's next action. No key-derived material beyond fingerprints.
- **Backup Sibling** — A copy of a store about to be mutated by `--repair`, written to `<original>.pre-repair.<unix-ts>.bak` at mode `0600` before any deletion or write. The recovery surface.

---

## Assumptions

- OpenClaw 2026.6.x SQLite schema is stable for the life of this mission's acceptance window: `auth_profile_store(store_key, store_json, updated_at)` and `auth_profile_state(state_key, state_json, updated_at)`, with `store_json["profiles"]["anthropic:default"]["key"]` holding the API key.
- The plaintext file at `/data/services/openclaw/secrets/anthropic` continues to be the documented integration substrate for `felix-doc-auditor-driver` and `felix-heartbeat-gate` (per `docs/design/architecture/data/credential-manifest.json` § _anthropic_).
- The Anthropic API endpoint at `https://api.anthropic.com/v1/messages` accepts `claude-haiku-4-5` for small (8-token) liveness pings; pinging budget is negligible (single-call cost well under $0.001 per `--check`).
- Python 3.10+ stdlib is available on office2 with `sqlite3`, `urllib.request`, `pathlib`, `hashlib`, and `shutil` — verified by the existing scripts that read the plaintext file directly.
- The `claude` user on office2 has read access to all sub-agent SQLite stores and to the plaintext file (verified by today's #596 investigation).
- `systemctl --user restart openclaw-gateway.service` remains the canonical post-mutation surface for picking up auth-store changes.
- `anthropic-rotate.sh` continues to follow the self-update-from-main convention; the verifier integration changes do not break the re-exec pattern.

---

## Out of Scope

- A daily user-systemd-timer that runs `--check` and writes `last-check.json` (operator-triggered only this mission; deferred per Q1-B; #597 acceptance criteria explicitly mark this as follow-on).
- JSON output mode for machine consumption (deferred until a timer or wrapper consumer materializes).
- Per-sub-agent Anthropic API liveness pings (only the canonical key is pinged; sub-agent topology is what's checked).
- An upstream fix or workaround for the OpenClaw behavior where `paste-api-key` against a sub-agent writes per-agent rows the runtime then rejects.
- Other credential types (Google OAuth refresh tokens for `gog`, GitHub PATs, etc.) — Anthropic only.
- A `doctor --fix` replacement or wrapper that prevents shadow rows from being planted in the first place.
- Changes to the existing rotation script's interactive paste flow (#591 owns that surface).
- Felix Constitution amendments.

---

## Notes

- The two failure modes covered by this mission are reproducible deterministically: `paste-api-key` against a sub-agent reliably plants a row the runtime rejects, and editing either side of the plaintext/SQLite sync produces drift. Both are testable without live operator state; SC-001 through SC-005 are verifiable in a smoke environment that mirrors office2's layout.
- The verifier deliberately does NOT trigger an `openclaw doctor --fix` invocation in either mode (per C-004). The doctor's auth-import path is the upstream source of shadow rows; perpetuating it would loop the operator.
- The fail-closed gate in `anthropic-rotate.sh` (FR-012, FR-013) intentionally stops short of auto-rollback. The operator owns the rollback decision because rotation backups touch three filesystem locations and a service restart; an automated rollback would have to be atomic across all four, which is more complex than a one-line `--rollback <ts>` command the operator can read before running.
- The verifier prints fingerprints, not key values. This rule is binding (C-005) and is verified in SC-007 by greppable test sentinel. The intent is to make the verifier safe to invoke in any logged or recorded operator session — chat transcripts, shell history, monitoring dashboards — without ever exposing key material.
- The Tier 3 classification (C-010) is operator-facing logic and workflow. The `--repair` mode touches application state (Tier 2 surface) but the backup-before-mutate invariant satisfies the Tier 2 pre-flight discipline inline.
- This mission's deliverable substrate (`scripts/security/` + runbook addenda + rotation-script integration) is small enough that a single-work-package plan or a two-WP split (verifier + rotation-script integration) is plausible. The plan phase owns that decomposition.
