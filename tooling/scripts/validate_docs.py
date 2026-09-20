#!/usr/bin/env python3
"""
Canon v3 Documentation Validator
Validates frontmatter against allowed values and policy.
Lightweight: only checks frontmatter and secrets.

Modes:
  (default)   Full repo scan: frontmatter validation + secret scan over
              the working tree.
  --staged    Pre-commit hook mode: scan ONLY the added lines in the
              current staged diff for SECRET_PATTERNS. Fast (~under
              1 second on typical diffs). Skips frontmatter validation.
              Exits 1 if any pattern matches, 0 otherwise. Used by
              tooling/hooks/pre-commit (installed via
              scripts/install-hooks.sh).
"""
import os, re, sys, json, subprocess
from datetime import date
from pathlib import Path

try:
    import yaml
except Exception:
    print('Missing deps: pip install pyyaml', file=sys.stderr)
    sys.exit(1)

ROOT = Path('.')
ERRORS = []
WARNINGS = []
STAGED_MODE = '--staged' in sys.argv

# ---------- Load policy ----------
# `decision_log` is in the SAFE DEFAULT, not only in the policy file: a typo in
# validator-policy.json previously fell back to defaults that omitted it,
# silently demoting a blocker to nothing and letting the demotion be committed
# (#987 post-merge review F4).
DEFAULT_POLICY = {
    'blockers': ['required_keys', 'enum_membership', 'decision_log'],
    'advisories': ['formats', 'id_filename_match', 'key_order',
                   'whitespace', 'array_style', 'title_blankline', 'case_style'],
}

POLICY_FILE = ROOT / 'docs' / 'design' / 'standards' / 'validator-policy.json'
POLICY = DEFAULT_POLICY.copy()
if POLICY_FILE.exists():
    # Fail closed. A malformed policy is a defect in the gate itself; continuing
    # on fallbacks means enforcing rules nobody can read (same reasoning as the
    # taxonomy loader).
    try:
        _loaded = json.loads(POLICY_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"FATAL: {POLICY_FILE}: invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(_loaded, dict):
        print(f"FATAL: {POLICY_FILE}: top level must be an object", file=sys.stderr)
        sys.exit(2)
    for _k in ('blockers', 'advisories'):
        if _k in _loaded and not (
            isinstance(_loaded[_k], list) and all(isinstance(v, str) for v in _loaded[_k])
        ):
            print(f"FATAL: {POLICY_FILE}: '{_k}' must be a list of strings", file=sys.stderr)
            sys.exit(2)
    POLICY.update(_loaded)

# ---------- Load allowed values ----------
ALLOWED_VALUES = {
    'doc_type': {'strategy','charter','decision','design','plan','explanation','policy','handbook',
                 'postmortem','runbook','guide','reference','readme','index',
                 'project','note','func-spec','standard'},
    'status': {'draft','in_review','approved','deprecated','archived','active'},
    'level': {'overview','concept','howto','reference','policy','1',1,'2',2},
    'audience': {'agents','humans','agents_and_humans'},
}

ALLOWED_FILE = ROOT / 'docs' / 'design' / 'standards' / 'allowed-values.json'

# The taxonomy is loaded through the shared fail-closed loader (#987 FR-005).
# The previous inline parse warned and continued on built-in fallbacks, which
# meant this validator could enforce rules that differed from the ones on disk
# with nothing to indicate it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_taxonomy import TaxonomyError, load_taxonomy  # noqa: E402

try:
    TAXONOMY = load_taxonomy(ALLOWED_FILE)
except TaxonomyError as _exc:
    print(f"FATAL: {_exc}", file=sys.stderr)
    sys.exit(2)

# Every vocabulary this validator enforces must come from the source. Keeping a
# built-in fallback for a missing key would reintroduce exactly the silent
# divergence fail-closed loading removes (review finding F5).
for _k in ('doc_type', 'status', 'level', 'audience'):
    try:
        ALLOWED_VALUES[_k] = set(TAXONOMY.allowed(_k))
    except TaxonomyError as _exc:
        print(f"FATAL: {_exc}", file=sys.stderr)
        sys.exit(2)

# ---------- Secret patterns ----------
SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'ASIA[0-9A-Z]{16}'),
    re.compile(r'ghp_[0-9A-Za-z]{36,}'),
    re.compile(r'gho_[0-9A-Za-z]{36,}'),
    re.compile(r'github_pat_[0-9A-Za-z_]{20,}'),
    re.compile(r'xox[abp]-[0-9A-Za-z-]{20,}'),
    re.compile(r'-----BEGIN PRIVATE KEY-----'),
    re.compile(r'AIzaSy[0-9A-Za-z_-]{33}'),
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}'),
]

ALLOWLIST_FILE = ROOT / 'tooling' / 'ci-secret-scan-allowlist.txt'
def load_secret_allowlist():
    try:
        items = set()
        for ln in ALLOWLIST_FILE.read_text(encoding='utf-8').splitlines():
            ln = ln.strip()
            if ln and not ln.startswith('#'):
                items.add(ln.replace('\\', '/').lstrip('./'))
        return items
    except Exception:
        return set()

EXCLUDE_SECRET_SCAN = load_secret_allowlist() or {'tooling/scripts/validate_docs.py'}

# ---------- Helpers ----------
SKIP_DIRS = {'.git', 'node_modules', '.venv', '_templates', '.obsidian',
             '.obsidian-shared', '_templater-scripts', 'archive', '.kittify',
             'kitty-specs', '.agents', '.claude', '.codex', '.codex-tmp-home',
             '.gemini', '.github', 'scripts', 'research', 'diagnostics',
             '.pytest_cache', 'temp', 'tests', '.worktrees', 'dist'}
# 'dist' is gitignored generated output. spec-kitty 3.2.6 projects managed tool
# surfaces into dist/spec-kitty-plugins/ (see kentonium3/kg-automation#962); those
# files can never be committed, so holding them to our frontmatter contract only
# blocks commits. Deliberately NOT added to SECRET_SCAN_SKIP_DIRS below.

# Directories the SECRET scanner skips. NOTE: 'archive' is intentionally
# NOT in this set — archived docs are still committed to the public repo
# and must be scanned. A 2026-04-08 leak of a Google API key into
# docs/archive/openclaw-runtime-state-audit.md remained undetected for a
# month because the secret scanner reused SKIP_DIRS.
SECRET_SCAN_SKIP_DIRS = {'.git', 'node_modules', '.venv', '.kittify',
                         '.codex-tmp-home', '.pytest_cache', 'temp', '.worktrees',
                         '__pycache__'}  # gitignored build artifacts; .pyc bytecode false-positives (#619)

def is_blocker(check_type):
    return check_type in POLICY.get('blockers', [])

def err(msg, path=None, is_blocker=True):
    full = f"{path}: {msg}" if path else msg
    (ERRORS if is_blocker else WARNINGS).append(full)

def front_matter(p):
    txt = Path(p).read_text(encoding='utf-8', errors='ignore')
    txt = txt.replace("\r\n", "\n").lstrip("\ufeff \t\r\n")
    if not txt.startswith('---'):
        err('Missing YAML front-matter', p)
        return None
    try:
        lines = txt.splitlines()
        end = None
        for i in range(1, min(len(lines), 500)):
            if lines[i].strip() == '---':
                end = i
                break
        if end is None:
            err("Front-matter closing '---' not found", p)
            return None
        return yaml.safe_load('\n'.join(lines[1:end])) or {}
    except Exception as e:
        err(f"Front-matter parse error: {e}", p)
        return None

# ---------- Staged-mode: pre-commit hook secret scan ----------
# When invoked with --staged, scan only the added lines in the current
# staged diff against SECRET_PATTERNS, then exit. Skips frontmatter
# validation entirely. Designed for use by tooling/hooks/pre-commit.
def secret_scan_staged():
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--no-color', '-U0', '--diff-filter=ACM'],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        print('ERROR: git not found on PATH', file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f'ERROR: git diff --cached failed: {e.stderr.strip()}', file=sys.stderr)
        sys.exit(2)

    findings = []
    current_file = None
    line_in_file = 0
    hunk_re = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')

    for raw in result.stdout.splitlines():
        if raw.startswith('+++ '):
            # File header: '+++ b/<path>' or '+++ /dev/null' (deletion — won't appear under ACM)
            path = raw[4:].strip()
            current_file = path[2:] if path.startswith('b/') else path
            line_in_file = 0
            continue
        if raw.startswith('--- '):
            continue
        if raw.startswith('@@'):
            m = hunk_re.match(raw)
            if m:
                # Set to one less than the new-side start; we'll increment
                # on the first '+' line.
                line_in_file = int(m.group(1)) - 1
            continue
        if raw.startswith('+') and not raw.startswith('+++'):
            line_in_file += 1
            content = raw[1:]
            # Don't self-flag this scanner's pattern definitions.
            if 're.compile' in content or 'SECRET_PATTERNS' in content:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(content):
                    findings.append((current_file, line_in_file, content[:120]))
                    break

    if findings:
        print('Pre-commit blocked: potential secret patterns in staged content.', file=sys.stderr)
        print('', file=sys.stderr)
        for path, lineno, snippet in findings:
            print(f'  {path}:{lineno}: {snippet.strip()}', file=sys.stderr)
        print('', file=sys.stderr)
        print(f'{len(findings)} match(es). Inspect the staged diff and either:', file=sys.stderr)
        print('  (a) Remove the secret and re-stage, OR', file=sys.stderr)
        print('  (b) If it is a false positive, add the path to tooling/ci-secret-scan-allowlist.txt', file=sys.stderr)
        print('      (only for non-secret literal patterns — e.g., scanner self-tests).', file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if STAGED_MODE:
    secret_scan_staged()
    # secret_scan_staged() always exits; this is unreachable.


# ---------- Decision-log contract (#987 FR-001..FR-003) ----------
# Applies to every `doc_type: decision` document — ADRs and RFCs alike. The log
# records how a decision reached its current standing; it carries NO authority
# of its own, which is why only `Type` is a controlled vocabulary and the rest
# is prose for humans.
DECISION_LOG_HEADING = '## Decision log'
DECISION_LOG_EMPTY = '*No entries.*'
DECISION_LOG_TYPES = {'erratum', 'amendment', 'superseded-by', 'context'}
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _is_iso_date(value):
    """Canonical YYYY-MM-DD *and* a real calendar date (finding F4)."""
    if not _ISO_DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _split_markdown_row(row):
    """Split a decision-log row on unescaped pipes.

    The decision log is *our* format, authored and generated by us, so the
    grammar is narrowed rather than the parser widened: a literal pipe inside a
    cell must be escaped as ``\\|`` — standard Markdown practice anyway. That
    removes the code-span state machine, which is where three rounds of review
    kept finding edge cases (multi-backtick spans, unmatched backticks). Only
    ``\\|`` is an escape; ``\\a`` stays two characters, so a typo like
    ``err\\atum`` can no longer normalise into a valid Type.
    """
    cells, buf, i = [], [], 0
    while i < len(row):
        if row[i] == '\\' and i + 1 < len(row) and row[i + 1] == '|':
            buf.append('|')
            i += 2
            continue
        if row[i] == '|':
            cells.append(''.join(buf))
            buf = []
            i += 1
            continue
        buf.append(row[i])
        i += 1
    cells.append(''.join(buf))
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.strip() for c in cells]


#: A fence delimiter. Per CommonMark a backtick fence's info string may not
#: contain a backtick — accepting one as an opener could hide the real log.
_FENCE_ANY = re.compile(r'^ {0,3}(?:(?P<b>`{3,})(?P<bi>[^`]*)|(?P<t>~{3,})(?P<ti>.*))$')


def _indent_columns(line, tab_width=4):
    """Leading indentation in COLUMNS, expanding tabs.

    CommonMark treats a leading tab as an indented code block. Testing
    ``startswith('    ')`` missed that, so a tab-indented ``## Decision log``
    inside a code example read as a real section — rejecting a legitimate
    document as having two logs, or letting code satisfy validation when the
    real log was absent (#987 post-merge review F3).
    """
    cols = 0
    for ch in line:
        if ch == ' ':
            cols += 1
        elif ch == '\t':
            cols += tab_width - (cols % tab_width)
        else:
            break
    return cols


def _strip_fenced(lines):
    """Blank out fenced-block content so it cannot satisfy validation.

    Also blanks 4-space indented code blocks, which are code, not headings —
    an indented ``## Decision log`` previously looked like a real section.
    """
    out, fence = [], None
    for ln in lines:
        m = _FENCE_ANY.match(ln)
        if m:
            delim = m.group('b') or m.group('t')
            char, length = delim[0], len(delim)
            if fence is None:
                out.append('')
                fence = (char, length)
                continue
            # A closer must be bare and at least as long, with the same char.
            bare = ln.strip() == delim or re.fullmatch(rf'{re.escape(char)}{{{length},}}', ln.strip())
            if char == fence[0] and len(ln.strip()) >= fence[1] and bare:
                fence = None
            out.append('')
            continue
        if fence is not None:
            out.append('')
            continue
        out.append('' if _indent_columns(ln) >= 4 else ln)
    return out


def check_decision_log(md, fm, text):
    """Validate the decision log of one decision document.

    Enforcement is policy-gated as 'decision_log' so it can land before the
    corpus migration (WP05) without turning the repo red; it is promoted to a
    blocker once every decision document carries a log.

    Deliberately strict about GRAMMAR, because this validator gates every commit
    and a fuzzy parser produces either false positives that block work or false
    negatives that defeat the contract. Two forms are legal: the placeholder
    alone, or an OPTIONAL blockquote preamble followed by a contiguous
    header/separator/data table — and nothing else in the section, and nothing
    after the table.
    """
    blocking = is_blocker('decision_log')
    raw_lines = text.replace('\r\n', '\n').split('\n')
    # Fenced content must not be able to SATISFY validation (cycle-1 F2)...
    lines = _strip_fenced(raw_lines)

    heads = [i for i, ln in enumerate(lines) if ln.strip() == DECISION_LOG_HEADING]
    if len(heads) != 1:
        err(f"expected exactly one '{DECISION_LOG_HEADING}' section, found {len(heads)}",
            md, is_blocker=blocking)
        return

    head = heads[0]
    later = [i for i in range(head + 1, len(lines)) if lines[i].startswith('#')]
    if later:
        err(f"'{DECISION_LOG_HEADING}' must be the last section; found a heading after it "
            f"({lines[later[0]].strip()[:40]})", md, is_blocker=blocking)
        return

    raw_tail = [ln.rstrip() for ln in lines[head + 1:]]
    while raw_tail and not raw_tail[0].strip():
        raw_tail.pop(0)
    while raw_tail and not raw_tail[-1].strip():
        raw_tail.pop()
    # Blank lines *inside* the section are only legal before the table starts;
    # a blank between rows means the table is not contiguous.
    body = [ln for ln in raw_tail if ln.strip()]
    rows_only = [ln for ln in body if not ln.lstrip().startswith('>')]
    blank_between_rows = False
    seen_row = False
    for ln in raw_tail:
        if ln.lstrip().startswith('|'):
            if seen_row and blank_between_rows:
                break
            seen_row = True
        elif seen_row and not ln.strip():
            blank_between_rows = True
    if rows_only and rows_only[0].lstrip().startswith('|') and blank_between_rows:
        err(f"'{DECISION_LOG_HEADING}' table must be contiguous; found a blank line between rows",
            md, is_blocker=blocking)
        return
    if not body:
        err(f"'{DECISION_LOG_HEADING}' is empty; use '{DECISION_LOG_EMPTY}' when there are no entries",
            md, is_blocker=blocking)
        return

    # A blockquote preamble is allowed ahead of EITHER form. Frozen ADRs that
    # carry a legacy changes-log section need a closure note pointing future
    # entries here, and those logs are empty (#987 post-merge review F7).
    while body and body[0].lstrip().startswith('>'):
        body.pop(0)
    if not body:
        err(f"'{DECISION_LOG_HEADING}' has a note but no entries; use '{DECISION_LOG_EMPTY}'",
            md, is_blocker=blocking)
        return

    # The empty form is a distinct grammar: the placeholder and nothing else.
    if body[0].strip() == DECISION_LOG_EMPTY:
        if len(body) > 1:
            err(f"'{DECISION_LOG_EMPTY}' must be the only content in the section; found "
                f"{len(body) - 1} more line(s)", md, is_blocker=blocking)
        if fm.get('status') == 'superseded':
            err("status is 'superseded' but the decision log has no 'superseded-by' row naming "
                "the successor", md, is_blocker=blocking)
        return

    non_rows = [ln for ln in body if not ln.lstrip().startswith('|')]
    if non_rows:
        err(f"'{DECISION_LOG_HEADING}' must be '{DECISION_LOG_EMPTY}', or an optional blockquote "
            f"note followed by a table and nothing else; found: {non_rows[0].strip()[:40]}",
            md, is_blocker=blocking)
        return
    if len(body) < 3:
        err(f"'{DECISION_LOG_HEADING}' table needs a header, a separator and at least one entry",
            md, is_blocker=blocking)
        return

    header = _split_markdown_row(body[0])
    if [h.lower() for h in header] != ['date', 'type', 'by', 'summary', 'refs']:
        err(f"decision-log header must be | Date | Type | By | Summary | Refs |, got {header}",
            md, is_blocker=blocking)
        return
    sep = _split_markdown_row(body[1])
    if len(sep) != len(header) or not all(set(c) <= set('-: ') and '-' in c for c in sep):
        err(f"decision-log separator row is malformed or has {len(sep)} columns, "
            f"expected {len(header)}", md, is_blocker=blocking)
        return

    # ...but blanking it must not let it HIDE either: a fenced block after the
    # table was silently tolerated, though the contract says nothing may follow
    # it (cycle-2 F2). Compare against the raw text, not the stripped copy.
    last_row = max(i for i, ln in enumerate(raw_lines) if ln.lstrip().startswith('|'))
    trailing = [ln for ln in raw_lines[last_row + 1:] if ln.strip()]
    if trailing:
        err(f"'{DECISION_LOG_HEADING}' must end with the table; found content after it: "
            f"{trailing[0].strip()[:40]}", md, is_blocker=blocking)
        return

    saw_superseded_by = False
    for row in body[2:]:
        cells = _split_markdown_row(row)
        if len(cells) != 5:
            err(f"decision-log row has {len(cells)} columns, expected 5 "
                f"(Date, Type, By, Summary, Refs) — escape any literal pipe as \\|: "
                f"{row.strip()[:60]}",
                md, is_blocker=blocking)
            continue
        date_cell, kind = cells[0], cells[1]
        if not _is_iso_date(date_cell):
            err(f"decision-log date '{date_cell}' is not a real ISO YYYY-MM-DD date",
                md, is_blocker=blocking)
        if kind not in DECISION_LOG_TYPES:
            err(f"decision-log Type '{kind}' is not one of "
                f"{', '.join(sorted(DECISION_LOG_TYPES))}", md, is_blocker=blocking)
        if kind == 'superseded-by':
            saw_superseded_by = True

    # `superseded-by` and `status: superseded` are set together; neither is
    # meaningful alone (contracts/decision-log-contract.md rule 5).
    if saw_superseded_by and fm.get('status') != 'superseded':
        err("decision log has a 'superseded-by' row but status is "
            f"'{fm.get('status')}' (expected 'superseded')", md, is_blocker=blocking)
    if fm.get('status') == 'superseded' and not saw_superseded_by:
        err("status is 'superseded' but the decision log has no 'superseded-by' row naming the "
            "successor", md, is_blocker=blocking)


# ---------- 1) Frontmatter validation ----------
REQUIRED = ['title', 'doc_type', 'status']

#: Categories under docs/ that are skipped for general frontmatter validation
#: but still hold real documents. A `doc_type: decision` file here is governed
#: like any other (#987 post-merge review F1) — the migrated RFC lives in
#: docs/design/research/, which is in SKIP_DIRS, so it was unguarded.
#:
#: The exemption is deliberately narrow: it applies only under docs/, so the
#: spec-kitty-owned trees (kitty-specs/, .kittify/, .agents/, .claude/,
#: .codex/, dist/ — all top-level) are never frontmatter-read, preserving
#: C-001. `archive` stays excluded because it is frozen history, and
#: `_templates` because a template is not a document.
DECISION_SCAN_EXCLUDE = {'archive', '_templates'}


def _is_decision_doc_in_skipped_category(md):
    """True for a decision document that general validation would have skipped.

    Deliberately does NOT call ``front_matter`` — that reports missing or
    malformed frontmatter as findings, so probing every skipped file would
    manufacture errors for documents nobody asked us to validate. This reads
    the ``doc_type`` line directly and answers only that question.
    """
    try:
        rel = md.relative_to(ROOT).parts
    except ValueError:
        return False
    # Must be under THIS repository's own docs/ tree. A nested `docs` directory
    # elsewhere (e.g. .agents/*/docs/) is not ours to police, and anchoring at
    # rel[0] is also what keeps the spec-kitty trees unread (C-001).
    if not rel or rel[0] != 'docs' or DECISION_SCAN_EXCLUDE & set(rel):
        return False
    try:
        head = md.read_text(encoding='utf-8', errors='ignore')[:2000]
    except OSError:
        return False
    if not head.lstrip('\ufeff \t\r\n').startswith('---'):
        return False
    return bool(re.search(r'^doc_type:\s*decision\s*$', head, re.M))


for md in ROOT.rglob('*.md'):
    if any(seg in md.parts for seg in SKIP_DIRS) and not _is_decision_doc_in_skipped_category(md):
        continue

    fm = front_matter(md)
    if not isinstance(fm, dict):
        continue

    # Required fields
    for k in REQUIRED:
        if k not in fm:
            err(f"Missing required field '{k}'", md,
                is_blocker=is_blocker('required_keys'))

    # Enum validation (only check if field is present)
    for field in ['doc_type', 'level', 'audience']:
        if field in fm and fm[field] not in ALLOWED_VALUES.get(field, set()):
            # 'level' allows both string and int forms ('1', 1, '2', 2) per
            # allowed-values.json — sort needs a str key to avoid TypeError on mixed.
            allowed = ', '.join(sorted((str(v) for v in ALLOWED_VALUES.get(field, set()))))
            err(f"Invalid {field} '{fm[field]}' (allowed: {allowed})", md,
                is_blocker=is_blocker('enum_membership'))

    # status is scoped by doc_type (#987 FR-004): a decision record may carry
    # `superseded`, an ordinary document may not, and `active` is meaningless
    # for a decision. The message names the doc_type and ITS permitted set —
    # naming the union would send the author to the wrong list.
    if 'status' in fm:
        doc_type = fm.get('doc_type')
        permitted = TAXONOMY.statuses_for(doc_type if isinstance(doc_type, str) else None)
        if fm['status'] not in permitted:
            scope = 'own set' if TAXONOMY.is_scoped(doc_type) else 'default scope'
            err(
                f"Invalid status '{fm['status']}' for doc_type '{doc_type}' ({scope}) "
                f"(allowed: {', '.join(permitted)})",
                md, is_blocker=is_blocker('enum_membership'))

    # Format checks (advisory only)
    if 'owners' in fm:
        if not isinstance(fm['owners'], list) or len(fm['owners']) == 0:
            err("'owners' must be a non-empty array", md,
                is_blocker=is_blocker('formats'))

    if 'revision' in fm:
        if not isinstance(fm['revision'], str) or not re.match(r'^v\d+\.\d+$', fm['revision']):
            err(f"'revision' should be vMAJOR.MINOR format, got '{fm['revision']}'", md,
                is_blocker=is_blocker('formats'))

    if fm.get('doc_type') == 'decision':
        check_decision_log(md, fm, md.read_text(encoding='utf-8', errors='ignore'))

# ---------- 2) Secret scan ----------
# Uses SECRET_SCAN_SKIP_DIRS (narrower than SKIP_DIRS) — scans archive/,
# kitty-specs/, .github/, scripts/, and similar that frontmatter validation
# skips. Anything committed to the public repo must be scanned.
for p in ROOT.rglob('*'):
    if p.is_dir():
        continue
    if any(seg in p.parts for seg in SECRET_SCAN_SKIP_DIRS):
        continue
    rel = str(p).replace('\\', '/').lstrip('./')
    if rel in EXCLUDE_SECRET_SCAN:
        continue
    try:
        txt = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    for lineno, line in enumerate(txt.splitlines(), start=1):
        if 're.compile' in line or 'SECRET_PATTERNS' in line:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(line):
                err(f"Potential secret pattern in {p}:{lineno}")
                break

# ---------- 3) Developer-portal runbook-filter drift check ----------
# Gated on docs/DEVELOPER_PORTAL.md existing so older branches and CI runs on
# unrelated refs still pass. Implementation note: invoked via subprocess
# (rather than direct import) to avoid coupling validate_docs to
# build_runbook_filter's module-level state and to keep this hook a thin
# shell that can be swapped or removed without refactoring imports.
PORTAL_PATH = ROOT / 'docs' / 'DEVELOPER_PORTAL.md'
FILTER_SCRIPT = ROOT / 'tooling' / 'scripts' / 'build_runbook_filter.py'
if PORTAL_PATH.exists() and FILTER_SCRIPT.exists():
    try:
        result = subprocess.run(
            [sys.executable, str(FILTER_SCRIPT)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
    except Exception as e:
        err(f"Portal drift check could not run: {e}",
            is_blocker=is_blocker('required_keys'))
    else:
        if result.returncode != 0:
            # build_runbook_filter prints a unified diff on stdout and the
            # run-hint as its final stdout line; mirror that to validate_docs
            # so contributors can copy-paste the fix.
            err(
                "Developer portal runbook-filter block is stale. "
                "run: python tooling/scripts/build_runbook_filter.py --write",
                path=str(PORTAL_PATH),
                is_blocker=is_blocker('required_keys'),
            )

# ---------- Report ----------
if WARNINGS:
    print("Warnings (non-blocking):")
    for w in WARNINGS:
        print(f"  WARN: {w}")
    print()

if ERRORS:
    print('\n'.join(str(e) for e in ERRORS))
    sys.exit(1)
else:
    print('validate_docs: OK')
