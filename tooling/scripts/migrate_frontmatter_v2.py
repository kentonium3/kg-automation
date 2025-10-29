#!/usr/bin/env python3
"""
Canon v2 Frontmatter Migration Script
Migrates Canon v1 frontmatter to Canon v2 format.
"""
import os
import re
import sys
import json
from pathlib import Path
from datetime import date

try:
    import yaml
except ImportError:
    print('Missing deps: pip install pyyaml', file=sys.stderr)
    sys.exit(1)

ROOT = Path('.')
TODAY = date.today().strftime('%Y-%m-%d')

# Load allowed values
ALLOWED_VALUES_FILE = ROOT / 'docs' / 'standards' / 'allowed-values.json'
ALLOWED_VALUES = {
    'doc_type': {'strategy', 'charter', 'decision', 'policy', 'handbook', 'runbook', 'guide', 'reference', 'readme', 'index', 'project', 'note'},
    'level': {'overview', 'concept', 'howto', 'reference', 'policy'},
    'status': {'draft', 'in_review', 'approved', 'deprecated', 'archived'},
    'audience': {'agents', 'humans', 'agents_and_humans'}
}

if ALLOWED_VALUES_FILE.exists():
    try:
        with open(ALLOWED_VALUES_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            for key, values in loaded.items():
                if isinstance(values, list):
                    ALLOWED_VALUES[key] = set(values)
    except Exception as e:
        print(f"Warning: Could not load allowed-values.json: {e}", file=sys.stderr)


def title_case(s):
    """Convert kebab-case to Title Case."""
    return ' '.join(word.capitalize() for word in s.split('-'))


def extract_first_h1(content):
    """Extract first H1 heading from markdown content."""
    for line in content.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return None


def normalize_owner(owner_value):
    """Normalize owner/owners field to Canon v2 format."""
    if owner_value is None:
        return ["@kentonium3"]

    if isinstance(owner_value, list):
        # Already a list, ensure @ prefix
        result = []
        for o in owner_value:
            o_str = str(o).strip()
            if o_str and not o_str.startswith('@'):
                result.append(f"@{o_str}")
            elif o_str:
                result.append(o_str)
        return result if result else ["@kentonium3"]

    # Single value, convert to list
    owner_str = str(owner_value).strip()
    if owner_str and not owner_str.startswith('@'):
        return [f"@{owner_str}"]
    elif owner_str:
        return [owner_str]
    else:
        return ["@kentonium3"]


def migrate_frontmatter(file_path):
    """Migrate a single markdown file's frontmatter to Canon v2."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return False

    # Check if file has frontmatter
    if not content.startswith('---'):
        print(f"Skipping {file_path}: no frontmatter")
        return False

    # Extract frontmatter and body
    lines = content.splitlines()
    end = None
    for i in range(1, min(len(lines), 500)):
        if lines[i].strip() == '---':
            end = i
            break

    if end is None:
        print(f"Skipping {file_path}: malformed frontmatter")
        return False

    fm_text = '\n'.join(lines[1:end])
    body = '\n'.join(lines[end+1:])

    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception as e:
        print(f"Error parsing frontmatter in {file_path}: {e}", file=sys.stderr)
        return False

    # Get filename stem and normalize to kebab-case
    filename_stem = file_path.stem.lower().replace('_', '-')

    # Build Canon v2 frontmatter
    new_fm = {}

    # 1. ID - ensure it matches filename stem (kebab-case)
    new_fm['id'] = filename_stem

    # 2. Title - use existing, extract from H1, or generate from id
    if 'title' in fm:
        new_fm['title'] = str(fm['title'])
    else:
        first_h1 = extract_first_h1(body)
        if first_h1:
            new_fm['title'] = first_h1
        else:
            new_fm['title'] = title_case(new_fm['id'])

    # 3. doc_type - validate or use default
    doc_type = fm.get('doc_type', 'guide')
    if doc_type not in ALLOWED_VALUES['doc_type']:
        # Map common old values or use default
        mapping = {
            'meta_index': 'index',
            'meta_reference': 'reference',
            'governance': 'charter',
            'process': 'handbook'
        }
        doc_type = mapping.get(doc_type, 'guide')
    new_fm['doc_type'] = doc_type

    # 4. level - validate or use default
    level = fm.get('level', 'reference')
    if level not in ALLOWED_VALUES['level']:
        level = 'reference'
    new_fm['level'] = level

    # 5. status - validate or use default
    status = fm.get('status', 'draft')
    # Map old values
    if status == 'active':
        status = 'approved'
    elif status not in ALLOWED_VALUES['status']:
        status = 'draft'
    new_fm['status'] = status

    # 6. owners - migrate from owner or use default
    if 'owners' in fm:
        new_fm['owners'] = normalize_owner(fm['owners'])
    elif 'owner' in fm:
        new_fm['owners'] = normalize_owner(fm['owner'])
    else:
        new_fm['owners'] = ["@kentonium3"]

    # 7. last_updated - map from last_validated or use today
    if 'last_updated' in fm:
        # Keep existing, but ensure it's a string
        lu = fm['last_updated']
        if isinstance(lu, str):
            new_fm['last_updated'] = lu
        else:
            new_fm['last_updated'] = str(lu)
    elif 'last_validated' in fm:
        lv = fm['last_validated']
        if isinstance(lv, str):
            new_fm['last_updated'] = lv
        else:
            new_fm['last_updated'] = str(lv)
    else:
        new_fm['last_updated'] = TODAY

    # 8. revision - map from version or use v1.0
    if 'revision' in fm:
        rev = str(fm['revision'])
        # Ensure vMAJOR.MINOR format
        if not rev.startswith('v'):
            rev = f"v{rev}"
        if not re.match(r'^v\d+\.\d+$', rev):
            rev = 'v1.0'
        new_fm['revision'] = rev
    elif 'version' in fm:
        ver = str(fm['version'])
        # Convert version to revision format
        if not ver.startswith('v'):
            ver = f"v{ver}"
        if not re.match(r'^v\d+\.\d+$', ver):
            ver = 'v1.0'
        new_fm['revision'] = ver
    else:
        new_fm['revision'] = 'v1.0'

    # 9. audience - use default if missing
    if 'audience' in fm:
        aud = fm['audience']
        if aud not in ALLOWED_VALUES['audience']:
            aud = 'agents_and_humans'
        new_fm['audience'] = aud
    else:
        new_fm['audience'] = 'agents_and_humans'

    # 10. Optional fields - preserve if present
    for optional_field in ['tags', 'aliases', 'links']:
        if optional_field in fm:
            val = fm[optional_field]
            if isinstance(val, list):
                new_fm[optional_field] = val
            elif val is not None:
                new_fm[optional_field] = [val]

    # Write back to file
    try:
        # Build new content with YAML frontmatter
        # Use custom YAML dumping to ensure proper formatting
        new_content_lines = ['---']

        # Write required fields in order
        new_content_lines.append(f"id: {new_fm['id']}")
        new_content_lines.append(f"title: {new_fm['title']}")
        new_content_lines.append(f"doc_type: {new_fm['doc_type']}")
        new_content_lines.append(f"level: {new_fm['level']}")
        new_content_lines.append(f"status: {new_fm['status']}")

        # Write owners
        new_content_lines.append("owners:")
        for owner in new_fm['owners']:
            new_content_lines.append(f'  - "{owner}"')

        # Write dates and revision as quoted strings to avoid YAML parsing issues
        new_content_lines.append(f'last_updated: "{new_fm["last_updated"]}"')
        new_content_lines.append(f"revision: {new_fm['revision']}")
        new_content_lines.append(f"audience: {new_fm['audience']}")

        # Write optional fields
        for optional_field in ['tags', 'aliases', 'links']:
            if optional_field in new_fm:
                if new_fm[optional_field]:
                    new_content_lines.append(f"{optional_field}:")
                    for item in new_fm[optional_field]:
                        new_content_lines.append(f"  - {item}")
                else:
                    new_content_lines.append(f"{optional_field}: []")

        new_content_lines.append('---')

        # Combine with body
        new_content = '\n'.join(new_content_lines) + '\n' + body

        file_path.write_text(new_content, encoding='utf-8')
        print(f"Migrated: {file_path}")
        return True

    except Exception as e:
        print(f"Error writing {file_path}: {e}", file=sys.stderr)
        return False


def main():
    """Main migration function."""
    docs_dir = ROOT / 'docs'

    if not docs_dir.exists():
        print("Error: docs/ directory not found", file=sys.stderr)
        return 1

    # Find all markdown files, excluding *_view.md
    md_files = []
    for md_file in docs_dir.rglob('*.md'):
        # Skip *_view.md files
        if md_file.stem.endswith('_view') or md_file.stem.endswith('.view'):
            continue

        # Skip _templates directory
        if '_templates' in md_file.parts:
            continue

        md_files.append(md_file)

    print(f"Found {len(md_files)} markdown files to migrate")

    success_count = 0
    for md_file in md_files:
        if migrate_frontmatter(md_file):
            success_count += 1

    print(f"\nMigration complete: {success_count}/{len(md_files)} files migrated successfully")
    return 0


if __name__ == '__main__':
    sys.exit(main())
