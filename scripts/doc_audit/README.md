# `scripts/doc_audit/` — felix-doc-auditor driver

Scripts-first Python driver that replaces the LLM-first procedural
felix-doc-auditor agent. Deterministic Python code owns the
control flow; an LLM is invoked only at narrow judgment moments
(tier classification, debt-body generation, cross-file implication).

Mission: `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX`
(GitHub issue #343).

## Design and operator docs

- Design and architecture:
  `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/plan.md`
- Operator usage and runbook:
  `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/quickstart.md`
- Inherited domain rules:
  `scripts/openclaw/skills/doc-audit/SKILL.md`
- Data-model entities (E-001..E-010):
  `kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/data-model.md`

## Module map

| Path | Purpose |
|---|---|
| `__init__.py` | Package marker + version |
| `data_model.py` | The 10 entities (E-001..E-010) as dataclasses |
| `config.py` | Config dataclasses + `load_config()` + `read_api_key()` |
| `config.toml` | Default driver configuration |
| `signals/` | Signal source adapters (gh_issue, drift_event) — added later |
| `judgment/` | LLM client + the 3 judgment moments — added later |
| `routing/` | Tier-A commit, pending-approval filing, debt filing — added later |
| `output/` | Activity log + tick-signal writers — added later |
| `helpers/` | Drift-event handler + audit-routing helper (WP01) |
| `prompts/` | Prompt templates for each judgment moment — added later |

## Running tests

```bash
# From the repo root
PYTHONPATH=scripts python3 -m pytest tests/doc_audit/ -v
```

Coverage for the data model and config layer is enforced in WP02:

```bash
PYTHONPATH=scripts python3 -m pytest tests/doc_audit/ \
    --cov=scripts/doc_audit/data_model \
    --cov=scripts/doc_audit/config \
    --cov-report=term-missing
```

Target: `data_model.py` >=90%; `config.py` >=85%.

## Importing from this package

```python
from doc_audit import __version__
from doc_audit.data_model import (
    Signal, AuditIssue, PendingApproval, ProposedEdit, EditTier,
    DebtIssue, DriftEvent, TickResult, TickSignal, ActivityLogEntry,
)
from doc_audit.config import load_config, read_api_key
```

`scripts/` must be on `sys.path` (the test conftest handles this).
