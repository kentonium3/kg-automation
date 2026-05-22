**Issue 1**: Invalid CLI flags exit with code 2 instead of the contracted validation/usage code 3.

Reproduction from the WP01 lane workspace:

```bash
python3 -m scripts.habits.morning_checkin_list --not-a-real-flag
echo $?
```

Actual: argparse prints an unrecognized-argument error and the process exits `2`.

Expected: per `contracts/cli.md`, usage/validation errors including bad flags must exit `3`. Exit `2` is reserved for filesystem write failure after the Vikunja step succeeds. This matters operationally because callers can distinguish "artifact persist failed" from "bad invocation".

Fix: make the CLI parser map argparse usage failures to return code `3` while preserving `--help` as exit `0`. Add a regression test for an unrecognized flag through `main([...])` or a subprocess invocation.

Downstream note: WP02 and WP04 depend on WP01; after this fix lands, those agents should rebase before continuing.
