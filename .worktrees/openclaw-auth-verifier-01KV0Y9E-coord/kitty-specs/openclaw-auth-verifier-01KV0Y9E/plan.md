# Implementation Plan: OpenClaw Auth Verifier

**Mission**: `openclaw-auth-verifier-01KV0Y9E`
**Date**: 2026-06-13
**Spec**: [spec.md](./spec.md)
**Source issue**: kentonium3/kg-automation#597
**Branch contract**: current `main` → planning/base `main` → merge target `main` (branch_matches_target=true).

---

## Summary

Deliver a deterministic, read-only-by-default helper script (`scripts/security/anthropic-verify.sh`) that detects per-agent SQLite auth-row shadow and plaintext-file/SQLite drift in the OpenClaw 2026.6.x Anthropic auth substrate. Integrate it as a fail-closed gate at the end of `scripts/security/anthropic-rotate.sh`, emit a copy-pasteable rollback hint on failure (no auto-rollback; operator-driven), and extend `anthropic-rotate.sh` with `--rollback <ts>` to restore the three rotation artifacts from per-step backups. Document both shadow and drift failure modes in `docs/runbooks/openclaw-ops.md` § _Known upgrade gotchas_ and reference the verifier from `docs/runbooks/credential-rotation-ops.md` § _anthropic_.

The deliverable is **all helper-script-tier work** (per Felix Constitution Directive 6 + `docs/design/helper-script-conventions.md`): a bash outer entrypoint dispatching to a Python core that uses only the stdlib (no third-party PyPI). The Python core is the deterministic substrate; the bash outer is the operator UX + TTY/path validation surface.

## Technical Context

**Language/Version**: Python 3.10+ (stdlib only) and Bash 5+. Both already present on office2 (Ubuntu 24.04 LTS).

**Primary Dependencies**: Python stdlib only — `sqlite3`, `urllib.request`, `urllib.error`, `hashlib`, `shutil`, `pathlib`, `os`, `json`, `sys`, `time`. No third-party PyPI packages (per spec NFR-005). Bash uses standard utilities present in the office2 image (`stat`, `chmod`, `mv`, `printf`).

**Storage**:
- Read: OpenClaw 2026.6.x per-agent SQLite stores at `~/.openclaw/agents/*/agent/openclaw-agent.sqlite` (tables `auth_profile_store` + `auth_profile_state`).
- Read: plaintext credential file at `/data/services/openclaw/secrets/anthropic` (mode 0600, owner `claude:claude`).
- Write (only in `--repair` mode): the affected sub-agent's SQLite store (`DELETE FROM auth_profile_store; DELETE FROM auth_profile_state`); the plaintext credential file (atomic rename from `.tmp` sibling).
- Write (always under `--repair`): a `.pre-repair.<unix-ts>.bak` sibling of any store about to be mutated.

**Testing**: pytest (per charter tools). Test discipline (per Felix Constitution test directive + `feedback_live_integration_tests` memory): mock at integration boundaries — `sqlite3` connections, `urllib.request.urlopen`, filesystem paths — using `unittest.mock` from stdlib. No live Anthropic API calls in CI tests. A `tests/security/fixtures/` directory mirrors office2's layout (`agents/<id>/agent/openclaw-agent.sqlite` with both populated and empty fixture databases) for end-to-end shadow + drift reproductions inside the test process. Coverage target: every FR-### exit-code path + every C-005 "no key in output" assertion.

**Target Platform**: office2 (Ubuntu 24.04 LTS Linux) only. Mac-side invocation is via `ssh office2-claude`; the helper itself runs on office2. No Windows. No macOS-native execution. Python `pathlib` + `os` portability concerns are out of scope.

**Project Type**: single — helper script + Python core in `scripts/security/`; tests in `tests/security/`. No web/mobile/multi-project structure.

**Performance Goals**:
- `--check` completes end-to-end (including the live Anthropic ping) in ≤ 30 seconds on office2 under normal network conditions (spec NFR-001).
- Rotation fail-closed gate adds ≤ 5 seconds to a successful `anthropic-rotate.sh` (spec NFR-006).
- `--repair` mutations are atomic per-store (FR-008 backup-before-mutate; NFR-004).

**Constraints**:
- Key values MUST NEVER appear in stdout, stderr, log files, finding evidence, or error messages — only sha256[:8] fingerprints. CI test verifies this with a sentinel grep (spec C-005, SC-007).
- `--check` is strictly read-only — zero filesystem mutations (spec NFR-003); verified by a before/after snapshot test.
- No mutation of `~/.openclaw/openclaw.json` or other OpenClaw config files (spec C-009).
- No call to `openclaw doctor --fix` from the verifier (spec C-004); that's the upstream source of shadow rows.
- Helper-tier — single bash entrypoint, small public surface, reusable from the rotation script and from operator ad-hoc invocation (spec C-012).

**Scale/Scope**: 5 sub-agents currently on office2 (`felix-admin-capture`, `felix-admin-habits`, `felix-admin-escalation`, `felix-admin-tasker`, `felix-admin-calendar`); plus `main`. The helper discovers them dynamically by globbing (spec FR-001) — no hardcoded list. Single host (office2 only); no multi-host orchestration.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_001 (Architectural Integrity)**: PASS. The verifier is a single helper-tier script with one entrypoint (`anthropic-verify.sh`) and a small Python core. The rotation-script integration is a single new step in `anthropic-rotate.sh` (call verifier, branch on exit code). Boundaries are clear: verifier doesn't touch rotation-script internals; rotation script doesn't replicate verifier logic.
- **DIRECTIVE_003 (Decision Documentation)**: PASS. Two scope decisions (Q1-B standalone vs combined, Q2-C emit-and-hint vs auto-rollback) are captured in `spec.md` § _Out of Scope_ and in the rotation-script-integration FRs. This plan documents the Python/Bash split and stdlib-only choice with rationale.
- **DIRECTIVE_010 (Spec Fidelity)**: PASS. Every IC below maps to specific FR/NFR/C IDs from spec.md. Implementation cannot drift from spec without amending it first.
- **DIRECTIVE_024 (Locality of Change)**: PASS. Changes are confined to `scripts/security/` (new helper + rotation-script integration), `tests/security/` (new test module), and `docs/runbooks/` (two addenda). No changes to existing helpers, agent prompts, or unrelated infrastructure.
- **DIRECTIVE_031 (Context-Aware Design)**: PASS. The bounded context is the OpenClaw 2026.6.x auth substrate (per-agent SQLite stores + plaintext credential file). The verifier does not cross into other credential types (`gog`, GitHub PATs) or other agent state (sessions, memory, plugins). Per spec _Out of Scope_.
- **DIRECTIVE_033 (Targeted Staging)**: PASS. Each WP's commit will list its owned files explicitly. No `git add -A` or directory-style staging at commit time.
- **DIRECTIVE_034 (Test-First Development)**: PASS. The test module is authored before the helper logic (acceptance contracts first); implementation is driven by pytest red→green per the WP convention.

**Project Directives (Felix Constitution)**:
- **DIR-001** (Production runs on office2; Mac is authoring only): PASS. Helper lives on office2; Mac-side invocation is via `ssh office2-claude` only.
- **Audited surfaces / rebaseline (#557)**: TRIGGERED — `scripts/security/` is an audited surface per `docs/design/architecture/data/audited-surfaces.json`. The merge commit MUST record `Rebaseline: completed at <ts>` per spec FR-017. The operator runs the rebaseline reset on office2 post-merge.

No charter violations. Proceed to Phase 0.

## Project Structure

### Documentation (this mission)

```
kitty-specs/openclaw-auth-verifier-01KV0Y9E/
├── plan.md              # This file
├── spec.md              # Mission specification (already committed)
├── research.md          # Phase 0 output (this command)
├── data-model.md        # Phase 1 output (this command)
├── quickstart.md        # Phase 1 output (this command)
├── contracts/           # Phase 1 output (this command)
├── checklists/
│   └── requirements.md  # Spec quality checklist (already committed)
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

Selected option: **Single project — helper script + Python core + tests in their respective conventional locations.**

```
scripts/security/
├── anthropic-verify.sh             # NEW — bash entrypoint, dispatches to Python core
├── anthropic_verify/                # NEW — Python core package
│   ├── __init__.py
│   ├── core.py                      # Discovery + topology + drift + Anthropic ping
│   ├── repair.py                    # --repair backup-and-mutate logic
│   └── findings.py                  # Structured finding dataclass + formatting
└── anthropic-rotate.sh             # EXISTING — extended with verifier invocation + --rollback

tests/security/
├── test_anthropic_verify_core.py   # NEW — topology + drift detection contract tests
├── test_anthropic_verify_repair.py # NEW — --repair backup + mutation tests
├── test_anthropic_verify_output.py # NEW — C-005 sentinel-grep + NFR-003 fs-snapshot tests
├── test_anthropic_rotate_gate.py   # NEW — rotation script fail-closed gate tests
└── fixtures/
    ├── healthy/                     # Empty per-agent stores, matched main + plaintext
    ├── shadow/                      # felix-admin-capture has rogue auth_profile_store row
    └── drift/                       # plaintext sha != main SQLite sha

docs/runbooks/
├── openclaw-ops.md                 # MODIFIED — § _Known upgrade gotchas_ addendum
└── credential-rotation-ops.md      # MODIFIED — § _anthropic_ references verifier
```

**Structure Decision**: Single project. The deliverable is one helper plus its tests plus runbook addenda. No web/mobile/multi-project structure applies.

## Complexity Tracking

No charter violations. No complexity tracking required.

## Implementation Concern Map

> Implementation concerns are NOT work packages. `/spec-kitty.tasks` translates these into executable WPs — one concern may become multiple WPs; multiple small concerns may merge.

### IC-01 — Topology + drift detection core

- **Purpose**: Detect the two failure modes — per-agent SQLite shadow rows and plaintext/SQLite drift — entirely from read-only access on office2. Produce structured findings; emit no key material.
- **Relevant requirements**: FR-001 (enumerate sub-agents), FR-002 (per-agent row count), FR-003 (sha256[:8] compare), FR-004 (Anthropic live ping), FR-005 (structured findings), FR-006 (no key in output), FR-011 (distinct exit codes), NFR-001 (≤ 30 s wall), NFR-002 (human-readable output), NFR-003 (zero fs mutation in --check), NFR-005 (stdlib only), C-001 (runs on office2 only), C-002 (--check read-only), C-005 (fingerprints only), C-008 (no per-sub-agent pings), C-009 (no openclaw.json mutation).
- **Affected surfaces**: `scripts/security/anthropic_verify/core.py`, `scripts/security/anthropic_verify/findings.py`, `scripts/security/anthropic-verify.sh` (bash entry that dispatches to `python3 -m anthropic_verify.core --check`). Tests at `tests/security/test_anthropic_verify_core.py` and `tests/security/test_anthropic_verify_output.py`.
- **Sequencing/depends-on**: none (foundational).
- **Risks**: (a) JSON path navigation into the SQLite blob (`store_json["profiles"]["anthropic:default"]["key"]`) must tolerate missing keys gracefully and emit `main_empty` finding rather than crash; (b) urllib's default 15 s connect timeout interacts with NFR-001 — total time budget for the Anthropic ping is the difference between wall budget and the discovery+sha overhead.

### IC-02 — Repair surface

- **Purpose**: When `--repair` is invoked on a finding from IC-01, mutate the affected store after a timestamped backup. Single-purpose: clear shadow rows OR rewrite the plaintext file. Operator owns the gateway restart.
- **Relevant requirements**: FR-007 (--check vs --repair modes), FR-008 (backup-before-mutate), FR-009 (clear shadow rows + print gateway-restart command), FR-010 (atomic rename for plaintext), NFR-004 (atomic mutations), C-003 (no --dry-run; --check IS dry-run), C-005 (fingerprints only — repair output also).
- **Affected surfaces**: `scripts/security/anthropic_verify/repair.py`, dispatched from the same bash entry (`anthropic-verify.sh --repair`). Tests at `tests/security/test_anthropic_verify_repair.py`.
- **Sequencing/depends-on**: IC-01 — repair operates on findings produced by the detection core; no duplicate detection logic.
- **Risks**: (a) atomic rename semantics on the `/data/services/openclaw/secrets/` mount; (b) `shutil.copy2` preserves mode 0600 but ownership may need an explicit chown if the source backup was created by a different uid (unlikely under `claude` only).

### IC-03 — Rotation-script integration

- **Purpose**: Make `anthropic-rotate.sh` invoke the verifier as a fail-closed gate after a successful rotation, and add the `--rollback <ts>` mode that restores the three rotation artifacts from per-step backups.
- **Relevant requirements**: FR-012 (rotate invokes --check), FR-013 (fail-closed with rollback hint), FR-014 (--rollback <ts> mode), NFR-006 (≤ 5 s overhead).
- **Affected surfaces**: `scripts/security/anthropic-rotate.sh` — add Step 6 (verify) after the existing Step 5 (liveness probe); add `--rollback <ts>` argparse branch with backup-restoration logic. Tests at `tests/security/test_anthropic_rotate_gate.py`.
- **Sequencing/depends-on**: IC-01 + IC-02 — the verifier and repair commands must exist before rotate can call them.
- **Risks**: (a) the existing rotate script's self-update-from-main re-exec must not break when new flags are added; (b) backup timestamps must be discoverable by the rollback flow without parsing rotate's stdout (write a per-rotation manifest file?).

### IC-04 — Runbook + rebaseline closeout

- **Purpose**: Document both failure modes in `docs/runbooks/openclaw-ops.md` § _Known upgrade gotchas_, reference the verifier from `docs/runbooks/credential-rotation-ops.md` § _anthropic_, and record the rebaseline status in the merge commit per #557.
- **Relevant requirements**: FR-015 (openclaw-ops runbook), FR-016 (credential-rotation-ops runbook), FR-017 (rebaseline obligation).
- **Affected surfaces**: `docs/runbooks/openclaw-ops.md`, `docs/runbooks/credential-rotation-ops.md`, merge-commit-message convention.
- **Sequencing/depends-on**: IC-01 + IC-02 + IC-03 — runbooks describe behavior that must already exist.
- **Risks**: minor — runbook drift if the helper's CLI surface changes between authoring and merge.

---

The plan above is sufficient for `/spec-kitty.tasks` to decompose into WPs. Phase 0 research + Phase 1 design artifacts follow.
