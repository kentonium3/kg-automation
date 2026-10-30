#!/usr/bin/env python3
"""STAGE: load and verify the Vikunja release image (#1087, WP03).

An inert step: it never touches a container or the Compose file. Design:
``kitty-specs/vikunja-image-deploy-01M65D3V/research.md`` R-2, R-3, R-13,
R-16, R-18 and R-23 (R-9 to R-24 take precedence over R-1 to R-8) and
``contracts/entrypoints.md``.

``--dry-run`` (read-only: an ``activation.lock`` probe, ``docker info``,
``docker image inspect``, a file stat and hash, a marker read)
    Classic store preflight; archive size and sha256 against the reviewed
    ``services/vikunja/release.json``, then the offline OCI chain; the release
    tag, ``active`` and the rollback image by identity; the activation
    marker. Prints what ``--apply`` would do.

``--apply`` (R-18 order)
    First, before any Docker call, the exclusive non-blocking ``flock`` on
    ``<activation root>/activation.lock`` that ACTIVATE and the rollback
    helper also hold (:func:`dbsafety.take_activation_lock`); held until the
    end, so the marker and ``active`` checks and the tags cannot interleave
    with them or with a second STAGE. A held lock is
    ``STAGE_ACTIVATION_LOCK_BUSY``; the dry run only probes it. Then the
    dry-run checks, then: ``docker load`` (unless the release tag already
    resolves to the config digest), require the loaded ID to equal the config
    digest, verify the image facts against the record, and only then tag the
    release. ``active`` is tagged to the rollback image only when it is
    absent AND no activation marker exists (R-23); an existing ``active`` is
    never retagged. A verification failure after the load leaves the image
    untagged and reports ``STAGE_VERIFY_FAILED`` with the loaded ID.

Output (R-16): line 1 is one fixed summary (``STAGE_*`` or ``FAILED
code=...``), then detail lines carrying only IDs, digests, paths, counts and
stable codes. Raw Docker output goes only to the private 0700 log folder, and
only under ``--apply``: the dry run writes nothing at all.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.vikunja_release import core, dbsafety  # noqa: E402
from scripts.deploy.vikunja_release.core import Fail  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = REPO_ROOT / "services" / "vikunja" / "release.json"

LOAD_TIMEOUT = 300  # R-15: docker load runs before any stop, so it is not outage
TAG_TIMEOUT = 30  # R-15: tag, rm and inspect

# Summary identifiers (registered at import; never free text).
STAGE_DRY_RUN_OK = "STAGE_DRY_RUN_OK"
STAGE_APPLIED = "STAGE_APPLIED"
STAGE_ALREADY_STAGED = "STAGE_ALREADY_STAGED"
# Detail-line identifiers.
STAGE_ARCHIVE_VERIFIED = "STAGE_ARCHIVE_VERIFIED"
STAGE_STATE = "STAGE_STATE"
STAGE_PLAN_LOAD = "STAGE_PLAN_LOAD"
STAGE_PLAN_TAG_RELEASE = "STAGE_PLAN_TAG_RELEASE"
STAGE_PLAN_CREATE_ACTIVE = "STAGE_PLAN_CREATE_ACTIVE"
STAGE_PLAN_NOTHING = "STAGE_PLAN_NOTHING"
STAGE_LOADED = "STAGE_LOADED"
STAGE_IMAGE_VERIFIED = "STAGE_IMAGE_VERIFIED"
STAGE_TAGGED_RELEASE = "STAGE_TAGGED_RELEASE"
STAGE_CREATED_ACTIVE = "STAGE_CREATED_ACTIVE"
STAGE_LOADED_UNTAGGED = "STAGE_LOADED_UNTAGGED"
STAGE_ACTIVATION_LOCK_FREE = "STAGE_ACTIVATION_LOCK_FREE"

core.register_summaries(
    STAGE_DRY_RUN_OK, STAGE_APPLIED, STAGE_ALREADY_STAGED, STAGE_ARCHIVE_VERIFIED, STAGE_STATE,
    STAGE_PLAN_LOAD, STAGE_PLAN_TAG_RELEASE, STAGE_PLAN_CREATE_ACTIVE, STAGE_PLAN_NOTHING,
    STAGE_LOADED, STAGE_IMAGE_VERIFIED, STAGE_TAGGED_RELEASE, STAGE_CREATED_ACTIVE,
    STAGE_LOADED_UNTAGGED, STAGE_ACTIVATION_LOCK_FREE,
)

_LOADED_ID_RE = re.compile(r"^Loaded image ID: (sha256:[0-9a-f]{64})\s*$", re.MULTILINE)

Line = tuple[str, dict[str, Any]]


class Stage:
    """One STAGE run against an injected Docker *runner* and release record."""

    def __init__(self, record: dict[str, Any], runner: Callable[..., Any]) -> None:
        self.rec = record
        self.runner = runner
        self.config_digest: str = record["image"]["config_digest"]
        self.rollback_id: str = record["rollback"]["image_id"]
        self.release_tag: str = record["tags"]["release"]
        self.active_tag: str = record["tags"]["active"]
        self.archive_path = Path(record["archive"]["path"])
        self.activation_root = Path(record["roots"]["activation"])
        self.marker_path = self.activation_root / f"{record['release_version']}.json"
        self.lock_path = self.activation_root / dbsafety.ACTIVATION_LOCK_NAME
        #: Steps completed by ``--apply`` so far; printed after a ``FAILED``
        #: line too, so a partial run says what it changed.
        self.done: list[Line] = []
        #: Detail lines printed after a ``FAILED`` line (e.g. the loaded ID).
        self.failure_details: list[Line] = []

    # -- read-only checks (T012) -------------------------------------------

    def check(self) -> dict[str, Any]:
        """Every dry-run check; refuses with a stable code. Read-only."""
        core.docker_store_ok(self.runner)
        archive = core.verify_archive(self.archive_path, self.rec)

        release_id = core.image_id(self.release_tag, self.runner)
        if release_id is not None and release_id != self.config_digest:
            raise Fail("STAGE_RELEASE_TAG_UNEXPECTED")

        rollback_id = core.image_id(self.rec["rollback"]["ref"], self.runner)
        if rollback_id is None:
            raise Fail("STAGE_ROLLBACK_IMAGE_MISSING")
        if rollback_id != self.rollback_id:
            raise Fail("STAGE_ROLLBACK_IMAGE_UNEXPECTED")

        active_id, marker = self._active_and_marker()
        return {"archive": archive, "release_id": release_id, "active_id": active_id,
                "rollback_id": rollback_id, "marker": marker}

    def _active_and_marker(self) -> tuple[str | None, dict[str, Any] | None]:
        """``active``'s ID and the activation marker, applying R-3 and R-23."""
        active_id = core.image_id(self.active_tag, self.runner)
        marker = core.marker_read(self.marker_path)
        if active_id is None:
            if marker is not None:
                raise Fail("STAGE_ACTIVE_HELD_BY_ACTIVATION")
        elif active_id not in (self.rollback_id, self.config_digest):
            raise Fail("STAGE_ACTIVE_UNEXPECTED")
        return active_id, marker

    def state_lines(self, facts: dict[str, Any]) -> list[Line]:
        archive = facts["archive"]
        marker = facts["marker"]
        return [
            (STAGE_ARCHIVE_VERIFIED, {"path": self.archive_path, "size": archive["size"],
                                      "sha256": archive["sha256"]}),
            (STAGE_STATE, {"release_tag_id": facts["release_id"], "active_id": facts["active_id"],
                           "rollback_id": facts["rollback_id"], "marker": self.marker_path,
                           "marker_phase": marker.get("phase") if marker else None,
                           "marker_outcome": marker.get("outcome") if marker else None}),
        ]

    # -- modes ---------------------------------------------------------------

    # -- activation lock (post-merge review: serialise with ACTIVATE/rollback) --

    def probe_lock(self) -> Line:
        """Dry run: refuse as the apply would when the lock is held; never
        creates the activation root or the lock file."""
        try:
            free = dbsafety.activation_lock_free(self.activation_root)
        except OSError as exc:
            raise Fail("STAGE_ACTIVATION_LOCK_UNAVAILABLE") from exc
        if not free:
            raise Fail("STAGE_ACTIVATION_LOCK_BUSY")
        return (STAGE_ACTIVATION_LOCK_FREE, {"lock": self.lock_path})

    def take_lock(self) -> int:
        """Hold ``activation.lock`` (the one ACTIVATE and the rollback helper
        take) from before the marker and tag checks to the end of the apply,
        so no concurrent STAGE, ACTIVATE or rollback can interleave with the
        ``active`` checks and tags (R-23). Taken before any Docker call."""
        root_fd = dbsafety.open_private_root(self.activation_root, code="ACTIVATION_ROOT")
        try:
            return dbsafety.take_activation_lock(root_fd, busy_code="STAGE_ACTIVATION_LOCK_BUSY",
                                                 unsafe_code="STAGE_ACTIVATION_LOCK_UNAVAILABLE")
        finally:
            os.close(root_fd)

    def dry_run(self) -> list[Line]:
        lock_line = self.probe_lock()
        facts = self.check()
        plan: list[Line] = []
        if facts["release_id"] is None:
            plan.append((STAGE_PLAN_LOAD, {"archive": self.archive_path}))
            plan.append((STAGE_PLAN_TAG_RELEASE, {"id": self.config_digest}))
        if facts["active_id"] is None:
            plan.append((STAGE_PLAN_CREATE_ACTIVE, {"id": self.rollback_id}))
        if not plan:
            plan.append((STAGE_PLAN_NOTHING, {"id": self.config_digest}))
        return [(STAGE_DRY_RUN_OK, {"release_version": self.rec["release_version"],
                                    "config_digest": self.config_digest}),
                *self.state_lines(facts), lock_line, *plan]

    def apply(self) -> list[Line]:
        lock_fd = self.take_lock()
        try:
            return self._apply_locked()
        finally:
            os.close(lock_fd)  # releases the flock

    def _apply_locked(self) -> list[Line]:
        facts = self.check()
        done = self.done
        if facts["release_id"] is None:
            loaded = self._load()
            done.append((STAGE_LOADED, {"id": loaded}))
            self._verify_facts(loaded, loaded_untagged=True)
            done.append((STAGE_IMAGE_VERIFIED, {"id": loaded}))
            self._tag(self.config_digest, self.release_tag, "STAGE_TAG_RELEASE_FAILED")
            done.append((STAGE_TAGGED_RELEASE, {"id": self.config_digest}))
        else:
            # Already staged: the tag resolves to the config digest; re-verify
            # its facts read-only so a no-op is still a verified success.
            self._verify_facts(self.config_digest, loaded_untagged=False)
            done.append((STAGE_IMAGE_VERIFIED, {"id": self.config_digest}))

        if facts["active_id"] is None:
            # Re-read both immediately before the tag (R-23): never create
            # `active` over an activation's hold, and never retag it.
            active_id, _ = self._active_and_marker()
            if active_id is None:
                self._tag(self.rollback_id, self.active_tag, "STAGE_ACTIVE_TAG_FAILED")
                done.append((STAGE_CREATED_ACTIVE, {"id": self.rollback_id}))

        changed = any(name in (STAGE_TAGGED_RELEASE, STAGE_CREATED_ACTIVE) for name, _ in done)
        summary = STAGE_APPLIED if changed else STAGE_ALREADY_STAGED
        return [(summary, {"release_version": self.rec["release_version"],
                           "config_digest": self.config_digest}),
                *self.state_lines(facts), *done]

    # -- mutating steps (T013, T014) ----------------------------------------

    def _load(self) -> str:
        rc, out, err = core.run(["docker", "load", "-i", str(self.archive_path)], LOAD_TIMEOUT,
                                step="DOCKER_LOAD", runner=self.runner)
        if rc != 0:
            raise Fail("STAGE_LOAD_FAILED", detail_private=err or out)
        ids = set(_LOADED_ID_RE.findall(out))
        if not ids:
            raise Fail("STAGE_LOAD_OUTPUT_UNPARSEABLE", detail_private=out)
        if ids != {self.config_digest}:
            for loaded in sorted(ids):
                self.failure_details.append((STAGE_LOADED_UNTAGGED, {"loaded_id": loaded}))
            raise Fail("STAGE_LOADED_ID_UNEXPECTED", detail_private=out)
        return self.config_digest

    def _verify_facts(self, image: str, *, loaded_untagged: bool) -> None:
        """R-2/R-13: ID, architecture, os, user and revision label against
        the record. A mismatch, or an inspection that fails outright (a
        daemon error, a timeout, unparseable output), leaves the image
        untagged and is ``STAGE_VERIFY_FAILED`` (R-18); the inspection's own
        code and raw detail go only to the private log."""
        os_want, arch_want = self.rec["image"]["platform"].split("/", 1)
        try:
            facts = core.image_facts(image, self.runner)
        except Fail as exc:
            if loaded_untagged:
                self.failure_details.append((STAGE_LOADED_UNTAGGED, {"loaded_id": image}))
            raise Fail("STAGE_VERIFY_FAILED",
                       detail_private=f"{exc.code}\n{exc.detail_private or ''}") from exc
        if (facts is None or facts["id"] != self.config_digest
                or facts["architecture"] != arch_want or facts["os"] != os_want
                or facts["user"] != self.rec["image"]["user"]
                or facts["revision"] != self.rec["source_revision"]):
            if loaded_untagged:
                self.failure_details.append((STAGE_LOADED_UNTAGGED, {"loaded_id": image}))
            raise Fail("STAGE_VERIFY_FAILED")

    def _tag(self, source_id: str, ref: str, code: str) -> None:
        rc, out, err = core.run(["docker", "tag", source_id, ref], TAG_TIMEOUT,
                                step="DOCKER_TAG", runner=self.runner)
        if rc != 0:
            raise Fail(code, detail_private=err or out)
        if core.image_id(ref, self.runner) != source_id:
            raise Fail(code)


def main(argv: list[str] | None = None, *, runner: Callable[..., Any] = subprocess.run,
         release_path: Path | str = RELEASE_PATH, stdout: TextIO | None = None,
         stderr: TextIO | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = stdout if stdout is not None else sys.stdout
    # Private raw logs only under --apply; the dry run writes nothing.
    private_root = None
    if args == ["--apply"]:
        try:
            private_root = core.load_release(release_path)["roots"]["private_logs"]
        except Fail:
            private_root = None
    holder: dict[str, Stage] = {}

    def body(mode: str) -> None:
        stage = Stage(core.load_release(release_path), runner)
        holder["stage"] = stage
        lines = stage.dry_run() if mode == "dry-run" else stage.apply()
        for summary, fields in lines:
            core.emit(summary, out, **fields)

    rc = core.run_cli(args, prog="deploy-vikunja-release-stage.py", body=body,
                      private_root=private_root, stdout=out, stderr=stderr)
    if rc == core.EXIT_FAIL and "stage" in holder:
        stage = holder["stage"]
        for summary, fields in [*stage.done, *stage.failure_details]:
            core.emit(summary, out, **fields)
    return rc


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
