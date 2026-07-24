# Contracts — Vikunja token seam + kent cutover (phase 2 of #860)

**No new external API contracts.** This is an internal identity/config refactor: it introduces one
in-code resolution helper and flips a credential. It adds no HTTP endpoint, event, webhook, or
serialized public interface.

The two internal contracts that matter are asserted by tests, not schemas:

1. **Single-resolution-point contract** — every runtime Vikunja consumer resolves its token via
   `get_vikunja_token_path()` (directly or through `VikunjaClient`). Enforced by **SC-001**
   (`grep -rnE "secrets/vikunja-api([^-]|$)" scripts/` → zero runtime matches) and by the
   single-point-flip test (**SC-002**): overriding `VIKUNJA_TOKEN_PATH` changes the resolved token for
   every consumer path with no per-consumer edit.

2. **Behavior-preservation contract (pre-flip)** — the Phase-1 per-consumer parity tests + the
   `tests/architectural/` ratchets stay green while the resolved token is still felix-bot (**NFR-001**).

The existing `VikunjaClient` contract (`scripts/common/vikunja_client.py` docstring +
`kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/vikunja_client.md`) is unchanged
except that default-token loading now resolves through `get_vikunja_token_path()`.
