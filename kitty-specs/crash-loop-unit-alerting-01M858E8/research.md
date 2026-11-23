# Research: Crash-loop unit alerting

Mission `crash-loop-unit-alerting-01M858E8` (kentonium3/kg-automation#1133). Phase 0 output of `/spec-kitty.plan`, 2026-11-23.

Each decision follows the template's format: Decision / Rationale / Alternatives considered. Forks were decided under the autonomous-run protocol's D-1 rule (durable, safe option) and its §5 quality bar, and are logged here rather than asked (protocol §1b).

---

## §0 Upstream sweep (autonomous-run protocol §0), 2026-11-23

- **Build in use**: `spec-kitty/spec-kitty` main @ `06af0c52e5aa863dd7f6834750347671c328588f` (uv git install; reports 4.0.0rc9). `origin/main` is 245 commits ahead of it.
- **Query 1** (our filings, all three upstream repos): 268 lines, 50 open.
- **Query 2** (closed in `spec-kitty/spec-kitty` since the register's last validation, 2026-11-17): 66 issues.
- **Query 3** (every reference in `spec-kitty-qa` origin/main `docs/spec-kitty-issues.md`, each against its own repository): all resolved.
- **Retirement candidates**: spec-kitty/spec-kitty#7753, #7754, #7755 (fixed by #7780), #7792, #2527 and #5925 are closed. Their closing commits checked so far (`075191b27`, `0cf851f90`, `01938dbeb`, `15a3ef81f`) are **not** ancestors of `06af0c52e`. The register rows therefore still apply to this build, and none is retired. The register is read-only from this repository, so no edit was made there.
- **Fault forecast for this mission** (open issues touching the surfaces it will use): spec-kitty/spec-kitty#7745 and #5011 (issue-matrix rows: record a verdict for every `#NNN` cited in spec, plan, research, tasks and contracts before approval). spec-kitty/spec-kitty#7746 (`consolidate` and the `decisions/index.json.lock`: the lock is present and untracked in this mission and must never be committed). The `spec-commit` rows (pass explicit file paths, and check `git show --stat`). The late-FR `accept` row (freeze the FR set before `finalize-tasks`). Also spec-kitty/spec-kitty#7830 (start-branch create rollback) and #7831 (CRLF analysis digest), both already known on this build.

---

## R-01 Where the detection runs

- **Decision**: A crash-loop *stage* inside `scripts.canary.run.run_pass`. It runs after inventory components and coverage gaps, and before the dedup state is saved.
- **Rationale**: C-001 says felix-canary owns detection on its existing timer. The canary's per-component model (one inventory entry, one `health_check`, one outcome, one dedup key) cannot express per-unit episodes over a host-wide, dynamically discovered unit set. A stage keeps per-unit identity, reuses the pass's emit, ledger and errors plumbing, and needs no synthetic inventory entry.
- **Alternatives considered**: (a) A new `health_check.method: crash-loop` on a synthetic inventory component. Rejected: it collapses all units into one outcome and one dedup key, so one looping unit would mask a second, and an alert could not name its unit without a second keying layer. (b) A new timer. Ruled out by Decision `owning_monitor`.

## R-02 Restart-count sources (C-002, NFR-003)

- **Decision**:
  - System units: `systemctl list-units --type=service --all --plain --no-legend --no-pager`, then a single `systemctl show -p Id,Restart,NRestarts,ActiveState,SubState,LoadState <units…>`.
  - User units: the same pair with `--user`. The canary is a `claude` user unit, so its user manager is its own.
  - Containers: `docker ps -aq --no-trunc`, then `docker inspect --format '{{json .Name}}|{{.RestartCount}}|{{json .HostConfig.RestartPolicy.Name}}|{{json .State.Status}}' <ids…>`.
  - All commands run as argv lists (no shell), each with a 5-second timeout.
- **Rationale**: `NRestarts` and `RestartCount` are the persistent counters (the spec's invariant). Both are readable by `claude` without sudo: `claude` is in the `docker` group, and systemd properties are world-readable. The `--format` template selects four fields, so `Config.Env` (which can hold credentials) is never read. A single `show` call over all units is about 0.34 s for 192 services. It replaces 192 calls, and keeps NFR-002 comfortably within budget.
- **Alternatives considered**: (a) The journal. It is unreadable by `claude` (C-002) and was rejected. (b) `systemctl show '*'`. It works, but the explicit list then show pair makes "which units were enumerated" testable and avoids glob semantics. (c) Full `docker inspect` JSON. Rejected because it reads container env (NFR-003).

## R-03 Live probe evidence (charter Directive 6), office2, 2026-11-23 (read-only, `ssh office2-claude`)

- `systemctl --version` is `systemd 255 (255.4-1ubuntu8.19)`. felix-canary.timer is a **user** timer.
- `systemctl show obsidian-sync.service -p …` printed `Restart=always`, `NRestarts=39`, `ActiveState=active`, `SubState=running`. This is the incident counter still visible about 10 h later, which confirms the spec's signal.
- `systemctl show` prints properties in **its own order** (`Restart, NRestarts, Id, LoadState, ActiveState, SubState`), not in `-p` order. Units are separated by a blank line. **The parser must key on `Id=` within a blank-line-separated block, never on position.**
- `list-units --all` includes `not-found` units (for example `auditd.service  not-found inactive dead`). These are excluded before `show`, because only `LoadState=loaded` units can loop.
- Counts: 192 system services (`Restart=` 11 always, 168 no, 1 on-abort, 12 on-failure). 2 had `NRestarts > 0` (obsidian-sync 39, snapd 1). 28 user services (1 always: `openclaw-gateway`). 3 containers: `/transcribe-api` (unless-stopped, 0), `/vikunja` (unless-stopped, 0), `/modest_colden` (no, exited).
- Docker `--format` sample output: `"/vikunja"|0|"unless-stopped"|"running"`. Names carry a leading `/`, which is stripped.
- Timing: `systemctl show` over 192 units took 0.335 s real. `docker inspect` over 3 containers took 0.036 s.
- Verbatim samples are kept for test fixtures (`tests/canary/fixtures/crash_loop/`).

## R-04 K (quiet ticks before "cleared"), the one value the spec delegates

- **Decision**: K = 2 (about 30 minutes without a restart). Stored as `quiet_ticks_to_clear` in the config.
- **Rationale**: The canary's dedup emits "recovered" on the first healthy tick, because its outcomes are observed states. A restart counter in a loop with back-off (for example `RestartSec=` plus systemd's start-limit pauses, or docker's exponential back-off up to a minute) can show one quiet 15-minute tick in the middle of a live loop. K = 1 would then send cleared, then a new alert: two pages for one episode, which breaks FR-007. K = 2 still reports the end within 30 minutes, and K stays a config value.
- **Alternatives considered**: K = 1 (matches the dedup literally, but flaps on back-off lulls). K = 4 (one hour; delays the all-clear and makes a recurrence within the hour look like the same episode).

## R-05 Threshold window and the comparison baseline

- **Decision**: Each unit keeps a short observation history of `(observed_at, restart_count)` pairs. At each tick the delta is `current − baseline`, where the **baseline is the newest observation at or before `now − (window − slack)`**. If no observation is that old, the baseline is the oldest retained one. Config defaults: `threshold = 3`, `window_seconds = 900`, `slack_seconds = 120`. A crash loop is flagged when `delta ≥ threshold`. History keeps the baseline candidate plus everything newer, capped at 16 entries.
- **Rationale**: The timer is `OnUnitActiveSec=15min`, so consecutive ticks are at least 15 minutes apart, plus timer accuracy (up to 1 minute later). Process start jitter can still make the measured gap look a fraction of a second under 15:00. The `slack` makes the previous tick the baseline in normal operation. Without it, the baseline would fall back two ticks, doubling the measured window and over-counting slow restarts (an NFR-004 risk). Extra manual runs (`systemctl --user start felix-canary.service`, which the deploy entrypoint itself does) add closer observations. Restarts that accumulate across those observations still count (spec edge case "Window longer than one tick").
- **Long gaps (judgment call, surfaced in plan.md)**: When ticks were missed, the baseline is the previous observation, possibly hours old. A rise of at least the threshold over that gap **alerts**, and the evidence states the real period. A counter cannot show when within the gap the restarts happened. Missing a real loop is the failure this mission exists to remove, and a sustained multi-restart rise is abnormal at any rate. NFR-004 is still met for the normal 15-minute cadence.
- **Alternatives considered**: Only ever compare with the previous tick (cannot accumulate across manual runs). Suppress when the gap is greater than the window (could miss exactly the 2026-11-23 shape if a tick was late).

## R-06 Counter resets and new or removed units

- **Decision**: If `current < last observed`, this is a reset (explicit restart, `daemon-reexec`, reboot, or container re-creation). History is replaced with `[(now, current)]` and nothing alerts (FR-009). In an open episode a reset tick counts as a **quiet** tick (the count did not rise). A unit seen for the first time gets a baseline and no alert (FR-010). A unit missing from a scope that was **read successfully** has its state dropped, and an open episode for it ends silently, because it was removed or renamed. A unit in a scope that **could not be read** keeps its state untouched.
- **Rationale**: These match the spec's edge cases. Dropping state only for a successfully read scope stops a transient docker outage from wiping container baselines and then hiding the next tick's delta.
- **Alternatives considered**: Sending "cleared" for removed units. Rejected because nothing confirms the loop ended, and the spec says to drop them without alerting.

## R-07 State persistence

- **Decision**: `/data/services/felix-canary/state/crash-loop.json` holds a versioned document `{"schema_version": 1, "units": {<key>: {...}}}`. It is written atomically (`tempfile.mkstemp` in the same directory, `fsync`, `os.replace`), the same pattern as `dedup.save_state`. If the file is missing, corrupt, of the wrong type or of an unknown `schema_version`, it loads as `{}`: every unit is first-seen, with no alert and no crash. A malformed per-unit entry is dropped on its own. The file is not written in `dry_run`.
- **Rationale**: This matches the spec's "persisted state missing or corrupt" edge case and the canary's existing fail-safe convention. A separate file keeps the dedup state format unchanged (FR-013).
- **Alternatives considered**: Extending `dedup.json`. Rejected because it changes an existing artifact's schema, and a crash-loop bug could then corrupt the dedup state of every component.

## R-08 Alert routing, could-not-check and fault isolation

- **Decision**:
  - **Crash-loop alert** (episode start) and **re-remind**: `Alert(source="felix-canary:crash-loop:<scope>:<name>", severity=ERROR, ...)` sent through the pass's `emit_fn`.
  - **Cleared**: `Severity.INFO`. This is the canary's "recovered" convention: a low-priority ntfy notification plus the alert-bus ledger entry.
  - **Episode lifecycle and re-remind**: these come from the crash-loop state machine. The dedup is not used for them, because its transition rule cannot express "threshold crossed" or "K quiet ticks". The re-remind interval is `scripts.canary.dedup.DEFAULT_WINDOW` (6 h), so it uses the canary's existing cadence by construction.
  - **Scope could-not-check (FR-011)**: each scope is also routed through the existing dedup path as a canary component, `crash-loop:system`, `crash-loop:user` or `crash-loop:container`, with outcome `healthy` when it was read and `unknown` (with the read error as evidence) when it was not. That reuses the canary's F5 rule (a first-seen `unknown` is recorded, then paged once it has persisted past the window) and its "recovered" transition.
  - **Fault isolation (FR-013, NFR-005)**: the whole stage runs in a `try/except Exception`. An unexpected fault appends `crash_loop:<ExcName>:<msg>` to `errors[]`, and the pass continues to the dedup save, tick-signal and summary. The stage runs after all existing components, so a fault can never stop one of them from being evaluated.
- **Rationale**: The decision uses existing plumbing only (C-003). `errors[]` is the canary's established channel for pass-level faults (`dedup_load`, `ledger`, `tick_signal`). It sets the tick's `status` to `error`, and felix-canary's own `tick-signal-file` check then reports that. A broken crash-loop check is therefore visible and never silent (engineering principle 14). Routing scope health through dedup gives could-not-check the same paging behaviour as any other `unknown` component.
- **Alternatives considered**: (a) Logging stage faults without `errors[]`. Rejected because it is silent. (b) Paging scope `unknown` immediately. Rejected because it diverges from the canary's F5 semantics, and a docker restart blip would page. (c) Severity WARN for crash-loop alerts. Rejected because a looping service is effectively down, which is the canary's `failed` = ERROR class.

## R-09 Wiring without disturbing the existing suite

- **Decision**: `run_pass` gains a keyword `crash_loop_check: Callable | None = None`. When it is `None` the stage is skipped entirely, so existing callers and tests are byte-for-byte unchanged and never touch real `systemctl` or `docker`. `main()` passes the real check, built from the default readers, the repo config path and the state path. A test asserts that `main()` passes a non-`None` check (the charter's "no dead code" rule). The tick-signal file schema is unchanged: crash-loop counters go into the returned summary under `crash_loop` and are excluded from the persisted signal, the same way `alerts_undelivered` is excluded today. Scope components add up to 3 to `components_evaluated`, and the crash-loop alert count is added to `emitted`.
- **Rationale**: FR-013/SC-005 require the existing behaviour to stay the same on the same inputs. An opt-in parameter makes that true by construction. Making the stage default-on in `run_pass` would make every existing `run_pass` test call real subprocesses.
- **Alternatives considered**: Default-on, with a module-level kill switch. Rejected because it leaks real effects into tests.

## R-10 Configuration file

- **Decision**: `scripts/canary/crash_loop_config.json` is read once per pass and validated strictly. `threshold` is an integer ≥ 2. `window_seconds` is an integer > `slack_seconds` ≥ 0. `quiet_ticks_to_clear` is an integer ≥ 1. `ignore` is a list of `{"unit": "<scope>:<name>", "reason": "<non-empty>"}`, where scope is `system`, `user` or `container`. Matching is exact. An **invalid or unreadable config** makes all three scopes `unknown` with evidence `config invalid: …`, and nothing is evaluated. The stage never silently falls back to defaults. The initial ignore list is empty.
- **Rationale**: Per the spec's assumptions, a threshold change is a config change, not a code change. A reason is required for every ignore entry. Failing closed into visible `unknown` follows principle 14 and the canary's INV-002 rule (no silent fallback). Exact matching keeps the ignore list auditable.
- **Alternatives considered**: Putting the config in service-inventory.json. Rejected because it mixes a host-wide policy into per-service entries and widens that file's schema. Glob matching. Rejected as an unneeded risk: it could ignore more than intended.

## R-11 Deploy path (C-004) and rebaseline

- **Decision**: Add the manifest `deploys/queued/<next>-crash-loop-unit-alerting.yaml` (tier 3) with the entrypoint `scripts/deploy/deploy-crash-loop-unit-alerting.py`.
  - `--dry-run`: preflight (euid `claude`, `HOME=/home/claude`), check that the config is valid, and run the three readers once, read-only, reporting counts and the time taken.
  - `--apply`: preflight, then `systemctl --user start felix-canary.service` (a oneshot that blocks until done). Then prove the stage from the fresh artifacts: `crash-loop.json` was written in this invocation; today's canary ledger has a `crash-loop:system` line from this invocation that is not `unknown`; and `last-tick.json` `errors` holds no `crash_loop:` entry.
  - The manifest is authored in the mission branch. **It is not merged or queued for application without Kent's approval**, because merging to `main` is what deploys.
  - Rebaseline: none of the changed files match an audited-surface pattern that has baselines. `audited_surface: false`, and the merge record will say `Rebaseline: not required — …`. This is to be confirmed by running `tooling/scripts/check_audited_surface_drift.py` on the final diff.
- **Rationale**: This follows the pattern of 0032 (health-check coverage): the code reaches office2 with the checkout, and the entrypoint proves it is live. `audited_surface` is declared false because no file on a hashed surface changes. The manifest file itself matches the `deploy-pipeline` patterns, whose `affected_baselines` is empty. If the drift checker disagrees, the manifest flips to `true` and its notes are updated.
- **Alternatives considered**: No manifest (code-only change via pull). Rejected because of C-004 and because the post-merge live verification needs an owner.

## R-12 Dependencies and supply chain (DIRECTIVE_051)

- **Decision**: No dependency is added, upgraded or removed. Standard library only. DIRECTIVE_051 controls are not triggered, and no adversarial-squad pass is required for dependencies.

## R-13 Watched-set definition details (FR-001, C-008)

- **Decision**: A system or user unit is watched when it is `.service`, `LoadState=loaded`, `Restart` is not `no`, `NRestarts` parses as a non-negative integer, and it is not ignored. A container is watched when its restart policy is not `no` or empty and it is not ignored. Keys are `system:<Id>`, `user:<Id>` and `container:<name without leading slash>`, so the same name in different scopes never collides. Only the canary's own user manager is read (C-008).
- **Rationale**: Other unit types (sockets, timers) have no `NRestarts` meaning for loops. The `Restart=` filter implements "restart policy other than never". The loaded filter drops `not-found` phantoms.
