---
affected_files: []
cycle_number: 1
mission_slug: vikunja-image-deploy-01M65D3V
reproduction_command:
reviewed_at: '2026-10-30T04:43:36Z'
reviewer_agent: codex-gpt-6.1-sol
wp_id: WP02
---

# WP02 review cycle 1 — Codex gpt-6.1-sol (OpenAI, read-only), 2026-10-30: REQUEST CHANGES (2 HIGH, 2 MEDIUM)

1. **HIGH — Readiness can succeed after its deadline.** [readiness.py:116](scripts/deploy/vikunja_release/readiness.py#L116) returns a matching version without checking elapsed time after `_probe`. A socket timeout bounds inactivity, so a slowly delivered body can exceed the overall deadline. An in-memory reproduction returned success at 20 seconds with a 1-second budget. Enforce the deadline during response reading and before accepting success; add a late-success test.

2. **HIGH — Log capture is unbounded before truncation.** [readiness.py:154](scripts/deploy/vikunja_release/readiness.py#L154) calls `core.run`, which buffers all stdout and stderr using `capture_output=True`. The 10 MB limit applies afterward. Large logs can exhaust memory during failure cleanup. Stream with a byte bound while draining or terminating the child safely. The current test verifies only the resulting file size.

3. **MEDIUM — Private-root validation has pathname races.** [dbsafety.py:165](scripts/deploy/vikunja_release/dbsafety.py#L165) follows the pathname with `chmod` before checking it with `lstat`; callers subsequently reuse the pathname. Replacement between these operations can redirect permissions or private writes. Static symlink, ownership and mode checks are sound, but do not cover replacement races. Anchor operations to verified directory descriptors using no-follow opens and descriptor-relative creation.

4. **MEDIUM — The retained “raw” files cease to match their recorded hashes.** [dbsafety.py:375](scripts/deploy/vikunja_release/dbsafety.py#L375) opens the hashed raw copy and checkpoints it. This modifies the main DB and truncates/removes sidecars, contradicting the Snapshot entity’s verbatim-copy contract. Preserve `raw/` and consolidate a separate working copy. Tests currently compare recorded hashes to the source, not to the retained raw files.

The live-data write boundary otherwise looks correct: snapshot SQLite connections target private copies; rollback rejects residual WAL/SHM before hashing, then inspects the same private bytes it hashed. Inspection errors refuse. The migration detector implements both specified signals without an identified false negative for the supplied migration shapes. The two private core imports introduce coupling, but no correctness defect here.

Principal WAL and rollback tests have meaningful controls. Coverage misses the failures above, and several smaller refusal tests lack the required same-fixture positive control. Privacy paths return fixed values and keep raw logs private, subject to the directory race.

No files changed; no network, SSH or Docker used. The filesystem-writing pytest suite was not run.

**REQUEST CHANGES**
