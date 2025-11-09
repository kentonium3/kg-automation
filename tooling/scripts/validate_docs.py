#!/usr/bin/env python3
"""
Canon v2 Documentation Validator
Validates frontmatter against machine-readable schema and allowed values.
Respects validator-policy.json for blocking vs advisory checks.
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
WARNINGS = []

# Default policy (overridden by docs/standards/validator-policy.json if present)
DEFAULT_POLICY = {
    'blockers': ['required_keys', 'enum_membership', 'formats', 'id_filename_match'],
    'advisories': ['key_order', 'whitespace', 'array_style', 'title_blankline', 'case_style'],
    'id_match_case_sensitive': False,
    'autofix_on_run': True
}

# Load validator policy
POLICY_FILE = ROOT / 'docs' / 'standards' / 'validator-policy.json'
POLICY = DEFAULT_POLICY.copy()
if POLICY_FILE.exists():
    try:
        with open(POLICY_FILE, 'r', encoding='utf-8') as f:
            loaded_policy = json.load(f)
            POLICY.update(loaded_policy)
    except Exception as e:
        print(f"Warning: Could not load validator-policy.json: {e}", file=sys.stderr)

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

def err(msg, path=None, is_blocker=True):
    """Add error or warning based on blocker status."""
    if path: msg = f"{path}: {msg}"
    if is_blocker:
        ERRORS.append(msg)
    else:
        WARNINGS.append(msg)


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
    # tolerate UTF-8 BOM and leading whitespace/newlines before the fence
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


def validate_kebab_case(s, allow_dots=False):
    """Validate kebab-case format.

    Args:
        s: String to validate
        allow_dots: If True, allow dots in addition to hyphens (for .view files)
    """
    if not isinstance(s, str):
        return False
    if allow_dots:
        # Allow lowercase letters, numbers, hyphens, and dots
        return bool(re.match(r'^[a-z0-9]+([-.][a-z0-9]+)*$', s))
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', s))


def normalize_to_kebab(s):
    """Normalize string to kebab-case (lowercase with hyphens)."""
    if not isinstance(s, str):
        return s
    # Convert to lowercase and replace underscores/spaces with hyphens
    return re.sub(r'[_\s]+', '-', s.lower())


def is_blocker(check_type):
    """Check if a validation type is a blocker based on policy."""
    return check_type in POLICY.get('blockers', [])


# ---------- 1) Markdown front-matter validation (Canon v2) ----------
ids = {}
for md in ROOT.rglob('*.md'):
    if any(seg in md.parts for seg in ['.git','node_modules','.venv','_templates']):
        continue

    fm = front_matter(md)
    if not isinstance(fm, dict):
        continue

    # Canon v2 required fields (note: last_updated/last_validated checked separately below)
    required = ['id','title','doc_type','level','status','owners','revision','audience']
    for k in required:
        if k not in fm:
            err(f"Missing front-matter key '{k}'", md, is_blocker=is_blocker('required_keys'))

    # Validate doc_type against allowed values
    if 'doc_type' in fm:
        if fm['doc_type'] not in ALLOWED_VALUES.get('doc_type', set()):
            err(f"Invalid doc_type '{fm['doc_type']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('doc_type', set())))})", md, is_blocker=is_blocker('enum_membership'))

    # Validate level against allowed values
    if 'level' in fm:
        if fm['level'] not in ALLOWED_VALUES.get('level', set()):
            err(f"Invalid level '{fm['level']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('level', set())))})", md, is_blocker=is_blocker('enum_membership'))

    # Validate status against allowed values
    if 'status' in fm:
        if fm['status'] not in ALLOWED_VALUES.get('status', set()):
            err(f"Invalid status '{fm['status']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('status', set())))})", md, is_blocker=is_blocker('enum_membership'))

    # Validate audience against allowed values
    if 'audience' in fm:
        if fm['audience'] not in ALLOWED_VALUES.get('audience', set()):
            err(f"Invalid audience '{fm['audience']}' (allowed: {', '.join(sorted(ALLOWED_VALUES.get('audience', set())))})", md, is_blocker=is_blocker('enum_membership'))

    # Validate owners is non-empty array
    if 'owners' in fm:
        if not isinstance(fm['owners'], list) or len(fm['owners']) == 0:
            err(f"'owners' must be a non-empty array", md, is_blocker=is_blocker('required_keys'))

    # Validate last_updated and last_validated (dual date policy)
    # Accept quoted or unquoted dates; require at least one; warn if validation is stale
    from datetime import date, timedelta

    def normalize_date_value(val):
        """Normalize date value to string (handles YAML date objects and quoted strings)."""
        if val is None:
            return None
        # YAML may parse unquoted YYYY-MM-DD as date object
        if isinstance(val, date):
            return val.strftime('%Y-%m-%d')
        if isinstance(val, str):
            return val.strip().strip('"').strip("'")
        return str(val)

    def parse_iso_date(val):
        """Parse YYYY-MM-DD date, handling YAML date objects and quoted strings."""
        if val is None:
            return None
        # Handle YAML date objects directly
        if isinstance(val, date):
            return val
        # Handle strings
        s = normalize_date_value(val)
        if not isinstance(s, str):
            return None
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return None
        try:
            y, m, d = map(int, s.split('-'))
            return date(y, m, d)
        except:
            return None

    # Get both date fields
    last_updated_raw = fm.get('last_updated')
    last_validated_raw = fm.get('last_validated')

    # Require at least one date field
    if not last_updated_raw and not last_validated_raw:
        err(f"Missing required date field: must have 'last_updated' or 'last_validated' (or both)", md, is_blocker=is_blocker('required_keys'))

    # Validate last_updated format if present
    if last_updated_raw:
        normalized = normalize_date_value(last_updated_raw)
        if not normalized or not re.match(r'^\d{4}-\d{2}-\d{2}$', normalized):
            err(f"'last_updated' must be in YYYY-MM-DD format, got '{last_updated_raw}'", md, is_blocker=is_blocker('formats'))

    # Validate last_validated format if present
    if last_validated_raw:
        normalized = normalize_date_value(last_validated_raw)
        if not normalized or not re.match(r'^\d{4}-\d{2}-\d{2}$', normalized):
            err(f"'last_validated' must be in YYYY-MM-DD format, got '{last_validated_raw}'", md, is_blocker=is_blocker('formats'))

    # Warn if last_validated is stale (>14 days behind last_updated)
    if last_updated_raw and last_validated_raw:
        lu_date = parse_iso_date(last_updated_raw)
        lv_date = parse_iso_date(last_validated_raw)
        if lu_date and lv_date:
            if lv_date < lu_date - timedelta(days=14):
                print(f"Warning: {md}: last_validated ({lv_date}) lags last_updated ({lu_date}) by >14 days")

    # Validate revision is vMAJOR.MINOR
    if 'revision' in fm:
        if not validate_revision(fm['revision']):
            err(f"'revision' must be in vMAJOR.MINOR format, got '{fm['revision']}'", md, is_blocker=is_blocker('formats'))

    # Validate id is kebab-case and matches filename stem
    if 'id' in fm:
        # Allow dots in IDs for .view.md files (generated diagram wrappers)
        is_view_file = md.name.endswith('.view.md')
        if not validate_kebab_case(fm['id'], allow_dots=is_view_file):
            err(f"'id' must be kebab-case, got '{fm['id']}'", md, is_blocker=is_blocker('case_style'))

        # Check id matches filename stem
        filename_stem = md.stem
        id_val = fm['id']

        # Normalize for comparison if policy allows case-insensitive matching
        if not POLICY.get('id_match_case_sensitive', True):
            id_normalized = normalize_to_kebab(id_val)
            stem_normalized = normalize_to_kebab(filename_stem)

            if id_normalized != stem_normalized:
                # Check for directory-prefixed IDs
                if id_normalized.endswith(stem_normalized):
                    prefix_with_dash = id_normalized[:-len(stem_normalized)]
                    if prefix_with_dash.endswith('-'):
                        prefix = prefix_with_dash[:-1]
                        if prefix in [normalize_to_kebab(p) for p in md.parts]:
                            # Valid directory-prefixed ID
                            pass
                        else:
                            err(f"'id' ('{id_val}') must match filename stem ('{filename_stem}')", md, is_blocker=is_blocker('id_filename_match'))
                    else:
                        err(f"'id' ('{id_val}') must match filename stem ('{filename_stem}')", md, is_blocker=is_blocker('id_filename_match'))
                else:
                    err(f"'id' ('{id_val}') must match filename stem ('{filename_stem}')", md, is_blocker=is_blocker('id_filename_match'))
        else:
            # Case-sensitive matching (strict)
            if id_val != filename_stem:
                # Allow directory-prefixed IDs to prevent duplicates
                if id_val.endswith(filename_stem):
                    prefix_with_dash = id_val[:-len(filename_stem)]
                    if prefix_with_dash.endswith('-'):
                        prefix = prefix_with_dash[:-1]
                        if prefix in [p for p in md.parts]:
                            # Valid directory-prefixed ID for duplicate prevention
                            pass
                        else:
                            err(f"'id' ('{id_val}') must match filename stem ('{filename_stem}')", md, is_blocker=is_blocker('id_filename_match'))
                    else:
                        err(f"'id' ('{id_val}') must match filename stem ('{filename_stem}')", md, is_blocker=is_blocker('id_filename_match'))
                else:
                    err(f"'id' ('{id_val}') must match filename stem ('{filename_stem}')", md, is_blocker=is_blocker('id_filename_match'))

        # Track for duplicate detection
        ids.setdefault(fm['id'], []).append(str(md))

# Check for duplicate IDs
for doc_id, paths in ids.items():
    if len(paths) > 1:
        err(f"Duplicate id '{doc_id}' across: {paths}", is_blocker=is_blocker('required_keys'))

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

# ---------- 7) No-drift guard for critical files ----------
def _check_linter_change_guard():
    """Prevent accidental changes to critical validation files without explicit approval."""
    # Only run in CI context or skip entirely
    is_ci = os.environ.get('CI', 'false').lower() == 'true'
    if not is_ci:
        # Skip check in local development
        return

    critical_files = [
        'docs/standards/frontmatter.schema.json',
        'docs/standards/allowed-values.json',
        'docs/standards/validator-policy.json',
        'tooling/scripts/validate_docs.py'
    ]

    try:
        # Check if any critical files are modified in the current branch vs main
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'origin/main...HEAD'],
            capture_output=True,
            text=True,
            cwd=ROOT
        )

        if result.returncode != 0:
            # Not in a git repo or git not available - skip check
            return

        modified_files = result.stdout.strip().split('\n')
        modified_critical = [f for f in modified_files if f in critical_files]

        if not modified_critical:
            return

        # Check commit messages for approval flag
        result = subprocess.run(
            ['git', 'log', '--format=%B', 'origin/main..HEAD'],
            capture_output=True,
            text=True,
            cwd=ROOT
        )

        if result.returncode == 0:
            commit_msgs = result.stdout.strip()
            if 'allow-linter-change: true' in commit_msgs.lower():
                return

        err(f"Critical validation files modified without approval: {modified_critical}. Include 'allow-linter-change: true' in commit message to override.")

    except Exception:
        # Skip check if git operations fail
        pass

_check_linter_change_guard()

# ---------- report ----------
if WARNINGS:
    print("Warnings (non-blocking):")
    print('\n'.join(f"  WARN: {w}" for w in WARNINGS))
    print()

if ERRORS:
    print('\n'.join(str(e) for e in ERRORS))
    sys.exit(1)
else:
    print('validate_docs: OK')
