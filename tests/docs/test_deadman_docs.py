"""The off-host dead-man pings are documented and recorded (#1077, FR-008/FR-009)."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "docs" / "design" / "architecture" / "data"
RUNBOOK = REPO / "docs" / "runbooks" / "canary-registry-ops.md"


def test_runbook_section_names_the_operational_facts():
    text = RUNBOOK.read_text()
    for needle in (
        "## Off-host dead-man pings (#1077)",
        "FELIX_DEADMAN_CANARY_URL",
        "FELIX_DEADMAN_HEALTHCHECK_URL",
        "/home/claude/.config/felix/deadman/env",
        "--outcome fail",
        "0 11,23 * * *",
        "read -rsp",
    ):
        assert needle in text, needle


def test_credential_manifest_records_the_ping_urls():
    creds = json.loads((DATA / "credential-manifest.json").read_text())["credentials"]
    (entry,) = [c for c in creds if c.get("name") == "felix-deadman-ping-urls"]
    assert set(entry["used_by"]) >= {"felix-canary", "felix-health-check"}
    assert entry["mode"] == "0600"
    (topic,) = [c for c in creds if c.get("name") == "felix-alert-ntfy-topic"]
    assert "felix-canary" in topic["used_by"]


def test_data_flows_record_the_egress():
    flows = json.loads((DATA / "data-flows.json").read_text())["flows"]
    names = {f["name"]: f for f in flows}
    assert "hc-ping.com" in names["deadman-ping-egress"]["destination"]
    assert "ntfy-health-probe" in names


_REAL_PING_URL = re.compile(r"hc-ping\.com/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")


def test_no_real_ping_url_is_committed_anywhere_in_docs_or_scripts():
    """A ping URL is a capability secret; only placeholders may appear."""
    offenders = []
    for root in (REPO / "docs", REPO / "scripts"):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".json", ".py", ".sample", ".sh", ".txt"}:
                if _REAL_PING_URL.search(path.read_text(errors="ignore")):
                    offenders.append(str(path.relative_to(REPO)))
    assert not offenders, offenders
