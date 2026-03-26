#!/usr/bin/env python3
"""
Canon v3 Documentation Validator
Validates frontmatter against allowed values and policy.
Lightweight: only checks frontmatter and secrets.
"""
import os, re, sys, json
from pathlib import Path

try:
    import yaml
except Exception:
    print('Missing deps: pip install pyyaml', file=sys.stderr)
    sys.exit(1)

ROOT = Path('.')
ERRORS = []
WARNINGS = []

# ---------- Load policy ----------
DEFAULT_POLICY = {
    'blockers': ['required_keys', 'enum_membership'],
    'advisories': ['formats', 'id_filename_match', 'key_order',
                   'whitespace', 'array_style', 'title_blankline', 'case_style'],
}

POLICY_FILE = ROOT / 'docs' / 'design' / 'standards' / 'validator-policy.json'
POLICY = DEFAULT_POLICY.copy()
if POLICY_FILE.exists():
    try:
        POLICY.update(json.loads(POLICY_FILE.read_text(encoding='utf-8')))
    except Exception as e:
        print(f"Warning: Could not load validator-policy.json: {e}", file=sys.stderr)

# ---------- Load allowed values ----------
ALLOWED_VALUES = {
    'doc_type': {'strategy','charter','decision','policy','handbook','runbook',
                 'guide','reference','readme','index','project','note'},
    'status': {'draft','in_review','approved','deprecated','archived'},
    'level': {'overview','concept','howto','reference','policy'},
    'audience': {'agents','humans','agents_and_humans'},
}

ALLOWED_FILE = ROOT / 'docs' / 'design' / 'standards' / 'allowed-values.json'
if ALLOWED_FILE.exists():
    try:
        for k, v in json.loads(ALLOWED_FILE.read_text(encoding='utf-8')).items():
            if isinstance(v, list):
                ALLOWED_VALUES[k] = set(v)
    except Exception as e:
        print(f"Warning: Could not load allowed-values.json: {e}", file=sys.stderr)

# ---------- Secret patterns ----------
SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'ASIA[0-9A-Z]{16}'),
    re.compile(r'ghp_[0-9A-Za-z]{36,}'),
    re.compile(r'xox[abp]-[0-9A-Za-z-]{20,}'),
    re.compile(r'-----BEGIN PRIVATE KEY-----'),
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
             'kitty-specs', '.agents', '.claude', '.codex', '.gemini',
             '.github'}

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

# ---------- 1) Frontmatter validation ----------
REQUIRED = ['title', 'doc_type', 'status']

for md in ROOT.rglob('*.md'):
    if any(seg in md.parts for seg in SKIP_DIRS):
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
    for field in ['doc_type', 'status', 'level', 'audience']:
        if field in fm and fm[field] not in ALLOWED_VALUES.get(field, set()):
            allowed = ', '.join(sorted(ALLOWED_VALUES.get(field, set())))
            err(f"Invalid {field} '{fm[field]}' (allowed: {allowed})", md,
                is_blocker=is_blocker('enum_membership'))

    # Format checks (advisory only)
    if 'owners' in fm:
        if not isinstance(fm['owners'], list) or len(fm['owners']) == 0:
            err("'owners' must be a non-empty array", md,
                is_blocker=is_blocker('formats'))

    if 'revision' in fm:
        if not isinstance(fm['revision'], str) or not re.match(r'^v\d+\.\d+$', fm['revision']):
            err(f"'revision' should be vMAJOR.MINOR format, got '{fm['revision']}'", md,
                is_blocker=is_blocker('formats'))

# ---------- 2) Secret scan ----------
for p in ROOT.rglob('*'):
    if p.is_dir():
        continue
    if any(seg in p.parts for seg in SKIP_DIRS):
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
