#!/usr/bin/env python3
"""Freeze gate for the #849 corpus (rubric §9).

Everything before this ran against SEED files. The arms never see those — they
see the rendered corpus, so this is the check that actually matters, and it is
the last one before a run. It closes the three gaps the design lead named when
the seed detector was all that existed:

1. **It runs on the rendered artifact**, not the seed. A seed comment is exempt
   in its own file and fatal in the output; a loader-side edge exists in
   neither seed nor stream and escaped every earlier check.
2. **It greps for oracle content.** Forbidden vocabulary catches verdict words;
   it does not catch a specific oracle VALUE leaking — a date, "14:00-15:45",
   a wrong-answer phrase reproduced verbatim.
3. **It runs a recoverability probe** for every inferred-pattern oracle point:
   a deterministic, non-LLM script must recover the claimed structure from the
   rendered events. If a script can recover it, the signal is present and an
   arm that misses it failed on merit. If it cannot, the corpus is too thin and
   we add signal BEFORE the run rather than discovering it after.

That third one is the answer to a question that cannot otherwise be answered:
whether an inferred pattern is really there, or whether one author convinced
themselves it was.

Two severities, deliberately:

* **FAIL** — a seed comment, a forbidden token, a non_rendered key, or a
  wrong-answer phrase reproduced verbatim in the corpus. Each is
  unambiguously a leak.
* **ADJUDICATE** — an oracle statement fragment that also appears in the
  corpus. That is often CORRECT: the oracle says "the moved 1:1 overlaps the PT
  session", and the corpus must contain both events for the point to be
  inferable. The rubric's rule is that each hit is judged by hand and logged,
  so this reports rather than fails.

Usage:
    python3 -m scripts.research.check_849_freeze [--scale N]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SYNTH = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis"
SEED_DIR = SYNTH / "seed"
ORACLE_DIR = SYNTH / "oracle"
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.check_849_seed import FORBIDDEN_TOKENS  # noqa: E402
from scripts.research.render_849_corpus import render  # noqa: E402

#: Comment lines too generic to be evidence of a leak if they appear.
_BORING_COMMENT = re.compile(
    r"^#*\s*(-+|=+|SEED MATERIAL.*|.{0,12})$", re.IGNORECASE
)


def corpus_text(corpus) -> str:
    return (json.dumps(corpus.events, default=str, sort_keys=True)
            + json.dumps(corpus.entities, default=str, sort_keys=True))


def seed_comment_lines() -> list[tuple[str, str]]:
    """Every substantive whole-line comment across the seed files.

    These carry the reasoning, and several quote oracle content directly —
    "True footprint 14:00-15:45" solves Arc A outright. They are safe in a
    seed and fatal in the output.
    """
    out: list[tuple[str, str]] = []
    for path in sorted(SEED_DIR.glob("*.yaml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            body = stripped.lstrip("#").strip()
            if len(body) < 25 or _BORING_COMMENT.match(stripped):
                continue
            out.append((path.name, body))
    return out


def load_oracles() -> list[dict]:
    docs = []
    for path in sorted(ORACLE_DIR.glob("*.yaml")):
        if path.name.endswith("-appendix.yaml"):
            continue
        raw = re.sub(r"(?m)^\s*#.*$", "", path.read_text(encoding="utf-8"))
        doc = yaml.safe_load(raw)
        doc["_file"] = path.name
        docs.append(doc)
    return docs


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_no_seed_comments(text: str) -> list[str]:
    hits = []
    for name, body in seed_comment_lines():
        if body in text:
            hits.append(f"FAIL: seed comment from {name} reached the corpus: {body[:90]!r}")
    return hits


def check_no_forbidden_vocabulary(text: str) -> list[str]:
    low = text.lower()
    return [
        f"FAIL: forbidden token {t!r} appears in the RENDERED corpus"
        for t in FORBIDDEN_TOKENS if t in low
    ]


def check_no_non_rendered_keys(text: str) -> list[str]:
    hits = []
    for path in sorted(SEED_DIR.glob("*.yaml")):
        raw = re.sub(r"(?m)^\s*#.*$", "", path.read_text(encoding="utf-8"))
        doc = yaml.safe_load(raw) or {}
        for key in (doc.get("meta") or {}).get("non_rendered") or []:
            if key in text:
                hits.append(
                    f"FAIL: non_rendered key {key!r} (declared by {path.name}) "
                    f"reached the corpus"
                )
    return hits


def check_no_wrong_answer_phrases(text: str, oracles: list[dict]) -> list[str]:
    """A wrong answer reproduced verbatim would be catastrophic.

    The corpus containing the literal string "counter-offer Thursday at 15:15"
    would not merely leak — it would ASSERT the wrong answer.
    """
    low = text.lower()
    hits = []
    for doc in oracles:
        for phrase in doc.get("wrong_answers") or []:
            if len(phrase) > 20 and phrase.lower() in low:
                hits.append(
                    f"FAIL: {doc['_file']} wrong-answer phrase appears verbatim "
                    f"in the corpus: {phrase!r}"
                )
    return hits


def adjudicate_oracle_statements(text: str, oracles: list[dict]) -> list[str]:
    """Report statement fragments that also appear in the corpus.

    Usually CORRECT — the oracle describes what the corpus must contain — so
    this reports for hand adjudication rather than failing, per rubric §9.
    """
    low = text.lower()
    notes = []
    for doc in oracles:
        for point in doc.get("must_identify") or []:
            words = re.findall(r"[a-z0-9:%-]+", str(point["statement"]).lower())
            for size in (8,):
                for i in range(len(words) - size + 1):
                    frag = " ".join(words[i:i + size])
                    if frag in low:
                        notes.append(
                            f"ADJUDICATE: {doc['_file']} {point['id']} statement "
                            f"fragment present in corpus: {frag!r}")
                        break
    return notes


# --------------------------------------------------------------------------
# Recoverability probe (rubric §9)
# --------------------------------------------------------------------------


def probe_arc_e_sessions(corpus) -> tuple[bool, str]:
    """Can a deterministic script recover E1's five-phase session shape?

    The claim under test: 13 marathon sessions, each the same five action
    types in the same order, span about two hours. If this recovers it, the
    signal is in the corpus and an arm that misses it failed on merit.
    """
    actions = sorted(
        (e for e in corpus.events if e.get("channel") == "mail-client" and e.get("action")),
        key=lambda e: str(e["at"]),
    )
    if not actions:
        return False, "no mail-client action events in the corpus at all"

    # Cluster by inter-event gap — the same operation an arm would have to do.
    sessions: list[list[dict]] = []
    current: list[dict] = []
    previous: datetime | None = None
    for ev in actions:
        when = datetime.fromisoformat(str(ev["at"]))
        if previous is not None and (when - previous).total_seconds() > 3 * 3600:
            sessions.append(current)
            current = []
        current.append(ev)
        previous = when
    if current:
        sessions.append(current)

    shapes = Counter()
    for session in sessions:
        ordered: list[str] = []
        for ev in session:
            if not ordered or ordered[-1] != ev["action"]:
                ordered.append(ev["action"])
        shapes[tuple(ordered)] += 1

    (dominant, count), = shapes.most_common(1)
    ok = count >= 11 and len(dominant) == 5
    detail = (
        f"{len(sessions)} sessions recovered; dominant shape {list(dominant)} "
        f"seen {count}x (need >= 11 sessions sharing a 5-phase shape)"
    )
    return ok, detail


def probe_arc_f_slope(corpus) -> tuple[bool, str]:
    """Is Arc F's decline recoverable as a slope from the check-in stream?"""
    per_week: dict[int, int] = defaultdict(int)
    for ev in corpus.events:
        if ev.get("channel") == "vikunja" and ev.get("task") == "TASK_MEDITATION":
            week = datetime.fromisoformat(str(ev["at"])).isocalendar()[1]
            per_week[week] += 1
    if len(per_week) < 10:
        return False, f"only {len(per_week)} weeks of check-ins recovered"
    weeks = sorted(per_week)
    first = sum(per_week[w] for w in weeks[:5]) / 5
    last = sum(per_week[w] for w in weeks[-5:]) / 5
    ok = last < first
    return ok, f"mean check-ins/week fell from {first:.1f} (first 5) to {last:.1f} (last 5)"


PROBES = {
    "E1-4 five-phase session shape": probe_arc_e_sessions,
    "F1-2 practice decline is a slope": probe_arc_f_slope,
}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def run(scale: int = 1) -> tuple[list[str], list[str], list[str]]:
    corpus, contract_problems = render(scale)
    text = corpus_text(corpus)
    oracles = load_oracles()

    failures = [f"FAIL: {p}" for p in contract_problems]
    failures += check_no_seed_comments(text)
    failures += check_no_forbidden_vocabulary(text)
    failures += check_no_non_rendered_keys(text)
    failures += check_no_wrong_answer_phrases(text, oracles)

    probe_lines = []
    for label, probe in PROBES.items():
        ok, detail = probe(corpus)
        probe_lines.append(f"{'PASS' if ok else 'FAIL'}: probe [{label}] — {detail}")
        if not ok:
            failures.append(
                f"FAIL: recoverability probe [{label}] could not recover the "
                f"claimed structure — the corpus is too thin to score that "
                f"oracle point. Add signal BEFORE the run. ({detail})"
            )

    return failures, adjudicate_oracle_statements(text, oracles), probe_lines


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args(argv[1:])

    failures, adjudications, probes = run(args.scale)

    for line in probes:
        print(f"  {line}")
    if adjudications:
        print(f"\n  {len(adjudications)} fragment(s) for hand adjudication "
              f"(expected — the oracle describes what the corpus contains):")
        for note in adjudications[:10]:
            print(f"    {note}")
        if len(adjudications) > 10:
            print(f"    … and {len(adjudications) - 10} more")

    if failures:
        print("\ncheck_849_freeze: NOT FROZEN")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("\ncheck_849_freeze: OK — corpus is clean and every probe recovered")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
