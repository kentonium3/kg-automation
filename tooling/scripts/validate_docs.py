#!/usr/bin/env python3
import os, re, sys, json
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft7Validator
except Exception as e:
    print('Missing deps: pip install pyyaml jsonschema', file=sys.stderr)
    sys.exit(1)

ROOT = Path('.')
ERRORS = []

DOC_TYPES = {'concept','design','spec','runbook','workflow','reference','handbook','governance','adr'}
LEVELS = {'concept','architecture','system','workflow','runbook','reference'}
STATUSES = {'draft','proposed','approved','deprecated'}

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
    txt = Path(p).read_text(encoding='utf-8', errors='ignore')
    if not txt.startswith('---'):
        err('Missing YAML front-matter', p)
        return None
    try:
        lines = txt.splitlines()
        # Find the next '---' line that closes the front matter
        end = None
        for i in range(1, min(len(lines), 500)):  # cap to avoid scanning whole huge files
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


# ---------- 1) Markdown front-matter validation ----------
ids = {}
for md in ROOT.rglob('*.md'):
    if any(seg in md.parts for seg in ['.git','node_modules','.venv']):
        continue
    fm = front_matter(md)
    if not isinstance(fm, dict):
        continue
    required = ['id','doc_type','level','status','owners','last_validated','revision']
    for k in required:
        if k not in fm:
            err(f"Missing front-matter key '{k}'", md)
    if 'doc_type' in fm and fm['doc_type'] not in DOC_TYPES:
        err(f"Invalid doc_type '{fm['doc_type']}'", md)
    if 'level' in fm and fm['level'] not in LEVELS:
        err(f"Invalid level '{fm['level']}'", md)
    if 'status' in fm and fm['status'] not in STATUSES:
        err(f"Invalid status '{fm['status']}'", md)
    if 'id' in fm:
        ids.setdefault(fm['id'], []).append(str(md))
    # runbook extras
    if fm.get('doc_type') == 'runbook':
        for rk in ['audience','severity','last_tested','revision']:
            if rk not in fm:
                err(f"Runbook missing '{rk}'", md)

for doc_id, paths in ids.items():
    if len(paths) > 1:
        err(f"Duplicate id '{doc_id}' across: {paths}")

# ---------- 2) Workflows schema ----------
if SCHEMAS['workflow'].exists():
    wf_schema = load_yaml(SCHEMAS['workflow'])
    if wf_schema:
        from jsonschema import Draft7Validator
        wf_validator = Draft7Validator(wf_schema)
        for y in (ROOT/'workflows').glob('*.yaml'):
            data = load_yaml(y)
            if data is None:
                continue
            for e in wf_validator.iter_errors(data):
                err(f"workflow schema: {e.message}", y)

# ---------- 3) Systems basic check ----------
for syml in (ROOT/'systems').glob('*/system.yaml'):
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
        from jsonschema import Draft7Validator
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
    if any(seg in p.parts for seg in ['.git','node_modules','.venv','.docgraph']):
        continue
    try:
        txt = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    for pat in SECRET_PATTERNS:
        if pat.search(txt):
            err(f"Potential secret pattern in {p}")
            break

# ---------- report ----------
if ERRORS:
    print('\n'.join(str(e) for e in ERRORS))
    sys.exit(1)
else:
    print('validate_docs: OK')
