#!/usr/bin/env python3
"""Generate the derived copies of the doc-status taxonomy.

`docs/design/standards/allowed-values.json` is the single enforced source. Two
other files restate the same vocabulary and had both silently drifted from it
before this existed — `active` was live and missing from each. This script makes
them build output so drift is impossible rather than merely discouraged.

Targets
  frontmatter.schema.json  the `status` constraint, as CONDITIONAL schema — a
                           flat enum cannot express per-doc_type sets (it would
                           either admit `active` on a decision record or reject
                           `superseded` on one).
  doc-standards.md         the status list, between GENERATED sentinels. Prose
                           outside them is hand-written and never touched.

Modes
  (default)    write the derived regions
  --check      write nothing; exit non-zero if any region is stale (CI gate)
  --bootstrap  one-time: insert the sentinels into a file that has none

Bootstrap exists because the rules are otherwise circular: the sentinels must be
present for the generator to write, the generator is the only permitted writer,
and the file ships without them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from doc_taxonomy import Taxonomy, TaxonomyError, load_taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "design" / "standards" / "frontmatter.schema.json"
NARRATIVE_PATH = ROOT / "docs" / "design" / "standards" / "doc-standards.md"
#: The ADR README restates the decision-status vocabulary for authors. Left
#: hand-maintained it is a third copy of the same list — the exact drift class
#: this generator exists to remove (#987 post-merge review F6).
ADR_README_PATH = ROOT / "docs" / "design" / "architecture" / "adr" / "README.md"

ADR_START = "<!-- GENERATED:decision-status-table START -->"
ADR_END = "<!-- GENERATED:decision-status-table END -->"

START = "<!-- GENERATED:status-list START -->"
END = "<!-- GENERATED:status-list END -->"
_WARNING = "<!-- Generated from allowed-values.json by generate_doc_standards.py. Do not edit by hand. -->"
#: Marks the single `allOf` entry this generator owns, so unrelated schema
#: constraints added later are preserved rather than silently replaced.
_SCHEMA_CLAUSE_MARKER = "GENERATED:status-by-doc_type"
#: Any markdown ATX heading ends a section. Matching only unindented "### "
#: let a "## appendix" or an indented/tab-separated heading be crossed
#: (review finding M2, cycle 2).
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}[ \t]")
#: A fenced block delimiter. Per CommonMark a closing fence must use the SAME
#: character and be at least as long as the opener — treating any fence as a
#: closer let a mismatched or shorter one reopen the document and expose fenced
#: sentinels as writable (review cycle 3).
_FENCE_RE = re.compile(r"^\s{0,3}(?P<char>`|~)(?P<fence>(?P=char){2,})")


class GeneratorError(Exception):
    """A target file is not in a state the generator can safely write."""


# ---------------------------------------------------------------- schema ----


def build_status_schema(tax: Taxonomy) -> dict:
    """The conditional `status` constraint.

    One `if/then` per scoped doc_type, plus a negative clause applying the
    default set to everything else. Emitting a flat union instead would make
    every scoped value legal everywhere, which is the bug this replaces.
    """
    scoped = sorted(tax.scoped_statuses)
    clauses: list[dict] = []
    for doc_type in scoped:
        clauses.append(
            {
                "if": {"properties": {"doc_type": {"const": doc_type}}, "required": ["doc_type"]},
                "then": {"properties": {"status": {"enum": list(tax.scoped_statuses[doc_type])}}},
            }
        )
    clauses.append(
        {
            "if": {"not": {"properties": {"doc_type": {"enum": scoped}}, "required": ["doc_type"]}},
            "then": {"properties": {"status": {"enum": list(tax.default_statuses)}}},
        }
    )
    return {"$comment": _SCHEMA_CLAUSE_MARKER, "allOf": clauses}


def _is_legacy_status_clause(clause: object) -> bool:
    """True only for a clause shaped like this generator's own pre-marker output.

    Deliberately narrow. An earlier draft asked "does this mention `status`
    anywhere", which both rejected legitimate foreign clauses that merely
    annotate the field and still missed exotic forms such as
    `patternProperties`. A fuzzy guard against a one-time migration hazard is
    worse than a precise one: this matches an if/then whose `then` constrains
    `status` with an enum — the exact shape we used to emit — and nothing else.
    Anything more exotic is a hand-edit, which the marker rule already covers.
    """
    if not isinstance(clause, dict) or "if" not in clause:
        return False
    then = clause.get("then")
    if not isinstance(then, dict):
        return False
    status = then.get("properties", {}).get("status")
    return isinstance(status, dict) and "enum" in status


def render_schema(tax: Taxonomy, current: dict) -> dict:
    """Return `current` with only the status constraint replaced."""
    out = json.loads(json.dumps(current))  # deep copy; leave the original alone
    status = out.setdefault("properties", {}).setdefault("status", {})
    status.pop("enum", None)  # the enum moves into the conditional clauses
    status["type"] = "string"
    status.setdefault("description", "Document lifecycle status")
    # Preserve every allOf entry that is not ours (review finding M1).
    existing = [
        c for c in out.get("allOf", [])
        if not (isinstance(c, dict) and c.get("$comment") == _SCHEMA_CLAUSE_MARKER)
    ]
    # A pre-marker generated clause would survive as "foreign" and produce two
    # active status rules. Refuse rather than silently double-constrain (M1).
    for clause in existing:
        if _is_legacy_status_clause(clause):
            raise GeneratorError(
                f"{SCHEMA_PATH}: an unmarked allOf clause constrains `status`; it is probably a "
                f"pre-marker generated clause. Remove it, then re-run."
            )
    out["allOf"] = existing + [build_status_schema(tax)]
    return out


# ------------------------------------------------------------- narrative ----


def render_narrative_region(tax: Taxonomy) -> str:
    """The generated block for doc-standards.md."""
    lines = [_WARNING, "", "Default (any `doc_type` without its own set):", ""]
    lines.append(", ".join(f"`{s}`" for s in tax.default_statuses))
    for doc_type in sorted(tax.scoped_statuses):
        lines += ["", f"`doc_type: {doc_type}`:", ""]
        lines.append(", ".join(f"`{s}`" for s in tax.scoped_statuses[doc_type]))
    return "\n".join(lines)


#: One-line meanings for the decision statuses. Prose belongs with the
#: vocabulary, so the generated table carries both.
DECISION_STATUS_MEANINGS = {
    "draft": "being written; not yet put forward",
    "proposed": "complete and coherent, but the concept is not settled and needs debate or design",
    "approved": "decided, by a stated authority, and safe to act on",
    "superseded": "a newer ADR replaces this decision; a `superseded-by` log row names it",
    "deprecated": "the topic is no longer relevant; no successor",
}


def render_decision_status_table(tax: Taxonomy) -> str:
    """The ADR README's status table, derived from the source."""
    lines = [_WARNING, "", "| Status | Meaning |", "|---|---|"]
    for status in tax.statuses_for("decision"):
        meaning = DECISION_STATUS_MEANINGS.get(status, "_(no description recorded)_")
        lines.append(f"| `{status}` | {meaning} |")
    return "\n".join(lines)


def _region_name(start: str) -> str:
    """'<!-- GENERATED:status-list START -->' -> 'GENERATED:status-list'.

    Error messages name the region, not the raw marker: an author reading
    "no GENERATED:status-list sentinels" knows what is missing without parsing
    an HTML comment out of the sentence.
    """
    m = re.search(r"(GENERATED:[\w-]+)", start)
    return m.group(1) if m else start


def _split_on_sentinels(text: str, path: Path, start: str = START, end: str = END) -> tuple[str, str]:
    """Return the text before and after the generated region.

    Strict by design: anything other than exactly one ordered pair fails without
    writing, rather than guessing an insertion point.
    """
    lines = text.splitlines(keepends=True)
    start_idx, end_idx = [], []
    open_fence: tuple[str, int] | None = None
    for i, ln in enumerate(lines):
        m = _FENCE_RE.match(ln)
        if m:
            char = m.group("char")
            length = len(m.group("char") + m.group("fence"))
            if open_fence is None:
                open_fence = (char, length)
            elif char == open_fence[0] and length >= open_fence[1]:
                open_fence = None
            # A mismatched or shorter fence is ordinary content inside the block.
            continue
        if open_fence is not None:
            # A documentation example may legitimately show the markers.
            continue
        if ln.strip() == start:
            start_idx.append(i)
        elif ln.strip() == end:
            end_idx.append(i)
    # Substring matching would make a fenced example containing the marker a
    # writable boundary and destroy the prose between them (finding M3).
    inline = sum(
        1
        for ln in lines
        for marker in (start, end)
        if marker in ln and ln.strip() != marker
    )
    if inline:
        raise GeneratorError(
            f"{path}: {_region_name(start)} marker appears {inline} time(s) other than as a "
            f"standalone line"
        )
    starts, ends = len(start_idx), len(end_idx)
    if starts == 0 and ends == 0:
        raise GeneratorError(f"{path}: no {_region_name(start)} sentinels — run with --bootstrap once")
    if starts != 1 or ends != 1:
        raise GeneratorError(
            f"{path}: expected exactly one {_region_name(start)} sentinel pair, "
            f"found {starts} START and {ends} END"
        )
    if end_idx[0] < start_idx[0]:
        raise GeneratorError(f"{path}: END sentinel precedes START")
    return "".join(lines[: start_idx[0]]), "".join(lines[end_idx[0] + 1 :])


def render_region(tax: Taxonomy, current: str, path: Path, start: str, end: str, body: str) -> str:
    """Replace one sentinel-delimited region, preserving everything else."""
    head, tail = _split_on_sentinels(current, path, start, end)
    close = f"{end}\n" if (tail or current.endswith("\n")) else end
    return f"{head}{start}\n{body}\n{close}{tail}"


def render_narrative(tax: Taxonomy, current: str, path: Path) -> str:
    head, tail = _split_on_sentinels(current, path)
    # Only re-add the newline the END line originally carried; a file that ended
    # directly after END must not gain one (review cycle 2, new defect).
    close = f"{END}\n" if (tail or current.endswith("\n")) else END
    return f"{head}{START}\n{render_narrative_region(tax)}\n{close}{tail}"


def bootstrap_narrative(tax: Taxonomy, current: str, path: Path) -> str:
    """Insert the sentinel pair once, replacing ONLY the hand-written status list.

    Exact, not heuristic. An earlier draft filtered the old section by dropping
    lines that begin with a backtick, which silently deleted a line of authored
    prose that happened to open with an inline code span. The generator must
    never touch anything but its own region — so it locates the single line that
    *is* the current default vocabulary and replaces exactly that.
    """
    if START in current or END in current:
        raise GeneratorError(f"{path}: sentinels already present — bootstrap is a one-time operation")

    lines = current.splitlines(keepends=True)
    heads = [i for i, ln in enumerate(lines) if ln.strip().rstrip() == "### status"]
    if len(heads) != 1:
        raise GeneratorError(
            f"{path}: expected exactly one '### status' heading, found {len(heads)}"
        )
    start = heads[0] + 1
    end = next(
        (i for i in range(start, len(lines)) if _HEADING_RE.match(lines[i])), len(lines)
    )

    target = ", ".join(f"`{s}`" for s in tax.default_statuses)
    # Scoped to the section: an identical line elsewhere in the document must
    # not become the insertion point (review finding M2).
    matches = [i for i in range(start, end) if lines[i].strip() == target]
    if len(matches) != 1:
        raise GeneratorError(
            f"{path}: expected exactly one line matching the current status list inside the "
            f"'### status' section, found {len(matches)}"
        )

    i = matches[0]
    block = f"{START}\n{render_narrative_region(tax)}\n{END}\n"
    return "".join(lines[:i] + [block] + lines[i + 1 :])


# ------------------------------------------------------------------ main ----


def _targets(tax: Taxonomy) -> list[tuple[Path, str]]:
    schema_now = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_next = json.dumps(render_schema(tax, schema_now), indent=2) + "\n"
    narrative_next = render_narrative(tax, NARRATIVE_PATH.read_text(encoding="utf-8"), NARRATIVE_PATH)
    adr_readme = ADR_README_PATH.read_text(encoding="utf-8")
    adr_next = render_region(
        tax, adr_readme, ADR_README_PATH, ADR_START, ADR_END, render_decision_status_table(tax)
    )
    return [(SCHEMA_PATH, schema_next), (NARRATIVE_PATH, narrative_next), (ADR_README_PATH, adr_next)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify freshness; write nothing")
    mode.add_argument("--bootstrap", action="store_true", help="one-time sentinel insertion")
    args = ap.parse_args(argv)

    try:
        tax = load_taxonomy()
    except TaxonomyError as exc:
        print(f"generate_doc_standards: {exc}", file=sys.stderr)
        return 2

    try:
        if args.bootstrap:
            NARRATIVE_PATH.write_text(
                bootstrap_narrative(tax, NARRATIVE_PATH.read_text(encoding="utf-8"), NARRATIVE_PATH),
                encoding="utf-8",
            )
            print(f"generate_doc_standards: bootstrapped sentinels in {NARRATIVE_PATH}")

        targets = _targets(tax)
    except GeneratorError as exc:
        print(f"generate_doc_standards: {exc}", file=sys.stderr)
        return 2

    stale = [p for p, want in targets if p.read_text(encoding="utf-8") != want]

    if args.check:
        for p in stale:
            print(f"generate_doc_standards: STALE {p}", file=sys.stderr)
        if stale:
            print("Run: python3 tooling/scripts/generate_doc_standards.py", file=sys.stderr)
            return 1
        print("generate_doc_standards: up to date")
        return 0

    for p, want in targets:
        if p.read_text(encoding="utf-8") != want:
            p.write_text(want, encoding="utf-8")
            print(f"generate_doc_standards: wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
