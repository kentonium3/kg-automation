---
affected_files: []
cycle_number: 5
mission_slug: refactor-doc-auditor-to-scripts-first-driver-01KS2XNX
reproduction_command:
reviewed_at: '2026-05-21T13:57:54Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP08
---

**Issue 1**: `scripts/office2/felix-doc-auditor.service` does not match `contracts/driver-invocation.contract.md` exactly. The contract's systemd unit block has `After=network-online.target openclaw-gateway.service` and no `Wants=network-online.target`, but the implemented unit still includes `Wants=network-online.target`. Remove the extra `Wants=` line so the in-repo unit matches the contract and WP08's "No accidental syntax change vs the contract" validation.

**Issue 2**: `scripts/office2/deploy/felix-doc-auditor-driver.sh` step 3 creates and chmods `/data/services/openclaw/felix-doc-auditor-driver`, but it omits the required `chown claude:claude`. Add the ownership operation in apply mode and show it in dry-run output. Make the step remain idempotent when the directory already exists, including correcting ownership/permissions if needed.

**Issue 3**: `scripts/office2/deploy/felix-doc-auditor-driver.sh --help` prints internal script implementation text (`set -euo pipefail`, separator lines, `Constants`) because `print_help` blindly emits header lines through line 50. Adjust help output so it mirrors the operator header/usage without leaking code internals, satisfying T039.

WP09 depends on WP08; downstream WP09 agents should rebase after these changes land.
