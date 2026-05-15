#!/usr/bin/env python3
"""Felix issue-queueing helper. Wraps `gh issue create` with template-compliant
body construction, label discipline, and kg-felix-bot identity verification.

Mission #291 / epic #270 (Felix governance discipline).

This helper is the operational implementation of the "queue an issue, do not
apply" reflex from GOVERNANCE.md. When Felix observes something worth surfacing
but doesn't have approval to act (Tier 2+ default per the governance protocol),
it invokes this helper instead of composing `gh issue create` ad-hoc or
attempting autonomous mutation.

The helper produces template-structured issue bodies matching
`.github/ISSUE_TEMPLATE/*.md`. Sections Felix has signal on are filled in;
unfilled sections carry `TBD — complete during spec-readiness work`
placeholders so the body is honest about what needs more work later.

Invocation:

    python3 scripts/openclaw/agents/main/felix-file-issue.py \\
        --type {bug|feature|infra|research} \\
        --title "<title-without-prefix>" \\
        --problem-statement-file <path-to-tempfile-with-paragraph> \\
        --tier-hypothesis {0|1|2|3|4|unknown} \\
        --area <area-label> \\
        --priority {P1|P2} \\
        [--observed-context-file <path-to-tempfile-with-evidence>] \\
        [--related-issues "<comma-sep, e.g., #270,#285>"] \\
        [--spec-ready-eval {brief|ready}] \\
        [--dry-run]

Output (stdout, JSON):

    {"issue_number": 290, "issue_url": "https://...", "title": "...", "labels": [...]}
    SUMMARY: type=bug priority=P2 area=felix-core tier=2 spec=brief issue=#290

Exit codes:
    0 — issue filed (or --dry-run preview printed)
    1 — operational error (gh CLI failure, file unreadable, identity mismatch)
    2 — usage error (malformed args, invalid label combinations)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


VALID_TYPES = {"bug", "feature", "infra", "research"}
# P3 intentionally excluded: the repo's only P3 label is `P3-candidate`
# (human-curated triage), and `P3-<type>` labels do not exist. Felix files
# at P1 (current cycle) or P2 (backlog). Humans promote ideas from
# P3-candidate when ready.
VALID_PRIORITIES = {"P1", "P2"}
VALID_TIERS = {"0", "1", "2", "3", "4", "unknown"}
VALID_SPEC_READY = {"brief", "ready"}

# Whitelist of area labels (subset; helper accepts any string matching the
# pattern but warns if not in the canonical list).
KNOWN_AREAS = {
    "felix-core",
    "security",
    "biz-ops",
    "tooling",
    "ea",
}

REPO = "kentonium3/kg-automation"
EXPECTED_GH_IDENTITY = "kg-felix-bot"

TITLE_PREFIX = {
    "bug": "Bug",
    "feature": "Feature",
    "infra": "Infra",
    "research": "Research",
}


def verify_gh_identity() -> tuple[bool, str]:
    """Check `gh auth status` and confirm kg-felix-bot is the active identity.

    Returns (ok, identity_or_error). On ok=False, identity_or_error is the
    error message to surface to the user.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError:
        return False, "gh CLI not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "gh auth status timed out after 10s"

    output = (result.stdout + result.stderr).strip()
    if "Logged in to github.com account" not in output:
        return False, f"gh CLI not authenticated:\n{output}"

    # Look for "Logged in to github.com account <name>"
    match = re.search(r"Logged in to github\.com account (\S+)", output)
    identity = match.group(1) if match else "unknown"

    if identity != EXPECTED_GH_IDENTITY:
        return False, (
            f"Expected gh identity {EXPECTED_GH_IDENTITY!r} but found "
            f"{identity!r}. Use `gh auth switch` to select the correct "
            f"account before filing Felix issues."
        )

    return True, identity


def read_input_file(path: Path | None, what: str) -> str:
    """Read a tempfile containing free-form input. Returns the content or ''."""
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print(f"ERROR: {what} file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"ERROR: permission denied reading {what} file: {path}", file=sys.stderr)
        sys.exit(1)


def normalize_related(related: str | None) -> list[str]:
    """Parse comma-separated issue references (e.g., '#270, #285') into a list."""
    if not related:
        return []
    parts = [p.strip() for p in related.split(",") if p.strip()]
    # Ensure each starts with '#'
    return [p if p.startswith("#") else f"#{p}" for p in parts]


def build_body_bug(
    title: str,
    problem_statement: str,
    observed_context: str,
    tier_hypothesis: str,
    related: list[str],
    spec_ready_eval: str,
    now_iso: str,
) -> str:
    """Build a bug.md-structured issue body."""
    tier_line = f"Tier {tier_hypothesis}" if tier_hypothesis != "unknown" else "Tier: unknown (needs assessment)"
    related_block = (
        "\n".join(f"- {ref}" for ref in related) if related else "- (none)"
    )
    evidence_block = (
        f"```\n{observed_context}\n```" if observed_context else "_TBD — complete during spec-readiness work._"
    )
    spec_ready_items = _spec_ready_items_bug(spec_ready_eval)

    return f"""## Summary

{problem_statement}

## Environment

- **Observed at**: {now_iso}
- **Filed by**: Felix via `felix-file-issue.py` (autonomous capture)
- **Felix's tier hypothesis**: {tier_line}

## Reproduction

**Prerequisites:**

_TBD — complete during spec-readiness work._

**Steps:**

_TBD — complete during spec-readiness work._

## Expected behavior

_TBD — complete during spec-readiness work._

## Actual behavior

{problem_statement}

## Evidence

{evidence_block}

## Workaround applied

_TBD — describe any temporary workaround applied while filing._

## Root cause hypothesis

_Felix's hypothesis: Tier {tier_hypothesis} ({_tier_name(tier_hypothesis)}). Detailed root cause to be assessed during spec-readiness work._

## Suggested fix

_TBD — complete during spec-readiness work._

## Impact

- **Severity**: TBD
- **Frequency**: TBD
- **Affected workflow**: TBD

## Cross-references

{related_block}

## Spec-ready criteria

{spec_ready_items}

---

_Filed at `spec: brief` quality for prioritization. Spec-readiness work
(complete reproduction, evidence, root cause, suggested fix) happens at
the laptop when the issue is prioritized._
"""


def build_body_feature(
    title: str,
    problem_statement: str,
    observed_context: str,
    tier_hypothesis: str,
    related: list[str],
    spec_ready_eval: str,
    now_iso: str,
) -> str:
    """Build a feature.md-structured issue body."""
    related_block = (
        "\n".join(f"- {ref}" for ref in related) if related else "- (none)"
    )
    context_block = (
        f"```\n{observed_context}\n```\n" if observed_context else ""
    )
    spec_ready_items = _spec_ready_items_feature(spec_ready_eval)

    return f"""## Executive Summary

{problem_statement}

{context_block}**Felix's tier hypothesis**: Tier {tier_hypothesis} ({_tier_name(tier_hypothesis)})

**Filed by**: Felix via `felix-file-issue.py` at {now_iso} (autonomous capture)

## Problem Statement

{problem_statement}

_Current state / target state diagrams TBD — complete during spec-readiness work._

## Study These Files First

_TBD — complete during spec-readiness work. Discovery pointers to internal sources._

## Assumptions

- _TBD — list assumptions during spec-readiness work._

## Functional Requirements

_TBD — define FRs with success criteria during spec-readiness work._

## Out of Scope

- _TBD — list explicit exclusions during spec-readiness work._

## Architecture Impact

_TBD — identify affected JSON files OR affirm no architecture changes._

## Constitutional Compliance

- **Autonomy level**: TBD
- **Scope**: TBD
- **Failure behavior**: TBD

## Risk Considerations

_TBD — list during spec-readiness work._

## Cross-references

{related_block}

## Spec-ready criteria

{spec_ready_items}

---

_Filed at `spec: brief` quality for prioritization. Spec-readiness work
happens at the laptop when the issue is prioritized for action._
"""


def build_body_infra(
    title: str,
    problem_statement: str,
    observed_context: str,
    tier_hypothesis: str,
    related: list[str],
    spec_ready_eval: str,
    now_iso: str,
) -> str:
    """Build an infra.md-structured issue body."""
    tier = tier_hypothesis if tier_hypothesis in {"0", "1", "2", "3", "4"} else "?"
    related_block = (
        "\n".join(f"- {ref}" for ref in related) if related else "- (none)"
    )
    context_block = (
        f"### Observed context\n\n```\n{observed_context}\n```\n\n" if observed_context else ""
    )
    spec_ready_items = _spec_ready_items_infra(spec_ready_eval)

    tier_checklist = "\n".join(
        f"- [{'x' if str(i) == tier else ' '}] **Tier {i} — {_tier_name(str(i))}**"
        for i in range(5)
    )

    return f"""## Summary

{problem_statement}

**Filed by**: Felix via `felix-file-issue.py` at {now_iso} (autonomous capture)
**Felix's tier hypothesis**: Tier {tier_hypothesis}

## Risk tier

Felix's initial hypothesis (verify during spec-readiness):

{tier_checklist}

{context_block}## Services affected

_TBD — list services from `docs/design/architecture/data/service-inventory.json`._

## Pre-flight checklist

_TBD — complete during spec-readiness, per tier protocol._

## Change description

{problem_statement}

_Specific scope and what is NOT changing: TBD during spec-readiness._

## Rollback plan

_TBD — must be specific enough to execute under pressure._

## Post-change verification

_TBD — list health checks for affected services._

## Architecture documentation updates

_TBD — list JSON files to update (or affirm none affected)._

## Cross-references

{related_block}

## Success criteria

- [ ] Change applied without service disruption
- [ ] All post-change verification steps pass
- [ ] Architecture docs updated

## Spec-ready criteria

{spec_ready_items}

---

_Filed at `spec: brief` quality for prioritization. Spec-readiness work
happens at the laptop when the issue is prioritized._
"""


def build_body_research(
    title: str,
    problem_statement: str,
    observed_context: str,
    tier_hypothesis: str,
    related: list[str],
    spec_ready_eval: str,
    now_iso: str,
) -> str:
    """Build a research.md-structured issue body."""
    related_block = (
        "\n".join(f"- {ref}" for ref in related) if related else "- (none)"
    )
    context_block = (
        f"### Observed context that prompted this research\n\n```\n{observed_context}\n```\n\n" if observed_context else ""
    )
    spec_ready_items = _spec_ready_items_research(spec_ready_eval)

    return f"""## Research Purpose

{problem_statement}

{context_block}**Filed by**: Felix via `felix-file-issue.py` at {now_iso} (autonomous capture)

**Decision gate**: _TBD — what decision does this research unblock?_

## Research Questions

_TBD — define 3-6 specific, answerable questions during spec-readiness work._

## Known Sources

### Internal sources

- _TBD_

### External sources

- _TBD_

## Scope

### In scope

- _TBD_

### Out of scope

- ❌ Implementation work — research missions produce findings, not code

## Expected Outputs

_TBD — what findings.md must contain. Map outputs to research questions._

## Constraints

- _TBD_

## Cross-references

{related_block}

## Success Criteria

### Evidence
- [ ] All research questions have findings with cited sources

### Findings
- [ ] findings.md addresses every RQ with supported conclusions

### Recommendation
- [ ] A clear recommendation is stated

## Spec-ready criteria

{spec_ready_items}

---

_Filed at `spec: brief` quality for prioritization. Spec-readiness work
happens at the laptop when the issue is prioritized._
"""


def _tier_name(tier: str) -> str:
    return {
        "0": "Host / Foundational — hard lock",
        "1": "Connectivity / Fabric — verification required",
        "2": "Application / State — snapshot required",
        "3": "Logic / Workflow — standard",
        "4": "Schema / Metadata — auto-commit",
        "unknown": "tier not yet assessed",
    }.get(tier, "unknown")


def _spec_ready_items_bug(spec_ready_eval: str) -> str:
    items = [
        "**Summary** is a single sentence stating what breaks",
        "**Environment** captures version/service/timing",
        "**Reproduction** steps are deterministic",
        "**Expected behavior** and **Actual behavior** are both stated",
        "**Evidence** includes the relevant log/error output",
        "**Root cause hypothesis** is present",
        "**Impact** severity and frequency are set",
    ]
    return _format_spec_ready_items(items, spec_ready_eval)


def _spec_ready_items_feature(spec_ready_eval: str) -> str:
    items = [
        "**Executive Summary** states what the feature delivers in 2-3 sentences",
        "**Problem Statement** captures current vs target state concretely",
        "**Study These Files First** lists internal pointers",
        "**Functional Requirements** has at least one FR with success criteria",
        "**Out of Scope** lists explicit exclusions",
        "**Architecture Impact** identifies affected JSON files",
        "**Constitutional Compliance** addresses autonomy, scope, failure",
        "**Design-time discipline** — deterministic-vs-stochastic split considered (Directive 6)",
    ]
    return _format_spec_ready_items(items, spec_ready_eval)


def _spec_ready_items_infra(spec_ready_eval: str) -> str:
    items = [
        "**Summary** clearly states what is changing and why",
        "**Risk tier** is selected (one box checked)",
        "**Services affected** lists dependents",
        "**Pre-flight checklist** items addressed",
        "**Change description** is specific enough for an operator",
        "**Rollback plan** is concrete enough to execute under pressure",
        "**Post-change verification** includes named health checks",
        "**Supply-chain review** — if applicable (per Constitution Directive 6)",
    ]
    return _format_spec_ready_items(items, spec_ready_eval)


def _spec_ready_items_research(spec_ready_eval: str) -> str:
    items = [
        "**Research Purpose** names the decision gate",
        "**Research Questions** lists 3-6 specific, answerable questions",
        "Each RQ has an **Acceptable answer form**",
        "**Known Sources** lists at least one starting point per RQ",
        "**Scope** has both In-scope and Out-of-scope items filled",
        "**Expected Outputs** maps outputs to RQs",
    ]
    return _format_spec_ready_items(items, spec_ready_eval)


def _format_spec_ready_items(items: list[str], spec_ready_eval: str) -> str:
    check = "x" if spec_ready_eval == "ready" else " "
    return "\n".join(f"- [{check}] {it}" for it in items)


BODY_BUILDERS = {
    "bug": build_body_bug,
    "feature": build_body_feature,
    "infra": build_body_infra,
    "research": build_body_research,
}


def file_issue(
    title: str,
    body: str,
    labels: list[str],
    dry_run: bool,
) -> tuple[int, str, str]:
    """Invoke gh issue create. Returns (returncode, stdout, stderr)."""
    if dry_run:
        return 0, "", "(dry-run: no gh invocation)"
    cmd = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--label", ",".join(labels),
        "--body", body,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "gh issue create timed out after 30s"
    return result.returncode, result.stdout, result.stderr


def parse_issue_url(stdout: str) -> tuple[int | None, str | None]:
    """Extract issue number + URL from gh issue create stdout.

    `gh issue create` outputs the issue URL like:
        https://github.com/kentonium3/kg-automation/issues/290
    """
    url = stdout.strip().splitlines()[-1].strip() if stdout.strip() else None
    if not url or not url.startswith("https://github.com/"):
        return None, None
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        return None, url
    return int(match.group(1)), url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", maxsplit=1)[0],
    )
    parser.add_argument("--type", required=True, choices=sorted(VALID_TYPES))
    parser.add_argument("--title", required=True, help="Title text WITHOUT type prefix; helper adds the prefix.")
    parser.add_argument("--problem-statement-file", required=True, type=Path, help="Path to tempfile with problem statement paragraph(s)")
    parser.add_argument("--tier-hypothesis", required=True, choices=sorted(VALID_TIERS))
    parser.add_argument("--area", required=True, help="Area label (e.g., felix-core, security, biz-ops, tooling, ea)")
    parser.add_argument("--priority", required=True, choices=sorted(VALID_PRIORITIES))
    parser.add_argument("--observed-context-file", type=Path, default=None, help="Optional path to tempfile with evidence (logs, diffs, etc.)")
    parser.add_argument("--related-issues", type=str, default=None, help="Comma-separated issue refs (e.g., '#270,#285')")
    parser.add_argument("--spec-ready-eval", choices=sorted(VALID_SPEC_READY), default="brief")
    parser.add_argument("--dry-run", action="store_true", help="Print would-be body to stdout; do not file.")
    args = parser.parse_args(argv)

    # --- Validation ---

    if args.area not in KNOWN_AREAS:
        print(
            f"WARN: --area {args.area!r} is not in the known list {sorted(KNOWN_AREAS)}; "
            f"proceeding anyway (helper trusts caller).",
            file=sys.stderr,
        )

    if not args.title.strip():
        print("ERROR: --title cannot be empty", file=sys.stderr)
        return 2

    problem_statement = read_input_file(args.problem_statement_file, "--problem-statement-file")
    if not problem_statement:
        print("ERROR: --problem-statement-file is empty", file=sys.stderr)
        return 2

    observed_context = read_input_file(args.observed_context_file, "--observed-context-file") if args.observed_context_file else ""

    # --- Identity verification (skip on --dry-run for testability) ---

    if not args.dry_run:
        ok, identity_or_err = verify_gh_identity()
        if not ok:
            print(f"ERROR: gh identity check failed: {identity_or_err}", file=sys.stderr)
            return 1

    # --- Body construction ---

    related = normalize_related(args.related_issues)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    builder = BODY_BUILDERS[args.type]
    body = builder(
        title=args.title,
        problem_statement=problem_statement,
        observed_context=observed_context,
        tier_hypothesis=args.tier_hypothesis,
        related=related,
        spec_ready_eval=args.spec_ready_eval,
        now_iso=now_iso,
    )

    # --- Labels + title prefix ---

    full_title = f"{TITLE_PREFIX[args.type]}: {args.title}"
    spec_label = f"spec: {args.spec_ready_eval}"
    labels = [
        f"{args.priority}-{args.type}",
        f"area/{args.area}",
        spec_label,
    ]

    # --- Filing or preview ---

    if args.dry_run:
        print(f"=== TITLE ===\n{full_title}\n")
        print(f"=== LABELS ===\n{', '.join(labels)}\n")
        print(f"=== BODY ===\n{body}")
        print(f"\nSUMMARY: type={args.type} priority={args.priority} area={args.area} "
              f"tier={args.tier_hypothesis} spec={args.spec_ready_eval} dry_run=True")
        return 0

    rc, stdout, stderr = file_issue(full_title, body, labels, dry_run=False)
    if rc != 0:
        print(f"ERROR: gh issue create failed (exit {rc}):\n{stderr}", file=sys.stderr)
        return 1

    issue_number, issue_url = parse_issue_url(stdout)
    output = {
        "issue_number": issue_number,
        "issue_url": issue_url,
        "title": full_title,
        "labels": labels,
    }
    print(json.dumps(output))
    print(
        f"SUMMARY: type={args.type} priority={args.priority} area={args.area} "
        f"tier={args.tier_hypothesis} spec={args.spec_ready_eval} "
        f"issue=#{issue_number}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
