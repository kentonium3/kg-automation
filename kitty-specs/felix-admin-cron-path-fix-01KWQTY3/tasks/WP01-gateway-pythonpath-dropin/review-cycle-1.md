**Issue 1**: SC-10b is not verified in a real OpenClaw agent/cron subprocess.

The WP, plan, and contract all make this the load-bearing acceptance gate: `PYTHONPATH` must be observed inside a real OpenClaw-launched agent or cron payload from a non-repo cwd. The current implementation verifies only a `python3 -c ...` child process launched by the deploy script itself (`scripts/deploy/install-gateway-pythonpath-dropin.py:130-151`) and repeats the same proxy in the manifest post check (`deploys/queued/0006-gateway-pythonpath-dropin.yaml:13-15`). That proves the deploy script's environment, not the gateway -> agent/cron subprocess inheritance path. The prompt explicitly says an SSH/login-shell proxy is not valid; the same reasoning blocks a deploy-script subprocess proxy.

Fix: replace the SC-10b deploy gate with an actual OpenClaw agent/cron execution path that launches a payload from a non-repo cwd and prints/asserts `os.environ["PYTHONPATH"] == "/home/claude/kg-automation"`. The entrypoint and manifest post verification should fail closed if that real agent/cron payload does not produce the expected value. Keep SC-10a (`systemctl --user show ... -p Environment`) as the unit-environment check.

Downstream note: WP06 depends on WP01, so dependent agents should rebase after this correction lands.
