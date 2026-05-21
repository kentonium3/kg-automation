**Issue 1**: `scripts/office2/deploy/felix-doc-auditor-driver.sh` step 5 silently treats `openclaw agents list` failures as "already deregistered." Both the presence check and the apply-mode post-condition pipe `openclaw agents list 2>/dev/null` into `grep`; if the `openclaw` CLI is missing, the gateway/API is unreachable, or the list command syntax changes, the pipeline simply evaluates false and the script proceeds. In `--apply --backup-confirmed`, that means step 6 can delete `/data/services/openclaw/felix-doc-auditor/` without verifying that the old OpenClaw registration was actually retired, violating FR-010 and the WP requirement that command failures print `STEP FAILED` and exit non-zero.

Fix by capturing the agent list output with an explicit error check before grepping, for example:

```bash
if ! AGENTS_OUTPUT="$(openclaw agents list 2>&1)"; then
  fail "openclaw agents list failed: ${AGENTS_OUTPUT}"
fi

if printf '%s\n' "${AGENTS_OUTPUT}" | grep -q "^- ${AGENT_NAME}\b"; then
  ...
else
  note "agent ${AGENT_NAME} already deregistered, skipping"
fi
```

After deletion, rerun the list command with the same explicit error handling and fail if the agent is still present. This preserves the idempotent "already deregistered" case while refusing to continue on an unverifiable OpenClaw state.

WP09 depends on WP08; downstream WP09 agents should rebase after this fix lands.
