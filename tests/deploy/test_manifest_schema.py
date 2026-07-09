"""Schema-conformance tests for the v1 deploy manifest.

The canonical schema is stored at ``deploys/schema/manifest-v1.schema.json``.
Each fixture under ``tests/deploy/fixtures/manifests/`` exercises one rule
of the schema. The valid_* fixtures must validate; the invalid_* fixtures
must each raise ``jsonschema.ValidationError``.

The schema targets JSON Schema 2020-12 (``$schema`` field), so we select
``Draft202012Validator`` explicitly. The library's default validator is
Draft 7, which silently ignores the ``allOf``/``if``/``then`` conditional
blocks the manifest schema depends on for Tier-1/2 verification enforcement.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"
FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "manifests"


def _load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _load_fixture(name: str) -> object:
    path = FIXTURES_DIR / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


VALID_FIXTURES = [
    "valid_tier3_minimal",
    "valid_tier2_with_verification",
    "valid_applied_entry",
]

INVALID_FIXTURES = [
    "invalid_tier0",
    "invalid_tier1_missing_verification",
    "invalid_missing_required",
    "invalid_both_source_identifiers",
]


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    return _load_validator()


@pytest.mark.parametrize("name", VALID_FIXTURES)
def test_valid_manifests_pass_schema(validator: Draft202012Validator, name: str) -> None:
    data = _load_fixture(name)
    validator.validate(data)


@pytest.mark.parametrize("name", INVALID_FIXTURES)
def test_invalid_manifests_fail_schema(validator: Draft202012Validator, name: str) -> None:
    data = _load_fixture(name)
    with pytest.raises(ValidationError):
        validator.validate(data)


# ---------------------------------------------------------------------------
# expected_baselines schema field (WP02 T014)
# ---------------------------------------------------------------------------


def _minimal_manifest() -> dict:
    return {
        "schema_version": "v1",
        "name": "expected-baselines-schema-example",
        "mission_slug": "felix-deployer-rebaseline-detection-01KX26DS",
        "tier": 3,
        "entrypoint": "scripts/deploy/tier3/example.sh",
        "audited_surface": True,
        "created_at": "2026-07-09T00:00:00Z",
        "created_by": "kent@intentional.biz",
    }


def test_manifest_with_expected_baselines_passes_schema(
    validator: Draft202012Validator,
) -> None:
    data = _minimal_manifest()
    data["expected_baselines"] = ["openclaw-cron.txt"]
    validator.validate(data)  # must not raise


def test_unknown_property_still_fails_additional_properties_false(
    validator: Draft202012Validator,
) -> None:
    data = _minimal_manifest()
    data["not_a_real_field"] = "nope"
    with pytest.raises(ValidationError):
        validator.validate(data)
