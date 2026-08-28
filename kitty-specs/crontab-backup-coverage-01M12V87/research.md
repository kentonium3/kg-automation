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
