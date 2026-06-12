"""Felix deploy library — vetted primitives for deploy scripts and the applier.

NEVER imports or shells to the system cron table. All cron operations route
through ``openclaw cron`` subcommands. See
``kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/deploy-library-api.md``
for the full API.

The library exposes a single shared return type — :class:`LibResult` — and a
collection of module-level primitives organised by concern:

* :mod:`scripts.deploy.lib.cron` — OpenClaw cron primitives.
* :mod:`scripts.deploy.lib.snapshot` — Restic backup recency verification.
* :mod:`scripts.deploy.lib.verify` — File / content / secret checks.
* :mod:`scripts.deploy.lib.manifest` — Manifest load + schema validation.
* :mod:`scripts.deploy.lib.applied` — Applied-entry writer.

Future modules (``tier``, ``apply``) are added in subsequent work packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class LibResult:
    """Canonical return type for every deploy-library primitive.

    Attributes:
        ok: The only signal callers should check for branching logic.
        summary: One-line human-readable description (suitable for logs;
            ``<=120`` chars by convention).
        details: Optional structured detail. Well-known keys (per
            ``contracts/deploy-library-api.md``):

            * ``phase`` — set by ``apply.dry_run_then_apply_gate``.
            * ``error_code`` — e.g. ``TIER_0_REJECTED``, ``RESTIC_TOO_OLD``.
            * ``stderr_excerpt`` — bounded stderr from a failed subprocess.
            * ``head_sha`` — post-pull HEAD SHA, when relevant.
    """

    ok: bool
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)


__all__ = ["LibResult"]
