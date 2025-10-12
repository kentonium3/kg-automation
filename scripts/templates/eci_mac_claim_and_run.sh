#!/usr/bin/env bash
# eci_mac_claim_and_run.sh — Template (copy to ~/bin/claim_and_run.sh)
# Purpose: Minimal ECI worker for macOS. Claims only jobs targeted to this machine.
# Identity source: ~/Library/Application Support/KG/MACHINE_ID_*.txt (first non-empty line).
set -euo pipefail

# Canonical roots (macOS)
DROPBOX_ROOT="$HOME/Library/CloudStorage/Dropbox"
AUTOMATION_ROOT="$DROPBOX_ROOT/Automation"
# Global queue (cross-project)
QUEUE_ROOT="${1:-$AUTOMATION_ROOT/.queue}"

# 1) Determine local machine_id (local-only; never in Dropbox)
id_dir="$HOME/Library/Application Support/KG"
id_file="$(find "$id_dir" -name 'MACHINE_ID_*.txt' 2>/dev/null | head -n1 || true)"
if [ -f "$id_file" ]; then
  machine_id="$(grep -m1 -v '^[[:space:]]*$' "$id_file" | tr -d '\r\n')"
else
  machine_id="${KG_PLATFORM:-$(scutil --get ComputerName 2>/dev/null || hostname)}"
fi

inbox="$QUEUE_ROOT/inbox"
claimed="$QUEUE_ROOT/claimed"
done="$QUEUE_ROOT/done"
events="$QUEUE_ROOT/events"
mkdir -p "$claimed" "$done" "$events"

# 2) First job in inbox
job_file="$(ls "$inbox"/*.json 2>/dev/null | head -n1 || true)"
[ -n "${job_file:-}" ] || { echo "No jobs."; exit 0; }

# 3) Check targeting (reads requested_executor array)
targets="$(
/usr/bin/python3 - "$job_file" <<'PY'
import json, sys
with open(sys.argv[1], 'r') as f:
    d = json.load(f)
print(",".join(d.get("requested_executor", [])))
PY
)"

eligible=false
if [ -z "$targets" ]; then
  eligible=true
else
  IFS=','; for t in $targets; do [ "$t" = "$machine_id" ] && eligible=true; done
fi

if [ "$eligible" != true ]; then
  echo "Skipping job (not targeted for $machine_id): $(basename "$job_file")"
  exit 0
fi

# 4) Claim & minimal work
base="$(basename "$job_file")"
mv "$job_file" "$claimed/$base"
echo "$(date -u +%FT%TZ)  CLAIM  $machine_id" >> "$events/${base%.json}.log"
sleep 2
echo "$(date -u +%FT%TZ)  DONE   $machine_id" >> "$events/${base%.json}.log"
mv "$claimed/$base" "$done/$base"
echo "Job completed: ${base%.json} on $machine_id"
