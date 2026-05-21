**Issue 1**: `scripts/office2/deploy/felix-doc-auditor-driver.sh` does not wrap mutating commands with the required `STEP FAILED` failure reporting. Commands executed through `run_cmd` rely on `set -e`:

```bash
run_cmd() {
  echo "    ${PFX} $ $*"
  if [ "${MODE}" = "apply" ]; then
    "$@"
  fi
}
```

If any apply-mode command fails, for example `git pull --rebase`, `mkdir`, `cp`, `systemctl --user daemon-reload`, `openclaw agents delete`, `rm -rf`, or `systemctl --user enable --now`, Bash exits non-zero but does not print the WP-required `STEP FAILED` line. T037 explicitly requires all commands to be wrapped in error checks and to print `STEP FAILED` on failure.

Fix `run_cmd` so apply-mode command failures are handled explicitly, for example:

```bash
run_cmd() {
  echo "    ${PFX} $ $*"
  if [ "${MODE}" = "apply" ]; then
    if ! "$@"; then
      fail "command failed: $*"
    fi
  fi
}
```

Then sanity-check at least one forced failure path with a harmless stub or controlled invalid command to confirm the output includes `STEP FAILED` and exits non-zero.

WP09 depends on WP08; downstream WP09 agents should rebase after this fix lands.
