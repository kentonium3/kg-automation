#!/usr/bin/env bash
# anthropic-verify.sh — detect per-agent SQLite shadow + plaintext/SQLite drift
# Origin: kentonium3/kg-automation#597; companion to anthropic-rotate.sh
#
# Read-only by default. --repair mutates state behind an explicit flag and
# always writes a .pre-repair.<ts>.bak sibling first. Repair is delivered by
# WP02; this WP01 build dispatches to the lazy-imported repair module which
# may not be present yet — in which case a clear error is emitted.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE=""

usage() {
  cat <<EOF
Usage: $0 [--check | --repair]

  --check    (default) Detect per-agent SQLite shadow + plaintext/SQLite drift.
             Read-only; exits 0 if green, 2/3/4/5/6 per finding type.
  --repair   Clear shadow rows or rewrite plaintext from main SQLite.
             Requires explicit flag; always writes .pre-repair.<ts>.bak before mutating.
             No interactive prompt; no auto gateway restart (prints the command).

Exit codes (per spec FR-011):
  0 green   1 error   2 shadow   3 drift   4 anthropic-rejected   5 network   6 substrate-gap
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      if [[ -n "$MODE" ]]; then
        echo "ERROR: --check and --repair are mutually exclusive" >&2
        exit 1
      fi
      MODE="check"
      shift
      ;;
    --repair)
      if [[ -n "$MODE" ]]; then
        echo "ERROR: --check and --repair are mutually exclusive" >&2
        exit 1
      fi
      MODE="repair"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown arg: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Default to --check when invoked with no flag.
if [[ -z "$MODE" ]]; then
  MODE="check"
fi

# Run the python package via -m so relative imports resolve. The package
# lives at SCRIPT_DIR/anthropic_verify/; PYTHONPATH points at SCRIPT_DIR.
cd "${SCRIPT_DIR}"
PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" exec python3 -m anthropic_verify "--${MODE}"
