"""Unit tests for the #849 recoverability probes: each probe must recover its
structure from a minimal synthetic stream, and must FAIL when the structure is
removed — a probe that cannot fail proves nothing."""
from __future__ import annotations

from scripts.research import probe_849_recoverability as p


def _cal(account, start, end, title):
    return {"channel": "calendar", "account": account, "at": start, "start": start, "end": end, "title": title}


def _arc_a_rows(with_travel=True, moved=True):
    rows = []
    for d, s, e in (("2026-06-08", "07:00", "08:00"), ("2026-06-10", "12:00", "13:00"), ("2026-06-12", "16:00", "17:00")):
        if with_travel:
            rows.append(_cal("personal", f"{d}T{_m(s,-30)}", f"{d}T{s}", "Travel — gym"))
            rows.append(_cal("personal", f"{d}T{e}", f"{d}T{_m(e,30)}", "Travel — home"))
        rows.append(_cal("personal", f"{d}T{s}", f"{d}T{e}", "Workout"))
    rows.append(_cal("personal", "2026-06-09T10:15", "2026-06-09T11:00", "PT — Northside"))
    rows.append(_cal("personal", "2026-06-11T14:30", "2026-06-11T15:15", "PT — Northside"))
    if moved:
        rows.append(_cal("spec-kitty", "2026-06-11T14:00", "2026-06-11T15:00", "1:1 Kent / Marcus"))
    return rows


def _m(hhmm, delta):
    h, m = map(int, hhmm.split(":"))
    t = h * 60 + m + delta
    return f"{t // 60:02d}:{t % 60:02d}"


def test_probe_a_recovers_absence_and_overlap():
    ok, _ = p.probe_a(_arc_a_rows(), [])
    assert ok


def test_probe_a_fails_without_the_move():
    ok, _ = p.probe_a(_arc_a_rows(moved=False), [])
    assert not ok


def _session(day, start_h, shape, step=8):
    rows, t = [], start_h * 60
    for action in shape:
        for _ in range(3):
            rows.append({"channel": "mail-client", "at": f"{day}T{t // 60:02d}:{t % 60:02d}", "action": action})
            t += step
    return rows


SHAPE = ["read_offers", "read_newsletters", "file_by_org", "purge_old", "late_replies"]


def test_probe_e_recovers_shape_and_span():
    rows = []
    for i in range(13):
        rows += _session(f"2026-{4 + i // 3:02d}-{5 + 7 * (i % 3):02d}", 19, SHAPE)
    ok, lines = p.probe_e(rows, [])
    assert ok, lines


def test_probe_e_fails_when_sessions_are_short():
    rows = []
    for i in range(13):
        rows += _session(f"2026-{4 + i // 3:02d}-{5 + 7 * (i % 3):02d}", 19, SHAPE, step=4)
    ok, _ = p.probe_e(rows, [])
    assert not ok


def test_probe_e_fails_when_order_varies():
    rows = []
    for i in range(13):
        shape = SHAPE if i % 2 else list(reversed(SHAPE))
        rows += _session(f"2026-{4 + i // 3:02d}-{5 + 7 * (i % 3):02d}", 19, shape)
    ok, _ = p.probe_e(rows, [])
    assert not ok
