#!/usr/bin/env python3
"""
Utility to add or merge YAML front-matter into markdown files.
Idempotent: preserves existing keys, only adds missing ones.
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import date

try:
    import yaml
except ImportError:
    print("Missing dependency: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML front-matter from markdown content.
    Returns (front_matter_dict, body_text).
    If no front-matter exists, returns ({}, original_content).
    """
    if not content.startswith('---'):
        return {}, content

    lines = content.splitlines(keepends=False)

    # Find closing ---
    end_idx = None
    for i in range(1, min(len(lines), 500)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return {}, content

    # Parse YAML between delimiters
    fm_lines = lines[1:end_idx]
    fm_text = '\n'.join(fm_lines)

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        print(f"Warning: YAML parse error in front-matter: {e}", file=sys.stderr)
        return {}, content

    # Body is everything after closing ---
    body_lines = lines[end_idx + 1:]
    body = '\n'.join(body_lines)

    return fm, body


def merge_frontmatter(existing: dict, defaults: dict) -> dict:
    """
    Merge defaults into existing front-matter.
    Only adds missing keys, never overwrites existing ones.
    Handles AUTO_TODAY replacement.
    """
    merged = existing.copy()

    for key, value in defaults.items():
        if key not in merged:
            # Replace AUTO_TODAY with current date
            if value == "AUTO_TODAY":
                merged[key] = date.today().isoformat()
            else:
                merged[key] = value

    return merged


def write_markdown_with_frontmatter(file_path: Path, frontmatter: dict, body: str):
    """
    Write markdown file with YAML front-matter.
    Format: ---\nYAML\n---\n\nbody
    """
    # Dump YAML with proper formatting
    yaml_str = yaml.safe_dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    ).strip()

    # Ensure body starts cleanly (strip leading blank lines, then add one)
    body = body.lstrip('\n')

    content = f"---\n{yaml_str}\n---\n\n{body}"

    file_path.write_text(content, encoding='utf-8')


def ensure_frontmatter(file_path: Path, defaults: dict):
    """
    Ensure a markdown file has all required front-matter keys.
    Idempotent: can be run multiple times safely.
    """
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text(encoding='utf-8')

    # Parse existing front-matter
    existing_fm, body = parse_frontmatter(content)

    # Merge with defaults
    merged_fm = merge_frontmatter(existing_fm, defaults)

    # Write back
    write_markdown_with_frontmatter(file_path, merged_fm, body)

    print(f"✓ Updated front-matter: {file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Add or merge YAML front-matter into markdown files"
    )
    parser.add_argument(
        '--ensure',
        type=Path,
        required=True,
        help="Path to markdown file to process"
    )
    parser.add_argument(
        '--defaults',
        type=Path,
        required=True,
        help="Path to JSON file with defaults by doc type"
    )
    parser.add_argument(
        '--type',
        default='guide',
        help="Doc type key to use from defaults (default: guide)"
    )

    args = parser.parse_args()

    # Load defaults
    if not args.defaults.exists():
        print(f"Error: Defaults file not found: {args.defaults}", file=sys.stderr)
        sys.exit(1)

    defaults_data = json.loads(args.defaults.read_text(encoding='utf-8'))

    if args.type not in defaults_data:
        print(f"Error: Doc type '{args.type}' not found in defaults", file=sys.stderr)
        sys.exit(1)

    defaults = defaults_data[args.type]

    # Process file
    ensure_frontmatter(args.ensure, defaults)


if __name__ == '__main__':
    main()
