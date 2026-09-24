#!/usr/bin/env python3
"""Recoverability probes for #849 (rubric §9).

For every oracle point whose evidence is an INFERRED PATTERN, a deterministic,
non-LLM script must recover the claimed structure from the RENDERED corpus.
Recovered -> the signal is present, and an arm that misses it failed on merit.
Not recovered -> the corpus is too thin; add signal before any run.

This is #844's seed-retrievability check generalised. It reads only what the
arms see (stream.jsonl + entities.json); it never opens a seed or an oracle.

Usage:
    python3 -m scripts.research.probe_849_recoverability [--corpus DIR] [--arc A|B|C|E|F ...]

Exit 0 = every probe recovered its structure; 1 = at least one did not.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO_ROOT / "build" / "849-corpus"


def _dt(s: str) -> datetime:
    s = s.replace(" ", "T")
    if len(s) >= 19 and (s[19:20] in ("+", "-")):
        s = s[:19]
    return datetime.fromisoformat(s[:16] if len(s) == 16 else s[:19])


def load(corpus: pathlib.Path):
    rows = [json.loads(l) for l in (corpus / "stream.jsonl").read_text().splitlines() if l.strip()]
    ents = json.load(open(corpus / "entities.json"))
    return rows, ents


# ---------------------------------------------------------------- Arc A
def probe_a(rows, ents) -> tuple[bool, list[str]]:
    """Travel-block absence + overlap + true footprint, from calendar rows only."""
    out = []
    cal = [r for r in rows if r.get("channel") == "calendar" and r.get("start") and r.get("end")]
    wk = [r for r in cal if r.get("account") == "personal" and r["start"].startswith("2026-06-")
          and date.fromisoformat(r["start"][:10]).isocalendar()[1] == date(2026, 6, 8).isocalendar()[1]]
    travel = [r for r in wk if "travel" in (r.get("title") or "").lower()]
    sessions = [r for r in wk if "travel" not in (r.get("title") or "").lower()]

    def abuts(sess, before: bool) -> bool:
        s, e = _dt(sess["start"]), _dt(sess["end"])
        for t in travel:
            ts, te = _dt(t["start"]), _dt(t["end"])
            if before and abs((te - s).total_seconds()) <= 300:
                return True
            if not before and abs((ts - e).total_seconds()) <= 300:
                return True
        return False

    with_travel = [r["title"] for r in sessions if abuts(r, True) and abuts(r, False)]
    without = [r for r in sessions if not (abuts(r, True) or abuts(r, False))]
    out.append(f"sessions with travel both sides: {with_travel}")
    out.append(f"sessions with NO travel: {[r['title'] for r in without]}")
    pt_thu = next((r for r in without if r["start"].startswith("2026-06-11")), None)
    ok_abs = len(with_travel) >= 3 and pt_thu is not None
    # overlap with any spec-kitty event on 06-11
    work = [r for r in cal if r.get("account") == "spec-kitty" and r["start"].startswith("2026-06-11")]
    ok_overlap = False
    if pt_thu and work:
        pts, pte = _dt(pt_thu["start"]), _dt(pt_thu["end"])
        travel_len = timedelta(minutes=30)  # inferred from the workouts' blocks
        for w in work:
            ws, we = _dt(w["start"]), _dt(w["end"])
            direct = max(timedelta(), min(pte, we) - max(pts, ws))
            foot = max(timedelta(), min(pte + travel_len, we) - max(pts - travel_len, ws))
            out.append(f"overlap vs {w.get('title')}: direct={direct}, vs true footprint={foot}")
            if direct >= timedelta(minutes=30) and foot >= we - ws:
                ok_overlap = True
    return ok_abs and ok_overlap, out


# ---------------------------------------------------------------- Arc B
def probe_b(rows, ents) -> tuple[bool, list[str]]:
    """Weekly core-run completion counts from Vikunja; halfway-point Saturday absence."""
    out = []
    runs = [r for r in rows if r.get("channel") == "vikunja" and (r.get("task") or "").lower().replace("_", " ") in ("core run", "task core run")]
    if not runs:
        # accept any task whose completions fall on Tue/Thu/Sat between 06-15 and 10-15 and is not the practice tasks
        cand = Counter(r.get("task") for r in rows if r.get("channel") == "vikunja" and r.get("task") and "MEDIT" not in r["task"] and "INVEST" not in r["task"])
        runs = [r for r in rows if r.get("channel") == "vikunja" and r.get("task") == (cand.most_common(1)[0][0] if cand else None)]
    start = date(2026, 6, 15)
    by_week: dict[int, set] = defaultdict(set)
    for r in runs:
        if r.get("status") != "completed":
            continue
        d = date.fromisoformat(r["at"][:10])
        wk = (d - start).days // 7 + 1
        if 1 <= wk <= 17:
            by_week[wk].add(d.strftime("%a"))
    counts = {w: len(by_week.get(w, ())) for w in range(1, 18)}
    out.append(f"weekly core-run completions: {counts}")
    misses_to_8 = sum(3 - counts[w] for w in range(1, 9))
    rate = misses_to_8 / 24
    out.append(f"raw misses through wk 8: {misses_to_8}/24 = {rate:.0%} (oracle counts ~29% after excluding legitimate rows)")
    sat6, sat7 = "Sat" in by_week.get(6, ()), "Sat" in by_week.get(7, ())
    out.append(f"Saturday (long-run) completion wk6={sat6} wk7={sat7} wk8={'Sat' in by_week.get(8, ())}")
    pace = [r for r in rows if r.get("channel") == "vikunja" and "11:10" in (r.get("note") or "")]
    out.append(f"wk7 progression pace note present: {bool(pace)}")
    ok = (not sat6) and (not sat7) and bool(pace) and 0.2 <= rate <= 0.45 and counts[9] == 3
    return ok, out


# ---------------------------------------------------------------- Arc C
def probe_c(rows, ents) -> tuple[bool, list[str]]:
    """Gate-met inference: trigger-gated commitment with nothing inbound; report-on-launch thread after the target date; retro invite naming Fred."""
    out = []
    edges = [e for e in ents if e.get("kind") == "Edge" or e.get("type") in ("DUE_BY", "GATES", "BLOCKS", "GATED_ON", "COMMITTED_TO")]
    coms = [e for e in ents if e.get("kind") == "Commitment" and e.get("trigger")]
    out.append(f"trigger-gated commitments: {[c['id'] for c in coms]}")
    ok_orphan = False
    gate_target = None
    for c in coms:
        inbound = [e for e in edges if e.get("to") == c["id"] and e.get("type") in ("DUE_BY", "GATES", "BLOCKS")]
        gated = [e for e in edges if e.get("from") == c["id"] and e.get("type") == "GATED_ON"]
        out.append(f"{c['id']}: inbound work edges={len(inbound)}, GATED_ON={[g.get('to') for g in gated]}")
        if not inbound and gated:
            ok_orphan = True
            tgt = next((e for e in ents if e.get("id") == gated[0].get("to")), None)
            gate_target = tgt.get("target_date") if tgt else None
    out.append(f"gate target_date: {gate_target}")
    report = [r for r in rows if r.get("channel") == "email" and "how the launch went" in (r.get("subject") or "").lower()]
    after = [r for r in report if gate_target and r["at"][:10] > str(gate_target)]
    out.append(f"'how the launch went' threads after target: {[r['at'] for r in after]}")
    probe = [r for r in rows if r.get("channel") == "slack" and "launch activity" in (r.get("text") or "").lower()]
    retro = [r for r in rows if r.get("channel") == "calendar" and "retrospective" in (r.get("subject") or "").lower() and "fred" in (r.get("text") or "").lower()]
    out.append(f"oblique probe present: {bool(probe)}; retro invite naming Fred: {bool(retro)}")
    return ok_orphan and bool(after) and bool(probe) and bool(retro), out


# ---------------------------------------------------------------- Arc E
def probe_e(rows, ents) -> tuple[bool, list[str]]:
    """Cluster mail-client actions into sessions by gap; recover the ordered action shape."""
    out = []
    acts = sorted([r for r in rows if r.get("channel") == "mail-client"], key=lambda r: r["at"])
    sessions, cur = [], []
    for r in acts:
        if cur and (_dt(r["at"]) - _dt(cur[-1]["at"])) > timedelta(minutes=45):
            sessions.append(cur); cur = []
        cur.append(r)
    if cur:
        sessions.append(cur)
    shapes = []
    for s in sessions:
        seq = [a["action"] for a in s]
        shape = [seq[0]] + [b for a, b in zip(seq, seq[1:]) if b != a]
        span = _dt(s[-1]["at"]) - _dt(s[0]["at"])
        shapes.append((tuple(shape), span))
    common = Counter(sh for sh, _ in shapes).most_common(1)
    out.append(f"sessions: {len(sessions)}; spans: {[str(sp) for _, sp in shapes]}")
    out.append(f"dominant shape: {common[0] if common else None}")
    n_same = common[0][1] if common else 0
    ok = len(sessions) >= 12 and n_same >= 11 and len(common[0][0]) == 5 and all(timedelta(minutes=90) <= sp <= timedelta(minutes=150) for _, sp in shapes)
    return ok, out


# ---------------------------------------------------------------- Arc F
def probe_f(rows, ents) -> tuple[bool, list[str]]:
    """Slope of weekly practice completions and journal marks; decided-vs-silent ratio."""
    out = []
    start = date(2026, 4, 6)
    med = Counter(); jour = Counter()
    for r in rows:
        # Human task names, not internal ids. `TASK_MEDITATION` used to reach
        # the stream and no longer does: an id like that is ontology
        # vocabulary appearing inside a task tracker, which is the same class
        # as EP_C_PROMISE naming the promise. The probe follows the corpus.
        if (r.get("channel") == "vikunja"
                and r.get("task") in ("Morning meditation", "Personal-investment time")
                and r.get("status") == "completed"):
            med[(date.fromisoformat(r["at"][:10]) - start).days // 7 + 1] += 1
        if r.get("channel") == "journal":
            jour[(date.fromisoformat(r["at"][:10]) - start).days // 7 + 1] += 1
    # Normalise PER PRACTICE TASK so the thresholds mean the same thing
    # whether one or two daily practices render (the corpus has two; the
    # oracle's phase bands are per task). Tasks are counted from the stream,
    # never assumed.
    tasks = {r.get("task") for r in rows if r.get("channel") == "vikunja"
             and r.get("task") in ("Morning meditation", "Personal-investment time")}
    n_tasks = max(1, len(tasks))
    m = [med.get(w, 0) / n_tasks for w in range(1, 26)]
    j = [jour.get(w, 0) for w in range(1, 26)]
    out.append(f"practice tasks in stream: {n_tasks}; check-ins/wk per task: {[round(x, 1) for x in m]}")
    out.append(f"journal entries/wk: {j}")
    early, late = sum(m[0:5]) / 5, sum(m[18:22]) / 4
    cross = next((w for w in range(1, 26) if jour.get(w, 0) < 3 and all(jour.get(x, 0) < 3 for x in range(w, min(w + 3, 26)))), None)
    decisions = [e for e in ents if e.get("kind") == "Decision" and e.get("id", "").startswith("DEC_F")]
    missed = sum(max(0.0, 7 - m[w - 1]) for w in range(1, 25))
    out.append(f"early mean {early:.1f}/wk -> late mean {late:.1f}/wk per task; journal <3 sustained from wk {cross}; Decisions={len(decisions)} vs ~{missed:.0f} missed mornings per task; wk25 return={m[24]:.1f}")
    ok = early >= 5.5 and late <= 2.5 and cross is not None and 12 <= cross <= 16 and 3 <= len(decisions) <= 5 and m[24] >= 4
    return ok, out


PROBES = {"A": probe_a, "B": probe_b, "C": probe_c, "E": probe_e, "F": probe_f}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    ap.add_argument("--arc", action="append", choices=sorted(PROBES))
    a = ap.parse_args(argv[1:])
    rows, ents = load(a.corpus)
    failed = 0
    for arc in a.arc or sorted(PROBES):
        ok, lines = PROBES[arc](rows, ents)
        print(f"[{arc}] {'RECOVERED' if ok else 'NOT RECOVERED'}")
        for l in lines:
            print(f"    {l}")
        failed += 0 if ok else 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
