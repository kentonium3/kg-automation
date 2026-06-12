# Research: Pull-Based Deploy Pipeline

**Mission**: `pull-based-deploy-pipeline-01KTYQQS`
**Phase**: 0 (research; precedes design)

This document captures the research decisions that resolved the planning-phase clarifications. Each entry has the form: **Decision** / **Rationale** / **Alternatives considered**.

---

## R-01 — Manifest file format: YAML, validated by JSON Schema

**Decision**: Manifest entries are YAML files in `deploys/queued/<name>.yaml`. They are validated against a canonical JSON Schema (`deploys/schema/manifest-v1.schema.json`). The schema language is JSON Schema (draft 2020-12); the data is YAML.

**Rationale**:
- YAML supports comments and human-readable nesting — important because manifests are operator/agent-authored, not machine-generated.
- JSON Schema is the most widely-supported declarative validation language; the `jsonschema` Python library validates YAML-loaded dicts identically to JSON-loaded dicts.
- Decision is consistent with the user's stated implementation choice: "JSON Schema for manifest" (the schema, not the file format).

**Alternatives considered**:
- *JSON manifests* — denser to author, no comments, common operator pain point. Rejected.
- *TOML* — fine but adds a parser dep; no advantage over YAML for this size.
- *Python literals* — too easy to embed code by accident; rejected.

---

## R-02 — Applier scheduling: systemd user timer + `Type=oneshot` service

**Decision**: The applier runs as a `systemd --user` unit on office2 (under the `claude` account, per existing service ownership pattern). The unit is `Type=oneshot`. A companion `.timer` unit fires every 5 minutes. systemd's natural serialization (a `oneshot` unit cannot have overlapping invocations) eliminates the need for explicit locking.

**Rationale**:
- Resolves Decision Moment `01KTYT07WJ368B2PE9QZE5046H` (`concurrency_locking_model`) with `systemd_type_oneshot_natural`.
- Matches the existing `felix-doc-auditor` precedent (per memory `reference_felix_doc_auditor_ops`) — same harness, same account, same observable surface.
- No new lock-file failure mode to manage (stale locks would otherwise be the next bug).
- The applier process completes within the tick budget for the typical deploy; the rare long-running deploy delays the next tick by minutes, not creates parallel chaos.

**Alternatives considered**:
- *Explicit `fcntl` lock file* — defense in depth, but adds a stale-lock failure mode and isn't necessary when the supervisor already serializes.
- *Both* — overkill for the operator-driven scale.
- *Cron* — would require the openclaw cron interface, which the applier itself depends on; cyclic dependency.

---

## R-03 — Failure notification dispatch: openclaw cron payload synthesis

**Decision**: On apply failure, the applier dispatches a WhatsApp DM by synthesizing an openclaw cron payload and invoking the existing openclaw cron interface (`openclaw cron run` against a dedicated `felix-deployer-alert` cron registered as part of this mission). The applier does not call the WhatsApp Business API directly and does not introduce a new credential consumer.

**Rationale**:
- Resolves Decision Moment `01KTYSZ051R7EKZ4CS5WVCZS13` (`whatsapp_dispatch_path`) with `existing_openclaw_cron_payload`.
- Reuses the existing operator-facing DM surface (felix-admin reply path) — same credential, same delivery semantics, same observability.
- Decouples the applier from the WhatsApp client library version; if openclaw changes, the applier doesn't need a redeploy.
- The synthesized payload includes manifest name, tier, and failure summary; recipient comes from the existing openclaw recipient config (no new config surface).

**Alternatives considered**:
- *Direct WhatsApp Business API* — adds Python WhatsApp client dep, parallel credential surface, separate retry/throttling logic. Rejected.
- *Drop a structured failure file for felix-admin-reply to pick up* — loose coupling, but adds polling latency (felix-admin-reply doesn't run continuously) and creates an implicit contract between two services that's hard to test in isolation. Rejected.

---

## R-04 — Bootstrap deploy writes a retroactive `deploys/applied/` entry

**Decision**: The bootstrap wrapper, after successfully deploying the applier itself, writes `deploys/applied/0001-bootstrap-felix-deployer.yaml` — a backdated manifest record describing the bootstrap deploy as if it had gone through the manifest discipline. This entry is the canonical first example for the runbook.

**Rationale**:
- Resolves Decision Moment `01KTYT0M1P91042MJ0G5WXCYN2` (`bootstrap_retroactive_applied_entry`) with `yes_canonical_example`.
- The discipline runbook teaches by example; an empty `applied/` directory makes the manifest format feel theoretical.
- The bootstrap is conceptually the first deploy — it happens to be applied differently (bash one-shot) but the *intent* is identical. Recording it captures that intent without misleading anyone about how subsequent deploys work.
- The entry's frontmatter explicitly notes `apply_mode: bootstrap` to distinguish it from manifest-driven applies — no ambiguity.

**Alternatives considered**:
- *applied/ starts empty* — ontologically purest but pedagogically weaker. Rejected.

---

## R-05 — Python dep stack: PyYAML + jsonschema only

**Decision**: The library and applier use only the Python standard library plus `PyYAML` and `jsonschema`. No HTTP client (openclaw cron is invoked via `subprocess`; the existing openclaw binary handles WhatsApp transport). No async runtime (the applier is single-threaded oneshot).

**Rationale**:
- Minimizes the deploy story for the deployer itself; fewer wheels to vendor, smaller attack surface, simpler pin updates.
- office2 already has Python 3.10+ from prior missions (`felix-doc-auditor` driver) so the runtime is established.
- `PyYAML` and `jsonschema` are both mature, low-churn, available in Debian/Ubuntu apt and in pipx.

**Alternatives considered**:
- *`requests` for HTTP* — only needed if we were calling the WhatsApp API directly (rejected by R-03).
- *`pydantic` for manifest models* — heavier; `jsonschema` validation + dict access is sufficient.
- *`click` for CLI args* — only relevant if the applier had user-facing CLI; it does not (systemd invokes it without args).

---

## R-06 — CI: GitHub Actions workflow, runs in <30 s

**Decision**: A new GitHub Actions workflow `.github/workflows/deploy-manifest-validate.yml` runs on every PR. It:
1. Sets up Python 3.10 with `PyYAML`, `jsonschema`, and `pytest`.
2. Validates every YAML file in `deploys/queued/` and `deploys/applied/` against `deploys/schema/manifest-v1.schema.json` — fails the build on any mismatch.
3. Rejects any manifest declaring `tier: 0`.
4. Runs `pytest tests/integration/test_cross_link.py` to walk the doctrinal cross-link graph.
5. Reports total runtime; fails if >30 s wall-clock.

**Rationale**:
- Defense in depth on tier guard (CI gate + runtime gate).
- Cross-link test catches the most fragile invariant — the agentic-visibility graph would silently break under doc edits otherwise.
- 30-second budget keeps the gate fast enough to run on every PR without push-back.

**Alternatives considered**:
- *pre-commit hook only* — local pre-commit hooks aren't enforced across collaborators (this is a solo-operator repo today, but the discipline should hold for future contributors).
- *Larger CI scope (full test suite gated on manifests)* — couples discipline drift to unrelated test stability. Rejected.

---

## R-07 — felix-deployer service inventory entry shape

**Decision**: The service inventory entry mirrors the `felix-doc-auditor` shape: `systemd_unit`, `account`, `schedule`, `state_root`, `health_signal`, `dependent_services`. The `health_signal` is the path to the most recent tick's success record (`/data/services/felix-deployer/state/last-tick.json`), following the `felix-doc-auditor` health-signal pattern (per memory).

**Rationale**:
- Consistency with prior service shape simplifies operator mental model and reuses the existing dashboard scanner conventions.
- The health-signal pattern (file-based "I'm alive at <ts>") is preferred over a process-liveness check because office2 has limited tooling for that.

**Alternatives considered**:
- *No health signal* — would leave the applier silent on success, only audible on failure. Rejected (poor observability).
- *Prometheus / push-gateway* — overkill; no other office2 service uses Prometheus.

---

## Open items (none deferred)

All Decision Moments for this plan are resolved. No `[NEEDS CLARIFICATION]` markers remain in plan.md, research.md, or downstream design artifacts.
