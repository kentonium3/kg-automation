# Research / Alignment: Google Workspace foundation

**Mission**: `google-workspace-foundation-01KRH4PE`
**Date**: 2026-05-13

This document consolidates the findings that inform the runbook content and architecture-doc updates. No new research beyond what ADR-0001 + the live 2026-05-13 setup chain already produced.

---

## Decision 1: Runbook structure — full setup procedure + pitfalls section as load-bearing

**Decision**: The runbook covers setup procedure top-to-bottom (every step we ran live, in order) AND a separate "Common pitfalls" section with the three failure modes we hit.

**Rationale**:
- The setup procedure is canonical reference. Future operator (new machine, business account, recovery from server rebuild) follows it linearly.
- The pitfalls section is **load-bearing**. Without it, a future operator hitting any of the three failure modes (Calendar MCP trap, headless keyring, per-user brew PATH) re-derives the diagnosis from scratch. Each cost ~10-30 min to diagnose live; documenting the symptom + fix compresses that to ~2 min.
- The two sections live separately because a successful linear walkthrough doesn't surface the pitfalls until they trip you up. Inlining "you might hit this" warnings at every step would dilute the procedure.

## Decision 2: Mark legacy creds deprecated, don't delete

**Decision**: The pre-#100 `/data/services/openclaw/secrets/google-calendar-{client-id,client-secret,refresh-token}` files stay on disk; the credential-manifest gets `status: deprecated` entries for them.

**Rationale**:
- Deletion is irreversible and easy to do later. Marking deprecated and waiting a few weeks for any latent consumer to fail loudly is the safer order.
- The legacy `authorize-calendar.py` is being archived in the same mission — if the move surfaces a forgotten consumer, that's a load-bearing test before deletion would happen.
- Operator-discretion deletion post-merge is the standard pattern in this repo for deprecated-but-not-removed artifacts.

## Decision 3: Archive the legacy script vs. banner-in-place

**Decision**: Archive-move via `git mv` to `docs/archive/scripts/authorize-calendar.py` is preferred. Banner-in-place is the fallback if archive-move surfaces problems.

**Rationale**:
- Repo convention (per `docs/archive/`) is that frozen historical artifacts move into the archive tree. `authorize-calendar.py` matches that pattern — it's frozen, superseded, and no longer load-bearing.
- Banner-in-place leaves the file under `scripts/google/` where someone might find it by directory traversal and assume it's still live.
- Implementer can switch to banner-in-place if the archive-move causes import-path surprises (we don't expect any since the file isn't imported anywhere — it's a one-shot CLI invocation), per FR-005.

## Decision 4: doc-domain-map mapping for the new runbook

**Decision**: `docs/runbooks/google-workspace-ops.md` maps to `area/ea` (Executive Assistant area, where this integration's user-stories live).

**Rationale**:
- The integration serves the EA capability area (calendar, email, drive — all EA territory).
- `area/ea` already has runbooks for related concerns (`escalation-ops.md`, `observation-ops.md`).
- Calendar/email integration is NOT infrastructure-level (those are area/infrastructure) — it's a user-facing capability substrate. Right home is area/ea.

## Decision 5: No agent-prompt changes in this mission

**Decision**: Per C-001, no Felix agent's AGENTS.md is modified. Agent-side integration (e.g., morning briefing agent uses gog for calendar lookup) is downstream user-story scope.

**Rationale**:
- Strict scope discipline: this mission is the *foundation* layer (auth + tooling + docs + state). Agent-side use is a separate concern with its own user stories per the epics #164, #165.
- Mixing the two would broaden the mission's review surface dramatically (every touched agent's prompt needs review for each affected user story).
- Future user-story missions reference this mission's foundation as a dependency and add gog invocations in their own AGENTS.md changes.

---

## Open questions

None. All technical decisions are locked.

## References

- ADR-0001 — `docs/design/architecture/adr/0001-google-workspace-via-gog.md` (committed `a0a7660`)
- gog SKILL.md on office2 — `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md`
- gog homepage — https://gogcli.sh
- Live setup chain (2026-05-13) — captured in conversation history; relevant findings already extracted into the runbook draft outline.
