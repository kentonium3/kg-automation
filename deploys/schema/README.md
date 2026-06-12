# Deploy Manifest Schema (v1)

The deploy manifest is the single declarative artifact an operator or agent
authors to request that the pull-based applier execute a deploy on office2.
One YAML file per deploy, queued under `deploys/queued/`, moved to
`deploys/applied/` (on success) or `deploys/failed/` (on failure) by the
applier.

## Canonical schema

[`manifest-v1.schema.json`](./manifest-v1.schema.json) — JSON Schema 2020-12.
Validate with `jsonschema.Draft202012Validator`. CI rejects malformed
manifests at PR time; the applier refuses to execute violating manifests
at runtime.

## Discipline runbook

[`docs/runbooks/deploy/discipline.md`](../../docs/runbooks/deploy/discipline.md)
— authoring conventions, tier-selection guidance, verification command
patterns, and operational walkthroughs. (Placeholder until WP07 ships.)

## Worked quickstart example

[`kitty-specs/pull-based-deploy-pipeline-01KTYQQS/quickstart.md`](../../kitty-specs/pull-based-deploy-pipeline-01KTYQQS/quickstart.md)
— end-to-end walkthrough of authoring a manifest, queuing it, and observing
the applier move it to `applied/`.

## Required fields (6)

Every manifest MUST set these six fields:

| Field | Purpose |
|---|---|
| `schema_version` | Always `v1`. Pins the manifest to this schema. |
| `name` | Kebab-case identifier; unique within `deploys/queued/`. |
| `tier` | Risk tier (1–4) per `docs/design/architecture/data/change-risk-taxonomy.json`. Tier 0 is rejected — host changes stay manual. |
| `entrypoint` | Repo-relative path to the deploy script (`scripts/deploy/.../<name>.(sh\|py)`). |
| `audited_surface` | Boolean — true if the deploy touches an entry in `docs/design/architecture/data/audited-surfaces.json`. Controls rebaseline accounting. |
| `created_at` / `created_by` | RFC 3339 timestamp + author identity. |

Additionally, exactly one of `mission_slug` OR `issue` is required (the
source identifier — which spec-kitty mission or GitHub issue motivated
the deploy).

## Conditional fields

- **Tier 1 or Tier 2** manifests MUST include a `verification` block with
  non-empty `pre` and `post` command arrays. Tier 3 and Tier 4 may omit it.
- **Applied** manifests (entries in `deploys/applied/`) MUST set
  `apply_mode` (`manifest` | `bootstrap`) and `applied_at`. Queued
  manifests MUST NOT carry these fields.

## See also

- Spec: [`kitty-specs/pull-based-deploy-pipeline-01KTYQQS/spec.md`](../../kitty-specs/pull-based-deploy-pipeline-01KTYQQS/spec.md)
- Plan: [`kitty-specs/pull-based-deploy-pipeline-01KTYQQS/plan.md`](../../kitty-specs/pull-based-deploy-pipeline-01KTYQQS/plan.md)
- Data model: [`kitty-specs/pull-based-deploy-pipeline-01KTYQQS/data-model.md`](../../kitty-specs/pull-based-deploy-pipeline-01KTYQQS/data-model.md)
