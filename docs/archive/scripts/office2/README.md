# Archived office2 deploy sources

Frozen deploy sources for retired office2 services. Kept for historical
reference only — **not deployed, not maintained.**

## second-brain-sync (F011) — retired 2026-07-12 (#712)

`second-brain-sync.{sh,service,timer}` — a 15-minute kgale user-timer that
did a bidirectional git sync (`git pull --rebase`, then commit + push) of
**non-vault** second-brain content (`agents/`, `logs/`, `config`) between
`/home/kgale/second-brain` and `kentonium3/second-brain` on GitHub. The vault
(`notes/`) was excluded via `.gitignore` and synced separately via Obsidian
Sync.

**Why retired:** its consumers were removed around it — the
`/home/claude/second-brain` clone that pulled the non-vault content from
GitHub was decommissioned by #659, and Restic (nightly `/home/kgale` backup)
superseded its backup role. Non-vault agent logs are read in place on office2
by the observation-digest flow; nothing consumes the GitHub side. The timer
had already stopped (last auto-sync commit 2026-06-12) and the outage went
unnoticed for a month. See `#712` and the service-inventory `second-brain-sync`
entry (`status: retired`).

If ever revived, do **not** restore the old `systemctl --user status …`
health check — it targeted a kgale user unit and was never evaluable by the
claude-run canary. Use a canary-readable freshness pointer instead (the
last-tick.json pattern from #720/#721).
