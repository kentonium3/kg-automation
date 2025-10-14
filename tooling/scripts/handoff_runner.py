#!/usr/bin/env python3
import os, sys, json
from pathlib import Path

ROOT = Path('.')
HANDOFFS = ROOT / 'ai-agents' / 'shared' / 'handoffs'
SCHEMA = ROOT / 'ai-agents' / 'shared' / 'contracts' / 'ai-handoff.schema.json'
BRANCH = os.getenv('GITHUB_REF_NAME', '')
SHA = os.getenv('GITHUB_SHA', '')

PRINT_PREFIX = '[handoff-runner] '

# ---------- helpers ----------
def log(msg):
    print(PRINT_PREFIX + str(msg))

def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        log(f'JSON parse error for {p}: {e}')
        return None

def save_json(p: Path, data: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')

def find_requests():
    if not HANDOFFS.exists():
        return []
    return sorted([p for p in HANDOFFS.glob('*.json') if p.name.endswith('-request.json')])

def counterpart_exists(req: Path):
    stem = req.name[:-len('-request.json')]
    for suffix in ['-claude-to-chatgpt-response.json','-github-runner-response.json','-response.json']:
        if (req.parent / f'{stem}{suffix}').exists():
            return True
    return False

def load_schema():
    if SCHEMA.exists():
        try:
            return json.loads(SCHEMA.read_text(encoding='utf-8'))
        except Exception as e:
            log(f'Warning: could not parse schema: {e}')
    return None

def validate_against_schema(data, schema):
    try:
        from jsonschema import Draft7Validator
        Draft7Validator(schema).validate(data)
        return []
    except Exception as e:
        return [str(e)]

# ---------- processors ----------
def plan_from_request(req_data: dict):
    purpose = req_data.get('purpose', '')
    inputs = req_data.get('inputs', {}) or {}
    next_actions = req_data.get('next_actions', []) or []

    plan = []

    file_edits = inputs.get('file_edits') or []
    for edit in file_edits:
        path = edit.get('path'); content = edit.get('content')
        if path and content is not None:
            plan.append({'action': 'write_file', 'path': path, 'bytes': len(content.encode('utf-8'))})

    new_files = inputs.get('new_files') or []
    for nf in new_files:
        plan.append({'action': 'create_file_if_missing', 'path': nf})

    plan.append({'action': 'summary', 'branch': BRANCH, 'sha': SHA, 'purpose': purpose, 'next_actions': next_actions})
    return plan

def perform_file_edits(req_data: dict):
    inputs = req_data.get('inputs', {}) or {}
    edits = inputs.get('file_edits') or []
    wrote = []
    for edit in edits:
        path = edit.get('path'); content = edit.get('content')
        if path and content is not None:
            p = ROOT / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            wrote.append(path)
    return wrote

def make_response(req_path: Path, req: dict, status: str, outputs: dict, notes: str, response_suffix='-github-runner-response.json'):
    stem = req_path.name[:-len('-request.json')]
    response = {
        'type': 'handoff.response',
        'handoff_id': req.get('handoff_id'),
        'from_agent': 'handoff-runner',
        'to_agent': req.get('from_agent', 'chatgpt'),
        'status': status,
        'branch': BRANCH,
        'request_ref': str(req_path),
        'outputs': outputs,
        'notes': notes
    }
    out = req_path.parent / f'{stem}{response_suffix}'
    save_json(out, response)
    return out

# ---------- main ----------
def main():
    processed = 0
    schema = load_schema()

    for req_path in find_requests():
        if counterpart_exists(req_path):
            log(f'Skipping {req_path.name} (response already exists)')
            continue

        req = load_json(req_path)
        if req is None:
            continue

        errors = []
        if schema:
            try:
                errors = validate_against_schema(req, schema)
            except Exception as e:
                log(f'Schema validation failed with exception: {e}')
        if errors:
            log(f'Schema validation errors for {req_path.name}: {errors}')

        wrote = perform_file_edits(req)
        if wrote:
            status = 'completed'
            outputs = {'edited_files': wrote}
            notes = 'Applied file_edits from request. No LLM required.'
        else:
            plan = plan_from_request(req)
            status = 'planned'
            outputs = {'plan': plan}
            notes = 'No actionable file_edits provided or LLM keys absent; recorded plan-only response.'

        out = make_response(req_path, req, status, outputs, notes)
        log(f'Wrote response: {out}')
        processed += 1

    if processed == 0:
        log('No new handoff requests to process.')

if __name__ == '__main__':
    main()
