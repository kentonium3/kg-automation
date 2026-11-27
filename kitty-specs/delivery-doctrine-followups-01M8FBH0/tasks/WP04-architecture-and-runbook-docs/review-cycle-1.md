---
affected_files: []
cycle_number: 1
mission_slug: delivery-doctrine-followups-01M8FBH0
reproduction_command:
reviewed_at: '2026-11-27T21:35:50Z'
reviewer_agent: codex
wp_id: WP04
---

# WP04 review feedback, round 1

**Reviewer:** Codex gpt-6.1-sol (read-only), 2026-11-27, independent of the implementer (curator-carla, claude-sonnet-5-5).
**Reviewed:** commit 1b79f55af, by hand. The printed range omits planning-lane work (spec-kitty/spec-kitty#7759).
**Verdict:** REQUEST CHANGES.

1. **MAJOR: the rollback sequence is wrong** (`service-inventory.md` ~L311, L440, L569, the matching JSON notes, and `discipline.md` ~L435).
   - **Problem:** the text reads "dequeue *or else* `--rollback`". A failed apply can leave both a queued manifest and persisted changes.
   - **Fix:** "if the manifest is still queued, remove it from `deploys/queued/` first; then, if any change landed, run `--rollback`; restore the whole-file backup only as a last resort."
2. **MINOR: initial-apply proof and retry confirmation are conflated** (`discipline.md` ~L426).
   - **Problem:** the initial apply requires the cursor acknowledgement AND an unchanged PID/start time. A retry accepts a cursor acknowledgement or a clean effective catalog, without the PID comparison (the lead's recorded decision). A receipt that is already verified returns immediately.
   - **Fix:** describe the two separately.
3. **MINOR: the hash scope is overstated** (`discipline.md` ~L421). "Hashes of everything untouched" should name the real scope: the non-target agent entries and the top-level `tools`.
4. **MINOR: the stale manual path** (`docs/runbooks/deploy/office2-deploy-paths.md` ~L93 and `docs/design/architecture/data/audited-surfaces.json` ~L32).
   - **Problem:** both still describe direct or out-of-band `openclaw.json` edits.
   - **Fix:** point both to the manifest-driven Gateway patch pattern in `discipline.md`.
   - **Ownership:** the lead authorises this out-of-map edit, limited to those two locations. Record the one-line rationale in the commit message.
5. **MINOR: the calendar note shape** (`service-inventory.json` ~L881). Describe `agents.entries.<id>` and label the `agents.list[]` shape historical. Mirror it in the Markdown if the Markdown carries it.

**Passed:** the JSON and Markdown agree for the announce agents; the names, flags, paths, deny groups and manifest fields match WP03; the validators pass.
