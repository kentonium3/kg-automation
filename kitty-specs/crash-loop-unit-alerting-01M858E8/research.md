# Research: Crash-loop unit alerting

Mission `crash-loop-unit-alerting-01M858E8` (kentonium3/kg-automation#1133). Phase 0 output of `/spec-kitty.plan`, 2026-11-23. Revised the same day after the post-plan Codex review. Each revised decision names the finding that changed it (CX-n refers to plan.md "Post-plan Codex review dispositions").

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
- **Alternatives considered**: (a) A new `health_check.method: crash-loop` on a synthetic inventory component. Rejected: it collapses all units into one outcome and one dedup key, so one looping unit would mask a second. (b) A new timer. Ruled out by Decision `owning_monitor`.

## R-02 Restart-count sources (C-002, NFR-003) — revised (CX-3, CX-5)

- **Decision**:
  - **System units**: `systemctl list-units --type=service --all --plain --no-legend --no-pager`. Keep the rows whose LOAD column is `loaded`. If none remain, call nothing further: an argument-free `show` would describe the manager itself. Otherwise make one call to `systemctl show -p Id,Restart,NRestarts,ActiveState,SubState,LoadState -- <units…>`.
  - **User units**: the same pair with `--user`. The canary is a `claude` user unit, so the user manager it reads is its own.
  - **Boot identity**: `/proc/sys/kernel/random/boot_id`, a world-readable kernel file and not a credential.
  - **Containers**: `docker ps -aq --no-trunc`. If it lists nothing, call nothing further. Otherwise `docker inspect --format '{{json .Id}}|{{json .Name}}|{{.RestartCount}}|{{json .HostConfig.RestartPolicy.Name}}|{{json .State.Status}}' -- <ids…>`.
  - **Docker isolation**: every docker command runs with `DOCKER_CONFIG` pointed at a fresh empty temporary directory, so the CLI loads no `config.json` and no registry credential, with `DOCKER_HOST=unix:///var/run/docker.sock` pinned so no remote context is consulted, and with `DOCKER_CONTEXT` unset.
  - **Execution**: all commands run as argv lists (no shell) with a minimal environment. Timeouts are cut from one stage deadline (R-15).
  - **Validation**: the output is reconciled against what was asked for (R-13).
- **Correction to the original claim (CX-3)**: `--format` limits what the docker CLI *prints*. It does not limit what the CLI *retrieves*. The CLI fetches the whole inspect object from the local daemon, `Config.Env` included, and formats it inside its own process. Our process receives only the formatted fields and never parses or holds the container environment. There is no restricted daemon endpoint that returns `RestartCount` without the full object, so this is the narrowest interface available. NFR-003 prohibits reading credential *files*, the journal and sudo, and all three are satisfied: the empty `DOCKER_CONFIG` stops the CLI reading `~/.docker/config.json`. The plan no longer claims that container environment is "never read".
- **Rationale**: `NRestarts` and `RestartCount` are the persistent counters (the spec's invariant). Both are readable by `claude` without sudo: `claude` is in the `docker` group, and systemd properties are world-readable. A single `show` call over all units is about 0.34 s for 192 services.
- **Alternatives considered**: (a) The journal. Unreadable by `claude` (C-002). (b) The Docker Engine API over the socket directly. Rejected because our own process would then parse the full container JSON, environment included, which is strictly worse. (c) Full `docker inspect` JSON. Rejected for the same reason.

## R-03 Live probe evidence (charter Directive 6), office2, 2026-11-23 (read-only, `ssh office2-claude`)

- `systemctl --version` is `systemd 255 (255.4-1ubuntu8.19)`. felix-canary.timer is a **user** timer.
- `systemctl show obsidian-sync.service -p …` printed `Restart=always`, `NRestarts=39`, `ActiveState=active`, `SubState=running`. This is the incident counter still visible about 10 h later, which confirms the spec's signal.
- `systemctl show` prints properties in **its own order** (`Restart, NRestarts, Id, LoadState, ActiveState, SubState`), not in `-p` order. Units are separated by a blank line. **The parser keys on `Id=` within a blank-line-separated block, never on position.**
- `list-units --all` includes `not-found` units (for example `auditd.service  not-found inactive dead`). These are excluded before `show`.
- Counts: 192 system services (`Restart=` 11 always, 168 no, 1 on-abort, 12 on-failure). 2 had `NRestarts > 0` (obsidian-sync 39, snapd 1). 28 user services (1 always: `openclaw-gateway`). 3 containers: `/transcribe-api` (unless-stopped, 0), `/vikunja` (unless-stopped, 0), `/modest_colden` (no, exited).
- Docker `--format` sample output: `"/vikunja"|0|"unless-stopped"|"running"`. Names carry a leading `/`, which is stripped.
- Timing: `systemctl show` over 192 units took 0.335 s real. `docker inspect` over 3 containers took 0.036 s.
- Verbatim samples are kept for test fixtures (`tests/canary/fixtures/crash_loop/`). The docker sample predates the added `.Id` field, so the fixture adds a realistic 64-hex ID and says that it does.

## R-04 K (quiet ticks before "cleared"), the one value the spec delegates

- **Decision**: K = 2 (about 30 minutes without a restart). Stored as `quiet_ticks_to_clear` in the config.
- **Rationale**: A restart counter in a loop with back-off (systemd `RestartSec=` and start-limit pauses, or docker's exponential back-off) can show one quiet 15-minute tick in the middle of a live loop. K = 1 would then send cleared and then a new alert, which is two pages for one episode and breaks FR-007. K = 2 still reports the end within 30 minutes.
- **Alternatives considered**: K = 1 (flaps on back-off lulls). K = 4 (delays the all-clear by an hour).

## R-05 The proven-crossing rule — revised twice (CX-1, round-2 C/HIGH)

- **What the counter can prove.** The canary samples cumulative counters about every 15 minutes (Kent's Decision `detection_latency`). Two samples `(t₀, c₀)` and `(t₁, c₁)` prove only that `Δ = c₁ − c₀` restarts happened somewhere in `L = t₁ − t₀`. Split `L` into `m = ceil(L / window)` consecutive sub-intervals, each no longer than `window`. By pigeonhole, **if `Δ ≥ m·(N − 1) + 1`, at least one sub-interval of length ≤ `window` contained ≥ N restarts.** That is a *proof* of Kent's literal rule ("N restarts within a window, e.g. ≥ 3 in 15 min"). It needs no slack, fudge or reinterpretation of the window.
- **Decision**:
  - For each retained observation `b` older than `now` (history, research R-07), let `L_b = now − b.at`, `m_b = ceil(L_b / window)` and `Δ_b = current − b.count`. The tick **proves a crossing** if any `b` satisfies `Δ_b ≥ m_b·(N − 1) + 1`.
  - The evidence reported is the proving pair with the **smallest `L_b`** (the tightest interval). The alert states Δ, the real period and `m`.
  - If no pair proves a crossing but some `Δ_b ≥ N`, the tick writes **one `crash-loop-unverified` ledger line** for the tightest such pair (Δ, period, the required bound), with no page. Example: 3 or 4 restarts in an interval just over 15 minutes.
  - `window_seconds` is the only window parameter. `slack_seconds` is removed.
- **What this means with real tick spacing.** `OnUnitActiveSec=15min` puts ticks 15:00 to about 16:00 apart, so the previous tick gives `m = 2`. A loop then needs `Δ ≥ 5` between consecutive ticks to be proven. When `Δ` is 3 or 4 over a 15–16-minute interval, the counter cannot prove ≥ 3 within 15 minutes, and the tick records an unverified rise. A real crash loop (the 2026-11-23 shape: 39 restarts in 7 minutes) is far above the bound. With extra observations inside the window (manual runs), `m = 1` pairs need only `Δ ≥ 3`.
- **Long gaps**: the same rule, with nothing special. Three restarts over 3 hours (`m = 12`, bound 25) are not proven, so the tick records an unverified rise. Thirty-nine restarts over 17 minutes (`m = 2`, bound 5) are proven, so a late tick never hides a real loop.
- **Accepted limits** (surfaced in plan.md): (1) slow loops of N to `2(N−1)` restarts per tick interval are recorded as unverified, not paged; (2) a short burst that straddles a tick boundary can be split so that no pair proves it. Both follow from Kent's sampling decision. Neither produces a false alert: **every page is a proven crossing** (NFR-004, SC-003).
- **Alternatives considered**: (a) "Δ ≥ N within `window + slack`" (round 1). Codex round 2 showed it alerts on intervals where no 15-minute window held N, so it changes Kent's window. (b) Treating every long gap as unverified (round 1). It hides real loops after a late tick. (c) A faster cadence. Declined by Kent's `detection_latency` decision.
- **Addendum 2026-11-23 (WP02 review cycle 1, Codex gpt-6.1-sol, MAJOR).** A **re-remind** proof may use only candidate baselines observed at or after the episode's `last_alert_utc`, so a page always rests on fresh evidence. Without this, a 0→39 burst followed by +1 per tick keeps the episode open, and the original baseline re-pages six hours later (Δ=62, m=26, bound 53). See data-model.md INV-CL-4.

## R-06 Counter resets, generations, new and removed units — revised (CX-2, CX-7, CX-8, round-2 B7)

- **Decision**:
  - **Host generation (round-3 HIGH)**: each unit stores the `boot_id` under which it was last observed. **When a unit is next observed in a complete read and its stored `boot_id` differs from the current one, it is rebased.** Rebasing sets the history to `[(now, current)]`, emits no event, and closes any open episode **silently**. This holds for every scope, containers included, and it holds even if the unit's scope was unreadable on the first post-reboot tick. The spec's "Host reboot … new baseline" covers containers too. If the boot ID cannot be read, all three scopes are incomplete for that tick.
  - **Container generation**: each container also carries its container ID. A changed ID (re-created under the same name) is a reset for that container.
  - **Reset**: a decrease (`current < history[-1].count`) or a container-ID change. The history is replaced with `[(now, current)]` and nothing alerts (FR-009). Within an open episode, a reset tick counts as **quiet** (round-3 M1). It can therefore reach K and emit the INFO **cleared** entry, for example when an operator's restart ended the loop. It never emits an alert or re-remind. A boot change closes the episode silently instead, because there is no observed quiet period to report.
  - **Episode consumption boundary (CX-2)**: when an episode **clears**, the history is replaced with `[(now, current)]`. A new episode needs a fresh proven crossing after the clear.
  - **First sight**: a unit seen for the first time gets a baseline and no alert (FR-010). That includes the first pass after deploy and the first pass after state loss.
  - **Removal**: a unit missing from a scope that was read completely (R-13) has its state dropped, and an open episode ends silently. A unit in a scope that was not read completely keeps its state.
- **Counter lifecycle matrix** (CX-7; from source reading cited by the post-plan reviewer: systemd v255 `src/core/service.c`, moby v27.5.1 `daemon/start.go` and `daemon/daemon.go`. Not measured live.)

  | Event | `NRestarts` / `RestartCount` | Stage sees |
  |---|---|---|
  | Automatic restart (`Restart=` policy) | +1 | rise |
  | `systemctl daemon-reload` / `daemon-reexec` | preserved (serialised) | no change |
  | Explicit `systemctl start` / `restart` by an operator | reset to 0 | decrease → reset |
  | Start-limit hit → `failed` | retained until reset/start | no rise (quiet); failed-state checks still fire |
  | Host reboot | 0, new boot ID | boot-ID change → every unit rebased |
  | Manual `docker start` / `docker restart` | reset | decrease → reset |
  | Docker daemon restart restoring a container | may reset | decrease → reset (or no change under live-restore) |
  | Compose re-creates a container | new ID, starts at 0 | container-ID change → reset |

- **Property**: every reset path under-counts and never over-counts. An invisible reset between observations shows up as a smaller rise. Resets can cause misses, never false alerts.
- **Alternatives considered**: counting a generation change as "Δ from 0" (rejected: it contradicts the spec's reboot-is-baseline edge case); systemd `InvocationID` as the generation (rejected: automatic restarts change it too).
## R-07 State persistence, history, clock and concurrency — revised (CX-9, CX-10, round-2 B5/B6)

- **Decision**:
  - **Document**: `/data/services/felix-canary/state/crash-loop.json` holds `{"schema_version": 1, "updated_at_utc", "boot_id", "units": {<key>: {generation, boot_id, history, episode}}}`. It is written atomically (temp file in the same directory, `fsync`, `os.replace`).
  - **Load is fail-safe**: a missing or corrupt document, a wrong type or an unknown `schema_version` loads as `{}`. Every unit is then first-seen, with no alert and no crash. Each unit entry is validated semantically, and a malformed one is dropped **alone**. Malformed means any of:
    - a bad key or generation;
    - negative counts;
    - unparseable or naive times;
    - history not strictly ascending in time, or decreasing in count;
    - a malformed episode.
  - **History: dominance compaction** (round-2 B5, round-3 M2). A candidate baseline `b1` *dominates* `b2` when `b1.at ≥ b2.at` and `b1.count ≤ b2.count`: it gives the same or a larger Δ over the same or a shorter interval, so it proves everything `b2` proves. Counts never decrease within a generation, so each tick's observation is either **appended** (count rose) or **replaces the newest entry** (same count: the later entry dominates). No proving baseline is ever discarded by spacing.
  - `history[-1]` is always the latest observation, and it drives the `rose`, reset and clock checks.
  - **Entries inside the last window (`at ≥ now − window`) are never pruned (round-4 M1).** Every single-window proof (`m = 1`) is therefore always found, whatever the config or sampling density.
  - **Older entries** are pruned when they are older than 24 h, and their number is capped at **64** by dropping the oldest. The newest entry is always kept.
  - The residual bound applies only to multi-window proofs (`m ≥ 2`) that need a baseline more than 64 older distinct-count observations, or 24 h, back. This is stated, not hidden.
  - The config bounds `threshold ≤ 50` and `window_seconds ≤ 3600` keep the supported envelope explicit (R-10).
  - **One clock rule (round-2 B6)**:
    - On load, a time later than `now + 60 s` makes its unit entry **malformed** (dropped, and the unit is first-seen) rather than being clamped.
    - During evaluation, if `now ≤ history[-1].at`, the unit's state is unchanged and it produces no event. This check runs **first**, before the generation and reset checks.
  - **Lock (CX-9)**: an exclusive, non-blocking `fcntl.flock` on `crash-loop.lock`, beside the state file, around load → evaluate → emit → save. If the lock is busy, the stage is skipped for that pass and `crash_loop:locked` goes to `errors[]`. `dry_run` takes no lock and writes nothing. Two systemd starts of the same unit coalesce into one job, so the lock only guards manual CLI runs.
  - **Order**: emit, then save. A failed save after a successful emit repeats the page on the next tick (fail loud), and the save fault goes to `errors[]`.
- **Alternatives considered**: extending `dedup.json` (rejected: it couples a crash-loop bug to every component); clamping future times (round 1; ambiguous, so replaced by the single rule above); middle-thinning (round 1) and 60 s spacing with 4 × window retention (round 2). Both can destroy a proving baseline (round-3 M2), so both were replaced by dominance compaction.
## R-08 Alert routing, delivery accounting, could-not-check and fault isolation — revised (CX-6, round-2 B1/B2)

- **Decision**:
  - **Crash-loop alert** (episode start) and **re-remind**: `Severity.ERROR`, `source="felix-canary:crash-loop:<scope>:<name>"`, sent through the pass's `emit_fn`.
  - **Cleared**: `Severity.INFO`, the canary's "recovered" convention.
  - **Lifecycle**: owned by the crash-loop state machine. The re-remind interval is `scripts.canary.dedup.DEFAULT_WINDOW` (6 h).
  - **Delivery accounting (CX-6)**: every crash-loop emission (alert, re-remind, cleared and aggregate) uses `_route`'s result handling. `getattr(result, "ok", True) is False` increments `alerts_undelivered`, so the off-host dead-man pings `fail` and healthchecks.io tells Kent that alerting is broken. Canary ledger event lines carry `emitted` (attempted) and `delivered`.
  - **No retry on failed delivery (round-2 B1/B2): the existing canary's policy.** `_route` advances dedup whether or not delivery succeeds, and the crash-loop machine does the same. `last_alert_utc` is the time of the *attempt*. Retry semantics are what produced the contradictions in round 2: an evidence payload with no home, clear-versus-pending priority, and resends on reset ticks. The failure is visible through the dead-man and both ledgers, and matching the existing canary keeps FR-013 parity.
  - **Scope could-not-check (FR-011)**: each scope is routed through the existing dedup path as a canary component: `crash-loop:system`, `crash-loop:user` and `crash-loop:container`. The outcome is `healthy` for a complete read and `unknown` (with the reason) otherwise. That reuses the canary's F5 rule and its "recovered" transition.
  - **Fault isolation (FR-013, NFR-005)**: the whole stage runs inside `try/except Exception`. An unexpected fault appends `crash_loop:<ExcName>:<msg>` to `errors[]`, and the pass continues to the dedup save, tick-signal and summary. The stage runs after every existing component.
- **Alternatives considered**: retry until delivered (round 1; contradictory, as above); paging scope `unknown` at once (diverges from F5); WARN severity for crash loops (a looping service is effectively down).
## R-09 Wiring, and the existing-test harness — revised (CX-12)

- **Decision**:
  - **The keyword**: `run_pass` gains the keyword `crash_loop_check: CrashLoopCheck | None = None`. `None` skips the stage, so direct `run_pass` callers and tests are unchanged and never reach real `systemctl` or `docker`.
  - **Wiring**: `main()` passes the real check: default readers, repo config, state path, lock path.
  - **The tick-signal file keeps its schema**: the crash-loop summary lives under `summary["crash_loop"]` and is excluded from the persisted signal, the same way `alerts_undelivered` is.
  - **Harness adaptation (CX-12)**: three existing test fakes replace `run_pass` with `def fake_run_pass(*, now, dry_run[=False])` (`tests/canary/test_run.py` ×2, `tests/canary/test_run_deadman.py` ×1). They gain `**_ignored`. Only the signature changes: no assertion changes and no behaviour changes, because each fake still calls the real `run_pass` without the check. This narrows the plan's earlier claim that the suite would pass "unmodified".
  - **Enabled-path evidence (CX-12)**: new tests run the same inputs with the stage disabled and then enabled (fake readers) and assert that every existing component's outcome, dedup entry and ledger line is identical in both runs (SC-005). Another test runs the real tick-signal key-ledger reconciliation (`tests/canary/ledger_reconcile.py`) against a pass with the stage enabled. Others drive the stage's successful, unknown, exception, undelivered and dry-run paths through the real `main()` with the dead-man stubbed. The dry-run test asserts no emit, no state write and no write to either ledger.
- **Alternatives considered**: (a) Default-on in `run_pass`. Leaks real effects into tests. (b) Enabling the stage implicitly when production paths are in use. Too magic.

## R-10 Configuration file

- **Decision**: `scripts/canary/crash_loop_config.json` is read once per pass and validated strictly:
  - `threshold`: an integer from 2 to 50;
  - `window_seconds`: an integer from 60 to 3600;
  - `quiet_ticks_to_clear`: an integer ≥ 1;
  - `max_alerts_per_tick`: an integer ≥ 1 (R-15);
  - `read_budget_seconds`: an integer from 1 to 10 (R-15);
  - `ignore`: a list of `{"unit": "<scope>:<name>", "reason": "<non-empty>"}`, where scope is `system`, `user` or `container`. Matching is exact, and duplicates are not allowed.
  - No unknown keys are allowed. `slack_seconds` was removed in round 2 (R-05).
  - An **invalid or unreadable config** makes all three scopes `unknown` with evidence `config invalid: …`, and nothing is evaluated. It never falls back silently to defaults. The initial ignore list is empty.
- **Rationale**: Per the spec's assumptions, a threshold change is a config change, not a code change. Failing closed into a visible `unknown` follows engineering principle 14 and the canary's INV-002.
- **Alternatives considered**: config in service-inventory.json (mixes a host-wide policy into per-service entries); glob ignore patterns (could ignore more than intended).

## R-11 Deploy path (C-004) and rebaseline — revised (CX-11, CX-13)

- **Decision**: Add the manifest `deploys/queued/<next>-crash-loop-unit-alerting.yaml` (tier 3, **`audited_surface: true`**) with the entrypoint `scripts/deploy/deploy-crash-loop-unit-alerting.py`.
  - `--dry-run`: preflight (euid `claude`, `HOME=/home/claude`). Validate the config. Run all three readers once, read-only, and report each scope's completeness and the time taken. Fail if any scope cannot be read.
  - `--apply`:
    1. Preflight.
    2. Record `t0`, then `systemctl --user start felix-canary.service` (a oneshot that blocks until done). If the start joined a pass already running from the timer, the artifacts may predate `t0`. In that case start the unit once more, and fail if they are still stale.
    3. Prove the stage from the fresh artifacts. `crash-loop.json` has `updated_at_utc ≥ t0`. Today's canary ledger has `crash-loop:system`, `crash-loop:user` **and** `crash-loop:container` lines from this run, each with outcome `healthy`, so all three scopes were read completely (FR-012/SC-004 coverage). `last-tick.json` has no `crash_loop:` entry in `errors`. Any crash-loop event ledger line from this run has `delivered: true`.
  - **Merge gate**: the manifest is authored in the mission branch. **It is not merged or queued for application without Kent's approval**, because merging to `main` is what deploys.
  - **Rebaseline (CX-13)**: the manifest matches the `deploy-pipeline` surface in `audited-surfaces.json` (`deploys/queued/*.yaml`, `rebaseline_required: true`, `affected_baselines: []`). felix-deployer's `rebaseline.py` opens a pending observation for any matched surface. So the manifest declares `audited_surface: true`, and the expected outcome is a clean reconciliation, with no fingerprint drift because no hashed file changes. Merge record: `Rebaseline: automated — felix-deployer (deferred-confirm) on the post-merge deploy`. `tooling/scripts/check_audited_surface_drift.py` is run on the final diff and its output recorded. Its matches are informational, and the declaration above does not depend on its exit code.
- **Alternatives considered**: no manifest (code-only pull). Rejected because of C-004, and because the post-merge live verification needs an owner.

## R-12 Dependencies and supply chain (DIRECTIVE_051)

- **Decision**: No dependency is added, upgraded or removed. Standard library only. DIRECTIVE_051 controls are not triggered.

## R-13 Watched set, and complete versus incomplete reads — revised (CX-5)

- **Decision**:
  - **Policy exclusion** (deliberate, never an error): a unit is not watched when its `LoadState` is not `loaded`, its `Restart` is `no`, or it is on the ignore list. A container is not watched when its restart policy is `no` or empty, or it is ignored.
  - **Observation failure** (the scope becomes `unknown` and every unit in it keeps its state):
    - a non-zero exit from any command;
    - a timeout or deadline overrun;
    - a `show` or `inspect` record missing for an identity that was asked for;
    - a duplicate `Id` or ID;
    - a loaded unit with `Restart` other than `no` whose `NRestarts` is missing or not a non-negative integer;
    - a container record with a malformed count, name or ID;
    - unparseable output.
  - **Benign race**: a unit enumerated and then reported by `show` as `LoadState=not-found` disappeared in between. It is treated as gone, and this is not an error.
  - **Watched units**: keys are `system:<Id>`, `user:<Id>` and `container:<name without leading slash>`, so the same name in different scopes never collides. Template instances (`foo@bar.service`) are ordinary Ids. Only the canary's own user manager is read (C-008).
- **Rationale**: A partial or malformed read must never silently delete coverage or an open episode (CX-5). Separating exclusion from failure makes that testable.

## R-14 Seven-day production acceptance (SC-003, NFR-004, NFR-005) — new (CX-14)

- **Decision**:
  - **Evidence retained**: each crash-loop event line in the canary ledger records `baseline_count`, `baseline_at`, `current_count`, `observed_at` and `delta`. Every `crash-loop-unverified` line records the same, plus the required bound. That is enough to check, alert by alert, that each page was a proven crossing (R-05). The canary ledger and the alert-bus ledger are both date-partitioned files that are kept.
  - **Owned follow-up**: 7 days after the deploy is applied, a dated check, recorded on kentonium3/kg-automation#1133:
    1. Every alert-bus ledger entry whose source starts `felix-canary:crash-loop:` and whose kind is `alert`, `reremind` or `aggregate` (the aggregate covers its listed and ledgered units) has matching canary-ledger event lines. Each line's interval satisfies the proven-crossing bound `delta ≥ m·(threshold−1)+1`, where `m = ceil(period/window)` (SC-003/NFR-004: zero violations).
    2. The user journal of `felix-canary.service` (an operator read, not the check's) shows no non-zero exit. In the canary ledger, every daily file has scope lines at the 15-minute cadence, and no tick recorded a `crash_loop:` error (NFR-005).
  - **Docs**: the procedure is written into `docs/runbooks/canary-registry-ops.md`.
- **Rationale**: The spec states 7-day outcomes. They need a defined procedure and the evidence to run it.

## R-15 Time budget and alert-burst bound (NFR-002, NFR-001) — revised (CX-4, round-2 B3/B4)

- **Decision**:
  - **Read deadline**: one monotonic deadline, `read_budget_seconds = 6`, covers all three scopes. Each command's timeout is `min(3 s, remaining)`. A scope not reached, or cut off, is `unknown` and keeps its state. Measured normal reads take about 0.4 s.
  - **Emission cap**: `max_alerts_per_tick`, default 3. The first three events of a tick (ordered alert, then re-remind, then cleared, then by key) are sent individually. **All** remaining events are folded into one aggregate alert, so a tick makes at most **4** alert-bus calls.
  - **Aggregate content** (round-2 B3): one entry per folded unit, `"<key> <kind> +Δ/<period> <state>"`, added to the description only while it stays within **900 characters**. That leaves room under the bus's `DESCRIPTION_MAX = 1000`, so the bus never truncates silently. Any entries that do not fit are summarised as `"… and <k> more — see canary ledger <date>"`. The canary ledger always has one line per event, with full detail. `details` carries `count` and `units_listed` (the number shown) as strings, kept below the bus's 500-character `DETAIL_VALUE_MAX`. Each folded unit's episode is stamped normally. Kent gets one page that says how many units are looping, names as many as fit, and points to where every unit is recorded.
- **NFR-002 / NFR-001 reconciliation (surfaced to Kent, plan.md)**:
  - On a pass with **no** crash-loop event, the stage costs the read time (measured about 0.4 s, hard-capped at 6 s) plus microseconds of evaluation, so it meets NFR-002's 10-second limit.
  - On a pass **with** events, each alert-bus call costs the bus's delivery time, typically under 1 s against ntfy. The bus's own ceiling is 15 s per call (`delivery.py` `_SUBPROCESS_TIMEOUT`), so the worst case is 6 s plus 4 × 15 s.
  - Bounding that further would need asynchronous delivery or a change to the shared alert bus. Both are outside this mission (C-003: use the existing bus).
  - NFR-001's "under 1 minute" run-time assumption holds for typical delivery. Only a degraded ntfy can break it, and a degraded ntfy is already reported by the dead-man's channel probe.
- **Alternatives considered**: no cap (an unbounded page storm and unbounded time); an aggregate that lists every unit (the bus would truncate it silently, round-2 B3); asynchronous delivery (changes the bus contract, out of scope).
