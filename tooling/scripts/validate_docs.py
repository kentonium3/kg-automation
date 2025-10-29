#!/usr/bin/env python3
"""
Canon v2 Documentation Validator
Validates frontmatter against machine-readable schema and allowed values.
"""
import os, re, sys, json, subprocess
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft7Validator, Draft202012Validator
except Exception as e:
    print('Missing deps: pip install pyyaml jsonschema', file=sys.stderr)
    sys.exit(1)

ROOT = Path('.')
ERRORS = []

# Fallback allowed values (overridden by docs/standards/allowed-values.json if present)
ALLOWED_VALUES = {
    'doc_type': {'strategy','charter','decision','policy','handbook','runbook','guide','reference','readme','index','project','note'},
    'level': {'overview','concept','howto','reference','policy'},
    'status': {'draft','in_review','approved','deprecated','archived'},
    'audience': {'agents','humans','agents_and_humans'}
}

# Load allowed values from JSON if available
ALLOWED_VALUES_FILE = ROOT / 'docs' / 'standards' / 'allowed-values.json'
if ALLOWED_VALUES_FILE.exists():
    try:
        with open(ALLOWED_VALUES_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            # Convert lists to sets for validation
            for key, values in loaded.items():
                if isinstance(values, list):
                    ALLOWED_VALUES[key] = set(values)
    except Exception as e:
        print(f"Warning: Could not load allowed-values.json: {e}", file=sys.stderr)

# Legacy compatibility - keep old constants for non-doc validation
DOC_TYPES = ALLOWED_VALUES.get('doc_type', set())
LEVELS = ALLOWED_VALUES.get('level', set())
STATUSES = ALLOWED_VALUES.get('status', set())

HANDOFF_PATTERN = re.compile(r'^[0-9]{8}-[0-9]{4,6}-[0-9]+-[a-z]+-to-[a-z]+-(request|response)\.json$')

SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'ASIA[0-9A-Z]{16}'),
    re.compile(r'ghp_[0-9A-Za-z]{36,}'),
    re.compile(r'xox[abp]-[0-9A-Za-z-]{20,}'),
    re.compile(r'-----BEGIN PRIVATE KEY-----')
]

SCHEMAS = {
    'workflow': ROOT / 'tooling/schemas/workflow.schema.yaml',
    'runbook': ROOT / 'tooling/schemas/runbook.schema.yaml',
    'handoff': ROOT / 'ai-agents/shared/contracts/ai-handoff.schema.json'
}

ALLOWLIST_FILE = ROOT / 'tooling' / 'ci-secret-scan-allowlist.txt'

def load_secret_allowlist():
    try:
        lines = ALLOWLIST_FILE.read_text(encoding='utf-8').splitlines()
        items = set()
        for ln in lines:
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            items.add(ln.replace('\\', '/').lstrip('./'))
        return items
    except Exception:
        return set()

EXCLUDE_SECRET_SCAN = load_secret_allowlist() or {'tooling/scripts/validate_docs.py'}


# ---------- helpers ----------

def err(msg, path=None):
    if path: msg = f"{path}: {msg}"
    ERRORS.append(msg)


def load_yaml(p):
    try:
        return yaml.safe_load(Path(p).read_text(encoding='utf-8'))
    except Exception as e:
        err(f"YAML parse error: {e}", p)
        return None


def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception as e:
        err(f"JSON parse error: {e}", p)
        return None


def front_matter(p):
    """Extract YAML frontmatter from markdown file."""
    txt = Path(p).read_text(encoding='utf-8', errors='ignore')
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
        fm_txt = '\n'.join(lines[1:end])
        return yaml.safe_load(fm_txt) or {}
    except Exception as e:
        err(f"Front-matter parse error: {e}", p)
        return None


def validate_iso_date(date_str):
    """Validate YYYY-MM-DD format."""
    if not isinstance(date_str, str):
        return False
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', date_str))


def validate_revision(rev_str):
    """Validate vMAJOR.MINOR format."""
    if not isinstance(rev_str, str):
        return False
    return bool(re.match(r'^v\d+\.\d+$', rev_str))


def validate_kebab_case(s):
    """Validate kebab-case format."""
    if not isinstance(s, str):
        return False
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', s))


# ---------- 1) Markdown front-matter validation (Canon v2) ----------
ids = {}
for md in ROOT.rglob('*.md'):
    if any(seg in md.parts for seg in ['.git','node_modules','.venv','_templates']):
        continue

    fm = front_matter(md)
    if not isinstance(fm, dict):
        continue

    # Canon v2 required fields
    required = ['id','title','doc_type','level','status','owners','last_updated','revision','audience']
    for k in required:
        if k not in fm:
            err(f"Missing front-matter key '{k}'", md)

    # Validate doc_type against allowed values
    if 'doc_type' in fm:
        if fm['doc_type'] not in ALLOWED_VALUES.get('doc_type', set()):
            err(f"Invalid doc_type '{fm['doc_type']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('doc_type', set())))})", md)

    # Validate level against allowed values
    if 'level' in fm:
        if fm['level'] not in ALLOWED_VALUES.get('level', set()):
            err(f"Invalid level '{fm['level']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('level', set())))})", md)

    # Validate status against allowed values
    if 'status' in fm:
        if fm['status'] not in ALLOWED_VALUES.get('status', set()):
            err(f"Invalid status '{fm['status']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('status', set())))})", md)

    # Validate audience against allowed values
    if 'audience' in fm:
        if fm['audience'] not in ALLOWED_VALUES.get('audience', set()):
            err(f"Invalid audience '{fm['audience']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('audience', set())))})", md)

    # Validate owners is non-empty array
    if 'owners' in fm:
        if not isinstance(fm['owners'], list) or len(fm['owners']) == 0:
            err(f"'owners' must be a non-empty array", md)

    # Validate last_updated is ISO date
    if 'last_updated' in fm:
        if not validate_iso_date(fm['last_updated']):
            err(f"'last_updated' must be in YYYY-MM-DD format, got '{fm['last_updated']}'", md)

    # Validate revision is vMAJOR.MINOR
    if 'revision' in fm:
        if not validate_revision(fm['revision']):
            err(f"'revision' must be in vMAJOR.MINOR format, got '{fm['revision']}'", md)

    # Validate id is kebab-case and matches filename stem
    if 'id' in fm:
        if not validate_kebab_case(fm['id']):
            err(f"'id' must be kebab-case, got '{fm['id']}'", md)

        # Check id matches filename stem (normalized to kebab-case)
        filename_stem = md.stem.lower().replace('_', '-')
        if fm['id'] != filename_stem:
            err(f"'id' ('{fm['id']}') must match filename stem ('{filename_stem}' from '{md.stem}')", md)

        # Track for duplicate detection
        ids.setdefault(fm['id'], []).append(str(md))

# Check for duplicate IDs
for doc_id, paths in ids.items():
    if len(paths) > 1:
        err(f"Duplicate id '{doc_id}' across: {paths}")

# ---------- 2) Workflows schema ----------
if SCHEMAS['workflow'].exists():
    wf_schema = load_yaml(SCHEMAS['workflow'])
    if wf_schema:
        wf_validator = Draft7Validator(wf_schema)
        workflows_dir = ROOT / 'workflows'
        if workflows_dir.exists():
            for y in workflows_dir.glob('*.yaml'):
                data = load_yaml(y)
                if data is None:
                    continue
                for e in wf_validator.iter_errors(data):
                    err(f"workflow schema: {e.message}", y)

# ---------- 3) Systems basic check ----------
systems_dir = ROOT / 'systems'
if systems_dir.exists():
    for syml in systems_dir.glob('*/system.yaml'):
        data = load_yaml(syml)
        if not isinstance(data, dict):
            continue
        for k in ['id','name','owners','status','last_validated']:
            if k not in data:
                err(f"system.yaml missing '{k}'", syml)

# ---------- 4) Handoffs validation ----------
if SCHEMAS['handoff'].exists():
    h_schema = load_json(SCHEMAS['handoff'])
    if h_schema:
        h_validator = Draft7Validator(h_schema)
        handoffs_dir = ROOT / 'ai-agents' / 'shared' / 'handoffs'
        if handoffs_dir.exists():
            for jf in handoffs_dir.glob('*.json'):
                if not HANDOFF_PATTERN.match(jf.name):
                    err(f"handoff filename violates convention: {jf.name}", jf)
                data = load_json(jf)
                if data is None:
                    continue
                for e in h_validator.iter_errors(data):
                    err(f"handoff schema: {e.message}", jf)

# ---------- 5) Simple secret scan ----------
for p in ROOT.rglob('*'):
    if p.is_dir():
        continue
    if any(seg in p.parts for seg in ['.git', 'node_modules', '.venv', '.docgraph']):
        continue

    rel = str(p).replace('\\', '/').lstrip('./')
    if rel in EXCLUDE_SECRET_SCAN:
        continue

    try:
        txt = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue

    hit = False
    for lineno, line in enumerate(txt.splitlines(), start=1):
        if 're.compile' in line or 'SECRET_PATTERNS' in line:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(line):
                err(f"Potential secret pattern in {p}:{lineno}")
                hit = True
                break
        if hit:
            break

# ---------- 6) Mermaid wrapper sync check ----------
def _run_mermaid_sync_check():
    sync_script = ROOT / "tooling" / "scripts" / "sync_mermaid_views.py"
    if not sync_script.exists():
        return
    cmd = [sys.executable, str(sync_script), "--check"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            if res.stdout.strip():
                print(res.stdout.strip())
            if res.stderr.strip():
                print(res.stderr.strip())
            err("docs/diagrams: wrapper drift detected (run sync_mermaid_views.py --write)")
    except Exception as e:
        err(f"failed to run mermaid sync check: {e}")

_run_mermaid_sync_check()

# ---------- report ----------
if ERRORS:
    print('\n'.join(str(e) for e in ERRORS))
    sys.exit(1)
else:
    print('validate_docs: OK')
