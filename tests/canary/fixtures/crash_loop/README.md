# Crash-loop reader fixtures (mission #1133, WP03)

Provenance: office2, captured 2026-11-23 by the mission orchestrator over
`ssh office2-claude` (read-only; no unit, container or file was changed).
See `kitty-specs/crash-loop-unit-alerting-01M858E8/research.md` R-03.

Commands sampled (as the `claude` user, no sudo):

- `systemctl list-units --type=service --all --plain --no-legend --no-pager`
- `systemctl show -p Id,Restart,NRestarts,ActiveState,SubState,LoadState -- <ids…>`
- the same two with `--user`
- `docker inspect --format '{{json .Name}}|{{.RestartCount}}|{{json .HostConfig.RestartPolicy.Name}}|{{json .State.Status}}' -- <ids…>`

## Files: verbatim versus synthesized

| File | Content |
|---|---|
| `system-list-units.txt` | Rows 1–5 (`apparmor` … `apt-daily`) and the three `not-found` rows (`auditd`, `connman`, `console-screen`) are **verbatim**. The `obsidian-sync`, `plymouth-quit` and `snapd` rows are **synthesized** in the same column layout: the capture did not include their list rows, but `show` output for them was captured. |
| `system-show.txt` | **Verbatim**: the three captured blocks, in systemd's own property order (`Restart, NRestarts, Id, LoadState, ActiveState, SubState`). |
| `system-show-synthesized.txt` | **Synthesized** `show` blocks (`Restart=no`) for the five verbatim loaded list rows, so that a fixture-driven read reconciles requested IDs against returned blocks. |
| `user-list-units.txt` | Rows 1–4 are **verbatim** (row 4 contains a UTF-8 em dash in its description). The `felix-canary` and `openclaw-gateway` rows are **synthesized**. |
| `user-show.txt` | **Verbatim**: the `openclaw-gateway` (`Restart=always`, `NRestarts=0`) and `felix-canary` (`Restart=no`) blocks. |
| `user-show-synthesized.txt` | **Synthesized** `Restart=no` blocks for the four verbatim user list rows. |
| `docker-inspect.txt` | Fields 2–5 (`"/name"`, count, policy, status) are **verbatim**. Field 1, the `{{json .Id}}`, is **synthesized**: the capture predates adding `.Id` to the format string. Each ID is a realistic 64-hex value, `sha256("office2-fixture-<name>")`. The capture's leading line `3` (the container count, not inspect output) is omitted. |
| `docker-ps.txt` | **Synthesized** `docker ps -aq --no-trunc` output: the three IDs above. |
