# Quickstart: the go packet skeleton

The final go packet fills in the exact SHAs, PR numbers and dry-run output. Steps marked **Kent** are his. Everything else is done by the agent through `office2-claude` or by the felix-deployer.

## 0. Preconditions

- Release acceptance, fork CI and the PM's packet are attached.
- `feat/vikunja-image-deploy` has passed its mission and post-merge reviews.
- The read-only dry runs of both entrypoints on office2 are attached.

## 1. Ingress (agent)

`scripts/vikunja/stage-release-archive.sh --dry-run`, then without `--dry-run`. Record both remote sha256 values.

## 2. STAGE (Kent)

Merge the STAGE commit set (`services/vikunja/release.json`, `scripts/deploy/vikunja_release.py`, both entrypoints, tests, `deploys/queued/vikunja-release-stage.yaml`) to `main`. It must not contain the Compose change or the ACTIVATE manifest.

Within 5 minutes: `deploys/applied/NNNN-vikunja-release-stage.yaml` records success. The agent verifies `docker image ls` shows both `office2.local` tags, and the service is unchanged (still 2.4.0, same container).

## 3. ACTIVATE: the cutover (Kent's go)

1. **Kent**: agree the window. Post-cutover writes are disposed of only by Kent.
2. **Kent**: merge the ACTIVATE commit set (the Compose image line → `office2.local/vikunja:active`, `deploys/queued/vikunja-release-activate.yaml`, docs).
3. Within 5 minutes the deployer runs it. The agent watches `deploys/applied/` and `/data/services/vikunja/activation/<version>.json`.
4. Acceptance:
   - the agent checks `/api/v1/info` shows 200 and the release version, the image ID, the migration line, and the task count against the snapshot;
   - **Kent** logs in to the UI and checks a recurring task's editor and preview.

## 4. Rollback (only on failure)

1. The agent runs `scripts/vikunja/rollback-release.sh --snapshot <dir>`.
2. **Kent** runs the printed `sudo install …` restore through `office2-kgale`.
3. The agent confirms; the guard checks; it retags to 2.4.0 and starts; the agent verifies 2.4.0.
4. Then the agent resets the baselines manually, as an out-of-band change.
