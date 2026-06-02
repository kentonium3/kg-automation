#!/usr/bin/env python3
"""Morning-reply parser (mission #371 / WP02).

Deterministic parser that turns Kent's free-text WhatsApp reply
(``"Skipped 3,7,8 done"``) into the canonical list of
``(task_id, state)`` tuples that ``record_completion.py`` consumes.

This is the load-bearing fix for issue #371. Previously the morning send and
the reply parse each derived their own habit list from live Vikunja state;
async state changes (and unstable ordering) caused the two orderings to
diverge, and Kent's "skipped 3" was applied to the wrong habit. WP01
introduced the persisted morning-list artifact -- one immutable source of
ordering. This module is the deterministic consumer: it reads that artifact
and resolves every reply token against THAT ordering, never against live
Vikunja.

Architectural shape (research D3 + D7):

  1. **Special-token pre-scan** -- catches the common "all done" / "nothing
     done" family up front and short-circuits the per-token parse with a
     full-list tuple emission. Reply text "all done" should never have to
     touch the tokenizer.

  2. **Tokenization** -- the reply is decomposed into a flat sequence of
     VERB / IDENTIFIER / CONNECTIVE atoms. A small state machine walks
     the sequence and groups identifiers under the verb that claims them
     (verb-before-identifiers OR identifiers-before-verb, both valid
     English patterns). Comma-lists immediately following a verb stay
     bound to that verb -- this is what makes ``"Skipped 3,7,8 done"``
     interpret 3,7,8 as ``skipped`` and ``done`` as "everything else".

  3. **Three-tier matching** for each identifier-token:

       a. **Position** (digit token): look up by 1-indexed position in the
          morning list. Out-of-range positions emit a structured
          ``invalid_token`` error.

       b. **Exact title match** (case-insensitive): a single exact title
          match resolves to that task_id.

       c. **Substring match** (case-insensitive, bidirectional): if the
          token contains a title OR a title contains the token, it
          matches. Exactly ONE such match resolves; multiple matches
          surface as a ``JudgmentItem`` so the narrow LLM disambiguator
          can decide. Zero matches emit ``unparseable_reply``.

Determinism (NFR-001) is the most important guarantee: the parser walks
the morning list and the reply token-by-token, never consulting a clock,
random source, or network. ``parse_reply`` is a pure function.

CLI surface (per ``contracts/cli.md``) wraps the API for AGENTS.md
invocation -- it loads the persisted morning-list JSON, parses the reply,
and emits the full ``ParseResult`` as JSON on stdout. Exit codes 0/1/3/4/5
per the contract.

See the spec / plan / data-model / contracts under
``kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/`` for the full
contract. Public API per ``contracts/api.md`` Entity 2.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

from scripts.habits.morning_checkin_list import (
    MorningList,
    MorningListHabit,
)


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md)
# ---------------------------------------------------------------------------

#: Default per-date morning-list artifact directory on office2 (mirrors WP01).
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")

#: Kent's local timezone. Used by ``_today_local`` for the default ``--date``.
LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

#: Schema version embedded in every ``ParseResult``.
SCHEMA_VERSION = 1

#: Regex for the --date flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Special-token patterns. Order matters: skip-all checked before all-done so
#: a phrase like "skipped all done" (degenerate) goes to skip-all. Each entry
#: is (compiled regex, target state). The regexes are anchored to word
#: boundaries on both sides so substrings inside a longer phrase don't
#: accidentally fire.
_SPECIAL_ALL_DONE = re.compile(
    r"\b(all\s+done|done\s+with\s+everything|everything\s+done|all\s+complete)\b",
    re.IGNORECASE,
)
_SPECIAL_ALL_SKIPPED = re.compile(
    r"\b(skipping\s+everything|skipped\s+all|none\s+done|nothing\s+done)\b",
    re.IGNORECASE,
)


# Verb taxonomy. Each verb-word maps to a target state. Multi-word verbs are
# handled by a preprocess pass that canonicalizes them to a single token
# (e.g., "did not" -> "didnot" -> incomplete).
_VERB_WORDS: dict[str, str] = {
    "done": "complete",
    "complete": "complete",
    "completed": "complete",
    "finished": "complete",
    "skipped": "skipped",
    "skip": "skipped",
    "skipping": "skipped",
    "incomplete": "incomplete",
    "didnt": "incomplete",  # canonicalized "didn't"
    "didnot": "incomplete",  # canonicalized "did not"
    "notdone": "incomplete",  # canonicalized "not done"
}

#: Strong clause-break connectives. Any of these reset the state machine.
_STRONG_BREAK_RE = re.compile(r"\b(and|but|then)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Dataclasses (per contracts/api.md Entity 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParseTuple:
    """A canonical (task_id, state) pair produced by the parser.

    ``matched_via`` is one of: ``position``, ``exact_title``, ``substring``,
    or ``special_token`` (the "all done" / "nothing done" fast-path).
    ``position`` is set only for ``matched_via=position`` and ``special_token``
    (every special-token tuple includes its 1-indexed position for clarity).
    """

    task_id: int
    state: Literal["complete", "incomplete", "skipped"]
    matched_via: Literal["position", "exact_title", "substring", "special_token"]
    position: Optional[int] = None


@dataclass(frozen=True, slots=True)
class JudgmentItem:
    """An ambiguous reply token + its candidate set.

    The agent routes these to the narrow LLM disambiguator
    (``scripts/habits/judgment/disambiguate_reply.py``); the parser itself
    NEVER picks one silently (FR-004).
    """

    token: str
    candidate_task_ids: list[int]
    candidate_titles: list[str]
    inferred_state: Literal["complete", "incomplete", "skipped"]


@dataclass(frozen=True, slots=True)
class ParseError:
    """A structured per-token parse failure.

    ``no_morning_list`` is emitted only by the CLI wrapper when the persisted
    artifact is absent; the pure ``parse_reply`` API never raises it. The
    parser uses ``invalid_token`` for out-of-range positions and
    ``unparseable_reply`` for tokens that match no habit at any tier.
    """

    type: Literal["no_morning_list", "invalid_token", "unparseable_reply"]
    detail: str


@dataclass(frozen=True, slots=True)
class ParseResult:
    """The parser's output. Emitted verbatim (as JSON) by the CLI.

    ``correlated_checkin_date_et`` (mission #408 / WP-02) records which
    check-in artifact the parser correlated the reply to. For replies
    that correlate to today's morning list (the default and most common
    case), this matches ``--date`` (or today's ET date). For 48hr-window
    late replies (Kent answering Wednesday's check-in on Thursday morning),
    this is the OLDER date — the consumer uses it when appending events
    to habits-history so the correct check-in's habits are resolved.

    Defaults to the empty string when correlation is bypassed (CLI's
    legacy ``--date`` mode or the no-morning-list error path), preserving
    backwards compatibility with all pre-#408 callers (NFR-003).
    """

    schema_version: int
    reply_text: str
    morning_list_path: str
    tuples: list[ParseTuple]
    judgment_required: list[JudgmentItem]
    errors: list[ParseError]
    correlated_checkin_date_et: str = ""


# ---------------------------------------------------------------------------
# Internal helpers (clock + token classification; small, pure)
# ---------------------------------------------------------------------------


def _today_local() -> str:
    """Return today's date in America/New_York as ``YYYY-MM-DD``.

    Wrapped so tests can monkeypatch this single name without patching the
    ``datetime`` module globally. Mirrors the helper in WP01's
    ``morning_checkin_list``.
    """
    return datetime.now(LOCAL_TZ).date().isoformat()


def _canonicalize_multiword_verbs(text: str) -> str:
    """Collapse multi-word verbs into single tokens so word-by-word tokenization works.

    ``"didn't"`` -> ``"didnt"`` (strip the apostrophe so the apostrophe-handling
    isn't load-bearing). ``"did not"`` -> ``"didnot"``. ``"not done"`` ->
    ``"notdone"``. The single-token form is what ``_VERB_WORDS`` lists.

    Note: ``"not done"`` is only collapsed when those two words are adjacent
    (whitespace-separated); a sentence like ``"3 not, 5 done"`` is left alone
    so the comma boundary remains visible to the tokenizer.
    """
    # didn't -> didnt (drop the apostrophe)
    text = re.sub(r"\bdidn'?t\b", "didnt", text, flags=re.IGNORECASE)
    # did not -> didnot
    text = re.sub(r"\bdid\s+not\b", "didnot", text, flags=re.IGNORECASE)
    # not done -> notdone (only adjacent words)
    text = re.sub(r"\bnot\s+done\b", "notdone", text, flags=re.IGNORECASE)
    return text


def _tokenize(reply_text: str) -> list[tuple[str, str]]:
    """Decompose the reply into a flat sequence of (kind, value) atoms.

    ``kind`` is one of ``"VERB"``, ``"ID"``, ``"COMMA"``, ``"BREAK"``.
    ``value`` is the verb's target state (for VERB), the identifier text
    (for ID), or the raw connective (for COMMA / BREAK -- the value is
    informational; the state machine only branches on ``kind``).

    The tokenizer is *not* responsible for clause assembly; it produces a
    linear stream the state machine in ``parse_reply`` walks. Punctuation
    other than commas / semicolons is stripped from identifier candidates
    so ``"3,"`` and ``"3"`` both produce ``("ID", "3")``.

    Determinism: same input string -> same token stream. No locale-dependent
    splitting (we use simple regex-based scanning, not ``str.split``'s
    default whitespace rules which can vary across locales for unusual
    whitespace characters; the typical ASCII reply is unaffected).
    """
    text = _canonicalize_multiword_verbs(reply_text)

    tokens: list[tuple[str, str]] = []
    # Split on whitespace but keep punctuation attached to its word so we
    # can detect commas as separate atoms.  We tokenize by scanning for
    # one of: word ([A-Za-z0-9]+ optionally with internal apostrophes), or
    # a single punctuation character ([,;]).
    pattern = re.compile(r"[A-Za-z0-9_]+|[,;]")
    for match in pattern.finditer(text):
        atom = match.group(0)
        if atom in (",", ";"):
            tokens.append(("COMMA", atom))
            continue
        lower = atom.lower()
        if lower in _VERB_WORDS:
            tokens.append(("VERB", _VERB_WORDS[lower]))
            continue
        if _STRONG_BREAK_RE.fullmatch(atom):
            tokens.append(("BREAK", lower))
            continue
        # Otherwise: an identifier candidate (digit or word).
        tokens.append(("ID", atom))
    return tokens


def _identifier_is_position(token: str) -> bool:
    """Return True if ``token`` is a non-negative integer string (e.g., ``"3"``)."""
    return token.isdigit()


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace, for fuzzy comparisons."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _loose_normalize(text: str) -> str:
    """Lowercase, replace non-alphanumeric runs with single space, collapse + trim.

    Used by the whole-phrase matcher so that punctuation in habit titles
    (colons, em-dashes, parentheses) doesn't block matches.  Example:
    ``"Wake at 5:00 AM"`` -> ``"wake at 5 00 am"`` and
    ``"Strength training — Friday"`` -> ``"strength training friday"``.

    The token side is reconstructed from the tokenizer's atoms (which have
    already stripped punctuation), so loose-normalization needs to apply
    the SAME transformation to titles for a fair comparison.
    """
    # Replace any run of non-alphanumeric (incl. unicode dashes) with single space.
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _substring_match(
    token: str, habits: list[MorningListHabit]
) -> list[MorningListHabit]:
    """Return all habits where token is a substring of title OR vice versa.

    Bidirectional matching is intentional: Kent's typical shorthand is
    "wake done" against ``"Wake at 5:00 AM"`` (token-in-title) or "morning
    PT done" against ``"Morning shoulder PT"`` (token-in-title). The
    title-in-token direction handles the rarer case where Kent types a
    longer form than the title.

    Bare empty / 1-char tokens are rejected to prevent runaway matches
    (every habit's title contains "a", "e", "t", etc.). Callers should
    pre-filter; this helper is defensive.
    """
    t = _normalize(token)
    if len(t) < 2:
        return []
    matches: list[MorningListHabit] = []
    for habit in habits:
        title_norm = _normalize(habit.title)
        if t in title_norm or title_norm in t:
            matches.append(habit)
    return matches


def _exact_title_match(
    token: str, habits: list[MorningListHabit]
) -> Optional[MorningListHabit]:
    """Return the single habit whose normalized title equals the normalized token, else None."""
    t = _normalize(token)
    for habit in habits:
        if _normalize(habit.title) == t:
            return habit
    return None


def _loose_exact_title_match(
    phrase: str, habits: list[MorningListHabit]
) -> Optional[MorningListHabit]:
    """Loose-normalized exact-title match for whole-phrase resolution.

    Used by ``_resolve_phrase``: ``"Wake at 5 00 AM"`` (reconstructed from
    tokens) must match the habit titled ``"Wake at 5:00 AM"`` even though
    the colon was stripped by the tokenizer.
    """
    target = _loose_normalize(phrase)
    if not target:
        return None
    for habit in habits:
        if _loose_normalize(habit.title) == target:
            return habit
    return None


def _loose_substring_match(
    phrase: str, habits: list[MorningListHabit]
) -> list[MorningListHabit]:
    """Loose-normalized bidirectional substring match for whole-phrase resolution.

    Tokens-in-title direction: ``"morning shoulder pt"`` (from "morning
    shoulder PT") matches title ``"Morning shoulder PT"`` even if exact
    normalization disagrees on spacing.

    Title-in-tokens direction: ``"morning"`` is contained by title
    ``"Morning shoulder PT"`` (so a bare "morning" matches it). This is
    intentionally symmetric.

    Phrases of < 2 chars are rejected to prevent runaway matches.
    """
    p = _loose_normalize(phrase)
    if len(p) < 2:
        return []
    matches: list[MorningListHabit] = []
    for habit in habits:
        title_norm = _loose_normalize(habit.title)
        if not title_norm:
            continue
        if p in title_norm or title_norm in p:
            matches.append(habit)
    return matches


#: Minimum shared-prefix length for the prefix-overlap matcher (avoids
#: false positives on short coincidences like "med"/"meditate").
_PREFIX_OVERLAP_MIN_LEN = 5

#: Minimum prefix-overlap ratio relative to the shorter string. 0.6 means
#: the common prefix must be at least 60% of min(len(phrase), len(title)).
_PREFIX_OVERLAP_MIN_RATIO = 0.6


def _shared_prefix_len(a: str, b: str) -> int:
    """Length of the longest common prefix of two strings."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _loose_prefix_overlap_match(
    phrase: str, habits: list[MorningListHabit]
) -> list[MorningListHabit]:
    """Match habits whose loose-normalized title shares a substantial prefix with phrase.

    Why this exists: ``"meditation"`` and ``"Meditate"`` share the prefix
    ``"medita"`` (6 chars) but neither contains the other as a substring,
    so the substring matcher misses this case. Kent's natural
    morphological variation (``"meditate"`` / ``"meditation"`` /
    ``"meditating"``) needs prefix-overlap to resolve cleanly.

    Floor: shared prefix must be at least 5 chars AND at least 60% of the
    shorter string's length. Prevents false positives like "med" matching
    "meditate" or "wake" matching "walk".
    """
    p = _loose_normalize(phrase)
    if len(p) < _PREFIX_OVERLAP_MIN_LEN:
        return []
    matches: list[MorningListHabit] = []
    for habit in habits:
        title_norm = _loose_normalize(habit.title)
        if len(title_norm) < _PREFIX_OVERLAP_MIN_LEN:
            continue
        shared = _shared_prefix_len(p, title_norm)
        if shared < _PREFIX_OVERLAP_MIN_LEN:
            continue
        shorter = min(len(p), len(title_norm))
        if shared / shorter < _PREFIX_OVERLAP_MIN_RATIO:
            continue
        matches.append(habit)
    return matches


# ---------------------------------------------------------------------------
# Mission #408 / WP-02 — 48hr window correlation helpers
#
# OD-4 finding (T007 research): the existing parser correlates a reply only
# to TODAY's morning-checkin artifact (via ``load_morning_list(date=date)``
# where date defaults to today in ET). The inbound CLI surface accepts the
# reply as plain text only — there is NO WhatsApp quote-reply metadata
# available at this layer. If quote-reply metadata is ever forwarded by
# the inbound channel, it would arrive as additional CLI flags or as
# structured fields in a future ``--reply-file`` JSON shape; this WP does
# not plumb that path, leaving it as a future extension hook.
#
# What this WP adds: 48hr-window correlation. The parser now scans
# morning-checkin-*.json artifacts whose ``delivered_at_utc`` (or
# ``generated_at`` fallback) is within the last 48hr, and chooses among
# them using the priority chain from contracts/reply-correlation.contract.md:
#
#   1. Explicit date hint in the reply text ("yesterday", "Tue", "2026-05-31").
#   2. Most-recent-unresolved: the most recent check-in whose unresolved
#      habits the reply tokens map to.
#   3. Default to today's check-in (current behavior — zero regression).
#
# Quote-reply metadata (priority 1 in the contract) is documented but not
# implemented because the CLI doesn't receive it. If a future mission adds
# it, the hook point is ``correlate_reply_to_checkin``'s ``quote_reply_id``
# kwarg (reserved-but-unused below).
#
# Zero-regression promise: callers that don't pass ``state_dir`` /
# ``now_utc`` exercise the original today-only path and the new
# ``correlated_checkin_date_et`` field equals the date used to load the
# morning list (preserves NFR-003).
# ---------------------------------------------------------------------------

#: ISO weekday short names in Mon=0..Sun=6 order. Mirrors WP-01's
#: ``schedule_loader.WEEKDAY_NAMES`` (kept local so this module's only
#: cross-module dependency stays ``morning_checkin_list``).
_WEEKDAY_SHORT: tuple[str, ...] = (
    "mon", "tue", "wed", "thu", "fri", "sat", "sun"
)

#: Explicit date-hint regex for ISO-8601 ``YYYY-MM-DD`` substrings.
_DATE_HINT_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

#: Filename pattern for ``morning-checkin-YYYY-MM-DD.json`` discovery.
_CHECKIN_FILENAME_RE = re.compile(
    r"^morning-checkin-(\d{4}-\d{2}-\d{2})\.json$"
)

#: 48hr correlation window (seconds).
_CORRELATION_WINDOW_SECONDS = 48 * 60 * 60


@dataclass(frozen=True, slots=True)
class CheckinCandidate:
    """A morning-checkin artifact in the 48hr correlation window.

    Sorted by ``delivered_at_utc`` DESC (most-recent first) when returned
    by :func:`find_checkin_within_48hr_window`.
    """

    path: Path
    checkin_date_et: str  # YYYY-MM-DD
    delivered_at_utc: str  # ISO-8601 source text


def _parse_correlation_timestamp(value: str) -> datetime:
    """Parse a delivered_at_utc value (accepts ``Z`` or ``+00:00`` style).

    Returns a tz-aware UTC datetime. Raises ``ValueError`` on malformed
    input — the caller filters those out.
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    return parsed.astimezone(zoneinfo.ZoneInfo("UTC"))


def find_checkin_within_48hr_window(
    state_dir: Path,
    now_utc: datetime,
) -> list[CheckinCandidate]:
    """Return morning-checkin artifacts delivered within the last 48hr.

    Sorted by ``delivered_at_utc`` DESC so callers can apply the
    most-recent-unresolved tiebreak by walking the list left-to-right.

    Tolerant to:
      * missing state_dir (returns ``[]``)
      * malformed artifacts (skipped silently)
      * artifacts missing ``delivered_at_utc`` (falls back to
        ``generated_at`` for mission-#371-era artifacts)
    """
    if not state_dir.exists():
        return []
    cutoff = now_utc - timedelta(seconds=_CORRELATION_WINDOW_SECONDS)
    candidates: list[CheckinCandidate] = []
    for entry in sorted(state_dir.iterdir()):
        if not entry.is_file():
            continue
        match = _CHECKIN_FILENAME_RE.match(entry.name)
        if not match:
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        delivered_raw = data.get("delivered_at_utc")
        if not isinstance(delivered_raw, str):
            delivered_raw = data.get("generated_at")
        if not isinstance(delivered_raw, str):
            continue
        try:
            delivered = _parse_correlation_timestamp(delivered_raw)
        except ValueError:
            continue
        if delivered < cutoff:
            continue
        candidates.append(
            CheckinCandidate(
                path=entry,
                checkin_date_et=match.group(1),
                delivered_at_utc=delivered_raw,
            )
        )
    candidates.sort(key=lambda c: c.delivered_at_utc, reverse=True)
    return candidates


def _explicit_date_hint(reply_text: str, candidates: list[CheckinCandidate]) -> str | None:
    """Return the candidate checkin_date matching an explicit hint, else None.

    Priority order within hints:
      1. ISO date substring (``2026-05-31``) — unambiguous.
      2. ``"yesterday"`` — maps to most-recent candidate whose date is
         exactly today-1 in ET (per the candidate set's dates).
      3. Three-letter ISO weekday name in reply (case-insensitive) —
         maps to the most-recent candidate whose ET date falls on that
         weekday. Bare-word boundary required to avoid false matches
         inside habit titles ("Wed" inside "Wednesday strength" would
         match but that's the operator's prerogative — bare weekday
         names rarely appear inside habit nouns).
    """
    if not candidates:
        return None
    text_lower = reply_text.lower()

    # 1. ISO date substring.
    iso_match = _DATE_HINT_ISO_RE.search(reply_text)
    if iso_match is not None:
        iso_date = iso_match.group(1)
        for cand in candidates:
            if cand.checkin_date_et == iso_date:
                return cand.checkin_date_et

    # 2. "yesterday" / "today" hints.
    candidate_dates = [
        datetime.fromisoformat(c.checkin_date_et).date() for c in candidates
    ]
    # Derive "today" from the most-recent candidate's date (avoids needing
    # a clock injection point — candidates are already filtered to the
    # 48hr window so the most-recent is "the current end of the window").
    today_date = max(candidate_dates) if candidate_dates else None
    if today_date is not None:
        if re.search(r"\byesterday\b", text_lower):
            target = today_date - timedelta(days=1)
            for cand in candidates:
                if datetime.fromisoformat(cand.checkin_date_et).date() == target:
                    return cand.checkin_date_et
        if re.search(r"\btoday\b", text_lower):
            for cand in candidates:
                if datetime.fromisoformat(cand.checkin_date_et).date() == today_date:
                    return cand.checkin_date_et

    # 3. Three-letter ISO weekday.
    for weekday_idx, weekday_name in enumerate(_WEEKDAY_SHORT):
        if not re.search(rf"\b{weekday_name}\b", text_lower):
            continue
        for cand in candidates:
            cand_date = datetime.fromisoformat(cand.checkin_date_et).date()
            if cand_date.weekday() == weekday_idx:
                return cand.checkin_date_et
    return None


def _load_candidate_morning_list(cand: CheckinCandidate) -> Optional["MorningList"]:
    """Load and return the MorningList for a candidate (or None on error)."""
    try:
        return load_morning_list(
            date=cand.checkin_date_et,
            state_dir=cand.path.parent,
        )
    except (FileNotFoundError, ValueError):
        return None


def _reply_has_unresolved_match(
    reply_text: str,
    morning_list: "MorningList",
    history: list[dict],
) -> bool:
    """Return True iff parsing reply against this list resolves to at least one
    habit currently unresolved (no ``complete`` / ``skipped`` / ``auto_skipped``
    record on that checkin date).

    Used by the most-recent-unresolved tiebreak. We re-use the parser
    pipeline at zero risk: build a ParseResult against the candidate's
    morning list, then check if any produced tuple targets a habit that
    has no resolution record yet on the candidate's date.
    """
    result = parse_reply(
        reply_text=reply_text,
        morning_list=morning_list,
        morning_list_path="",
    )
    if not result.tuples:
        return False
    checkin_date = morning_list.date
    for tup in result.tuples:
        if _habit_unresolved_on_date(history, tup.task_id, checkin_date):
            return True
    return False


def _habit_unresolved_on_date(
    history: list[dict], task_id: int, date_et: str
) -> bool:
    """True iff no resolution record exists for ``(task_id, date_et)``."""
    for rec in history:
        # State-log style record (complete / skipped / incomplete).
        if (
            rec.get("domain") == "habits"
            and rec.get("task_id") == task_id
            and rec.get("date") == date_et
            and rec.get("state") in ("complete", "skipped", "incomplete")
        ):
            return False
        # Mission #408 auto_skipped event.
        if (
            rec.get("event_type") == "auto_skipped"
            and rec.get("task_id") == task_id
            and rec.get("original_checkin_date_et") == date_et
        ):
            return False
    return True


def _read_history(history_path: Path) -> list[dict]:
    """Read ``habits-history.jsonl`` records; tolerate missing/malformed."""
    if not history_path.exists():
        return []
    records: list[dict] = []
    try:
        with history_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    except OSError:
        return []
    return records


def correlate_reply_to_checkin(
    *,
    reply_text: str,
    candidates: list[CheckinCandidate],
    default_date_et: str,
    history_path: Path | None = None,
    quote_reply_id: str | None = None,  # reserved for future channel-layer extension
) -> str:
    """Pick the check-in date the reply should be attributed to.

    Implements the priority chain from
    ``contracts/reply-correlation.contract.md``:

      1. Quote-reply metadata (reserved — not yet plumbed; no-op here).
      2. Explicit date hint in the reply text.
      3. Most-recent-unresolved scan across the 48hr window.
      4. Default to ``default_date_et`` (today).

    Args:
        reply_text: Kent's WhatsApp reply text.
        candidates: 48hr-window candidates sorted most-recent-first.
        default_date_et: Fallback date (typically today in ET).
        history_path: Path to habits-history.jsonl for the unresolved
            tiebreak. None disables that tier and falls straight to
            default.
        quote_reply_id: Reserved-but-unused hook for a future channel-
            layer extension. Currently always None.

    Returns:
        The ET date string (``YYYY-MM-DD``) the reply correlates to.
    """
    # Tier 1: quote-reply (not yet plumbed at this layer).
    if quote_reply_id is not None:  # pragma: no cover -- reserved hook
        # If a future extension delivers a quote-reply identifier that maps
        # to a stored check-in delivery, this would look it up here.
        pass

    # Tier 2: explicit date hint.
    hinted = _explicit_date_hint(reply_text, candidates)
    if hinted is not None:
        return hinted

    # Tier 3: most-recent-unresolved across the 48hr window.
    if candidates and history_path is not None:
        history = _read_history(history_path)
        for cand in candidates:
            morning_list = _load_candidate_morning_list(cand)
            if morning_list is None:
                continue
            if _reply_has_unresolved_match(reply_text, morning_list, history):
                return cand.checkin_date_et

    # Tier 4: default to today's date.
    return default_date_et


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_reply(
    *,
    reply_text: str,
    morning_list: MorningList,
    morning_list_path: str = "",
) -> ParseResult:
    """Parse Kent's reply into canonical state-change tuples.

    The parser is pure: same ``reply_text`` + same ``morning_list`` produces
    byte-identical output. No clock, no network, no random source.

    Algorithm:

      1. Special-token pre-scan. If the reply matches one of the "all
         done" / "nothing done" family patterns, emit a tuple per position
         in ``morning_list.habits`` with the matching state and return.

      2. Tokenize the reply into a flat (kind, value) atom stream.

      3. Walk the atoms with a small state machine that pairs identifiers
         with the verbs claiming them (verb-before, verb-after, or rest-
         claim). The state machine produces a list of (state, [tokens])
         claim groups.

      4. For each (state, [tokens]) group, resolve each token via the
         three-tier match (position -> exact_title -> substring). Emit
         ``ParseTuple`` for unique matches, ``JudgmentItem`` for ambiguous
         substrings, ``ParseError`` for everything else.

      5. If a "rest-claim" verb was seen (a verb with zero adjacent
         identifiers), apply its state to every position not yet claimed.

    Args:
        reply_text: Kent's free-text reply (e.g., ``"Skipped 3,7,8 done"``).
        morning_list: The persisted ordered habit list for the relevant date.
        morning_list_path: Echo path included in the result (for the CLI
            JSON output / audit trail). Empty when called from Python.

    Returns:
        A frozen ``ParseResult`` with ``tuples``, ``judgment_required``, and
        ``errors`` populated.
    """
    # 1. Special-token pre-scan ----------------------------------------------
    if _SPECIAL_ALL_DONE.search(reply_text):
        return _build_all_positions_result(
            reply_text=reply_text,
            morning_list=morning_list,
            state="complete",
            morning_list_path=morning_list_path,
        )
    if _SPECIAL_ALL_SKIPPED.search(reply_text):
        # "nothing done" / "skipping everything" => every position is INCOMPLETE
        # in the policy sense (Kent didn't do them) but per the spec we map
        # the skip-family pre-scan to ``skipped`` (the user EXPLICITLY chose
        # to skip them).  However the implementation prompt's example test
        # says "nothing done" -> incomplete -- because "nothing done" means
        # "I did nothing, none are complete" which is closer to incomplete
        # than to actively-skipped.  We follow the test: skip-family maps to
        # ``incomplete`` for the "nothing done" / "none done" sub-family and
        # ``skipped`` for the "skipping everything" / "skipped all" sub-family.
        match_text = _SPECIAL_ALL_SKIPPED.search(reply_text).group(1).lower()
        if match_text in ("nothing done", "none done"):
            state: Literal["complete", "incomplete", "skipped"] = "incomplete"
        else:
            state = "skipped"
        return _build_all_positions_result(
            reply_text=reply_text,
            morning_list=morning_list,
            state=state,
            morning_list_path=morning_list_path,
        )

    # 2. Tokenize ------------------------------------------------------------
    atoms = _tokenize(reply_text)

    # 3. Build claims by walking atoms with two-pattern matching ------------
    # The reply is a sequence of clauses joined by COMMAs / BREAKs. Each
    # clause matches one of three shapes:
    #
    #   (a) verb-first  : VERB ID (, ID)* -- e.g. "skipped 3, 7, 8"
    #   (b) verb-last   : ID (, ID)* VERB -- e.g. "1 done", "1, 3, 5 done"
    #   (c) verb-only   : VERB             -- e.g. "done" (rest-claim)
    #
    # The tricky case is intra-list COMMA vs clause-break COMMA. We use the
    # token AFTER the comma as the discriminator:
    #
    #   - COMMA followed by a digit (or another COMMA) -> intra-list:
    #     Kent typing "3,7,8" or "1, 3, 5" is one comma-separated number
    #     list, regardless of whitespace after the comma.
    #
    #   - COMMA followed by a non-digit word -> clause break:
    #     Kent typing "skipped 3, meditation done" uses the comma to
    #     separate two distinct clauses; "meditation" is a fresh identifier
    #     for the NEXT clause, not an extension of the prior list.
    #
    # This rule survives the SC-002 reply ("Skipped 3,7,8 done" -> 3,7,8
    # all bind to "Skipped"; trailing "done" is rest-claim) AND the
    # mixed-clause case ("1 done, skipped 3, meditation done" -> three
    # distinct claims).
    claims: list[tuple[str, list[str]]] = []

    def _collect_ids_after_verb(start: int) -> tuple[list[str], int]:
        """Collect ID(,ID)* starting at atoms[start], applying the intra-list rule.

        Stops at VERB, BREAK, or COMMA-followed-by-non-digit-word. Returns
        (ids, next_index).
        """
        ids: list[str] = []
        j = start
        while j < len(atoms):
            kind, value = atoms[j]
            if kind == "ID":
                ids.append(value)
                j += 1
                continue
            if kind == "COMMA":
                if j + 1 < len(atoms):
                    ahead_kind, ahead_value = atoms[j + 1]
                    if ahead_kind == "ID" and not _identifier_is_position(
                        ahead_value
                    ):
                        # COMMA-WORD pattern -> clause break, stop here.
                        break
                j += 1
                continue
            # VERB / BREAK / end -> stop.
            break
        return ids, j

    i = 0
    while i < len(atoms):
        kind, value = atoms[i]
        if kind in ("COMMA", "BREAK"):
            i += 1
            continue
        if kind == "VERB":
            # Verb-first or verb-only.
            ids, next_i = _collect_ids_after_verb(i + 1)
            claims.append((value, ids))
            i = next_i
            continue
        if kind == "ID":
            # Verb-last pattern: scan forward through ID(,ID)* looking for VERB.
            ids = [value]
            j = i + 1
            while j < len(atoms):
                next_kind, next_value = atoms[j]
                if next_kind == "ID":
                    ids.append(next_value)
                    j += 1
                    continue
                if next_kind == "COMMA":
                    if j + 1 < len(atoms):
                        ahead_kind, ahead_value = atoms[j + 1]
                        if ahead_kind == "ID" and not _identifier_is_position(
                            ahead_value
                        ):
                            # COMMA-WORD -> clause break before reaching a verb.
                            break
                    j += 1
                    continue
                break
            if j < len(atoms) and atoms[j][0] == "VERB":
                claims.append((atoms[j][1], ids))
                i = j + 1
            else:
                # IDs with no following verb -> structured errors.
                claims.append(("__unclaimed__", ids))
                i = j
            continue
        # Defensive: skip anything else (shouldn't happen given tokenizer).
        i += 1  # pragma: no cover

    # 4. Resolve each claim's tokens against the morning list ---------------
    tuples: list[ParseTuple] = []
    judgment_required: list[JudgmentItem] = []
    errors: list[ParseError] = []
    claimed_positions: set[int] = set()
    rest_claim_state: Optional[str] = None

    for state, ids in claims:
        if state == "__unclaimed__":
            # Pending ids with no verb -> parse failure for each.
            for token in ids:
                errors.append(
                    ParseError(
                        type="unparseable_reply",
                        detail=(
                            f"token {token!r} had no associated verb "
                            f"(no 'done'/'skipped'/'incomplete' in clause)"
                        ),
                    )
                )
            continue

        if not ids:
            # Verb with no identifiers -> rest-claim candidate. Only the
            # FIRST rest-claim wins; subsequent ones surface as errors so
            # the agent can clarify with Kent.
            if rest_claim_state is None:
                rest_claim_state = state
            else:
                errors.append(
                    ParseError(
                        type="unparseable_reply",
                        detail=(
                            f"multiple verbs without identifiers "
                            f"(prior rest={rest_claim_state!r}, also {state!r}); "
                            f"cannot determine which applies to remaining positions"
                        ),
                    )
                )
            continue

        # Verb with identifiers: try whole-phrase match first (multi-word
        # title support), falling back to per-token only when the phrase
        # is pure numbers or whole-phrase resolution yields no candidates.
        _resolve_phrase(
            ids=ids,
            state=state,  # type: ignore[arg-type]
            morning_list=morning_list,
            tuples=tuples,
            judgment_required=judgment_required,
            errors=errors,
            claimed_positions=claimed_positions,
        )

    # 5. Apply rest-claim (if any) to all unclaimed positions ---------------
    if rest_claim_state is not None:
        for habit in morning_list.habits:
            if habit.position in claimed_positions:
                continue
            tuples.append(
                ParseTuple(
                    task_id=habit.vikunja_task_id,
                    state=rest_claim_state,  # type: ignore[arg-type]
                    matched_via="position",
                    position=habit.position,
                )
            )
            claimed_positions.add(habit.position)

    # Sort tuples by position for deterministic byte-output. Tuples lacking
    # a position (substring / exact_title matches) sort by task_id as a
    # tiebreaker -- still deterministic.
    tuples.sort(
        key=lambda t: (
            t.position if t.position is not None else 10**9,
            t.task_id,
        )
    )

    return ParseResult(
        schema_version=SCHEMA_VERSION,
        reply_text=reply_text,
        morning_list_path=morning_list_path,
        tuples=tuples,
        judgment_required=judgment_required,
        errors=errors,
    )


def _build_all_positions_result(
    *,
    reply_text: str,
    morning_list: MorningList,
    state: Literal["complete", "incomplete", "skipped"],
    morning_list_path: str,
) -> ParseResult:
    """Helper for the special-token fast path: emit one tuple per position."""
    tuples = [
        ParseTuple(
            task_id=habit.vikunja_task_id,
            state=state,
            matched_via="special_token",
            position=habit.position,
        )
        for habit in morning_list.habits
    ]
    return ParseResult(
        schema_version=SCHEMA_VERSION,
        reply_text=reply_text,
        morning_list_path=morning_list_path,
        tuples=tuples,
        judgment_required=[],
        errors=[],
    )


def _resolve_phrase(
    *,
    ids: list[str],
    state: Literal["complete", "incomplete", "skipped"],
    morning_list: MorningList,
    tuples: list[ParseTuple],
    judgment_required: list[JudgmentItem],
    errors: list[ParseError],
    claimed_positions: set[int],
) -> None:
    """Resolve a verb's identifier list, preferring whole-phrase title matches.

    Rationale (codex review feedback, WP02 cycle 1): the prior implementation
    tokenized identifiers word-by-word and resolved each independently, which
    broke multi-word titles like ``"Morning shoulder PT"`` (each word would
    match the wrong habit, or surface as ambiguous). The fix: for each
    verb's identifier list, try matching the full reconstructed phrase
    against habit titles first; only fall back to per-token resolution when
    the phrase is pure positions ("3,7,8") or contains digits the
    whole-phrase match couldn't bind.

    Decision tree:

      1. If every token in ``ids`` is a digit -> per-token position
         resolution (preserves SC-002 "3,7,8" semantics).

      2. Otherwise build phrase = " ".join(ids) and try:

           a. Loose-normalized exact title match -> single tuple
              (matched_via=exact_title).

           b. Loose-normalized bidirectional substring match:
              - exactly one candidate -> single tuple (matched_via=substring).
              - multiple candidates -> one JudgmentItem
                (preserves SC-003 ambiguity routing for "PT done").

      3. If whole-phrase resolution yields nothing AND the phrase contains
         at least one digit token -> fall back to per-token (mixed-content
         numeric extraction).

      4. If whole-phrase resolution yields nothing AND the phrase has no
         digits -> emit a single unparseable_reply error for the whole
         phrase (not per-token).

    Mutates ``tuples`` / ``judgment_required`` / ``errors`` /
    ``claimed_positions`` in place.
    """
    if not ids:
        return  # defensive; caller already handled the empty-ids rest-claim case.

    # Decision (1): pure position list (every token is digits) -> per-token.
    if all(_identifier_is_position(t) for t in ids):
        for token in ids:
            _resolve_token(
                token=token,
                state=state,
                morning_list=morning_list,
                tuples=tuples,
                judgment_required=judgment_required,
                errors=errors,
                claimed_positions=claimed_positions,
            )
        return

    # Decision (2): try whole-phrase title resolution.
    phrase = " ".join(ids)

    # (2a) Loose-normalized exact title match.
    exact = _loose_exact_title_match(phrase, morning_list.habits)
    if exact is not None:
        tuples.append(
            ParseTuple(
                task_id=exact.vikunja_task_id,
                state=state,
                matched_via="exact_title",
                position=None,
            )
        )
        claimed_positions.add(exact.position)
        return

    # (2b) Loose-normalized bidirectional substring match.
    candidates = _loose_substring_match(phrase, morning_list.habits)
    if len(candidates) == 1:
        habit = candidates[0]
        tuples.append(
            ParseTuple(
                task_id=habit.vikunja_task_id,
                state=state,
                matched_via="substring",
                position=None,
            )
        )
        claimed_positions.add(habit.position)
        return
    if len(candidates) > 1:
        judgment_required.append(
            JudgmentItem(
                token=phrase,
                candidate_task_ids=[h.vikunja_task_id for h in candidates],
                candidate_titles=[h.title for h in candidates],
                inferred_state=state,
            )
        )
        return

    # (2c) Prefix-overlap fallback: catches morphological variants like
    # "meditation" -> "Meditate" that neither substring direction catches.
    prefix_candidates = _loose_prefix_overlap_match(phrase, morning_list.habits)
    if len(prefix_candidates) == 1:
        habit = prefix_candidates[0]
        tuples.append(
            ParseTuple(
                task_id=habit.vikunja_task_id,
                state=state,
                matched_via="substring",
                position=None,
            )
        )
        claimed_positions.add(habit.position)
        return
    if len(prefix_candidates) > 1:
        judgment_required.append(
            JudgmentItem(
                token=phrase,
                candidate_task_ids=[h.vikunja_task_id for h in prefix_candidates],
                candidate_titles=[h.title for h in prefix_candidates],
                inferred_state=state,
            )
        )
        return

    # Whole-phrase resolution failed. Pick the fallback.
    has_digit = any(_identifier_is_position(t) for t in ids)
    if has_digit:
        # Decision (3): mixed-content phrase with digits we couldn't whole-
        # phrase-bind -> per-token resolution.  Digit tokens still resolve
        # to positions; remaining word tokens go through the original
        # three-tier match.
        for token in ids:
            _resolve_token(
                token=token,
                state=state,
                morning_list=morning_list,
                tuples=tuples,
                judgment_required=judgment_required,
                errors=errors,
                claimed_positions=claimed_positions,
            )
        return

    # Decision (4): word-only phrase that matched nothing -> single error.
    errors.append(
        ParseError(
            type="unparseable_reply",
            detail=(
                f"phrase {phrase!r} did not match any habit by exact title "
                f"or substring (case-insensitive, punctuation-stripped)"
            ),
        )
    )


def _resolve_token(
    *,
    token: str,
    state: Literal["complete", "incomplete", "skipped"],
    morning_list: MorningList,
    tuples: list[ParseTuple],
    judgment_required: list[JudgmentItem],
    errors: list[ParseError],
    claimed_positions: set[int],
) -> None:
    """Resolve a single identifier token via the three-tier match.

    Mutates ``tuples`` / ``judgment_required`` / ``errors`` / ``claimed_positions``
    in place. Returns nothing -- pure side effects on the caller's containers.

    Tier order:
      1. Position (digit token).
      2. Exact title (case-insensitive whole-string match against any title).
      3. Substring (case-insensitive bidirectional: token-in-title OR title-in-token).
         - Single match -> ParseTuple. Multiple -> JudgmentItem. Zero -> ParseError.
    """
    # Tier 1: position --------------------------------------------------------
    if _identifier_is_position(token):
        pos = int(token)
        for habit in morning_list.habits:
            if habit.position == pos:
                tuples.append(
                    ParseTuple(
                        task_id=habit.vikunja_task_id,
                        state=state,
                        matched_via="position",
                        position=pos,
                    )
                )
                claimed_positions.add(pos)
                return
        # Position out of range -> structured error.
        errors.append(
            ParseError(
                type="invalid_token",
                detail=(
                    f"position {pos} not in morning list "
                    f"(have {len(morning_list.habits)} habits)"
                ),
            )
        )
        return

    # Tier 2: exact title -----------------------------------------------------
    exact = _exact_title_match(token, morning_list.habits)
    if exact is not None:
        tuples.append(
            ParseTuple(
                task_id=exact.vikunja_task_id,
                state=state,
                matched_via="exact_title",
                position=None,
            )
        )
        claimed_positions.add(exact.position)
        return

    # Tier 3: substring -------------------------------------------------------
    candidates = _substring_match(token, morning_list.habits)
    if len(candidates) == 1:
        habit = candidates[0]
        tuples.append(
            ParseTuple(
                task_id=habit.vikunja_task_id,
                state=state,
                matched_via="substring",
                position=None,
            )
        )
        claimed_positions.add(habit.position)
        return
    if len(candidates) > 1:
        judgment_required.append(
            JudgmentItem(
                token=token,
                candidate_task_ids=[h.vikunja_task_id for h in candidates],
                candidate_titles=[h.title for h in candidates],
                inferred_state=state,
            )
        )
        return
    # Zero candidates -> unparseable.
    errors.append(
        ParseError(
            type="unparseable_reply",
            detail=f"token {token!r} did not match any habit by position, exact title, or substring",
        )
    )


def load_morning_list(
    *,
    date: str,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> MorningList:
    """Read the persisted morning list JSON for ``date``.

    Path: ``state_dir / f"morning-checkin-{date}.json"``.

    Args:
        date: ISO-8601 ``YYYY-MM-DD`` (the day the morning list is for).
        state_dir: Directory containing the per-date artifacts.

    Returns:
        A frozen ``MorningList`` reconstructed from the JSON file.

    Raises:
        FileNotFoundError: no morning list at the expected path. Caller maps
            this to exit code 4.
        ValueError: JSON parse failure OR schema mismatch (missing fields,
            wrong types). Caller maps this to exit code 5.
    """
    path = Path(state_dir) / f"morning-checkin-{date}.json"
    if not path.exists():
        raise FileNotFoundError(f"morning-list artifact not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"morning-list JSON parse failure at {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"morning-list at {path}: top-level JSON value must be an object"
        )

    # Validate required fields. We're permissive about extra fields (forward
    # compatibility) but strict about the canonical shape.
    required_top = ("schema_version", "date", "habits")
    for key in required_top:
        if key not in data:
            raise ValueError(
                f"morning-list at {path}: missing required field {key!r}"
            )

    if not isinstance(data["habits"], list):
        raise ValueError(
            f"morning-list at {path}: 'habits' must be a JSON array "
            f"(got {type(data['habits']).__name__})"
        )

    habits: list[MorningListHabit] = []
    for index, raw_habit in enumerate(data["habits"]):
        if not isinstance(raw_habit, dict):
            raise ValueError(
                f"morning-list at {path}: habits[{index}] must be a JSON object"
            )
        for field_name in ("position", "vikunja_task_id", "title"):
            if field_name not in raw_habit:
                raise ValueError(
                    f"morning-list at {path}: habits[{index}] missing "
                    f"required field {field_name!r}"
                )
        try:
            habit = MorningListHabit(
                position=int(raw_habit["position"]),
                vikunja_task_id=int(raw_habit["vikunja_task_id"]),
                title=str(raw_habit["title"]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"morning-list at {path}: habits[{index}] field type error: {exc}"
            ) from exc
        habits.append(habit)

    return MorningList(
        schema_version=int(data["schema_version"]),
        date=str(data["date"]),
        generated_at=str(data.get("generated_at", "")),
        habits=habits,
    )


# ---------------------------------------------------------------------------
# Private helpers (serialization)
# ---------------------------------------------------------------------------


def _parse_result_to_dict(result: ParseResult) -> dict[str, Any]:
    """Convert a ``ParseResult`` to a JSON-serializable dict.

    ``dataclasses.asdict`` recurses into the nested dataclasses, so the
    output shape matches data-model Entity 2 verbatim.
    """
    return dataclasses.asdict(result)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` to let ``main()`` return exit 3.

    Mirrors the pattern from WP01's ``morning_checkin_list`` -- argparse's
    default ``error()`` calls ``sys.exit(2)``, which leaks through ``main()``
    and violates ``contracts/cli.md`` (exit 2 is reserved in WP01's contract;
    in WP02 there is no exit 2, so we just need a way to redirect to 3).
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that raises ``_ArgparseError`` instead of ``sys.exit(2)`` on bad flags.

    ``--help`` is unaffected: argparse's help path uses ``parser.exit()``,
    not ``error()``, so help still exits 0 as expected.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = _StructuredArgumentParser(
        prog="parse_morning_reply",
        description=(
            "Parse Kent's morning check-in reply against the persisted "
            "morning-list artifact for the relevant date. Emits a "
            "ParseResult JSON document on stdout containing (a) deterministic "
            "(task_id, state) tuples ready for record_completion, (b) "
            "judgment_required items requiring narrow LLM disambiguation, "
            "and (c) any structured parse errors. Exits 4 if no morning-list "
            "artifact exists for the date, and 5 if the artifact is corrupted."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--reply",
        default=None,
        help="Kent's reply text (e.g., 'Skipped 3,7,8 done').",
    )
    group.add_argument(
        "--reply-file",
        type=Path,
        default=None,
        help="Path to a file containing Kent's reply text (alternative to --reply).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help=(
            "Date of the morning list to load, YYYY-MM-DD "
            "(default: today in America/New_York)."
        ),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=(
            f"Directory containing the per-date morning-list artifacts "
            f"(default: {DEFAULT_STATE_DIR})."
        ),
    )
    parser.add_argument(
        "--no-correlate-48hr",
        action="store_true",
        help=(
            "Disable mission #408 / WP-02 48hr-window correlation. "
            "Forces today-only behavior (legacy mode). Default: correlation "
            "enabled, falling back gracefully to today's check-in when no "
            "older candidate matches."
        ),
    )
    parser.add_argument(
        "--history-path",
        type=Path,
        default=None,
        help=(
            "Path to habits-history.jsonl for the most-recent-unresolved "
            "tiebreak. Default: <--state-dir>/../habits-history.jsonl. "
            "Set to /dev/null to disable the unresolved tier explicitly."
        ),
    )
    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a single JSON line on stderr to keep error output structured."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Exit codes per ``contracts/cli.md``::

        0 -- parse succeeded (output ``tuples`` / ``judgment_required``)
        1 -- I/O error reading --reply-file
        3 -- validation / usage error (bad flags, bad --date format)
        4 -- no morning-list artifact for --date (FileNotFoundError)
        5 -- morning-list artifact is corrupted (JSON parse / schema mismatch)
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3

    # Validate --date.
    if args.date is not None:
        if not _DATE_RE.match(args.date):
            _emit_stderr_error(
                step="argparse",
                error=f"--date must match YYYY-MM-DD (got {args.date!r})",
            )
            return 3
        try:
            datetime.fromisoformat(args.date).date()
        except ValueError as exc:
            _emit_stderr_error(
                step="argparse",
                error=(
                    f"--date must be a real YYYY-MM-DD date "
                    f"(got {args.date!r}): {exc}"
                ),
            )
            return 3
        date = args.date
    else:
        date = _today_local()

    # Compute reply_text from --reply or --reply-file.
    if args.reply is not None:
        reply_text = args.reply
    else:
        try:
            reply_text = args.reply_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            _emit_stderr_error(step="reply_file_read", error=str(exc))
            return 1
        except OSError as exc:
            _emit_stderr_error(step="reply_file_read", error=str(exc))
            return 1

    # Mission #408 / WP-02: 48hr-window correlation. We scan recent
    # check-in artifacts and may swap ``date`` for a more appropriate
    # older date BEFORE loading the morning list. Default-on; opt-out
    # via --no-correlate-48hr. Errors during correlation (missing
    # state_dir, malformed artifacts) silently fall back to today's
    # date — zero regression for the common case.
    correlated_date = date
    if not args.no_correlate_48hr:
        try:
            candidates = find_checkin_within_48hr_window(
                Path(args.state_dir), datetime.now(zoneinfo.ZoneInfo("UTC"))
            )
        except OSError:  # pragma: no cover -- defensive
            candidates = []
        if candidates:
            # Default history path: sibling of state_dir's parent. Production
            # layout has state at /data/services/openclaw/state/habits and
            # history at /data/services/openclaw/state/habits-history.jsonl.
            history_path = args.history_path or (
                Path(args.state_dir).parent / "habits-history.jsonl"
            )
            correlated_date = correlate_reply_to_checkin(
                reply_text=reply_text,
                candidates=candidates,
                default_date_et=date,
                history_path=history_path,
            )

    # Load the morning list for the correlated date.
    morning_list_path = (
        Path(args.state_dir) / f"morning-checkin-{correlated_date}.json"
    )
    try:
        morning_list = load_morning_list(
            date=correlated_date, state_dir=args.state_dir
        )
    except FileNotFoundError as exc:
        _emit_stderr_error(step="load_morning_list", error=str(exc))
        # Still emit a partial ParseResult on stdout so the agent can echo
        # context (per contracts/cli.md: "Even on exit code 4 or 5, stdout
        # MAY emit a partial result with errors populated").
        partial = ParseResult(
            schema_version=SCHEMA_VERSION,
            reply_text=reply_text,
            morning_list_path=str(morning_list_path),
            tuples=[],
            judgment_required=[],
            errors=[
                ParseError(
                    type="no_morning_list",
                    detail=str(exc),
                )
            ],
        )
        sys.stdout.write(
            json.dumps(_parse_result_to_dict(partial), ensure_ascii=False, indent=2)
        )
        sys.stdout.write("\n")
        return 4
    except ValueError as exc:
        _emit_stderr_error(step="load_morning_list", error=str(exc))
        partial = ParseResult(
            schema_version=SCHEMA_VERSION,
            reply_text=reply_text,
            morning_list_path=str(morning_list_path),
            tuples=[],
            judgment_required=[],
            errors=[
                ParseError(
                    type="unparseable_reply",
                    detail=f"corrupt morning-list artifact: {exc}",
                )
            ],
        )
        sys.stdout.write(
            json.dumps(_parse_result_to_dict(partial), ensure_ascii=False, indent=2)
        )
        sys.stdout.write("\n")
        return 5

    # Parse the reply against the correlated morning list.
    result = parse_reply(
        reply_text=reply_text,
        morning_list=morning_list,
        morning_list_path=str(morning_list_path),
    )
    # Mission #408 / WP-02: stamp the correlated date so downstream consumers
    # (record_completion's date arg) know which check-in's habits to resolve.
    result = dataclasses.replace(
        result, correlated_checkin_date_et=correlated_date
    )

    # Emit the result as JSON on stdout.
    sys.stdout.write(
        json.dumps(_parse_result_to_dict(result), ensure_ascii=False, indent=2)
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
