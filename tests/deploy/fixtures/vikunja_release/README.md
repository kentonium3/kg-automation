# vikunja_release test fixtures (#1087)

Captured shapes, no production data. Used by `tests/deploy/test_vikunja_release_core.py`.

- `index.json`: the real release archive's `index.json`, verbatim.
- `manifest.json`: the real archive's `manifest.json` shape. `Config` is the real config blob path;
  the four `Layers` entries are placeholders (`LAYER1`..`LAYER4`). The tests replace `Config` and
  `Layers` with digests they compute for a tiny synthetic archive; the real archive is never read.
- `config.json`: the identity fields of the real image config (architecture, os, `config.User`,
  the revision label, and the image's default `VIKUNJA_DATABASE_PATH`). Its sha256 is computed by
  the tests, not pinned.
- `docker_info.json`: office2 `docker info` `Driver` and `DriverStatus` (classic store, 2026-10-30).
- `image_inspect_vikunja_2.4.0.json`: identity fields of `docker image inspect vikunja/vikunja:2.4.0`
  on office2.
- `container_inspect_vikunja.json`: `.Image` and `.Config.Image` of the running `vikunja` container.
