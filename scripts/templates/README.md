# ECI Worker Templates

These are **templates** for local ECI workers. Copy them to the correct local paths; do **not** run from the repo directly.

## Identity Convention (both platforms)
- File path (local-only):
  - **Windows:** `C:\temp\MACHINE_ID_<machine-name>.txt` (e.g., `MACHINE_ID_OFFICE3.txt`)
  - **macOS:** `~/Library/Application Support/KG/MACHINE_ID_<machine-name>.txt` (e.g., `MACHINE_ID_MACBOOK.txt`)
- **First non-empty line** = canonical `machine_id` (e.g., `Windows-Office3`, `kg_macbook_pro`)
- Subsequent lines optional: `OS=...`, `HW=...`
- These files must **not** be stored in Dropbox or the repo.

## Install (macOS)
1) Copy `scripts/templates/eci_mac_claim_and_run.sh` → `~/bin/claim_and_run.sh`
2) `chmod +x ~/bin/claim_and_run.sh`
3) Ensure queue exists under Dropbox: `~/Library/CloudStorage/Dropbox/Automation/.queue/{inbox,claimed,done,events}`
4) Run: `~/bin/claim_and_run.sh`

## Install (Windows)
1) Copy `scripts/templates/eci_win_Claim-And-Run.ps1` → `%USERPROFILE%\Dropbox\Automation\.queue\Claim-And-Run.ps1`
2) Create queue folders under `%USERPROFILE%\Dropbox\Automation\.queue\`
3) Run: `powershell -ExecutionPolicy Bypass -File "%USERPROFILE%\Dropbox\Automation\.queue\Claim-And-Run.ps1"`

## Notes
- Workers only claim jobs where `requested_executor` contains their `machine_id` (or where it's empty).
- Keep identity files **local-only** to avoid cross-system confusion.
