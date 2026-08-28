# Research: Crontab Backup Coverage

All findings below were verified against the live office2 host or the installed
source on 2026-08-28, not inferred. Where a claim from the filed issue turned
out to be wrong or unsafe, that is stated.

## R-01 — Adding a restic source path would freeze the existing snapshots

- **Decision**: Do not add `/var/spool/cron` (or anything else) to the restic
  source set. Write the artifact under `/data/services/`, already a source path.
- **Rationale**: `scripts/office2/restic-backup.sh` runs `restic forget` with no
  `--group-by`, so it defaults to `host,paths`. Snapshots are pruned within
  their path group. Adding a fifth path makes every future snapshot a different
  group from the existing 17, which would then match no `forget` policy and
  never be pruned again — silent, permanent, and discovered only as disk
  exhaustion.
- **Alternatives considered**: (a) add the path *and* pin `--group-by host` —
  rejected, it changes global retention semantics for an unrelated reason and is
  a far larger blast radius than the problem; (b) a pre-backup export step
  inside `backup.sh` — rejected under R-04.
- **Verification**: read the `restic forget` invocation directly; confirmed no
  `--group-by` flag present.

## R-02 — The rebaseline command string is executable input, not documentation

- **Decision**: Satisfy FR-007 in prose only. Leave
  `audited-surfaces.json` → `rebaseline_command` byte-identical.
- **Rationale**: `scripts/deploy/felix-deployer/rebaseline.py:585-586` splits the
  command and asserts `rm_tokens[0] == "rm"`; on failure
  `_build_readonly_audit_cmd` returns `["true"]`, which produces no output and
  is documented in-code as "inconclusive". Rewriting the command to archive
  rather than delete — which issue #895 proposes as the *better* option — would
  therefore silently disable the deferred-confirm rebaseline audit for every
  future deploy. The issue's suggestion is unsafe as written.
- **Alternatives considered**: change the command and teach the parser to accept
  an archive form. Rejected for this mission: it edits a fragile seam whose
  failure mode is silent, for a benefit that IC-02 delivers structurally anyway
  (once the crontab is independently backed up, the baseline is no longer
  anyone's only copy). Worth filing separately if the archive form is still
  wanted later.

## R-03 — An unprivileged capture cannot cover `kgale` or `root`

- **Decision**: Scope to the `claude` crontab and say so explicitly everywhere.
- **Rationale**: `audit.sh:302` loops `for u in claude kgale root` but runs
  unprivileged, so two of three silently fail into `|| true`. Tested directly:
  `claude: READABLE`, `kgale: DENIED`, `root: DENIED` — and the resulting
  baseline contains only a `--- claude ---` section. The `kgale` and `root`
  crontabs have never been captured by any surface on this host.
- **Alternatives considered**: a privileged capture via sudo. Rejected — it
  requires a sudoers change, which is Tier 0 and cannot be done autonomously;
  and #899 has already demonstrated that a `claude`-writable path in a sudo rule
  is a privilege-escalation vector. Out of scope, recorded in the spec.

## R-04 — `restic-backup.sh` is repo-tracked but hand-deployed

- **Decision**: Do not put the capture inside `backup.sh`.
- **Rationale**: The repo copy `scripts/office2/restic-backup.sh` is
  byte-identical to the live `/data/services/backup/scripts/backup.sh` (md5
  `767da888…`), but #889 modified it with no `deploys/queued/` manifest and the
  live file was hand-installed with sudo — it is `root:root 0755`. Editing it
  buys a manual privileged deploy step and a Kent block, for no benefit over a
  standalone component.
- **Alternatives considered**: fix the deployment story first, then edit.
  Rejected as scope — filed as #903 instead.

## R-05 — A `/tmp` health probe is barred by two independent gates

- **Decision**: `drift_check.py` must emit a durable pointer under
  `/data/services/openclaw/state/enforcement/` before it can be registered.
- **Rationale**: Its only current trace is `/tmp/drift-check.log`, emptied by
  `systemd-tmpfiles --remove --boot`. `tests/canary/test_inventory_health_checks.py:131-139`
  pins the set of components probing `/tmp` and fails when it changes (only
  `obsidian-sync-heartbeat` is grandfathered, owned by #894); the same file
  restricts `max_age_seconds` to pointer methods and requires an absolute path.
  So registering it against the log is both wrong and mechanically blocked.
- **Alternatives considered**: a `self-check-command` that re-runs the drift
  comparison. Rejected — it answers "is there drift right now", not "did the
  scheduled job run", which is the thing that failed silently for eight hours.
  Freshness is the requirement.

## R-06 — Timer versus cron

- **Decision**: systemd user timer, hourly, `Persistent=true`.
- **Rationale**: `Linger=yes` and 15 user timers already run for `claude`; the
  crontab holds only the five legacy jobs #890 exists to retire. A timer is
  repo-tracked, manifest-deployable, and catches up after downtime. A cron entry
  would enlarge the surface this mission's sibling issue is trying to shrink,
  and would additionally drift `crontabs.txt` during the very window in which
  that baseline is still the only copy of the crontab.
- **Alternatives considered**: daily at 03:30 UTC, just before the 04:00 backup.
  Rejected in favour of hourly — see the plan's rationale: the snapshot copy
  refreshes daily either way, so cadence only improves the *live* artifact,
  which is the fast recovery path and sits on a different tree from
  `/home/claude`. Hourly is free because the artifact is rewritten only on
  change.

## R-07 — `expected_baselines` is not required here

- **Decision**: Omit `expected_baselines` from the manifest.
- **Rationale**: It exists for deploys that mutate host state through a runtime
  CLI with **no repo-file signal** (the canonical case being `openclaw cron rm`
  drifting `openclaw-cron.txt`). Enabling a user timer drifts
  `systemd-user-units.txt` and `systemd-user-unit-contents.txt`, but the unit
  files are tracked in the repo, so felix-deployer's observe-range detects the
  change and auto-rebaselines. The precedent is stated in
  `deploys/applied/0020-openclaw-ecosystem-update-check.yaml`. Declaring it
  anyway would also require `audited_surface: true` coupling and adds a claim
  the pipeline does not need.

## R-08 — Two known pipeline hazards to route around

- CI does **not** schema-validate manifests placed in `deploys/queued/`; the
  workflow only runs schema unit tests over fixtures. A malformed manifest
  therefore passes CI. Mitigation: validate locally before merge with
  `python3 -m scripts.deploy.lib.manifest validate_manifest_file`.
- `notes` has `maxLength: 2000`. Exceeding it is not caught before apply:
  felix-deployer runs the entrypoint's side effects and *then* refuses to write
  the applied record, leaving the manifest queued and re-applying every
  five-minute tick with no alert (#891; the underlying ordering defect is #901).

## Adversarial evidence

No dependency is added, upgraded, or removed by this plan, so the
supply-chain-security decision set is empty and there is nothing for an
adversarial pass to contest on that axis. The post-plan review checkpoint is run
separately against the whole artifact set; its contested findings and their
dispositions (`accepted` / `changed` / `deferred_with_rationale`) are recorded
in the "Post-plan review" section appended below.

## Post-plan review (Codex, read-only, 2026-08-28)

Dispatched via `codex-review-readonly.sh` — no profile, `--sandbox read-only`,
no write access to `.git/`. Seven findings, **all accepted and folded in**; none
deferred, none dropped. The review independently re-verified four of the plan's
load-bearing claims (restic source set and the absent `--group-by`; the
`rebaseline.py` `["true"]` degradation; the canary `/tmp` pin; the
`expected_baselines` omission precedent) — those are recorded as confirmed, not
merely asserted.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | FR-002 ("capture ahead of the backup") had no verification anywhere in the test matrix. | **changed** — added an FR-002 row asserting the timer interval is strictly shorter than the backup interval, plus an end-to-end snapshot check in quickstart. |
| 2 | HIGH | Writing `drift_check.py`'s process exit code into the freshness pointer would make a healthy run that *found drift* (exit 1) read as a component failure, because `probes.py:267-269` treats any non-zero `exit_code` as an explicit error. | **changed** — data-model now defines `exit_code` as runner-execution health only, moves the result to a separate `has_drift` field, and pins the three-row exit mapping. A test asserts drift-found is healthy through the real `run_probe`. |
| 3 | MEDIUM | FR-004 guarded only empty/failed reads; a non-empty *truncated* read could still replace a good artifact. | **changed** — added a shrink guard (>50% smaller body is refused) with first-run carve-out and a `--force` escape, plus a test. |
| 4 | MEDIUM | The SC-004 staleness check in quickstart was not executable — it said "point a dry-run probe" at a fixture, but `scripts.canary.run` exposes no such flag. | **changed** — replaced with concrete `run_probe` invocations covering fresh, stale, and errored pointers, and added the inverse drift-found-is-healthy check. |
| 5 | MEDIUM | Architecture-doc scope was too narrow: `signal-to-doc-map.json` requires the narrative and view surfaces for service/systemd changes, and the data-flow surfaces for a new producer→storage→consumer flow. | **changed** — added `service-inventory.md`, `service-dependencies.view.md`, `data-flows.{json,md,view.md}`, and `docs/INDEX.md` to the project structure. This is the #492 precedent that motivated the map; the query had to be run as `match.change_class`, not a top-level key. |
| 6 | MEDIUM | The plan's test row said the artifact is byte-identical to `crontab -l`, contradicting the data model's provenance header. | **changed** — reworded to "body below the header is byte-identical", plus direct reinstallability. |
| 7 | LOW | Sequencing was presented as a strict IC-01→IC-02→IC-03 chain, but IC-03 has no technical dependency on IC-02. | **changed** — dependency graph stated honestly as `IC-01 -> {IC-02, IC-03}`. |

### Confirmed during review, worth recording

- `systemd-user-units` in `audited-surfaces.json` already covers
  `scripts/office2/*.service` and `scripts/office2/*.timer`, so the new units do
  carry the repo-file signal that R-07's no-`expected_baselines` conclusion
  depends on. R-07 stands.
- Incidental gap, **not** fixed here: the `deploy-pipeline` surface lists
  `scripts/deploy/*.sh` but not `*.py`, while nearly every real entrypoint in
  `scripts/deploy/` is `.py`. This mission is unaffected (its manifest under
  `deploys/queued/*.yaml` supplies the signal), but the pattern set looks like an
  oversight from when `*.sh` was added. Worth a separate issue rather than an
  opportunistic edit to a file this mission is otherwise constrained not to touch.
