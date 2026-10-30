"""The ACTIVATE merge's change set (#1087, WP08).

These files merge together, and only after STAGE is applied; the go packet
assembles the STAGE merge from everything else (WP09). Checks:

* the Compose change is exactly two lines against the mission base
  (``93f40d4a``, origin/main): ``image:`` now names the local indirection tag
  and ``pull_policy: never`` is added directly under it (FR-007 as amended);
* the ACTIVATE manifest validates, declares its baseline, and its post checks
  are release-exact, built here from ``services/vikunja/release.json`` rather
  than hard-coded a second time (R-12);
* the service inventory (JSON and markdown) matches the Compose file and the
  release record (FR-016);
* the exact path set of this change set.

CI checks out with depth 1, so the base Compose file is pinned by sha256
(taken from ``git show 93f40d4a:services/vikunja/docker-compose.yml``); the
test reverses the two-line change and requires that hash. Where the base
commit is available, a second test ties the pin to ``git show``.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.deploy.lib import manifest as manifest_lib

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = _ROOT / "services" / "vikunja" / "docker-compose.yml"
_RELEASE = _ROOT / "services" / "vikunja" / "release.json"
_INVENTORY_JSON = _ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
_INVENTORY_MD = _ROOT / "docs" / "design" / "architecture" / "service-inventory.md"
_MANIFEST_QUEUED = _ROOT / "deploys" / "queued" / "vikunja-release-activate.yaml"
_ENTRY_REL = "scripts/deploy/deploy-vikunja-release-activate.py"

#: The mission base on origin/main, and the sha256 of its Compose file.
BASE_COMMIT = "93f40d4a"
BASE_COMPOSE_SHA256 = "ae5c779b6acd8bde58c2de3f9f0377948b23511e3d6aac8504cd221c8197cd7b"
OLD_LINE = "    image: vikunja/vikunja:2.4.0\n"
NEW_LINES = "    image: office2.local/vikunja:active\n    pull_policy: never\n"

#: The ACTIVATE merge: exactly these paths. The STAGE merge is everything
#: else in the mission (WP09 documents the assembly).
CUTOVER_PATHS = frozenset({
    "services/vikunja/docker-compose.yml",
    "deploys/queued/vikunja-release-activate.yaml",
    "docs/design/architecture/data/service-inventory.json",
    "docs/design/architecture/service-inventory.md",
    "tests/deploy/test_vikunja_cutover_change_set.py",
})
#: Paths the cutover depends on that must ship EARLIER, in the STAGE merge:
#: the inert ACTIVATE code, the release record and the STAGE manifest.
STAGE_MERGE_PREREQUISITES = frozenset({
    "scripts/deploy/deploy-vikunja-release-activate.py",
    "services/vikunja/release.json",
    "deploys/queued/vikunja-release-stage.yaml",
    "scripts/deploy/vikunja_release/core.py",
})


def _release() -> dict:
    return json.loads(_RELEASE.read_text(encoding="utf-8"))


def _resolve_manifest_path() -> Path:
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted((_ROOT / "deploys" / "applied").glob("*-vikunja-release-activate.yaml"))
    return applied[-1] if applied else _MANIFEST_QUEUED


def _manifest() -> dict:
    return yaml.safe_load(_resolve_manifest_path().read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# T033 — the two-line Compose change
# ---------------------------------------------------------------------------


def two_line_change_problems(text: str) -> list[str]:
    """Why *text* is not exactly the base plus the two-line change ([] = ok)."""
    problems = []
    if text.count(NEW_LINES) != 1:
        problems.append("the new image line with pull_policy directly under it appears != 1 time")
        return problems
    base = text.replace(NEW_LINES, OLD_LINE)
    if hashlib.sha256(base.encode("utf-8")).hexdigest() != BASE_COMPOSE_SHA256:
        problems.append("reversing the two lines does not give the base file byte for byte")
    removed = [l for l in difflib.ndiff(base.splitlines(True), text.splitlines(True)) if l.startswith("- ")]
    added = [l for l in difflib.ndiff(base.splitlines(True), text.splitlines(True)) if l.startswith("+ ")]
    if removed != ["- " + OLD_LINE] or added != ["+ " + l + "\n" for l in NEW_LINES.splitlines()]:
        problems.append("the diff is not exactly -image/+image/+pull_policy")
    return problems


def test_compose_is_the_base_plus_exactly_two_lines():
    text = _COMPOSE.read_text(encoding="utf-8")
    assert two_line_change_problems(text) == []
    svc = yaml.safe_load(text)["services"]["vikunja"]
    base_svc = yaml.safe_load(text.replace(NEW_LINES, OLD_LINE))["services"]["vikunja"]
    assert svc["image"] == _release()["tags"]["active"] == "office2.local/vikunja:active"
    assert svc["pull_policy"] == "never"
    assert {k: v for k, v in svc.items() if k not in ("image", "pull_policy")} == \
        {k: v for k, v in base_svc.items() if k != "image"}
    # The fields FR-007 names, unchanged:
    assert svc["container_name"] == "vikunja" and svc["restart"] == "unless-stopped"
    assert svc["ports"] == ["100.92.197.90:3456:3456"]
    assert svc["volumes"] == ["/data/services/vikunja/data:/app/vikunja/files"]
    assert svc["environment"]["VIKUNJA_DATABASE_PATH"] == "/app/vikunja/files/vikunja.db"


@pytest.mark.parametrize("mutate", [
    lambda t: t.replace("100.92.197.90:3456:3456", "0.0.0.0:3456:3456"),
    lambda t: t.replace("/app/vikunja/files/vikunja.db", "/db/vikunja.db"),
    lambda t: t.replace("restart: unless-stopped", "restart: always"),
    lambda t: t.replace(NEW_LINES, "    image: office2.local/vikunja:active\n"),  # pull_policy missing
    lambda t: t.replace(NEW_LINES, "    pull_policy: never\n    image: office2.local/vikunja:active\n"),
    lambda t: t.replace("# Vikunja Task Manager", "# Vikunja task manager"),  # header comment
    lambda t: t + "\n",
], ids=["bind", "db-path", "restart", "no-pull-policy", "order", "header", "trailing-newline"])
def test_any_other_change_is_detected(mutate):
    text = _COMPOSE.read_text(encoding="utf-8")
    assert two_line_change_problems(text) == []  # positive control on the same text
    assert two_line_change_problems(mutate(text)) != []


def test_base_pin_matches_the_mission_base_commit():
    try:
        base = subprocess.run(["git", "show", f"{BASE_COMMIT}:services/vikunja/docker-compose.yml"],
                              cwd=_ROOT, capture_output=True, check=True, timeout=30).stdout
    except (subprocess.CalledProcessError, OSError) as exc:  # shallow CI clone
        pytest.skip(f"mission base {BASE_COMMIT} not in this clone: {type(exc).__name__}")
    assert hashlib.sha256(base).hexdigest() == BASE_COMPOSE_SHA256
    assert base.decode("utf-8").count(OLD_LINE) == 1


# ---------------------------------------------------------------------------
# T034 — the ACTIVATE manifest
# ---------------------------------------------------------------------------


def expected_post_checks(rec: dict) -> list[str]:
    """The release-exact reconcile (R-12), built from the release record."""
    svc = rec["service"]
    return [
        f"docker inspect {svc['container']} --format '{{{{.Image}}}}' | grep -qx {rec['image']['config_digest']}",
        f"curl -fsS --max-time 5 {svc['info_url']} | jq -e '.version == \"{rec['release_version']}\"'",
    ]


def test_manifest_fields():
    m = _manifest()
    assert m["schema_version"] == "v1"
    assert m["name"] == "vikunja-release-activate"
    assert m["issue"] == "kentonium3/kg-automation#1087"
    assert m["tier"] == 2
    assert m["entrypoint"] == _ENTRY_REL and (_ROOT / _ENTRY_REL).is_file()
    assert m["audited_surface"] is True
    assert m["expected_baselines"] == ["docker-images.txt"]
    assert m["created_by"] == "claude-code-1087"
    assert m["verification"]["pre"] == [f"{_ENTRY_REL} --dry-run"]
    notes = m["notes"]
    assert 0 < len(notes) <= 2000
    for needle in ("R-21", "Cancel (R-17)", "ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST", "Retry (R-24)",
                   "retired.json"):
        assert needle in notes


def test_manifest_post_checks_are_the_release_records_identities():
    rec = _release()
    posts = _manifest()["verification"]["post"]
    assert posts == expected_post_checks(rec)
    # Spot-check the pinned values once, so a record edit is visible here too.
    assert rec["image"]["config_digest"] in posts[0] and rec["release_version"] in posts[1]
    # Negative control: a record for another release would not match.
    other = json.loads(json.dumps(rec))
    other["release_version"] = "v2.7.1-671-0000000000"
    assert posts != expected_post_checks(other)


def test_manifest_validates_against_the_schema():
    result = manifest_lib.validate_manifest_file(_resolve_manifest_path())
    assert result.ok, result.details
    assert not manifest_lib.validate_manifest(dict(_manifest(), surprise=True)).ok


def test_manifest_expected_baselines_are_known():
    m = _manifest()
    assert manifest_lib.validate_expected_baselines_only(m).ok
    assert not manifest_lib.validate_expected_baselines_only(dict(m, expected_baselines=["nope.txt"])).ok
    assert not manifest_lib.validate_expected_baselines_only(dict(m, audited_surface=False)).ok


# ---------------------------------------------------------------------------
# T035 — service inventory
# ---------------------------------------------------------------------------


def _vikunja_entry() -> dict:
    data = json.loads(_INVENTORY_JSON.read_text(encoding="utf-8"))
    [entry] = [s for s in data["services"] if s.get("name") == "vikunja"]
    return entry


def test_inventory_json_matches_compose_and_release():
    rec = _release()
    entry = _vikunja_entry()
    compose_image = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))["services"]["vikunja"]["image"]
    assert entry["image"] == compose_image == rec["tags"]["active"]
    assert entry["updated_by"] == "#1087"
    for value in (rec["release_version"], rec["source_revision"], rec["archive"]["sha256"],
                  rec["image"]["config_digest"], rec["rollback"]["image_id"]):
        assert value in entry["notes"]
    top = json.loads(_INVENTORY_JSON.read_text(encoding="utf-8"))
    assert "#1087" in top["updated_by"].split(" + ")[0]


def test_inventory_markdown_matches():
    md = _INVENTORY_MD.read_text(encoding="utf-8")
    row = [l for l in md.splitlines() if l.startswith("| Vikunja |")]
    assert len(row) == 1 and "`office2.local/vikunja:active`" in row[0]
    assert "v2.7.1-670-420c7bcb75" in row[0]
    assert "vikunja/vikunja:0.24.6" not in md
    assert "**Image selection (#1087)**" in md and "`pull_policy: never`" in md


# ---------------------------------------------------------------------------
# T036 — the change-set path set
# ---------------------------------------------------------------------------


def test_cutover_path_set_is_exact_and_present():
    assert CUTOVER_PATHS == {
        "services/vikunja/docker-compose.yml",
        "deploys/queued/vikunja-release-activate.yaml",
        "docs/design/architecture/data/service-inventory.json",
        "docs/design/architecture/service-inventory.md",
        "tests/deploy/test_vikunja_cutover_change_set.py",
    }
    for rel in CUTOVER_PATHS:
        if rel.startswith("deploys/queued/"):
            assert _resolve_manifest_path().exists(), rel
        else:
            assert (_ROOT / rel).is_file(), rel
    assert Path(__file__).resolve().relative_to(_ROOT).as_posix() in CUTOVER_PATHS


def test_cutover_set_excludes_what_must_ship_first_with_stage():
    """The ACTIVATE code, release record and STAGE manifest ship in the STAGE
    merge, before this set; none may be in the cutover set."""
    assert CUTOVER_PATHS.isdisjoint(STAGE_MERGE_PREREQUISITES)
    assert _manifest()["entrypoint"] in STAGE_MERGE_PREREQUISITES
    # The ACTIVATE manifest names an entrypoint outside this set, so a STAGE
    # merge that lacked it would fail the deployer's tier guard, not run.
    assert _manifest()["entrypoint"] not in CUTOVER_PATHS
