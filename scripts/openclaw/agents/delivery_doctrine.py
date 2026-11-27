"""Canonical announce-delivery doctrine block + wording check (#1143).

Single source of truth for the delivery doctrine carried by every agent whose
cron runs with ``delivery.mode: "announce"`` (the cron posts the agent's final
reply to WhatsApp). Follows the :mod:`truthful_doctrine` pattern: one literal,
asserted byte-for-byte in each repo-source ``AGENTS.md`` by
``scripts/openclaw/agents/tests/test_delivery_doctrine.py``.

Why it exists: under OpenClaw 2026.11.7 Code Mode an agent sees only ``exec``
and ``wait``; other tools are reached through ``catalog.search()``. Capture's
prompt said "Send Kent ONE WhatsApp", so on a non-idle turn the model searched
for a send tool, called ``conversations_send`` (rejected: ``input_contract``),
invented ``send()`` and was stopped by the tool-loop detector, delivering
nothing. Delivery is the final reply, and only that.

:func:`delivery_violations` is the deterministic check (string membership and
regex only, no LLM). It proves the wording, not the model's behaviour.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

__all__ = [
    "DELIVERY_DOCTRINE_BLOCK",
    "ANNOUNCE_AGENTS",
    "FORBIDDEN_DELIVERY_PATTERNS",
    "delivery_violations",
]

# Must appear byte-for-byte, exactly once, in every ANNOUNCE_AGENTS AGENTS.md.
DELIVERY_DOCTRINE_BLOCK = (
    "## Delivery — your final reply (ABSOLUTE)\n"
    "\n"
    "- Your final reply is your ONLY delivery path: OpenClaw posts it to "
    "WhatsApp automatically. There is nothing to send.\n"
    "- Collect everything this turn must tell Kent (report, digest, alarms, "
    "errors, clarification asks) into ONE final reply, after all tool work.\n"
    "- **Never** search for or call `conversations_*`, `sessions_*`, "
    "`message` or any other send, notify or agent tool, and never invent "
    "`send()`, in exec code or via the CLI (`openclaw agent`, `gog`). You "
    "have none and need none.\n"
    "- Do not call `automations` or `record_result`, and ignore any runtime "
    "hint to \"record no_change\": a recorded no_change suppresses your final "
    "reply.\n"
    "- Never repeat an unchanged call that was rejected for invalid input or "
    "schema: fix the input from the error, or skip it and say so in your "
    "final reply. Recovery steps this prompt documents (re-running after `partial`, an `--idempotent` "
    "retry) still apply.\n"
)

# The agents whose crons deliver by announce (read-only check on office2 for
# #1143: inbox-* -> capture, escalation-daily -> escalation,
# habits-morning-checkin -> habits).
ANNOUNCE_AGENTS = (
    "felix-admin-capture",
    "felix-admin-escalation",
    "felix-admin-habits",
)

# Wording that tells the model to deliver by itself (send / ship / relay a
# payload, or call a send tool) rather than through its final reply. Checked
# outside the canonical block, which is the one place these names may appear.
#
# Imperatives are matched only where an instruction starts: line start (after
# any list marker, numbering, bold or table pipe), after a sentence break or
# em dash, after "then", or after "Next," and its kin. The verb must be followed
# by whitespace, so hyphenated forms ("Post-processing") never match.
# ``_BOLD_START`` marks where bold opened on a verb before the scan stripped it.
_BOLD_START = "\x02"
_IMPERATIVE_AT = (
    r"(?:^|[.!?:;—]\s+|\*\*|\x02|\|\s*|\bthen\s+"
    r"|\b(?:next|finally|afterwards?|also),\s+)"
    r"(?:\d+\.\s+|[-*]\s+)?(?:\*\*)?"
)
# What a deliver-verb must be followed by to count. The object starts with a
# determiner, pronoun, Kent/main or "to" (so nouns such as "Message field" or
# "Message identity" never match), and the phrase names a delivery channel:
# WhatsApp, or main as a relay target. "Tell Kent: ..." in a reply turn is the
# final reply's own content and has no channel, so it is not flagged; nor is
# "before the main loop".
_DESTINATION = (
    r"(?:(?:to\s+)?main\b"
    r"|(?:the|this|that|these|those|it|them|each|every|any|all|a|an|kent|to)\b"
    r"[^.|]{0,60}?(?:\b(?:to|via|on|through|over|with|in)\s+(?:the\s+)?whatsapp\b"
    r"|\b(?:to|with)\s+main\b))"
)
FORBIDDEN_DELIVERY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("send-whatsapp", re.compile(r"\bsend\s+(?:kent\s+)?(?:one|a|an|the)\s+whatsapp", re.I)),
    ("ship-message", re.compile(r"\bship\s+(?:the|this|a)\s+message", re.I)),
    ("whatsapp-skill", re.compile(r"\bvia\s+the\s+(?:existing\s+)?whatsapp\s+skill", re.I)),
    ("payload-to-main", re.compile(r"payload\s+to\s+main", re.I)),
    ("this-turns-message", re.compile(r"this\s+turn['’]s\s+message", re.I)),
    # Send/agent tool names: never named outside the block.
    ("tool-conversations", re.compile(r"\bconversations_(?:\w+|\*)")),
    ("tool-sessions", re.compile(r"\bsessions_(?:\w+|\*)")),
    ("tool-openclaw-agent", re.compile(r"\bopenclaw\s+agent\b")),
    (
        "tool-message",
        re.compile(r"\bmessage\s+tool\b|(?<![.\w])message\(|\bcall(?:ing)?\s+`?message`?(?:\s|$)", re.I),
    ),
    # Cron result recording (#1143 r3b): OpenClaw's injected hint says
    # "record no_change", and a recorded no_change suppresses the final reply.
    ("tool-record-result", re.compile(r"\brecord_result\b")),
    # The tool by call, method, name or catalog lookup; "the cron automations
    # list" is prose.
    (
        "tool-automations",
        re.compile(
            r"\bautomations\s*\(|\bautomations\.\w+\s*\(|(?i:\bautomations\s+tools?\b)"
            r"|\bcatalog\.search\s*\(\s*[\"']?automations\b"
        ),
    ),
    # Record / mark / set the outcome to no_change, within one sentence, table
    # cell or list item.
    (
        "record-no-change",
        re.compile(
            r"\b(?:record(?:s|ed|ing)?|mark(?:s|ed|ing)?"
            r"|set(?:s|ting)?\s+(?:[\w-]+\s+){0,2}?outcome\s+(?:to|as))\b"
            # A stray closing underscore may stay glued to no_change.
            r"[^.;|]{0,40}?\bno_change(?!_*[^\W_])",
            re.I,
        ),
    ),
    # Imperative "send" ("Sent by" and "Kent sends" do not match).
    ("imperative-send", re.compile(_IMPERATIVE_AT + r"(?P<verb>send)\s", re.I | re.M)),
    # Imperative notify/message/post/ship/forward/relay/tell aimed at a
    # channel ("Notify Kent via WhatsApp", "forward to main").
    (
        "imperative-deliver",
        re.compile(
            _IMPERATIVE_AT
            + r"(?P<verb>notify|message|post|ship|forward|relay|tell)\s+"
            + _DESTINATION,
            re.I | re.M,
        ),
    ),
)

# Imperative patterns are waived in a clause that routes the content into the
# final reply ("Relay the helper's stdout verbatim as your final reply").
_FINAL_REPLY_EXEMPT = frozenset({"imperative-send", "imperative-deliver"})

# Exemptions apply to one clause, never a whole line (#1146). A clause ends at a
# block boundary or table cell ("|"), semicolon, colon, em dash, sentence end, a
# comma before "and", "but" or "then", or a line end followed by a capitalised
# word (indented, quoted, bracketed or bold), which starts a new sentence. A line
# end before anything else is a soft wrap and does not end it.
_CLAUSE_BREAK = re.compile(
    r"[|;:—]|(?<=[.!?])\s|,\s+(?=(?:and|but|then)\b)"
    r"|(?-i:\n(?=[ \t]*[\"'“‘(\[\x02]*[A-Z]))",
    re.I,
)
# Exception words are looked for in the whole sentence, across soft wraps,
# semicolons and commas.
_SENTENCE_BREAK = re.compile(r"\||(?<=[.!?])(?<!e\.g\.)(?<!i\.e\.)\s", re.I)

# "Send the digest: it is your final reply" - the words after the colon route the
# lead-in into the final reply.
_ROUTED_AFTER_COLON = re.compile(
    r"\s*(?:(?:it|this|that|which)\s+(?:is|goes\s+(?:in|into|to|as))\s+"
    r"|(?:put|include|place|deliver)\s+(?:it|this|that|them)\s+(?:as|in|into)\s+"
    r"|as\s+)"
    r"(?:(?:your|the)\s+)?(?:one\s+)?final\s+reply\b",
    re.I,
)
_FINAL_REPLY = re.compile(r"final\s+reply", re.I)
# How far back from the verb a negator, "field" or "cron" is looked for.
_LOOK_BEHIND = 80
# "Do not record no_change", "never use the automations tool": the negator sits
# directly on the verb, a recording verb takes no_change as its direct object,
# and no exception word is in the sentence.
_NEGATION = r"\b(?:do\s+not|don['’]t|never|must\s+not|mustn['’]t)\s+(?:ever\s+)?"
_NEGATOR = re.compile(_NEGATION + "$", re.I)
_NEGATED_TOOL_USE = re.compile(_NEGATION + r"(?:use|call|invoke)\s+(?:the\s+)?$", re.I)
_DIRECT_NO_CHANGE = re.compile(
    r"\w+(?:\s+(?:the|its|a|an|any|this|that))?(?:\s+(?:cron|run|turn|result|outcome)){0,2}"
    r"(?:\s+(?:as|to))?\s+[\"']?no_change",
    re.I,
)
_EXCEPTION = re.compile(r"\b(?:unless|except|but|without|other\s+than)\b", re.I)
_EXCEPTION_OPENS = re.compile(r"\s*(?:unless|except)\b", re.I)
# A mention of a field or key named record_result, never the bare word.
_FIELD_AFTER = re.compile(r"[\"']?\s+(?:field|key)\b", re.I)
_FIELD_BEFORE = re.compile(r"\b(?:field|key)\s+(?:(?:named|called)\s+)?[\"']?$", re.I)
_QUOTED_KEY_AFTER = re.compile(r"[\"']\s*:")
# "the cron automations (inbox-7am, noon)": a plain parenthesised list.
_CRON_BEFORE = re.compile(r"\bcron\s+$", re.I)
_PROSE_LIST = re.compile(r"automations\s+\([^(){}\[\]=:\"'|]{1,80}\)")

# Formatting stripped from the scanned copy, in matched pairs only, within one
# block (a pair may span a soft wrap, never a "|" boundary). Underscore
# forms need a non-word character outside, so identifiers (no_change,
# record_result, conversations_send) survive. The "_*" of a tool-name glob
# (sessions_*) is held aside while stripping, as neither half is formatting.
_PAIRED_DELIMITERS = tuple(
    re.compile(p)
    for p in (
        r"`([^`|]{1,200})`",
        r"\*\*(?=\S)([^|]{1,200}?)(?<=\S)\*\*",
        r"(?<!\w)__(?=\S)([^|]{1,200}?)(?<=\S)__(?!\w)",
        r"(?<![\w*])\*(?=[^\s*])([^*|]{1,200}?)(?<=\S)\*(?![\w*])",
        r"(?<!\w)_(?=[^\s_])([^|]{1,200}?)(?<=[^\s_])_(?!\w)",
    )
)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
_GLOB = re.compile(r"(?<=[A-Za-z0-9])_\*")
_GLOB_HELD = "\x03"
# Lines that are their own block, so no sentence runs into or out of them.
_OWN_BLOCK = re.compile(r"^\s*(?:#{1,6}\s.*|```.*|~~~.*|(?:-\s*){3,}|(?:\*\s*){3,})$")
_QUOTE_MARKER = re.compile(r"^\s*(?:>\s*)+")
_BOLD_VERB = re.compile(r"(?=\*\*(?:send|notify|message|post|ship|forward|relay|tell)\b)", re.I)


def _mark_line(line: str, previous: str) -> str:
    """One line with its block boundaries written as ``|``.

    That is a blank line, the start of a list item or block quote, and both sides
    of a heading, rule or code fence (table rows already carry it). A line end
    without one is a soft wrap.
    """
    quoted = _QUOTE_MARKER.match(line)
    if quoted:
        opens = "" if _QUOTE_MARKER.match(previous) else "| "
        line = opens + line[quoted.end() :]
    if not line.strip():
        return "|"
    own_block = _OWN_BLOCK.match(line)
    line = _BOLD_VERB.sub(_BOLD_START, _LIST_MARKER.sub("| ", line))
    return f"| {line} |" if own_block else line


def _normalise(lines: list[str]) -> str:
    """The text the patterns see: same line count, formatting removed."""
    text = "\n".join(_mark_line(line, previous) for previous, line in zip(["", *lines], lines))
    text = _GLOB.sub(_GLOB_HELD, text)
    for _ in range(2):  # a second pass for pairs nested in or beside another
        for pattern in _PAIRED_DELIMITERS:
            text = pattern.sub(r"\1", text)
    return text.replace(_GLOB_HELD, "_*")


Span = tuple[int, int]


def _braced_spans(text: str) -> list[Span]:
    """Each outermost ``{...}`` value, in order. An unclosed one runs to the end."""
    spans: list[Span] = []
    depth = start = 0
    for brace in re.finditer(r"[{}]", text):
        if brace.group() == "{":
            if not depth:
                start = brace.start()
            depth += 1
        elif depth:
            depth -= 1
            if not depth:
                spans.append((start, brace.end()))
    if depth:
        spans.append((start, len(text)))
    return spans


@dataclass(frozen=True)
class _Scan:
    """The text the patterns see, indexed once so each match is cheap to judge."""

    text: str
    clauses: list[Span]  # the breaks between clauses
    sentences: list[Span]  # the breaks between sentences
    braced: list[Span]  # outermost {...} values
    newlines: list[int]
    boundaries: list[int]  # where a "|" block or cell boundary sits
    exceptions: list[int]  # where an exception word starts
    no_changes: list[int]  # where "no_change" starts

    @classmethod
    def of(cls, text: str) -> "_Scan":
        def starts(pattern: str) -> list[int]:
            return [m.start() for m in re.finditer(pattern, text, re.I)]

        return cls(
            text,
            [m.span() for m in _CLAUSE_BREAK.finditer(text)],
            [m.span() for m in _SENTENCE_BREAK.finditer(text)],
            _braced_spans(text),
            starts("\n"),
            starts(r"\|"),
            [m.start() for m in _EXCEPTION.finditer(text)],
            starts("no_change"),
        )

    def between(self, breaks: list[Span], position: int) -> Span:
        """The stretch between two breaks that holds ``position``."""
        index = bisect_right(breaks, position, key=lambda span: span[1])
        start = breaks[index - 1][1] if index else 0
        return start, breaks[index][0] if index < len(breaks) else len(self.text)

    def excepted(self, position: int) -> bool:
        """An exception word in the sentence, or the next one opens with one."""
        sentence = self.between(self.sentences, position)
        following = bisect_left(self.sentences, sentence[1], key=lambda span: span[0])
        return _any_within(self.exceptions, sentence) or (
            following < len(self.sentences)
            and bool(_EXCEPTION_OPENS.match(self.text, self.sentences[following][1]))
        )

    def line(self, position: int) -> Span:
        index = bisect_left(self.newlines, position)
        start = self.newlines[index - 1] + 1 if index else 0
        return start, self.newlines[index] if index < len(self.newlines) else len(self.text)

    def block(self, position: int) -> Span:
        """The paragraph, list item or table cell holding ``position``."""
        index = bisect_left(self.boundaries, position)
        start = self.boundaries[index - 1] + 1 if index else 0
        return start, self.boundaries[index] if index < len(self.boundaries) else len(self.text)

    def enclosing_value(self, position: int) -> Span | None:
        index = bisect_right(self.braced, position, key=lambda span: span[0]) - 1
        if index >= 0 and position < self.braced[index][1]:
            return self.braced[index]
        return None


def _any_within(positions: list[int], span: Span) -> bool:
    index = bisect_left(positions, span[0])
    return index < len(positions) and positions[index] < span[1]


def _is_exempt(name: str, scan: _Scan, match: re.Match[str], clause: Span, anchor: int) -> bool:
    """True when the surrounding words excuse this match."""
    text = scan.text
    start, end = clause
    before = text[max(start, anchor - _LOOK_BEHIND) : anchor]
    if name in _FINAL_REPLY_EXEMPT:
        return bool(
            _FINAL_REPLY.search(text, start, end)
            or (text[end : end + 1] == ":" and _ROUTED_AFTER_COLON.match(text, end + 1))
        )
    if name == "record-no-change":
        return bool(
            _NEGATOR.search(before)
            and _DIRECT_NO_CHANGE.fullmatch(match.group())
            and not scan.excepted(anchor)
        )
    if name == "tool-record-result":
        # Refused if no_change is anywhere in the line, the paragraph or the
        # structured value holding the word, however it is wrapped.
        scopes = (scan.line(anchor), scan.block(anchor), scan.enclosing_value(anchor))
        if any(span and _any_within(scan.no_changes, span) for span in scopes):
            return False
        quoted_key = before.endswith(('"', "'")) and _QUOTED_KEY_AFTER.match(text, match.end())
        return bool(
            quoted_key or _FIELD_AFTER.match(text, match.end()) or _FIELD_BEFORE.search(before)
        )
    if name == "tool-automations":
        if _CRON_BEFORE.search(before) and _PROSE_LIST.match(text, anchor):
            return True
        return bool(
            "(" not in match.group()
            and _NEGATED_TOOL_USE.search(before)
            and not scan.excepted(anchor)
        )
    return False


def delivery_violations(text: str, *, require_block: bool = True) -> list[str]:
    """Return the delivery-doctrine violations in an announce agent's prompt.

    Empty means compliant: the canonical block is present exactly once (unless
    ``require_block`` is false, as for a skill an announce agent reads) and no
    forbidden delivery wording appears outside it. The block is counted on the
    raw text; the rest is scanned with Markdown formatting removed and soft-wrapped
    lines read as one. Each problem cites the original line where the match
    starts. At most one problem per pattern per clause.
    """
    problems: list[str] = []
    count = text.count(DELIVERY_DOCTRINE_BLOCK)
    if require_block and count != 1:
        problems.append(f"delivery block occurrences: {count} (expected 1)")
    lines = text.replace(DELIVERY_DOCTRINE_BLOCK, "").splitlines()
    scan = _Scan.of(_normalise(lines))
    for name, pattern in FORBIDDEN_DELIVERY_PATTERNS:
        settled: set[int] = set()  # clauses already reported or waived
        position = 0
        # Search again from just past each verb, so an exempt match whose window
        # reaches a later instruction cannot swallow it.
        while match := pattern.search(scan.text, position):
            anchor = match.start("verb") if "verb" in pattern.groupindex else match.start()
            position = anchor + 1
            clause = scan.between(scan.clauses, anchor)
            if clause[0] in settled:
                continue
            if _is_exempt(name, scan, match, clause, anchor):
                # A final-reply waiver covers the whole clause.
                if name in _FINAL_REPLY_EXEMPT:
                    settled.add(clause[0])
                continue
            settled.add(clause[0])
            line_no = bisect_left(scan.newlines, anchor) + 1
            problems.append(f"{name} at line ~{line_no}: {lines[line_no - 1].strip()[:120]}")
    return problems
