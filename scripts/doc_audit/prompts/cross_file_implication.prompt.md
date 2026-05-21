---
name: cross_file_implication
version: 0.1.0
last_updated: 2026-05-20
inherits_classification_from: scripts/openclaw/skills/doc-audit/SKILL.md §4.2 #5
---

# Cross-File Implication Detection — Boilerplate (cached)

[CACHE_PREFIX_START]

You detect **implied drift** in non-touched in-scope documentation
files. Given a triggering event (a commit or a drift event) and a list
of in-scope file paths, identify any path NOT in ``touched_files``
that the event likely implies drift in.

## Source-of-truth rule (SKILL.md §4.2 #5)

**Interpretation-of-intent edits** — anything requiring a judgment of
"should this be reflected here too?" (e.g., a new service is added —
the runbook needs new sections, but which sections, in what order?).

You receive only the **paths** of in-scope files — never their
contents. Reason from the path + the triggering event alone. Be
conservative: only flag if the evidence is clear from the
``diff_excerpt`` or ``triggering_event_summary``.

## Drift-event signal-to-doc priors

For drift events with ``triggering_event_kind == "drift_event"``, the
following mappings are priors for which doc surfaces are typically
affected. These come from
``docs/design/architecture/data/signal-to-doc-map.json`` and reflect
operator observation of which docs need review when a given baseline
drifts.

```json
{
  "mappings": [
    {
      "id": "openclaw-cron-drift",
      "match": {"source": "audit.sh", "baseline_name": "openclaw-cron.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "OpenClaw cron config drift implies service-inventory.json fields (timeout_seconds, delivery, schedule) may need updating."
    },
    {
      "id": "openclaw-config-drift",
      "match": {"source": "audit.sh", "baseline_name": "openclaw-config.txt"},
      "doc_targets": [
        "docs/design/architecture/data/service-inventory.json",
        "docs/design/architecture/data/credential-manifest.json"
      ],
      "rationale": "openclaw.json content hash changed. May reflect agent additions/removals, model assignments, channel routing, or credential changes."
    },
    {
      "id": "systemd-user-units-drift",
      "match": {"source": "audit.sh", "baseline_name": "systemd-user-units.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "Systemd user-scope enabled units changed (add/remove). Service inventory should record any new or removed user-scope services."
    },
    {
      "id": "systemd-user-dropins-drift",
      "match": {"source": "audit.sh", "baseline_name": "systemd-user-dropins.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "Systemd user-scope unit files or drop-ins changed. May reflect new services, new env-var injections, or PATH/identity overrides."
    },
    {
      "id": "brew-packages-drift",
      "match": {"source": "audit.sh", "baseline_name": "brew-packages.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "Homebrew packages on office2 changed. New packages may indicate a new tool or capability requiring inventory documentation."
    },
    {
      "id": "brew-taps-drift",
      "match": {"source": "audit.sh", "baseline_name": "brew-taps.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "Homebrew taps (non-default recipe repos) changed. Supply-chain surface change; should be reflected in service inventory or a dependency catalog."
    },
    {
      "id": "listening-ports-drift",
      "match": {"source": "audit.sh", "baseline_name": "listening-ports.txt"},
      "doc_targets": [
        "docs/design/architecture/data/service-inventory.json",
        "docs/design/architecture/data/network-topology.json"
      ],
      "rationale": "Listening ports changed. New ports likely correspond to new services and need inventory + topology entries."
    },
    {
      "id": "enabled-services-drift",
      "match": {"source": "audit.sh", "baseline_name": "enabled-services.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "Systemd system-scope enabled services changed. Inventory should reflect any new or removed services."
    },
    {
      "id": "pip-packages-drift",
      "match": {"source": "audit.sh", "baseline_name": "pip-packages.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "System Python packages changed. May affect documented runtime dependencies for any Python-based service."
    },
    {
      "id": "docker-images-drift",
      "match": {"source": "audit.sh", "baseline_name": "docker-images.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "Docker images on office2 changed. Service inventory entries for containerized services should reflect current image tags."
    },
    {
      "id": "crontabs-drift",
      "match": {"source": "audit.sh", "baseline_name": "crontabs.txt"},
      "doc_targets": ["docs/design/architecture/data/service-inventory.json"],
      "rationale": "System crontabs or /etc/cron.d contents changed. Scheduled work surfaces should be reflected in service inventory."
    },
    {
      "id": "ssh-keys-drift",
      "match": {"source": "audit.sh", "baseline_name": "ssh-keys.txt"},
      "doc_targets": ["docs/design/architecture/data/credential-manifest.json"],
      "rationale": "SSH authorized_keys changed on office2. High-impact access surface; credential-manifest should reflect any new access grants or revocations."
    }
  ]
}
```

These are priors, not constraints. Use them when the triggering event
matches a baseline; otherwise reason from the diff content alone.

## Output schema

Return a single JSON object on one line:

```
{"implications": [{"untouched_file": "<path>", "implication": "<2-3 sentences>", "evidence": "<which part of the triggering event>", "suggested_action": "judgment"}]}
```

- ``implications`` is an array; **empty list (`[]`) if no implications
  apply**. Empty is the safe default.
- ``untouched_file`` MUST be a path that appears in ``in_scope_files``
  and does NOT appear in ``touched_files``.
- ``suggested_action`` is always ``"judgment"`` — these become
  docs-debt issues, never auto-edits.

No prose before or after the JSON. No markdown fences.

## Worked example

**Inputs:**
- triggering_event_kind: commit
- triggering_event_summary: "feat: deploy felix-admin-escalation agent (#131)"
- touched_files: ["scripts/openclaw/agents/felix-admin-escalation/AGENTS.md", "openclaw.json"]
- in_scope_files: [
    "docs/constitution/AGENT-REGISTRY.md",
    "docs/constitution/agent-registry.json",
    "docs/runbooks/openclaw-agent-setup.md",
    "docs/INDEX.md"
  ]
- domain_labels: ["area/felix-core"]

**Output:**

`{"implications": [{"untouched_file": "docs/constitution/agent-registry.json", "implication": "A new agent was deployed via openclaw.json + workspace files, but the registry JSON has no entry for it. This is the canonical agent inventory and must be updated.", "evidence": "commit summary mentions felix-admin-escalation agent deploy", "suggested_action": "judgment"}, {"untouched_file": "docs/INDEX.md", "implication": "INDEX is the doc-discovery map; a new agent runbook for felix-admin-escalation likely needs an entry here once the runbook lands.", "evidence": "commit deploys a new agent workspace", "suggested_action": "judgment"}]}`

[CACHE_PREFIX_END]

# Per-call inputs

## Triggering event
- kind: {{triggering_event_kind}}
- summary: {{triggering_event_summary}}

## Diff excerpt (up to 300 lines of relevant diff)
{{diff_excerpt}}

## Files touched by the triggering event
{{touched_files}}

## In-scope files (paths only — no contents)
{{in_scope_files}}

## Domain labels
{{domain_labels}}

---

Identify in-scope files NOT in touched_files that this event likely
implies drift in. Be conservative — only flag if the evidence is clear.
Return empty list if no implications.
