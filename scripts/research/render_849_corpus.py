#!/usr/bin/env python3
"""Render the #849 seed into the corpus the arms actually consume.

The arms never see seed files. They see this output: a timestamped event
stream and an entity set, as an adapter would have written them. Three
properties matter more than completeness, and each is enforced rather than
intended:

**Comments never render.** Seed files carry the reasoning — which leak a file
is avoiding, why an absence is deliberate, what the oracle expects to be
inferred. Several of those comments quote oracle content directly. They are
valuable and they must not reach an arm, so the renderer strips them and the
freeze check greps the output for them anyway.

**Declared blocks never render.** A seed lists `meta.non_rendered`: generator
input and cross-arc references the renderer *consumes*. Arc B's names which
misses the oracle counts; Arc F's carries the phase bands. Emitting them
verbatim would hand over the answer key.

**Every declared emit is produced.** `meta.emits` is the two-way contract from
rubric §3.1: oracle traceability may name these ids, so the renderer is bound
to produce them. A generator that silently stops emitting one would leave an
oracle point unverifiable, which is the failure this contract exists to make
loud.

Determinism: every generator draws from a `random.Random` seeded from the
seed file's own declared seed, so the corpus is reproducible byte-for-byte.
A corpus that differs between runs cannot support 3 repeats per arm.

Usage:
    python3 -m scripts.research.render_849_corpus [--out DIR] [--scale N]

`--scale` divides generated volume (default 1 = full ~5,000 emails). It exists
for tests; a scaled corpus is NOT valid for a run and the manifest records the
scale so that can be checked.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
from datetime import datetime, timedelta

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SYNTH = REPO_ROOT / "docs" / "design" / "research" / "849-synthesis"
SEED_DIR = SYNTH / "seed"
DEFAULT_OUT = REPO_ROOT / "build" / "849-corpus"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def strip_comments(raw: str) -> str:
    """Remove whole-line comments before parsing.

    Not cosmetic. Seed comments quote oracle content — "True footprint
    14:00-15:45", the phrase that solves Arc A outright — so anything derived
    from a seed must be derived from parsed DATA, never from its text.
    """
    return re.sub(r"(?m)^\s*#.*$", "", raw)


def load_seed(path: pathlib.Path) -> dict:
    return yaml.safe_load(strip_comments(path.read_text(encoding="utf-8"))) or {}


def rendered_view(doc: dict) -> dict:
    """The part of a seed that may reach an arm."""
    skip = set((doc.get("meta") or {}).get("non_rendered") or []) | {"meta"}
    return {k: v for k, v in doc.items() if k not in skip}


def load_all() -> dict[str, dict]:
    return {p.stem: load_seed(p) for p in sorted(SEED_DIR.glob("*.yaml"))}


# --------------------------------------------------------------------------
# Output model
# --------------------------------------------------------------------------


class Corpus:
    """Accumulates rendered events and entities, and tracks emitted ids."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.entities: list[dict] = []
        self.emitted: set[str] = set()

    def event(self, emit_id: str, when: str, channel: str, fields: dict | None = None) -> None:
        """Record one rendered event.

        `fields` is a dict rather than **kwargs on purpose: seed rows carry
        their own `when` / `channel` / `id` keys, and unpacking them collided
        with the positional parameters. Passing the payload explicitly keeps
        seed vocabulary and renderer vocabulary from fighting.
        """
        payload = dict(fields or {})
        payload.pop("when", None)
        payload.pop("channel", None)
        self.events.append({"at": when, "channel": channel, **payload})
        self.emitted.add(emit_id)

    def entity(self, kind: str, data: dict, emit_id: str | None = None) -> None:
        self.entities.append({"kind": kind, **data})
        if emit_id:
            self.emitted.add(emit_id)

    def sort(self) -> None:
        # `default=str` because YAML parses bare dates into datetime.date,
        # which json cannot serialise. The tiebreaker exists so the ordering is
        # total and therefore reproducible — 3 repeats per arm need a corpus
        # that is byte-identical between runs.
        self.events.sort(
            key=lambda e: (str(e["at"]), str(e.get("channel", "")),
                           json.dumps(e, sort_keys=True, default=str)))


# --------------------------------------------------------------------------
# Entity rendering — the parts every arc shares
# --------------------------------------------------------------------------

ENTITY_SECTIONS = (
    ("purposes", "Purpose"),
    ("domains", "Domain"),
    ("capacities", "Capacity"),
    ("outcomes", "Outcome"),
    ("principles", "Principle"),
    ("commitments", "Commitment"),
    ("tasks", "Task"),
    ("decisions", "Decision"),
    ("interests", "Interest"),
    ("persons", "Person"),
)


def render_entities(corpus: Corpus, seeds: dict[str, dict]) -> None:
    for name, doc in seeds.items():
        view = rendered_view(doc)
        emits = set((doc.get("meta") or {}).get("emits") or [])
        for key, kind in ENTITY_SECTIONS:
            for item in view.get(key) or []:
                corpus.entity(kind, item)
        for key in ("edges", "decision_edges"):
            for edge in view.get(key) or []:
                corpus.entity("Edge", edge)
        # Files whose whole job is entities mark their emit satisfied here.
        for emit in emits:
            if emit.endswith(("_PERSONS", "_ENTITIES")):
                corpus.emitted.add(emit)


def render_explicit_events(corpus: Corpus, seeds: dict[str, dict]) -> None:
    """Episodes, calendar rows and traffic that the seed states literally."""
    for name, doc in seeds.items():
        view = rendered_view(doc)

        for key in ("episodes", "episodes_booking", "interest_episodes"):
            for ep in view.get(key) or []:
                corpus.event(
                    ep.get("id", key), str(ep["reference_time"]), "episode", {
                        "id": ep.get("id"),
                        "source_description": ep.get("source_description"),
                        "content": ep.get("content"),
                        "content_ref": ep.get("content_ref"),
                        "mentions": ep.get("mentions") or [],
                    })

        for key in ("calendar_events", "calendar_events_after_move", "slot_fillers"):
            for row in view.get(key) or []:
                when = str(row.get("start") or row.get("when") or "")
                corpus.event(row.get("emit", "GEN_A_CALENDAR"), when, "calendar", row)

        for row in view.get("traffic") or []:
            # A row may name the emit it satisfies; otherwise it is ordinary
            # traffic. This is how a specific primitive the oracle cites (the
            # report thread, the probe, the retrospective invite) stays
            # attributable while still rendering as an ordinary message.
            corpus.event(
                row.get("emit", "GEN_C_TRAFFIC"), str(row["when"]),
                row.get("channel", "email"), row
            )

        # Decoy events render as ORDINARY calendar/message rows. Their emit id
        # exists only for the traceability contract and never reaches output.
        for row in view.get("events") or []:
            emit = row.get("id", "GEN_A_NM")
            payload = {k: v for k, v in row.items() if k not in ("id", "variants")}
            if row.get("variants"):
                for variant in row["variants"]:
                    corpus.event(emit, str(variant.get("when")), "calendar",
                                 {k: v for k, v in variant.items() if k != "when"})
            else:
                corpus.event(emit, str(row.get("when")), row.get("channel", "calendar"),
                             payload)

        for row in view.get("calendar_sharing") or []:
            corpus.event("GEN_A_SHARING", "2026-04-06T00:00", "config", row)


# --------------------------------------------------------------------------
# Generators — the volume
# --------------------------------------------------------------------------


def _rng(label: str) -> random.Random:
    return random.Random(label)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def generate_arc_f(corpus: Corpus, doc: dict, scale: int) -> None:
    gi = doc.get("generator_input") or {}
    weeks = gi.get("weeks") or {}
    start = datetime.fromisoformat(str(weeks.get("start", "2026-04-06")))
    rng = _rng(str(gi.get("seed", "arc-f")))

    for phase in gi.get("phases") or []:
        lo_wk, hi_wk = phase["weeks"]
        for wk in range(lo_wk, hi_wk + 1):
            monday = start + timedelta(weeks=wk - 1)
            n_check = max(1, rng.randint(*phase["check_ins"]) // scale)
            n_journal = max(1, rng.randint(*phase["journal"]) // scale)
            days = rng.sample(range(7), min(n_check, 7))
            for d in days:
                when = monday + timedelta(days=d, hours=6, minutes=rng.randint(5, 55))
                corpus.event("GEN_F_CHECKINS", _iso(when), "vikunja",
                             {"task": "TASK_MEDITATION", "status": "completed"})
            for d in rng.sample(range(7), min(n_journal, 7)):
                when = monday + timedelta(days=d, hours=6, minutes=rng.randint(10, 58))
                corpus.event("GEN_F_JOURNAL", _iso(when), "journal", {"kind": "entry"})

    # GAP F5 — the dominant slot-filler, as sent mail in the practice window.
    efm = doc.get("email_first_mornings") or {}
    rng = _rng(str(efm.get("seed", "emailfirst")))
    for wk, per_week in [(8, 1)] + [(w, 3) for w in range(14, 19)] + [(w, 2) for w in range(19, 25)]:
        monday = start + timedelta(weeks=wk - 1)
        for d in rng.sample(range(5), min(per_week // scale or 1, 5)):
            when = monday + timedelta(days=d, hours=6, minutes=rng.randint(2, 50))
            corpus.event("GEN_F_EMAIL_FIRST", _iso(when), "email",
                         {"direction": "outbound", "account": rng.choice(
                             ["personal", "Intentional", "spec-kitty"])})

    # The shared late nights — owned here, consumed by Arc B (R5).
    sln = doc.get("shared_late_nights") or {}
    rng = _rng(str(sln.get("seed", "latenights")))
    for wk in (7, 8, 9, 11, 13, 14, 16, 17, 19, 20, 21, 22):
        monday = start + timedelta(weeks=wk - 1)
        for _ in range(rng.randint(2, 5)):
            when = monday + timedelta(
                days=rng.randint(0, 4), hours=23, minutes=rng.randint(30, 59))
            corpus.event("SHARED_LATE_NIGHTS", _iso(when), rng.choice(
                ["git", "email", "slack"]), {"direction": "outbound", "week": wk})


def generate_arc_e(corpus: Corpus, doc: dict, scale: int) -> None:
    gi = doc.get("generator_input") or {}
    rng = _rng(str(gi.get("seed", "arc-e")))
    window = gi.get("window") or {}
    start = datetime.fromisoformat(str(window.get("start", "2026-04-06")))
    n_weeks = int(window.get("weeks", 24))

    accounts = gi.get("accounts") or {}
    senders = gi.get("senders") or {}
    vendors = [f"vendor{i:02d}.example" for i in range(int(senders.get("vendor_orgs", 25)))]
    letters = [f"news{i:02d}.example" for i in range(int(senders.get("newsletter_orgs", 15)))]

    for wk in range(1, n_weeks + 1):
        monday = start + timedelta(weeks=wk - 1)
        for account, cfg in accounts.items():
            for _ in range(max(1, int(cfg.get("per_week", 60)) // scale)):
                when = monday + timedelta(
                    days=rng.randint(0, 6), hours=rng.randint(6, 22),
                    minutes=rng.randint(0, 59))
                sender = rng.choice(vendors + letters)
                corpus.event("GEN_E_MAIL_MASS", _iso(when), "email",
                             {"account": account, "direction": "inbound",
                              "sender": f"news@{sender}"})

    # The 13 sessions, rendered as their observable ACTIONS only. Nothing here
    # says session, step, process or triage — the shape is the signal.
    sessions = gi.get("sessions") or {}
    shape = sessions.get("action_shape") or []
    rng = _rng("arc-e-sessions")
    day = start + timedelta(days=4)
    for _ in range(int(sessions.get("count", 13))):
        cursor = day.replace(hour=rng.randint(19, 20), minute=rng.randint(0, 40))
        for action in shape:
            for _ in range(rng.randint(3, 9) // max(scale, 1) or 1):
                cursor += timedelta(minutes=rng.randint(1, 6))
                corpus.event("GEN_E_SESSIONS", _iso(cursor), "mail-client",
                             {"action": action,
                              "sender": f"news@{rng.choice(vendors + letters)}"})
        day += timedelta(days=rng.randint(10, 14))

    for row in doc.get("generator_input", {}).get("buried_with_consequence") or []:
        monday = start + timedelta(weeks=int(row["wk"]) - 1)
        corpus.event("GEN_E_BURIED", _iso(monday + timedelta(days=1, hours=9)),
                     "email", {"account": row.get("account"), "kind": row.get("kind")})
        corpus.event("GEN_E_CONSEQUENCES",
                     _iso(monday + timedelta(days=6, hours=11)), "email",
                     {"note": row.get("consequence")})

    for g in (doc.get("generator_input", {}).get("grounding") or []):
        corpus.event("GEN_E_GROUNDING", _iso(start), "record", g)

    for a in (doc.get("generator_input", {}).get("already_automated") or []):
        for wk in range(1, n_weeks + 1):
            when = start + timedelta(weeks=wk - 1, hours=7)
            corpus.event("GEN_E_AUTOMATED", _iso(when), "email", a)

    for v in (doc.get("generator_input", {}).get("varying_recurrence") or []):
        for wk in range(1, n_weeks + 1):
            when = start + timedelta(weeks=wk - 1, days=2, hours=15)
            corpus.event("GEN_E_VARYING", _iso(when), "note", v)

    week = doc.get("e2_sample_week") or {}
    ws = datetime.fromisoformat(str(week.get("start", "2026-08-31")))
    for i, item in enumerate(doc.get("scored_items") or []):
        corpus.event("GEN_E_SAMPLE_WEEK",
                     _iso(ws + timedelta(days=i % 5, hours=8 + i % 9)),
                     "email", item)


def generate_arc_b(corpus: Corpus, doc: dict, scale: int) -> None:
    gi = doc.get("generator_input") or {}
    rng = _rng(str(gi.get("seed", "arc-b")))
    day_of = {"tue": 1, "thu": 3, "sat": 5}

    for wk in gi.get("weeks") or []:
        monday = datetime.fromisoformat(str(wk["mon"]))
        missed_days = {m["day"] for m in (wk.get("missed") or [])}
        for label, offset in day_of.items():
            if label in missed_days or "all" in missed_days:
                continue  # completions-only: a miss is an ABSENCE, not a row
            when = monday + timedelta(days=offset, hours=6, minutes=rng.randint(30, 59))
            corpus.event("GEN_B_SESSIONS", _iso(when), "vikunja",
                         {"task": "core run", "status": "completed"})
        for m in (wk.get("missed") or []):
            if m.get("reason"):
                when = monday + timedelta(days=day_of.get(m["day"], 0), hours=7)
                corpus.event(f"GEN_B_WK{wk['wk']}_{m['day'].upper()}",
                             _iso(when), "note", {"text": m["reason"]})
            if m.get("decision"):
                corpus.event("GEN_B_DECISIONS",
                             _iso(monday + timedelta(days=day_of.get(m['day'], 0), hours=7, minutes=5)),
                             "episode", {"kind": "decision-source", "text": m.get("reason")})
        if wk.get("note"):
            corpus.event(f"GEN_B_WK{wk['wk']}_PROG", _iso(monday + timedelta(days=3, hours=7)),
                         "vikunja", {"note": wk["note"]})

    race = gi.get("race") or {}
    if race:
        corpus.event("GEN_B_RACE", f"{race['date']}T08:00", "vikunja",
                     {"event": "race", "result": race.get("result")})


GENERATORS = {"arc-f": generate_arc_f, "arc-e": generate_arc_e, "arc-b": generate_arc_b}


# --------------------------------------------------------------------------
# Render + contract check
# --------------------------------------------------------------------------


def render(scale: int = 1) -> tuple[Corpus, list[str]]:
    seeds = load_all()
    corpus = Corpus()
    render_entities(corpus, seeds)
    render_explicit_events(corpus, seeds)
    for name, gen in GENERATORS.items():
        if name in seeds:
            gen(corpus, seeds[name], scale)
    corpus.sort()

    declared: set[str] = set()
    for doc in seeds.values():
        declared |= set((doc.get("meta") or {}).get("emits") or [])

    missing = sorted(declared - corpus.emitted)
    problems = [
        f"declared emit {m!r} was never produced — oracle traceability names it, "
        f"so the point it supports would be unverifiable"
        for m in missing
    ]
    return corpus, problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args(argv[1:])

    corpus, problems = render(args.scale)

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "stream.jsonl").open("w", encoding="utf-8") as fh:
        for event in corpus.events:
            fh.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    (args.out / "entities.json").write_text(
        json.dumps(corpus.entities, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8")
    (args.out / "manifest.json").write_text(
        json.dumps({
            "scale": args.scale,
            "valid_for_run": args.scale == 1,
            "events": len(corpus.events),
            "entities": len(corpus.entities),
            "emitted": sorted(corpus.emitted),
        }, indent=2) + "\n", encoding="utf-8")

    print(f"render_849_corpus: {len(corpus.events)} events, "
          f"{len(corpus.entities)} entities -> {args.out}")
    if args.scale != 1:
        print("  ⚠ scaled corpus — NOT valid for a run (manifest records this)")
    if problems:
        print("render_849_corpus: CONTRACT FAILURES")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
