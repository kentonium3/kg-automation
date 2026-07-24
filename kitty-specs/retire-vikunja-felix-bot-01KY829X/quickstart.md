# Quickstart / Verification: Consolidate Felix→Vikunja onto the shared client (phase 1 of #860)

**Behavior-preserving refactor — no identity change, no live cutover.** (The token flip + attended
Tier-2 cutover are Phase 2, a follow-on kitty-light change.)

## Unit / parity tests (local — the core acceptance gate)

- **`VikunjaClient` new methods**: unit-test each operation added under FR-002 (comments,
  completions, label ops, bulk reads, partial-update read-modify-write) against the client contract
  + error model.
- **Per-consumer parity**: for each migrated consumer, a test proves the migrated path issues the
  **same** Vikunja requests / produces the same effects as the raw-HTTP path (mock/record the HTTP).
  `sync/cycle.py` (bidirectional) gets the most coverage.
- Run the full Vikunja + inbox + habits + escalation + enrichment + trust + credential-health suites.

## Grep gate (SC-001)

- `grep -rnE "secrets/vikunja-api([^-]|$)" scripts/` → **no runtime** consumer hand-loads a token or
  issues raw HTTP to Vikunja; every runtime Vikunja op goes through `VikunjaClient` (only
  admin/one-shot + docs may remain).

## Identity unchanged (SC-004)

- `grep -n "DEFAULT_TOKEN_PATH" scripts/common/vikunja_client.py` → still `…/vikunja-api`
  (felix-bot). This phase changes **no** identity/token.

## Deploy + spot-check (SC-002/003)

- Merge → felix-deployer self-pulls; consumers run through `VikunjaClient` on next invocation
  (still felix-bot; no restart, no cutover). No deploy manifest; **Rebaseline: not required**.
- Spot-verify each migrated consumer runs correctly on office2 (same behavior as before) — no
  regression.

## Rollback

- Revert the mission commit + redeploy (self-pull). No credential/auth state changed, so rollback is
  a pure code revert.

## Hand-off to Phase 2

- On a green, deployed, soaked Phase 1, Phase 2 (kitty-light under #860) does the one-line flip to
  the kent token + felix-bot Vikunja retirement + attended Tier-2 cutover + projects-16–20 verify +
  #831/#750 resolution.
