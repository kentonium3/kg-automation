"""Shared machinery for this repository's Claude Code hook guards.

One implementation of payload parsing, session-ledger IO, argv tokenisation, marker
detection and the three response shapes — so the guards in ``scripts/hooks/`` cannot
drift apart. ``mission_lifecycle_gate.py`` uses it today; ``upstream_filing_guard.py``
adopts it in WP07.

**Body resolution is deliberately NOT here.** It was, and it was removed on review: it
exists to fix qa #276, which is WP07's defect in WP07's file, and a general
whole-command resolver with no caller in this work package produced two findings of its
own (a false positive naming a flag that belonged to a different program, and a
``--body-file`` at a FIFO that hung the gate forever). WP07 resolves the body of the one
segment it actually gates. Do not re-add a general version here without a caller.

WHAT THIS PROVES, AND WHAT IT CANNOT
------------------------------------
Every gate built on this library proves the same narrow thing: **a step ran** — a command
was tokenised and matched, a file was read, a marker was written after a tool *succeeded*.
It cannot prove the judgment was sound: that a sweep's output was read, that a near-match
was correctly rejected, that a workaround applied to a closed upstream issue was still
warranted. Nothing observable from a hook payload can prove that.

What it removes is **silent omission** — the step nobody decided to skip, that simply
never happened because the runbook was never opened.

=============================================================================
DIVERGENCE 1 — C-001 says extend the proven pattern. The proven pattern FAILS OPEN.
              NFR-001 wins, and this is where it wins.
=============================================================================
``upstream_filing_guard.py`` opens ``main()`` with::

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

An unparseable payload **permits the action**. That is qa #277, WP02 has pinned the
guard's correct behaviours around it, and WP07 will invert it there.

``parse_payload`` here does the opposite: every malformed payload raises, and every
caller answers a raise with a denial. The same inversion is applied to that guard's
``read_ledger``, whose blanket ``except Exception: return {}`` conflates *unreadable*
with *empty*. That idiom is harmless in the filing guard, because both outcomes deny
there — but it is **not** harmless in a gate that must distinguish "you have not run the
sweep" from "I could not read your ledger", which is why ``read_session_ledger`` returns
a :class:`LedgerStatus` instead of a bare dict.

This divergence is written here, at the top, on purpose. An undocumented divergence from
a pattern the codebase calls "proven" is exactly the thing the next reader silently
corrects back.

What C-001 still governs, and what is kept unchanged: the wire shape (structured JSON on
stdout, ``exit 0``), the per-``session_id`` ledger, ``permissionDecision: deny``, and
sanitised path derivation. The divergence is in the *failure direction* only. There is no
second response format.

=============================================================================
DIVERGENCE 2 — the ledger root is the git common dir, NOT $TMPDIR.
=============================================================================
``contracts/session-ledger.md`` §1 and ``data-model.md`` §5 both say
``$TMPDIR/spec-kitty-lifecycle-gate/``. **They are superseded**; ``plan.md``'s Technical
Context resolves a three-way contradiction the post-plan review found (F1) and makes the
canonical root::

    <git-common-dir>/spec-kitty-hooks/
    ├── sessions/<safe_session_id>.json      # this module
    └── faults/<mission_key>.jsonl           # WP05's fault ledger

``git rev-parse --git-common-dir`` is **shared across worktrees**, so a marker or fault
recorded inside a WP lane worktree is visible to the merge check running in the primary
checkout. A ``$TMPDIR`` ledger plus an ``assert-none`` operator command was a
fail-open-by-reassertion path.

Everything *else* in ``contracts/session-ledger.md`` is authoritative and implemented
unchanged: the sanitisation rule, the JSON shape, the schema string, the status enum, the
marker vocabulary, the write protocol and the failure-mode table. **Only the root moves.**
Neither contract is edited here — this module does not own them; the orchestrator
reconciles them on the planning branch.

A root that cannot be resolved raises :class:`HooksRootError`, and every caller answers
that with a denial. A gate that cannot locate its own ledger has established nothing.

``SPEC_KITTY_HOOKS_ROOT`` overrides the root, and every public function also takes a
``root=`` parameter. Both exist so tests can isolate without monkeypatching a private.
The honest note: an operator who *sets* that variable to an empty directory gets a
**denial**, because an empty ledger has no markers — the override cannot manufacture a
pass. Pointing it at a hand-written ledger is deliberate circumvention, which is the same
class as deleting the hook, and is outside what any of this claims to stop.

=============================================================================
DIVERGENCE 3 — segments are split by LINE first, and ``shlex`` never sees the newline.
=============================================================================
``data-model.md`` §4.1 names newline a segment boundary, and the first implementation of
it was a ``\n`` in the separator pattern. **MEASURED: that branch can never fire.**
``shlex`` classifies a newline as whitespace and emits no token for it, so
``cd /tmp && spec-kitty agent mission create`` denied while
``cd /tmp⏎spec-kitty agent mission create`` **allowed** — and multi-line is the default
shape of a Claude Code Bash call. It broke the marker side symmetrically: a sweep run as a
multi-line script earned nothing, so CP-BEFORE would deny forever while telling the agent
to run the step it had just run. A pattern that names the operator is not the same thing
as a tokeniser that produces it.

**Implemented:** :func:`_logical_lines` joins backslash continuations, then
:func:`_tokenise_lines` tokenises each line and treats its end as a boundary. A line that
will not tokenise absorbs the next and retries, because a quoted string may legitimately
span lines and per-line tokenisation in isolation would turn every multi-line commit
message into a denial.

One consequence, stated rather than discovered: ``shlex`` does not model **heredoc**
redirection — it yields the delimiter token (``<<EOF``) and nothing else — so a heredoc's
*content* lines are now tokenised as commands in their own right. A heredoc line that
begins with a gated verb is denied. That is a false positive in the safe direction, and
its remedy is the one every denial already names: run the step.

=============================================================================
THE HONEST LIMITS (NFR-002) — two of them, each unclosable
=============================================================================
**1. Command matching has a residual false negative, and it is not fully closable.**
``split_segments`` tokenises with ``shlex`` and ``argv_matches`` compares token
*positions*, which kills the whole class of false positives where a command merely
*mentions* a gated verb (``echo "spec-kitty merge"`` has ``argv[0] == "echo"``). What it
cannot close: a command assembled through a variable, an alias, or ``eval`` evades token
matching entirely. Mitigated cheaply — flexible whitespace, flag-order independence,
``argv[0]`` compared by basename, leading ``env``-style assignments and shell keywords
skipped, and a gated subcommand reached through ``sh -c`` is unwrapped and matched. Not
closed. A false
*positive* denies, which is the safe direction, and its remedy is to run the step.

Two consequences of tokenising worth stating rather than discovering:

* the blast radius widens in **both** directions. Commands the old substring matcher
  missed (a gated verb after ``&&``) now gate; commands it wrongly caught now do not.
  This change is not purely additive.
* a Bash command ``shlex`` cannot tokenise **denies** on a ``PreToolUse`` route, as
  NFR-001 requires. A genuinely mis-quoted command would have failed in the shell anyway,
  but a validly-quoted command using shell syntax ``shlex`` does not model (an apostrophe
  in an unquoted word, say) is denied too. The remedy is to quote it.

**2. Marker detection cannot tell an intended command from an effective one**, even
marking from ``PostToolUse``. A wrapper that exits 0 without doing the work marks. The
allowlist on ``argv[0]`` (never a denylist — ``printf``, ``:`` and ``true`` fake an
``echo`` equally well) plus requiring each marker's own distinguishing flags is what
makes a *token* command fail to mark. Deliberate circumvention is out of scope.

Reference: ``kitty-specs/mission-lifecycle-gate-01M0VRDZ/`` — ``spec.md`` (FR-002,
FR-009, FR-010, FR-011, NFR-001, NFR-004), ``contracts/session-ledger.md``,
``contracts/denial-payload.md``.
"""

from __future__ import annotations

import enum
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

# =============================================================================
# Constants
# =============================================================================

SCHEMA = "spec-kitty-qa/session-ledger@1"

HOOKS_DIR_NAME = "spec-kitty-hooks"
SESSIONS_DIR_NAME = "sessions"
FAULTS_DIR_NAME = "faults"
HOOKS_ROOT_ENV = "SPEC_KITTY_HOOKS_ROOT"

RETENTION_DAYS = 14

RUNBOOK = "docs/runbooks/autonomous-run-protocol.md"
REGISTER = "docs/spec-kitty-issues.md"

#: Every repository WE own, as a full ``owner/name`` reference. This is the single
#: place that answers "is this ours?", and classification is INVERTED around it:
#: anything not in this set is UPSTREAM (FR-002).
#:
#: CRITERION — apply this, not the list. **A tracker is ours only when its issues are
#: QA's own work items. It is never ours when it receives defect reports about a
#: product under test, no matter who maintains it.**
#:
#: Why inverted. The predecessor of this constant enumerated upstream ORG PREFIXES.
#: The Team Kitty migration changed the prefix and the guard went silently inert —
#: running, reporting nothing, checking nothing — and four issues were filed through
#: it. The list WE control is short and stable; the list someone else controls is not.
#:
#: ⚠ A bare organisation is NOT a discriminator, and this matters MORE now than when
#: the warning was first written: `spec-kitty/EXPERIMENTAL-spec-kitty-saas` becomes
#: `spec-kitty/spec-kitty-saas`, after which `spec-kitty/` matches upstream and us
#: alike. Entries are full ``owner/name`` — never a bare org, never a trailing slash.
#:
#: ⚠ `spec-kitty/spec-kitty-analyzer` is UPSTREAM despite being operator-maintained.
#: That case was contested and is recorded resolved here so it is not re-litigated:
#: it receives defect reports about a product we test, and the second half of the
#: criterion is decisive.
#:
#: ⛔ Do not relocate this into `env/*.json` or any other config file. Configuration
#: is exactly what went stale identically and just as silently on the same day — six
#: descriptors, all wrong, read by eight consumers. Relocation is not the mechanism;
#: assertion is (`tests/hooks/test_ownership_set.py`).
OURS: frozenset[str] = frozenset({"spec-kitty/spec-kitty-qa"})

#: The repositories we FILE INTO. Used ONLY to build remedy text (FR-013); it is
#: never a classification input.
#:
#: The asymmetry is easy to get backwards: the inversion above removes the need to
#: enumerate upstream FOR CLASSIFICATION. It does not remove the need to name
#: upstream FOR A REMEDY — a remedy has to tell a human which repository to sweep.
#:
#: ⚠ Every printed remedy derives from this tuple, and that is the point. When these
#: literals were hand-copied into five places, a rename left the gate printing four
#: commands naming a repository that does not exist: `gh` fails on every one, no
#: marker can ever be earned, and mission start is refused PERMANENTLY behind a
#: remedy that cannot satisfy it. That is a livelock, not a refusal.
#: ⚠ Updated 2026-09-27 after the §0 sweep silently swept an ARCHIVED repository.
#: `spec-kitty/EXPERIMENTAL-spec-kitty` is archived and does NOT redirect, so every
#: query against it returned nothing — indistinguishable from "nothing to report".
#: The -saas and -planning names DID redirect, which is why only one entry was broken
#: and why nobody noticed: two thirds of the sweep kept working. Redirects are not a
#: contract; these are now the resolved canonical names, verified with `gh repo view`.
UPSTREAM_TARGETS: tuple[str, ...] = (
    "spec-kitty/spec-kitty",  # the CLI under test (was EXPERIMENTAL-spec-kitty, archived)
    "spec-kitty/spec-kitty-saas",  # the product under test
    "spec-kitty/spec-kitty-planning",  # receives our docs and questions
)

#: Compared case-folded, so `Spec-Kitty/Spec-Kitty-QA` is still ours. Matches the
#: semantics of the other `owner/name` comparator in the tree
#: (`scripts/scope_resolve.py:172-180`); deliberately NOT imported from it — different
#: layer, and this module has no dependencies outside the standard library.
_OURS_FOLDED: frozenset[str] = frozenset(name.casefold() for name in OURS)

#: ONE flag with two spellings. `gh`'s own help prints it as a single entry —
#: `-R, --repo [HOST/]OWNER/REPO` — so "last occurrence wins" spans BOTH spellings and
#: they are read in ONE loop below, never in per-spelling branches. Per-spelling
#: branches are exactly what produced the divergence where `--repo=` returned `None`
#: and `--repo ""` returned `''`, two spellings `gh` treats identically getting
#: opposite verdicts from this gate.
_TARGET_FLAG_LONG: str = "--repo"
_TARGET_FLAG_SHORT: str = "-R"

#: The URL schemes `gh` treats as a clone URL rather than a bare `owner/name`.
#: MEASURED case-SENSITIVELY (gh 2.98.0, 2026-08-27): `https://github.com/cli/cli`
#: resolves, `HTTPS://GitHub.com/cli/cli` is refused with *expected the
#: "[HOST/]OWNER/REPO" format*, and `ftp://github.com/cli/cli` is refused likewise.
#: So this is a literal lower-case prefix test and deliberately NOT case-folded.
_URL_SCHEMES: tuple[str, ...] = ("git+ssh://", "ssh://", "git://", "http://", "https://")

#: The scp-like clone form. MEASURED: `git@github.com:cli/cli` resolves; the same
#: shape under any other user — `foo@github.com:cli/cli` — does not, so the literal
#: `git@` is the discriminator, not the `@`.
_SCP_PREFIX: str = "git@"

#: The one host whose repositories `OURS` can name. A value carrying a DIFFERENT host
#: is returned verbatim so it can never match `OURS`: a repository of the same
#: `owner/name` on another host is a different repository, and unknown must fall to
#: the enforcing side (FR-002). MEASURED: `--repo evil.example/cli/cli` makes `gh`
#: connect to `evil.example`, not to GitHub.
_GITHUB_HOST: str = "github.com"

_DOT_GIT: str = ".git"


def _canonical_target(value: str) -> str:
    """The `owner/name` `gh` resolves this target VALUE to, or the value verbatim.

    `gh` documents its target value as `[HOST/]OWNER/REPO` in its own `--help`, and
    also accepts clone URLs. MEASURED (gh 2.98.0, 2026-08-27) — every one of these
    queried `cli/cli`, read back out of the issue URL `gh` returned::

        --repo cli/cli                          --repo github.com/cli/cli
        --repo GitHub.com/CLI/cli               --repo https://GITHUB.COM/cli/cli
        --repo http://github.com/cli/cli        --repo https://github.com/cli/cli
        --repo https://github.com/cli/cli.git   --repo https://user@github.com/cli/cli
        --repo git://github.com/cli/cli         --repo ssh://git@github.com/cli/cli.git
        --repo git+ssh://git@github.com/cli/cli.git
        --repo git@github.com:cli/cli           --repo git@github.com:cli/cli.git

    ⚠ THIS IS NOT COSMETIC — it is the same hole as the attached short form, in the
    value axis instead of the flag axis, and it was measured end to end::

        $ gh issue list --repo github.com/spec-kitty/spec-kitty-qa --limit 1 --json url
        [{"url":"https://github.com/spec-kitty/spec-kitty-qa/issues/291"}]

    `gh` queries OUR OWN tracker. An extractor that returned the value verbatim would
    find `github.com/spec-kitty/spec-kitty-qa` is not in :data:`OURS`, answer
    "upstream", and award a sweep marker for a sweep of our own issues — the exact
    thing T004 exists to prevent.

    Forms `gh` REFUSES are returned VERBATIM rather than repaired. Repairing them would
    make this extractor accept more than the tool does, which is its own divergence in
    the opposite direction. Measured refusals::

        --repo cli/cli.git              # `.git` is stripped off a URL, never off a name
        --repo github.com/cli/cli.git   # likewise: *Could not resolve … 'cli/cli.git'*
        --repo github.com/cli/cli/extra --repo https://github.com/cli/cli/issues/1
        --repo //github.com/cli/cli     --repo /cli/cli     --repo cli/cli/
        --repo HTTPS://GitHub.com/cli/cli   --repo ftp://github.com/cli/cli
        --repo foo@github.com:cli/cli

    A refused value cannot earn a marker anyway — `PostToolUse` fires only on success
    (`mission_lifecycle_gate._route_post_tool_use`) — so verbatim is the safe answer
    in both directions: not in `OURS`, therefore upstream, therefore enforcing.
    """
    text = value
    from_url = False

    scheme = next((s for s in _URL_SCHEMES if text.startswith(s)), None)
    if scheme is not None:
        text = text[len(scheme) :]
        from_url = True
        # userinfo (`user@host`) belongs to the authority, never to the path
        authority, slash, path = text.partition("/")
        if "@" in authority:
            authority = authority.rpartition("@")[2]
        text = f"{authority}{slash}{path}"
    elif text.startswith(_SCP_PREFIX):
        text = text[len(_SCP_PREFIX) :]
        from_url = True
        host, separator, path = text.partition(":")
        if separator:
            text = f"{host}/{path}"

    if from_url and text.endswith(_DOT_GIT):
        text = text[: -len(_DOT_GIT)]

    parts = text.split("/")
    if len(parts) == 3 and all(parts) and parts[0].casefold() == _GITHUB_HOST:
        return f"{parts[1]}/{parts[2]}"
    return value


def target_repo(argv: Sequence[str]) -> str | None:
    """The repository this command targets, or ``None`` if it names none.

    ONE extractor, used by every caller. Two extractors is how the split-brain this
    seam exists to fix was born.

    ⚠ THE GRAMMAR IS `gh`'s, NOT ONE WE CHOSE. It was established by RUNNING `gh`
    2.98.0 (2026-08-27) and reading back the repository it actually queried out of the
    returned issue URL — never by reasoning about how a parser "ought" to work, because
    a parser for someone else's language is unbounded. Every accepted spelling of the
    flag, all resolving to `cli/cli`::

        $ gh issue list --repo cli/cli  --limit 1 --json url   ->  cli/cli
        $ gh issue list --repo=cli/cli  --limit 1 --json url   ->  cli/cli
        $ gh issue list -R cli/cli      --limit 1 --json url   ->  cli/cli
        $ gh issue list -Rcli/cli       --limit 1 --json url   ->  cli/cli
        $ gh issue list -R=cli/cli      --limit 1 --json url   ->  cli/cli

    Rendered as the rule this function implements — one loop, one flag, two spellings:

    ==========================  ==============================================
    token                       value
    ==========================  ==============================================
    ``--repo`` / ``-R``         the NEXT token, taken verbatim even if it
                                begins with ``-`` (measured: ``--repo --limit
                                1`` sets the target to the string ``--limit``
                                and then fails on the stray ``1``); ``None``
                                when the flag is last
    ``--repo=VALUE``            everything after the first ``=``; ``--repo=``
                                is the EMPTY value, not the value ``=``
    ``-RVALUE``                 ``VALUE`` — pflag's shorthand rule
    ``-R=VALUE``                ``VALUE`` — a single leading ``=`` is stripped,
                                but ONLY when something follows it. ``-R=``
                                alone is the value ``=``, which `gh` then
                                refuses: *expected the "[HOST/]OWNER/REPO"
                                format, got "="*.
    ==========================  ==============================================

    The last two rows are pflag's shorthand rule verbatim — value is
    ``shorthands[2:]`` when ``len(shorthands) > 2 and shorthands[1] == '='``, else
    ``shorthands[1:]`` — which is why ``-R=`` and ``--repo=`` differ. They are not a
    guess: all four cases above were run.

    The VALUE grammar is `gh`'s too; see :func:`_canonical_target`. `gh` accepts
    ``[HOST/]OWNER/REPO`` and clone URLs, so ``--repo github.com/spec-kitty/spec-kitty-qa``
    reaches the same tracker as ``--repo spec-kitty/spec-kitty-qa`` and must reach the
    same verdict here.

    ⚠ EMPTY VALUE — a DECISION, pinned, not an accident. Measured::

        $ gh issue list --repo "" --limit 1 --json url     ->  spec-kitty/spec-kitty-qa
        $ gh issue list --repo=   --limit 1 --json url     ->  spec-kitty/spec-kitty-qa
        $ gh issue list -R ""     --limit 1 --json url     ->  spec-kitty/spec-kitty-qa
        $ gh issue list --repo cli/cli --repo "" --limit 1 --json url
                                                          ->  spec-kitty/spec-kitty-qa

    `gh` resolves an empty value from the git remote — and an empty LAST occurrence
    overrides an earlier real one, so it cannot be skipped. Resolving a git remote here
    was considered and CUT (qa#291 item 4), and this function does not add it. Of the
    two honest options — "no target named" or a third INDETERMINATE state — this
    returns ``None``, *no target named*, which is today's behaviour for a bare filing.
    The justification is that the answer `gh` would compute is this checkout's origin,
    and `tests/hooks/test_ownership_set.py` asserts that origin is in :data:`OURS`;
    "ours" and "no target named" agree at the only call sites, both withholding every
    sweep marker. A third state would ripple through :func:`names_upstream` and every
    WP that builds on this seam to buy nothing here. ALL FOUR spellings above return
    ``None`` — including the last, where the empty value must DEFEAT the earlier
    `cli/cli`, exactly as `gh` does.

    Five spellings reach argv and every one of them is load-bearing::

        --repo owner/name        # value in the NEXT token
        --repo=owner/name        # value INSIDE this token
        -R owner/name            # short form, value in the next token
        -Rowner/name             # short form, value ATTACHED to the flag token
        -R=owner/name            # short form, `=` stripped

    ⚠ TWO DIFFERENT OPERATIONS LIVE HERE, and conflating them is directly
    exploitable. Substring matching **locates** the value inside a token — that is
    what ``token.startswith("--repo=")`` and the slice below are doing, and it is the
    only reason the ``=`` form works at all. Comparison **after** extraction is
    case-folded FULL-STRING equality, never ``in``::

        >>> "spec-kitty/spec-kitty" in "spec-kitty/spec-kitty-qa"
        True

    Under a substring comparison our own tracker would satisfy a requirement about
    upstream. The comment this function replaced commanded ``in``-matching in bold, a
    line away from the rule that forbids it — the loud instruction is about LOCATING
    a value, never about COMPARING one.

    ⚠ THE LAST TARGET FLAG WINS, not the first. This is not inferred from how a
    parser "ought" to work — a parser for someone else's language is unbounded, so it
    was MEASURED against the real tool (`gh version 2.98.0`, measured 2026-08-27)::

        $ gh issue list --repo cli/cli --repo octocat/Hello-World --limit 1 --json url
        [{"url":"https://github.com/octocat/Hello-World/issues/11019"}]

        $ gh issue list --repo octocat/Hello-World --repo cli/cli --limit 1 --json url
        [{"url":"https://github.com/cli/cli/issues/14257"}]

    ``gh`` binds the target with a cobra/pflag string flag, so a repeated occurrence
    OVERWRITES the earlier one, and it does so across spellings too. MEASURED: all
    FOURTEEN ordered pairs over the five accepted spellings resolved to the SECOND
    repository, and the reversed pairs resolved to the first — ``--repo A -RB``,
    ``-RA --repo B``, ``-R=A -RB``, ``-RA -R=B``, ``--repo=A -RB`` among them.
    Returning the FIRST occurrence (this function's first shape) disagreed with the
    tool in both directions and both were reproduced end to end:
    ``--repo <upstream> --repo <ours>`` earned ``sweep.authored`` while ``gh`` queried
    OUR OWN tracker — the T004 gaming path reopened one token wide — and
    ``--repo <ours> --repo <upstream>`` made :func:`names_upstream` answer ``False``
    while ``gh`` filed upstream, which is a guard bypass the moment a filing guard
    routes through this seam.

    ⚠ WHAT THIS DOES NOT MODEL, and why the boundary is here rather than further out.
    This function models the TARGET flag's grammar exactly. It does not model the
    arity of `gh`'s OTHER flags, because that table is per-subcommand and unbounded —
    and imitating it is precisely how a parser for someone else's language goes wrong.
    Two consequences, both measured, both stated with their direction:

    * A ``-R`` inside a SHORTHAND CLUSTER is not read. Measured, and the measurement
      is the argument for the boundary rather than against it::

          $ gh issue list -aRcli/cli --limit 1 --json url
          GraphQL: Could not find an assignee with the login 'Rcli/cli'.
          $ GH_BROWSER=echo gh issue list -wRcli/cli
          https://github.com/cli/cli/issues?q=state%3Aopen+type%3Aissue

      In the first, ``-a`` SWALLOWS the ``R`` — a cluster-aware extractor would read
      `cli/cli` as the target where `gh` reads it as an assignee and queries our own
      remote, which is the marker-awarding direction and a NEW hole. Reading nothing
      is correct there. In the second `gh` really does target `cli/cli` and this reads
      nothing: no target, no marker — the withholding direction. On the FILING axis
      the only boolean shorthands on ``gh issue create`` are ``-e``/``--editor`` and
      ``-w``/``--web``, both of which are interactive, so a cluster cannot silently
      file anything in an unattended run. Closing this properly means asking `gh` for
      its per-command flag table, not guessing at it.

    * ``GH_REPO`` in the environment sets the target with no argv token at all, so
      nothing in ``argv`` can reveal it. It fails to the marker-withholding side here
      (no token → ``None`` → no marker). Closing it needs an environment source the
      hook payload does not carry, which is a design decision and belongs to qa#291,
      not to a parser fix. It was rediscovered independently during review; an
      independent rediscovery of a cut item is evidence the cut is load-bearing, not
      evidence the cut was wrong.

    Returns ``None`` when no target flag is present, and when the winning occurrence
    carries an empty value (see above).
    """
    target: str | None = None
    index = 0
    # ONE loop over ONE flag. `--repo` and `-R` are two spellings of the same `gh`
    # flag, so they must share the last-wins accumulator; splitting them into separate
    # branches is what let two spellings `gh` treats identically disagree here.
    while index < len(argv):
        token = argv[index]
        raw: str | None = None
        is_target = True

        if token in (_TARGET_FLAG_LONG, _TARGET_FLAG_SHORT):
            # SEPARATED. pflag takes the next token verbatim, even one starting with
            # `-`; the extra advance below stops that value being re-read as a flag.
            raw = argv[index + 1] if index + 1 < len(argv) else None
            index += 1
        elif token.startswith(f"{_TARGET_FLAG_LONG}="):
            raw = token[len(_TARGET_FLAG_LONG) + 1 :]
        elif token.startswith(_TARGET_FLAG_SHORT) and len(token) > len(_TARGET_FLAG_SHORT):
            # ATTACHED SHORT FORM, pflag's shorthand rule verbatim. `R` must be the
            # FIRST shorthand character for this to be unambiguous — see the cluster
            # note above.
            shorthands = token[1:]
            if len(shorthands) > 2 and shorthands[1] == "=":
                raw = shorthands[2:]
            else:
                raw = shorthands[1:]
        else:
            is_target = False

        if is_target:
            # An empty or absent value RESETS the target, because in `gh` it defeats
            # any earlier occurrence and falls back to the git remote.
            target = _canonical_target(raw) if raw else None
        index += 1
    return target


def is_ours(target: str | None) -> bool:
    """Full-string, case-folded membership of :data:`OURS`. Never a substring test."""
    return target is not None and target.casefold() in _OURS_FOLDED


def names_upstream(argv: Sequence[str]) -> bool:
    """True when this command names a target that is **not ours**.

    ⚠ The name is unchanged for its callers but the CLAIM has changed, and the
    difference is the whole mission. It no longer means "names a repo under a known
    upstream org prefix" — a claim that quietly became false the day the org was
    renamed. It means "names something that is not ours", so an unknown repository
    such as ``octocat/hello`` classifies as upstream. That is intended: the unknown
    falls to the enforcing side (FR-002).

    A command naming NO target returns ``False``, preserving today's behaviour at the
    sole call site — no target named is no evidence about upstream.
    """
    target = target_repo(argv)
    if target is None:
        return False
    return not is_ours(target)


#: A GitHub `owner/name` slug and nothing else. Used ONLY on the marker-AWARD path.
_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def names_a_repository(target: str | None) -> bool:
    """True when `target` is a well-formed `owner/name` slug.

    ⚠ This exists because :func:`names_upstream` answers a question with the OPPOSITE
    polarity to the one the award path needs, and using it there was a measured bypass
    (post-merge mission review, C-1).

    :func:`_canonical_target` returns a value it cannot parse VERBATIM, deliberately: on
    the FILING path an unparseable target is not in :data:`OURS`, so it classifies as
    upstream and is enforced against. That is the safe direction. On the AWARD path the
    same answer inverts — unparseable, therefore not ours, therefore upstream, therefore
    *grant the marker*. Measured before this check existed::

        gh issue list --repo $X                      --author @me  -> sweep.authored
        gh issue list --repo spec-kitty/spec-kitty-qa --author @me -> nothing

    The honest command earned nothing and the unresolvable one earned the marker, so four
    sweeps of our own tracker behind a variable satisfied the whole §0 gate.

    ⚠ This is a positive test over slug SYNTAX, and deliberately **not** membership of
    :data:`UPSTREAM_TARGETS`. Membership was proposed and rejected: a post-rename name is
    not a member, so the gate would demand a sweep of a repository that no longer exists
    and no edit-free rename would survive — the exact fragility this mission deleted, and
    `test_a_post_rename_name_is_upstream_with_no_list_edit` pins it. Syntax converges
    without a list: every shape nobody has enumerated fails closed.

    What it accepts, and must keep accepting: post-rename names, `octocat/hello-world`
    (FR-002), and the legacy org two runbooks still sweep. What it refuses: variable and
    command expansions, globs, brace expansions, tildes.

    Residual, stated rather than hidden: a literal but irrelevant repository — an operator
    can sweep any real repository — `octocat/hello-world` exists, returns rc=0, and costs
    nothing; creating one is not even required. Scoping evidence to the
    repository being filed into needs the marker to record what it was earned against, and
    that is qa#291 item 4.
    """
    return target is not None and bool(_REPO_SLUG_RE.match(target))


#: The vocabulary is CLOSED, so a later writer cannot invent a key that unlocks an older
#: gate. ``MARKER_ORDER`` fixes the reporting order: a denial whose text reorders itself
#: between runs is a denial nobody can write a test against (FR-009).
MARKER_ORDER: tuple[str, ...] = (
    "sweep.authored",
    "sweep.recent_closed",
    "sweep.register_refs",
    "register.read",
)
MARKERS = frozenset(MARKER_ORDER)


def _marker_commands() -> dict[str, tuple[str, ...]]:
    """The printed remedies. No repository literal is written by hand here.

    Built rather than typed out because a hand-copied literal is what re-arms the
    livelock: change ``UPSTREAM_TARGETS`` and every remedy site moves with it, or none
    of them do. One command per target, so a printed sweep covers every queue we
    actually file into rather than one of the three.

    ⚠ TWO KINDS OF REMEDY LIVE HERE, and the difference is measured. A remedy that
    asks *"what is in that queue?"* must name the queues — those derive from
    :data:`UPSTREAM_TARGETS`. A remedy that asks *"where does THIS reference live?"*
    must not: see the note on ``sweep.register_refs`` below.
    """
    authored: list[str] = []
    recent: list[str] = []
    recheck: list[str] = []
    # ⚠ `sweep.register_refs` is the ONE remedy that must NOT derive its repository from
    # UPSTREAM_TARGETS, and the reason is measured, not stylistic. WP03 qualified all 53
    # references in the register and they live in THREE repositories — 48 under
    # `Priivacy-ai/spec-kitty`, 4 under `spec-kitty/spec-kitty-qa`, 1 under
    # `Priivacy-ai/spec-kitty-saas`. ANY single repository is wrong here, and deriving
    # from a constant would only swap one wrong repository for another. Worse than
    # failing: measured, querying #205/#214 against the CLI repo returned CLOSED for two
    # entirely unrelated issues — a CONFIDENT WRONG ANSWER, the exact defect class this
    # mission exists to remove. So each reference carries its own repository and the
    # remedy reads it off the reference.
    #
    # Verified by WP03 against the real queues: 53 of 53 resolved, zero failures, and the
    # marker actually moved (3 → 4 in the ledger) — this form tokenises so that
    # `positional[1:3] == ["issue", "view"]`, which the previous shape did not achieve
    # against a register whose refs are qualified.
    refs: list[str] = [
        f'for ref in $(grep -oE "[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#[0-9]+" {REGISTER} | sort -u); do',
        '  gh issue view "${ref#*#}" --repo "${ref%#*}" --json number,state,title',
        "done",
    ]
    for target in UPSTREAM_TARGETS:
        authored.extend(
            (
                f"gh issue list --repo {target} --author @me --state all \\",
                "    --json number,title,state",
            )
        )
        recent.extend(
            (
                f"gh issue list --repo {target} --state closed --limit 100 \\",
                '    --search "closed:>=<date-of-last-sweep>" --json number,title,closedAt',
            )
        )
        recheck.append(f"gh issue view <number> --repo {target} --json state,title")
    return {
        "sweep.authored": tuple(authored),
        "sweep.recent_closed": tuple(recent),
        "sweep.register_refs": tuple(refs),
        "register.read": (
            "# read the register FIRST — it answers what the queue cannot",
            f"cat {REGISTER}",
            "# then re-check any upstream ref it cites, in whichever queue it lives",
            *recheck,
        ),
    }


#: One runnable remedy per marker (FR-009). Constants in code — never a substring
#: copied out of ``tool_input`` (NFR-004).
MARKER_COMMANDS: dict[str, tuple[str, ...]] = _marker_commands()

MARKER_WHY: dict[str, str] = {
    "sweep.authored": "what we reported, and where it now stands",
    "sweep.recent_closed": "fixes we may now be entitled to stop working around",
    "sweep.register_refs": "every upstream ref the register cites, re-checked",
    "register.read": "the register itself, which answers what the queue cannot",
}

#: Verbatim and mandatory in every denial (``contracts/denial-payload.md`` §3.1, §4a).
#: Two claims: the anti-pattern, and the honest limit. Both come from the proven guard.
CLOSING_BLOCK = (
    "⚠ Fix this by RUNNING the step, never by adding a token command to satisfy the\n"
    "  marker. This gate proves a step ran; it cannot prove the judgment was sound.\n"
    f"  Full lifecycle: {RUNBOOK}"
)

#: FR-009 requires every denial to carry something runnable. Checkpoint denials supply
#: their own; an *infrastructure* denial (a payload the gate could not read, an exception
#: nobody predicted) has no step to re-run, so the runnable remediation is to exercise the
#: gate's own tests.
GATE_SELF_CHECK = ".venv/bin/python -m pytest tests/hooks -q"

# =============================================================================
# Exceptions — every one of these is answered by a denial, never by an allow
# =============================================================================


class HookError(Exception):
    """Base for every condition this library resolves toward DENY."""


class PayloadError(HookError):
    """The hook payload could not be trusted. Callers deny."""


class CommandParseError(HookError):
    """A Bash command could not be tokenised. Callers deny."""


class HooksRootError(HookError):
    """The ledger root could not be resolved. Callers deny."""


# =============================================================================
# T011 — payload parsing that DENIES on malformed input
# =============================================================================


@dataclass(frozen=True)
class Payload:
    """A hook payload that has been *validated*, not merely deserialised.

    ``error``/``error_type``/``is_interrupt``/``is_timeout`` are optional and default to
    ``None``/``None``/``False``/``False``: a ``PreToolUse`` payload carries none of them,
    and requiring them would deny every legitimate call. ``PostToolUse`` and
    ``PostToolUseFailure`` carry **different** field sets (``tool_response`` versus
    ``error``/``error_type``), so every consumer must branch on ``hook_event_name``.

    ✅ MEASURED by WP01 (Claude Code 2.1.231), reconciled here by the orchestrator because no
    single lane could see both artifacts — WP01's evidence landed on the mission branch while
    this lane branched from WP02's lane tip.

    ``PostToolUseFailure`` carries exactly: ``cwd``, ``duration_ms``, ``effort``, ``error``,
    ``hook_event_name``, ``permission_mode``, ``prompt_id``, ``session_id``, ``tool_input``,
    ``tool_name``, ``tool_use_id``, ``transcript_path``, and ``is_interrupt``.

    ⚠ ``error_type`` and ``is_timeout`` **DO NOT EXIST.** The shipped hook reference documents
    both; the implementation constructs neither (it does construct ``duration_ms``, which the
    reference omits). So there is no key-name risk to hedge against — there is no key. Any
    branch keyed on ``error_type`` reads nothing, and the interrupt filter has exactly one
    input: ``is_interrupt``.

    ⚠ And do not infer a fault from a non-zero exit. A timed-out Bash call never reaches this
    event at all — it arrives as a *successful* ``PostToolUse`` with
    ``tool_response.timedOutAfterMs`` — and a benign non-zero exit (``grep`` with no match) is
    likewise routed to ``PostToolUse``, carrying ``returnCodeInterpretation``. **The event
    performs the classification**; an exit-status heuristic would misfire on the second and
    miss the first.
    """

    session_id: str
    hook_event_name: str
    tool_name: str
    tool_input: Mapping[str, Any]
    cwd: str | None
    tool_use_id: str | None
    error: str | None
    error_type: str | None
    is_interrupt: bool
    is_timeout: bool
    raw: Mapping[str, Any]

    @property
    def command(self) -> str:
        """The Bash command, or ``""`` for any other tool."""
        value = self.tool_input.get("command")
        return value if isinstance(value, str) else ""

    @property
    def file_path(self) -> str:
        value = self.tool_input.get("file_path")
        return value if isinstance(value, str) else ""


def _optional_str(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


def _optional_bool(raw: Mapping[str, Any], key: str) -> bool:
    value = raw.get(key)
    return value if isinstance(value, bool) else False


def parse_json_object(stream: Any) -> Mapping[str, Any]:
    """Read one JSON object from ``stream``, or raise.

    Deliberately separate from :func:`parse_payload_mapping` so a dispatcher can learn
    ``hook_event_name`` before deciding whether a *full* validation failure is even
    answerable — only ``PreToolUse`` has the authority to deny.
    """
    try:
        raw = json.load(stream)
    except Exception as exc:  # noqa: BLE001 - answered by a denial, never by an allow
        # The exception CLASS only. Its message can quote payload content (NFR-004).
        raise PayloadError(
            f"the hook payload is not valid JSON ({type(exc).__name__})"
        ) from exc
    if not isinstance(raw, dict):
        raise PayloadError("the hook payload's top level is not a JSON object")
    return raw


def parse_payload_mapping(raw: Mapping[str, Any]) -> Payload:
    """Validate an already-deserialised payload. Raises :class:`PayloadError`."""
    if not isinstance(raw, dict):
        raise PayloadError("the hook payload's top level is not a JSON object")

    session_id = raw.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        # An unidentifiable session has no evidence, and the sanitised `unknown.json`
        # would be a shared bucket that must never satisfy a gate.
        raise PayloadError("the hook payload carries no usable session_id")

    event = raw.get("hook_event_name")
    if not isinstance(event, str) or not event.strip():
        raise PayloadError("the hook payload carries no hook_event_name")

    if "tool_input" not in raw:
        raise PayloadError("the hook payload carries no tool_input")
    tool_input = raw.get("tool_input")
    if not isinstance(tool_input, dict):
        raise PayloadError("the hook payload's tool_input is not a JSON object")

    tool_name = raw.get("tool_name")
    return Payload(
        session_id=session_id,
        hook_event_name=event,
        tool_name=tool_name if isinstance(tool_name, str) else "",
        tool_input=tool_input,
        cwd=_optional_str(raw, "cwd"),
        tool_use_id=_optional_str(raw, "tool_use_id"),
        error=_optional_str(raw, "error"),
        error_type=_optional_str(raw, "error_type"),
        is_interrupt=_optional_bool(raw, "is_interrupt"),
        is_timeout=_optional_bool(raw, "is_timeout"),
        raw=raw,
    )


def parse_payload(stream: Any) -> Payload:
    """Read and validate a hook payload from ``stream``. Raises :class:`PayloadError`."""
    return parse_payload_mapping(parse_json_object(stream))


# =============================================================================
# T012 — the session ledger
# =============================================================================


class LedgerStatus(enum.Enum):
    """Why a read returned what it returned.

    The existence of ``UNREADABLE`` and ``CORRUPT`` as *separate* values from ``FRESH``
    is the whole point of Divergence 1: all three deny, but they must not deny with the
    same message. "You have not run the sweep" sends the reader to do the right thing;
    "your ledger is corrupt" sends it to delete a file. Emitting the first for the second
    wastes a sweep and leaves the corrupt file in place to deny again.
    """

    OK = "ok"
    FRESH = "fresh"
    UNREADABLE = "unreadable"
    CORRUPT = "corrupt"


def safe_component(value: str) -> str:
    """Sanitise a path component. A traversal guard, not cosmetics.

    ``session_id`` and mission keys arrive from outside the process, so a ``../`` in one
    would otherwise escape the ledger directory.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", value or "unknown")


_ROOT_CACHE: dict[str, Path] = {}


def hooks_root(cwd: str | os.PathLike[str] | None = None) -> Path:
    """``<git-common-dir>/spec-kitty-hooks`` — see Divergence 2.

    ``cwd`` is the *payload's* cwd when one is available: the hook process's own cwd is
    whatever the harness chose, while the payload names the directory the tool call was
    made from. Both land on the same common dir inside one repository; passing the
    payload's is the more defensible of the two.

    Raises :class:`HooksRootError` rather than guessing. Callers deny.
    """
    override = os.environ.get(HOOKS_ROOT_ENV)
    if override:
        return Path(override)

    key = str(cwd or "")
    cached = _ROOT_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 - answered by a denial
        raise HooksRootError(
            f"`git rev-parse --git-common-dir` could not be run ({type(exc).__name__})"
        ) from exc

    if proc.returncode != 0 or not proc.stdout.strip():
        raise HooksRootError("`git rev-parse --git-common-dir` produced no usable path")

    common = Path(proc.stdout.strip())
    if not common.is_absolute():
        common = Path(cwd) / common if cwd else Path.cwd() / common
    try:
        common = common.resolve()
    except OSError as exc:
        raise HooksRootError(f"the git common dir could not be resolved ({type(exc).__name__})") from exc
    if not common.is_dir():
        raise HooksRootError("the git common dir does not exist")

    resolved = common / HOOKS_DIR_NAME
    _ROOT_CACHE[key] = resolved
    return resolved


def _root(root: str | os.PathLike[str] | None, cwd: str | os.PathLike[str] | None) -> Path:
    return Path(root) if root is not None else hooks_root(cwd)


def sessions_dir(*, root: str | os.PathLike[str] | None = None, cwd: str | None = None) -> Path:
    return _root(root, cwd) / SESSIONS_DIR_NAME


def session_ledger_path(
    session_id: str, *, root: str | os.PathLike[str] | None = None, cwd: str | None = None
) -> Path:
    return sessions_dir(root=root, cwd=cwd) / f"{safe_component(session_id)}.json"


def _marker_is_valid(value: Any) -> bool:
    """A malformed marker counts as ABSENT — it can never satisfy a gate — while the rest
    of the ledger stays valid (``contracts/session-ledger.md`` §2)."""
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("first_seen_at"), str):
        return False
    count = value.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return False
    return isinstance(value.get("source_tool"), str)


def _read_detail(
    session_id: str, *, root: str | os.PathLike[str] | None = None, cwd: str | None = None
) -> tuple[dict, LedgerStatus, str | None]:
    """:func:`read_session_ledger` plus the error class, which a denial must name.

    The public reader keeps the two-tuple the contract specifies (§8); the third element
    exists because ``UNREADABLE`` has to name *which* error it was without ever naming
    the file's contents.
    """
    path = session_ledger_path(session_id, root=root, cwd=cwd)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # A read must never create a directory: the gate would be manufacturing its own
        # evidence store on the way to deciding it has no evidence.
        return ({}, LedgerStatus.FRESH, None)
    except UnicodeDecodeError as exc:
        return ({}, LedgerStatus.CORRUPT, type(exc).__name__)
    except OSError as exc:
        return ({}, LedgerStatus.UNREADABLE, type(exc).__name__)

    try:
        state = json.loads(text)
    except json.JSONDecodeError as exc:
        return ({}, LedgerStatus.CORRUPT, type(exc).__name__)

    if not isinstance(state, dict):
        return ({}, LedgerStatus.CORRUPT, "top level is not an object")
    if state.get("schema") != SCHEMA:
        return ({}, LedgerStatus.CORRUPT, "unrecognised schema")
    if not isinstance(state.get("markers"), dict):
        return ({}, LedgerStatus.CORRUPT, "markers is not an object")
    return (state, LedgerStatus.OK, None)


def read_session_ledger(
    session_id: str, *, root: str | os.PathLike[str] | None = None, cwd: str | None = None
) -> tuple[dict, LedgerStatus]:
    """Read the ledger and say *why*. Never raises for a bad file; see :class:`LedgerStatus`."""
    state, status, _ = _read_detail(session_id, root=root, cwd=cwd)
    return state, status


def present_markers(state: Mapping[str, Any]) -> list[str]:
    markers = state.get("markers")
    if not isinstance(markers, dict):
        return []
    return [name for name in MARKER_ORDER if _marker_is_valid(markers.get(name))]


def missing_markers(state: Mapping[str, Any]) -> list[str]:
    """Ordered and stable, so the denial text is testable (FR-009)."""
    satisfied = set(present_markers(state))
    return [name for name in MARKER_ORDER if name not in satisfied]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prune_old_sessions(directory: Path) -> None:
    """Best-effort housekeeping. Never an error, never touches ``faults/``, never touches
    a file inside the retention window (``contracts/session-ledger.md`` §7)."""
    try:
        cutoff = time.time() - RETENTION_DAYS * 86400
        for child in directory.iterdir():
            if child.suffix != ".json" or not child.is_file():
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    child.unlink()
            except OSError:
                continue
    except OSError:
        return


def mark(
    session_id: str,
    marker_id: str,
    source_tool: str,
    *,
    root: str | os.PathLike[str] | None = None,
    cwd: str | None = None,
) -> None:
    """Record a marker. A no-op for any id outside :data:`MARKERS`.

    Write protocol (``contracts/session-ledger.md`` §5): makedirs, read, refuse to write
    over an ``UNREADABLE`` or ``CORRUPT`` ledger, mutate, atomic ``os.replace``.

    No lock. Read-modify-write may **lose** a marker under concurrency, and loss points
    toward deny — the step must be re-run. A lock file would add a stale-lock mode
    pointing toward hang-or-allow, which is the wrong direction to fail in.
    """
    if marker_id not in MARKERS:
        return
    try:
        path = session_ledger_path(session_id, root=root, cwd=cwd)
        path.parent.mkdir(parents=True, exist_ok=True)
        state, status, _ = _read_detail(session_id, root=root, cwd=cwd)
        if status in (LedgerStatus.UNREADABLE, LedgerStatus.CORRUPT):
            # Overwriting would erase the evidence that it was broken and hand the next
            # call a clean pass.
            return

        now = _now()
        if status is LedgerStatus.FRESH:
            # Only `session_id` is payload-derived, and it is sanitised (NFR-004).
            state = {
                "schema": SCHEMA,
                "session_id": safe_component(session_id),
                "created_at": now,
                "markers": {},
            }

        # `setdefault`, not `state["markers"]`, ON PURPOSE. With the subscript, removing
        # the UNREADABLE/CORRUPT guard above raised a KeyError that the outer swallow
        # turned into "no write" — so the guard looked load-bearing while the real
        # protection was an accident. The mutation pass caught that (M11): the guard's
        # removal reddened nothing. Now the guard is the only thing stopping the
        # overwrite, and `test_corrupt_ledger_is_not_overwritten` actually demonstrates it.
        markers = state.setdefault("markers", {})
        existing = markers.get(marker_id)
        tool = safe_component(source_tool)[:32]
        if _marker_is_valid(existing):
            existing["count"] = int(existing["count"]) + 1
            existing["source_tool"] = tool
        else:
            markers[marker_id] = {"first_seen_at": now, "count": 1, "source_tool": tool}
        state["updated_at"] = now

        # ⚠ MEASURED divergence from `contracts/session-ledger.md` §5, which names the
        # temp file `<safe>.<pid>.tmp`. Two THREADS in one process share a pid, so twenty
        # concurrent writers all opened the same temp path, interleaved their bytes, and
        # `os.replace` then published a half-written file as a CORRUPT ledger — found by
        # `test_concurrent_writers_never_fabricate_a_marker`, which is why that test
        # exists. A unique temp name per writer is the fix; the atomic replace is
        # unchanged.
        handle, tmp_name = tempfile.mkstemp(
            prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent)
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(state, stream)
            os.replace(tmp, path)  # atomic; never an in-place truncate
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        _prune_old_sessions(path.parent)
    except Exception:  # noqa: BLE001
        # Bookkeeping must never break a tool call (the proven pattern, kept). The
        # consequence of a failed write is a MISSING MARKER, which denies. That is the
        # safe direction, and it is the reason this swallow is not Divergence 1's defect.
        return


# =============================================================================
# T013 — argv tokenisation (FR-010a): a MENTION is not an INVOCATION
# =============================================================================

#: ``shlex.split`` cannot be told about punctuation, so an unspaced ``a&&b`` or ``a;b``
#: stays one token and a chained invocation escapes the gate. MEASURED on this build:
#: ``shlex.shlex(posix=True, punctuation_chars="();|&")`` with ``whitespace_split=True``
#: segments ``foo&&spk merge`` and ``a;b`` correctly, still raises ``ValueError`` on an
#: unterminated quote, still keeps ``echo "a && spec-kitty merge"`` as ONE token (so the
#: mention-is-not-invocation property survives), and — because ``<`` and ``>`` are
#: deliberately EXCLUDED — leaves ``closed:>=<date>`` intact, which the
#: ``sweep.recent_closed`` marker matches on. This is the prescribed mechanism (``shlex``)
#: with the one setting that makes it correct, not a different mechanism.
#:
#: ⚠ It emits punctuation in RUNS, not one character per token: ``);`` and ``&&(`` each
#: arrive as a single token. That is F2, and :data:`_SEPARATOR_RE` is where it is handled.
_PUNCTUATION_CHARS = "();|&"

#: A token that is nothing but these characters separates shell segments.
#:
#: ⚠ ``()`` are in the class, and that is F2's half of the fix. ``punctuation_chars``
#: emits *runs*: MEASURED, ``(cd /tmp); spec-kitty merge`` tokenises to
#: ``['(', 'cd', '/tmp', ');', 'spec-kitty', 'merge']`` and ``true&&(spec-kitty merge)``
#: to ``['true', '&&(', 'spec-kitty', 'merge', ')']``. A pattern of ``[;|&]`` matches
#: neither ``);`` nor ``&&(``, so both chained invocations escaped — while the *spaced*
#: ``(cd /tmp) ; spec-kitty merge`` denied. Enforcement turned on whether a space had been
#: typed. ``data-model.md`` §4.1 names ``(`` a segment boundary; this implements it.
#:
#: ⚠ ``\n`` is in the class and is NOT dead code, but it no longer carries the newline:
#: physical newlines are handled by :func:`_logical_lines` before tokenising, because
#: ``shlex`` treats a newline as whitespace and never emits one as a token (F1: that
#: branch used to be the only newline handling there was, and a line break was a complete
#: escape). What still reaches here is a *quoted* newline — ``foo "⏎"`` yields a token
#: whose whole content is ``\n``, which ``shlex`` has already stripped the quotes from and
#: which is therefore indistinguishable from an operator. Splitting is the safe direction,
#: and ``test_a_quoted_newline_token_is_a_separator`` pins it.
_SEPARATOR_RE = re.compile(r"^[;|&()\n]+$")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_WRAPPERS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_MAX_WRAPPER_DEPTH = 3

#: Leading tokens that are shell SYNTAX or a transparent wrapper, not the program being
#: invoked. F2's other half: ``{ spec-kitty merge; }`` segments to ``['{', 'spec-kitty',
#: 'merge']``, and a matcher reading ``argv[0]`` literally sees ``{`` and allows.
#:
#: ``if``/``while``/``until`` are here and are NOT in the review's enumeration. They are
#: the same defect: ``if spec-kitty merge; then :; fi`` and ``while spec-kitty merge; do
#: :; done`` invoke the gated verb in the condition, and both ALLOWED under the listed set
#: alone (``then`` is skipped, ``if`` is not). Completing the class was the point of F2;
#: leaving three known holes in a frozenset would repeat the defect the finding names.
#:
#: This list is a SKIP list, never a match list — ``argv[0]`` is still compared by
#: basename afterwards, so ``nohup git merge main`` remains unmatched.
_KEYWORD_PREFIXES = frozenset(
    {
        "{",
        "}",
        "!",
        # MEASURED: `exec spec-kitty merge` and `sudo spec-kitty merge` both allowed —
        # program_of read "exec"/"sudo". Same family as the keywords above.
        "exec",
        "sudo",
        "then",
        "else",
        "elif",
        "fi",
        "do",
        "done",
        "if",
        "while",
        "until",
        "time",
        "nohup",
        "command",
    }
)

#: How many lines one un-tokenisable chunk may absorb before the gate gives up and denies.
#:
#: ⚠ A BOUND, not a limit anyone should hit. Absorbing re-tokenises the chunk from the
#: start, so the cost is O(n²): MEASURED on this build at 0.06s for 100 lines, 1.8s for
#: 500 and **71s for 2000** — a hook that stalls the tool call it was asked to judge. Only
#: a chunk that does not tokenise absorbs at all, and such a chunk ends in a denial
#: whichever line it gives up on; the cap decides how soon, not what. 200 lines is far
#: past any real quoted string and answers in well under a second.
_MAX_ABSORBED_LINES = 200

#: A line ending in an ODD number of backslashes continues onto the next one.
_CONTINUATION_RE = re.compile(r"(?<!\\)(?:\\\\)*\\$")


def _tokenise(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION_CHARS)
    lexer.whitespace_split = True
    # MEASURED bypass, and it is complete rather than adversarial: shlex's `commenters`
    # defaults to "#" and discards to end of line EVEN MID-WORD, while bash treats a `#`
    # inside a word as a literal. So `echo a#b && spec-kitty merge` reached the gate as
    # [['echo','a']] and ALLOWED, and a URL fragment is the everyday shape of it. It broke
    # the marker side symmetrically — a sweep chained after any word containing `#` earned
    # nothing, which is F1's own livelock.
    #
    # Clearing it is the safe direction: `ls # note` now tokenises `#` and `note` as inert
    # arguments, and `ls; # spec-kitty merge` becomes a FALSE POSITIVE denial rather than a
    # false negative. A gate that occasionally denies a commented-out invocation is worth
    # more than one a fragment identifier switches off.
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as exc:
        # MEASURED: `ValueError: No closing quotation`. A ValueError is the natural deny
        # trigger; no extra machinery is needed.
        raise CommandParseError("the command could not be tokenised (malformed quoting)") from exc


def _logical_lines(command: str) -> list[str]:
    """``command`` split into logical lines, backslash continuations already joined.

    A trailing backslash is a line continuation in every shell, and it was its own escape
    hatch: MEASURED, ``cd /tmp && \\⏎spec-kitty merge`` tokenised to
    ``['cd', '/tmp', '&&', '\\nspec-kitty', 'merge']`` — ``shlex`` escaped the newline INTO
    the next token, so ``argv[0]`` was ``"\\nspec-kitty"``, whose basename is not
    ``spec-kitty``, and the gated verb was not matched. Joining with ``""`` reproduces the
    shell's own removal of the backslash-newline pair.
    """
    joined: list[str] = []
    buffer = ""
    for line in command.splitlines():
        if _CONTINUATION_RE.search(line):
            buffer += line[:-1]
            continue
        joined.append(buffer + line)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return joined


def _tokenise_lines(command: str) -> list[list[str]]:
    """Tokenise each logical line, so that a LINE BREAK IS A BOUNDARY (F1).

    ⚠ Why not simply tokenise line by line and be done. A quoted string may legitimately
    span lines — ``git commit -m "line one⏎⏎line two"`` is the everyday case — and each
    physical line of it is an unterminated quote. Tokenising them in isolation raises, and
    an untokenisable command DENIES, so the naive fix refuses every multi-line commit
    message in this repository. A line that will not tokenise therefore ABSORBS the next
    one and retries; the boundary falls where the text actually tokenises.

    The absorb is greedy-minimal — a chunk is emitted the moment it parses — so a line
    break outside quotes is never swallowed by one inside them. If the final chunk still
    will not tokenise, that raise propagates: the caller denies (NFR-001). It is bounded
    at :data:`_MAX_ABSORBED_LINES`, because re-tokenising a growing chunk is quadratic and
    an unterminated quote near the top of a long heredoc otherwise takes over a minute.

    The residual, stated rather than discovered: ``shlex`` does not model heredocs, so the
    *content* lines of a heredoc are tokenised as commands of their own. A heredoc line that
    begins with a gated verb is therefore denied — a false positive in the safe direction.

    ⚠ An apostrophe in a heredoc body also makes the whole command untokenisable. That is
    handled at the CALLERS, which only deny an untokenisable command when it shows some sign
    of being in their scope; see ``evaluate_bash`` and ``_segments_or_deny``. An attempt to
    solve it here by stripping heredoc bodies was REVERTED: a delimiter matcher over raw text
    desynchronises on ``<<<`` here-strings, ``<<`` inside a quoted string, and ``<<`` in
    arithmetic, silently converting denials into ALLOWS in both guards. Fixing a false
    positive with a fail-open is a bad trade, and the untested direction was the failing one.

    """
    chunks: list[list[str]] = []
    pending = ""
    for line in _logical_lines(command):
        candidate = f"{pending}\n{line}" if pending else line
        try:
            chunks.append(_tokenise(candidate))
        except CommandParseError:
            if candidate.count("\n") >= _MAX_ABSORBED_LINES:
                raise  # the caller denies, which is where this chunk was heading anyway
            pending = candidate
            continue
        pending = ""
    if pending:
        _tokenise(pending)  # raises CommandParseError; the caller denies
    return chunks


def split_segments(command: str, *, _depth: int = 0) -> list[list[str]]:
    """Tokenise ``command`` and split it into shell segments.

    Segments break at every boundary ``data-model.md`` §4.1 names — ``;``, ``&&``, ``||``,
    ``|``, ``&``, ``(`` and **newline** — so a gated verb chained after ``&&``, wrapped in
    a brace group, or simply written on the next line is still gated.

    A ``sh -c '<command>'`` wrapper is unwrapped and its inner command contributes its own
    segments, so a gated subcommand reached that way is matched.

    Raises :class:`CommandParseError` on malformed quoting. Callers deny.
    """
    if not command or not command.strip():
        return []

    segments: list[list[str]] = []
    for tokens in _tokenise_lines(command):
        current: list[str] = []
        for token in tokens:
            if _SEPARATOR_RE.match(token):
                if current:
                    segments.append(current)
                current = []
                continue
            current.append(token)
        if current:
            # End of a logical line ends the segment: the line break IS the operator.
            segments.append(current)

    expanded: list[list[str]] = []
    for argv in segments:
        if not argv:
            continue
        expanded.append(argv)
        inner = _shell_wrapped_command(effective_argv(argv))
        if inner is not None and _depth < _MAX_WRAPPER_DEPTH:
            # ⚠ NOT swallowed. An inner command we cannot tokenise may hide a gated verb,
            # and `sh -c` is precisely the wrapper someone would reach for. Swallowing it
            # here made `sh -c \'spec-kitty merge --mission "unterminated\'` ALLOW, because
            # the outer argv is only `sh`. Propagating denies instead (NFR-001).
            expanded.extend(split_segments(inner, _depth=_depth + 1))
    return expanded




def _shell_wrapped_command(argv: Sequence[str]) -> str | None:
    if not argv:
        return None
    if Path(argv[0]).name not in _SHELL_WRAPPERS:
        return None
    for index, token in enumerate(argv[1:], start=1):
        if token == "-c" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def effective_argv(argv: Sequence[str]) -> list[str]:
    """``argv`` with everything that is not the program stripped off the front.

    Three prefixes hide ``argv[0]`` from a matcher that reads it literally, and all three
    are removed here, repeatedly and in any order:

    * ``env``-style assignments and a leading ``env`` — ``FOO=1 spec-kitty merge``;
    * shell syntax and transparent wrappers (:data:`_KEYWORD_PREFIXES`) — ``{ spec-kitty
      merge; }``, ``then spec-kitty merge``, ``nohup spec-kitty merge`` (F2);
    * a stray separator token, which ``split_segments`` already removes but which a caller
      passing raw tokens may not have.

    A SKIP is not a MATCH: what remains is still compared by basename, so
    ``nohup git merge main`` is as unmatched as ``git merge main``.
    """
    tokens = list(argv)
    changed = True
    while tokens and changed:
        changed = False
        if _SEPARATOR_RE.match(tokens[0]) or tokens[0] in _KEYWORD_PREFIXES:
            tokens, changed = tokens[1:], True
            continue
        if Path(tokens[0]).name == "env":
            tokens, changed = tokens[1:], True
            continue
        if _ASSIGNMENT_RE.match(tokens[0]):
            tokens, changed = tokens[1:], True
    return tokens


def _positional_tokens(argv: Sequence[str]) -> list[str]:
    """Drop option tokens, so matching is independent of flag ORDER.

    ``spec-kitty --json merge`` and ``spec-kitty merge --json`` are the same invocation.
    The cost is a false positive when a flag *value* happens to equal a gated verb
    (``spec-kitty --mission merge``); that denies, which is the safe direction.
    """
    return [token for token in argv if not token.startswith("-")]


def argv_matches(argv: Sequence[str], verb: Sequence[str]) -> bool:
    """Does ``argv`` invoke ``verb``? Compared by token POSITION, never by substring.

    ``argv[0]`` is compared by basename, so ``/usr/local/bin/spec-kitty`` matches. The
    verb must be a prefix of the positional tokens, which is what distinguishes
    ``spec-kitty merge`` from ``spec-kitty merge-driver-meta`` (``\\b`` matches before a
    hyphen and a naive regex false-positives on all six ``merge-driver-*`` subcommands)
    and what lets ``spec-kitty agent mission merge`` match at all.
    """
    if not verb:
        return False
    tokens = _positional_tokens(effective_argv(argv))
    if len(tokens) < len(verb):
        return False
    if Path(tokens[0]).name != verb[0]:
        return False
    return list(tokens[1 : len(verb)]) == list(verb[1:])


def program_of(argv: Sequence[str]) -> str:
    """The basename of the program a segment invokes, or ``""``."""
    tokens = effective_argv(argv)
    return Path(tokens[0]).name if tokens else ""


# =============================================================================
# T013b — marker detection: only what the REAL step produces
# =============================================================================

#: ``argv[0]`` values that actually READ a file. An ALLOWLIST, because a denylist of
#: ``echo`` is defeated by ``printf``, ``:`` and ``true`` equally well. ``ls``, ``touch``
#: and ``stat`` are absent on purpose: they name the path without reading it
#: (``contracts/denial-payload.md`` §4b).
_READERS = frozenset(
    {"cat", "bat", "head", "tail", "less", "more", "sed", "awk", "grep", "rg", "view", "nl"}
)
_REGISTER_BASENAME = "spec-kitty-issues.md"


def _has_flag(argv: Sequence[str], flag: str, value: str | None = None) -> bool:
    for index, token in enumerate(argv):
        if token == flag:
            if value is None:
                return True
            return index + 1 < len(argv) and argv[index + 1] == value
        if token.startswith(f"{flag}="):
            return value is None or token[len(flag) + 1 :] == value
    return False


def detect_markers(payload: Payload, segments: Sequence[Sequence[str]]) -> list[str]:
    """Which markers this *successful* tool call is evidence for.

    Each pattern requires the step's own distinguishing evidence, so a token command
    cannot set it (``contracts/denial-payload.md`` §4b). Returned in
    :data:`MARKER_ORDER`.
    """
    found: set[str] = set()

    #: The register may be named in a different segment from the ``gh issue view`` that
    #: cross-checks its refs — see the note at ``sweep.register_refs`` below.
    _register_named_anywhere = any(
        _REGISTER_BASENAME in token for raw in segments for token in raw
    )

    if payload.tool_name in {"Read", "Grep", "Glob"} and _REGISTER_BASENAME in payload.file_path:
        found.add("register.read")

    for raw_argv in segments:
        argv = effective_argv(raw_argv)
        if not argv:
            continue
        program = Path(argv[0]).name

        if program in _READERS and any(_REGISTER_BASENAME in token for token in argv[1:]):
            found.add("register.read")

        if program != "gh":
            continue
        positional = _positional_tokens(argv)

        if positional[1:3] == ["issue", "list"]:
            # ⚠ ALL sweep markers are conditioned on upstream, not just this first one.
            # Three of the four used to be earnable against OUR OWN tracker, which the
            # note at :data:`OURS` says must never count: a sweep of our own issues
            # would satisfy a gate whose entire purpose is to make us look at the
            # product under test. An unattended agent satisfies markers mechanically,
            # and an open path is found at 3am.
            #
            # ⚠ AND the target must be a repository NAME, not merely "not ours".
            # `names_upstream` is a filing-path predicate; on this path its answer
            # inverts. See :func:`names_a_repository` — an unparseable target used to
            # earn the marker the honest command could not.
            swept = names_upstream(argv) and names_a_repository(target_repo(argv))
            if swept and _has_flag(argv, "--author"):
                found.add("sweep.authored")
            if (
                swept
                and _has_flag(argv, "--state", "closed")
                and any("closed:>=" in t for t in argv)
            ):
                found.add("sweep.recent_closed")
        if (
            positional[1:3] == ["issue", "view"]
            and _register_named_anywhere
            and names_upstream(argv)
        ):
            # ⚠ FIXED — this required the register basename in the SAME segment as
            # `gh issue view`, and the gate's own printed remedy could not satisfy it.
            # MEASURED: the runbook's actual §0 query 3 loops the refs out of the register
            # and views each one, so the filename lands in the `grep` segment while the view
            # lands in the loop body — two segments, marker never earned. An agent running
            # exactly what the gate told it to run was refused again with the identical
            # message. That is a livelock, and it is this mission's own defect class — a
            # correct check that can never pass — inside the mechanism built to prevent it.
            #
            # The cross-check is one activity spanning several segments, so the register may
            # be named anywhere in the same command. It is still a conjunction: a bare
            # `gh issue view` with no register reference earns nothing.
            #
            # ⚠ THIS MARKER KEEPS `names_upstream` AND TAKES NO SLUG CONDITION, while the
            # two `issue list` markers above take one. The asymmetry is deliberate and was
            # arrived at by measurement, twice, in opposite directions.
            #
            # No slug condition, because the register's refs span three repositories: the
            # sanctioned query reads each reference's repository off the reference itself,
            # so its target is necessarily `${ref%#*}`. A slug condition here is
            # unsatisfiable by every CORRECT spelling of this query — and the gate PRINTS
            # that query as the way to earn this marker, so the operator would run exactly
            # what they were told and be refused again with the identical text. That is the
            # livelock repaired above, re-armed. `test_the_gate_accepts_the_command_it_prints`
            # now fails the suite if anyone reintroduces it.
            #
            # But `names_upstream` STAYS. A review argued it was pure liability — passing
            # only because an unparseable target reads as upstream. Measured: false. It is
            # what refuses a cross-check of OUR OWN tracker, in every flag form and every
            # host-qualified spelling; deleting it turns 16 tests red (15 before this change added its own). It does
            # admit a dynamic target, which is the price of query 3 being expressible at all.
            # The §0 gate requires all four markers and the two above now demand a slug, so
            # that admission cannot be assembled into a bypass on its own.
            found.add("sweep.register_refs")

    return [name for name in MARKER_ORDER if name in found]


def record_markers(
    payload: Payload,
    segments: Sequence[Sequence[str]],
    *,
    root: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Write every marker this call is evidence for. Returns what was written."""
    detected = detect_markers(payload, segments)
    for marker_id in detected:
        mark(payload.session_id, marker_id, payload.tool_name, root=root, cwd=payload.cwd)
    return detected


# =============================================================================
# T015 — the three response shapes
# =============================================================================


def allow() -> NoReturn:
    """Silence IS the allow: write nothing, exit 0.

    ⚠ Never emit an explicit allow decision — i.e. ``permissionDecision`` set to the
    affirmative value. An explicit allow from a hook can *override* a decision another
    layer would have made; this gate is only ever entitled to say **no**
    (``contracts/denial-payload.md`` §2). The literal string is deliberately not spelled
    out anywhere in this file, so a grep for it stays a reliable check.
    """
    sys.exit(0)


def _emit(body: Mapping[str, Any]) -> NoReturn:
    # Compact separators and an explicit single newline: the payload must be ONE physical
    # line, because a stray line makes the JSON unparseable and the decision is LOST.
    sys.stdout.write(json.dumps({"hookSpecificOutput": body}, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    sys.exit(0)


def deny(reason: str, *, event: str = "PreToolUse") -> NoReturn:
    """Emit a denial: single-line JSON on stdout, exit 0. The JSON carries the decision.

    ``event`` exists to make the refusal below explicit rather than implicit:
    ``permissionDecision`` is a ``PreToolUse``-only field, so a caller that asks to deny
    on another event is asking this library to overstate its authority (C-004). It raises
    instead. stderr stays free for diagnostics.
    """
    if event != "PreToolUse":
        raise ValueError(
            f"permissionDecision is PreToolUse-only; {event} has no deny authority"
        )
    _emit(
        {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    )


def additional_context(text: str, *, event: str) -> NoReturn:
    """Inject context without deciding anything. The only response a post-tool event has."""
    _emit({"hookEventName": event, "additionalContext": text})


# =============================================================================
# T015b — the message contract (contracts/denial-payload.md §3)
# =============================================================================


def render_denial(
    headline: str,
    *,
    missing: Sequence[str] = (),
    commands: Sequence[str] = (),
    why: Sequence[str] = (),
    satisfied: Sequence[str] = (),
) -> str:
    """Assemble a denial from CONSTANTS IN CODE plus non-secret ledger fields.

    Never the raw command, never flag values, never a file's contents (NFR-004). The
    closing block is appended verbatim, and a runnable line is guaranteed: FR-009 is not
    met by a denial the reader cannot act on.
    """
    lines = [f"BLOCKED — {headline}", ""]
    for item in missing:
        lines.append(f"  ✗ {item}")
    if missing:
        lines.append("")
    lines.extend(commands)
    if commands:
        lines.append("")
    if satisfied:
        lines.append(f"Already satisfied this session: {', '.join(satisfied)}.")
        lines.append("")
    lines.extend(why)
    if why:
        lines.append("")

    body = "\n".join(lines)
    if not re.search(r"^\s*(gh|spec-kitty|python|\.venv/bin)\b", body, re.MULTILINE):
        body += f"\nVerify the gate itself:\n\n  {GATE_SELF_CHECK}\n\n"
    return body + CLOSING_BLOCK


def infrastructure_denial(headline: str, *why: str) -> str:
    """A denial for a fault in the gate itself, rather than a step the reader skipped."""
    return render_denial(
        headline,
        why=[
            *why,
            "",
            "This is a fault in the gate, not a step you skipped. A guard that fails open",
            "manufactures a green nobody earned, so an unreadable input is a denial rather",
            "than a pass.",
        ],
    )


def sweep_evidence_denial(missing: Sequence[str], satisfied: Sequence[str]) -> str:
    """FRESH / incomplete ledger: name each missing step and the query that produces it."""
    commands: list[str] = ["Run these, then retry:", ""]
    for marker_id in missing:
        commands.extend(f"  {line}" for line in MARKER_COMMANDS[marker_id])
        commands.append("")
    return render_denial(
        "this session has no §0 upstream-sweep evidence for "
        f"{len(missing)} of the {len(MARKER_ORDER)} required steps.",
        missing=[f"{name} — {MARKER_WHY[name]}" for name in missing],
        commands=commands[:-1] if commands[-1] == "" else commands,
        satisfied=satisfied,
        why=[
            "Why: measured 2026-08-24, 27 of the 54 upstream refs the register cites were",
            "already CLOSED upstream. A workaround applied to a fixed defect is not neutral —",
            "it adds steps, can mask the real behaviour, and teaches the next reader a false",
            "constraint. Closed is not the same as fixed-in-our-build: verify the symptom is",
            "gone before retiring a row.",
        ],
    )


def unreadable_ledger_denial(path: Path, error_class: str | None) -> str:
    """UNREADABLE: name the path and the error CLASS. Never the file's contents."""
    return render_denial(
        "this session's evidence ledger could not be read, so no step can be shown to have run.",
        missing=[f"{path.name} — {error_class or 'OSError'}"],
        commands=[
            "Check the path, then retry:",
            "",
            f"  {path}",
            "",
            "If it is unrecoverable, remove it and re-run the sweep:",
            "",
            f"  {GATE_SELF_CHECK}",
        ],
        why=[
            "This is not a missing step — it is a ledger this gate cannot read. Treating an",
            "unreadable ledger as an empty one would send you to re-run work that may already",
            "be recorded, and treating it as satisfied would be a pass over an unknown.",
        ],
    )


def corrupt_ledger_denial(path: Path, error_class: str | None) -> str:
    """CORRUPT: a DIFFERENT message from FRESH, because the remediation is different."""
    return render_denial(
        "this session's evidence ledger is corrupt, so no step can be shown to have run.",
        missing=[f"{path.name} — {error_class or 'malformed JSON'}"],
        commands=[
            "Delete the file, then re-run the sweep:",
            "",
            f"  rm {path}",
            # Derived, not hand-copied. This line WAS a hand-copied duplicate of the
            # first MARKER_COMMANDS entry, which is precisely how a rename strands one
            # remedy while the others are updated.
            *(
                f"  gh issue list --repo {target} --author @me --state all"
                for target in UPSTREAM_TARGETS
            ),
        ],
        why=[
            "A corrupt ledger is deliberately NOT overwritten by the recording path: an",
            "overwrite would erase the evidence that it was broken and hand the next call a",
            "clean pass. So it has to be removed on purpose.",
        ],
    )


def no_hooks_root_denial(detail: str) -> str:
    """The gate could not locate its own ledger, so it has established nothing."""
    return infrastructure_denial(
        "this gate could not locate its evidence ledger, so it cannot show any step ran.",
        f"  ✗ {detail}",
        "",
        "The ledger root is <git-common-dir>/spec-kitty-hooks/. Check that this is a git",
        "checkout and that `git rev-parse --git-common-dir` answers:",
        "",
        "  spec-kitty status   # any repo-aware command confirms the checkout is sane",
    )



def malformed_command_denial() -> str:
    return infrastructure_denial(
        "this command could not be tokenised (malformed quoting), so this gate cannot tell "
        "whether it is gated.",
        "  ✗ shlex could not find a closing quotation",
        "",
        "Quote the command so it parses, then retry.",
    )


# =============================================================================
# The shared ledger evaluator — the seam CP-BEFORE (WP04) calls
# =============================================================================


def evaluate_session_ledger(
    session_id: str,
    *,
    root: str | os.PathLike[str] | None = None,
    cwd: str | None = None,
) -> None:
    """Deny unless this session shows **all four** §0 markers (FR-011).

    Returns normally only on the allow path — every other branch calls :func:`deny` and
    exits. The all-four conjunction is a *spec* decision, not a measurement: each query
    buys something different, and the register read is what makes the third one
    interpretable. Weakening it changes what the gate means.
    """
    try:
        path = session_ledger_path(session_id, root=root, cwd=cwd)
        state, status, error_class = _read_detail(session_id, root=root, cwd=cwd)
    except HooksRootError as exc:
        deny(no_hooks_root_denial(str(exc)))

    if status is LedgerStatus.UNREADABLE:
        deny(unreadable_ledger_denial(path, error_class))
    if status is LedgerStatus.CORRUPT:
        deny(corrupt_ledger_denial(path, error_class))

    missing = missing_markers(state)
    if missing:
        deny(sweep_evidence_denial(missing, present_markers(state)))
    return None
