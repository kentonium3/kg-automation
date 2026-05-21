---
affected_files: []
cycle_number: 7
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-21T15:05:53Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP10
---

**Issue 1**: Architecture markdown views still contradict the updated authoritative JSON sources.

WP10 updated `docs/design/architecture/data/service-inventory.json` and `docs/design/architecture/data/credential-manifest.json`, but the corresponding human-facing architecture docs were not refreshed. The WP prompt states that the architecture JSONs are authoritative and that markdown views must match, and reviewer guidance explicitly asks to confirm the markdown views match the JSON sources.

Current stale examples:

- `docs/design/architecture/service-inventory.md:40` still says the Doc Audit Poll runs through `openclaw agent felix-doc-auditor`.
- `docs/design/architecture/service-inventory.md:261-268` still describes the service as an OpenClaw agent with `/data/services/openclaw/felix-doc-auditor/`, runtime `~/.openclaw/skills/doc-audit/`, Sonnet model, and `openclaw agent --agent felix-doc-auditor ...` invocation.
- `docs/design/architecture/service-inventory.md:272` still points operators at the pre-#343 runbook as the active runbook.
- `docs/design/architecture/credentials-and-secrets.md:208` still lists the `anthropic` credential as stored only in the OpenClaw native auth store and used only by `openclaw-gateway`, while `credential-manifest.json` now correctly lists both `openclaw-gateway` and `felix-doc-auditor-driver`.

How to fix:

Refresh the markdown views that correspond to the touched architecture JSONs so they match the post-#343 driver model. At minimum, update `docs/design/architecture/service-inventory.md` and `docs/design/architecture/credentials-and-secrets.md` to reflect:

- Direct `/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py` invocation.
- `stateless` per-tick session mode and no runtime OpenClaw workspace/SKILL.md dependency.
- `anthropic/claude-haiku-4-5` direct SDK use.
- `last-tick.json` health check and the new `docs/runbooks/doc-auditor-driver-ops.md` runbook.
- The Anthropic key's dual-consumer model: `openclaw-gateway` plus `felix-doc-auditor-driver` direct file read from `/data/services/openclaw/secrets/anthropic`.

If these views are generated, run the appropriate regeneration path and commit the generated markdown. If they are manually maintained, update them directly and re-check for remaining stale references to the old openclaw-agent doc auditor.
