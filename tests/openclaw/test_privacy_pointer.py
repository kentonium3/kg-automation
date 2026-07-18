"""Privacy-pointer CI guard (#752, safety net replacing `{{VAULT_GROWTH_NAME}}`).

Retiring the vault `.tmpl` render mechanism (#752) removed the
`{{VAULT_GROWTH_NAME}}` render-time indirection that guaranteed each agent
prompt's enforceable privacy rule referenced the *current* Growth folder name
from the registry. The literal `04-Growth/_private` string now lives hardcoded
in `validate_workspace.PRIVACY_TOKEN` and in the committed agent prompts.

Without a guard, renaming the Growth folder in `scripts/vault/paths.json` (e.g.
`04-Growth` → `05-Growth`) would silently leave every privacy rule — and the
`PRIVACY_TOKEN` constant — pointing at a folder that no longer exists, while
`check_privacy_boundary` still passed (it only checks the *literal* token is
present). This test ties the privacy token back to the registry so that drift
fails CI, which is what the retired template substitution used to enforce.

Scope note: this guards the Growth-folder *name* (the `{{VAULT_GROWTH_NAME}}`
concern). The separate home-prefix representation inconsistency (`~/…` vs
`/home/kgale/…`) is #732's open canonicalization decision, not enforced here.
"""
from __future__ import annotations

from pathlib import Path

from scripts.openclaw.agents import validate_workspace as vw
from scripts.vault.resolver import get_vault_folder_name

_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "openclaw" / "agents"


def test_privacy_token_matches_registry_growth_name():
    """`PRIVACY_TOKEN` must derive from the registry's `growth` folder name.

    This is the core safety net: if the Growth folder is renamed in paths.json,
    the hardcoded token no longer matches and CI fails until it (and the prompts)
    are updated — the guarantee `{{VAULT_GROWTH_NAME}}` gave at render time.
    """
    growth_name = get_vault_folder_name("growth")
    assert vw.PRIVACY_TOKEN == f"{growth_name}/_private", (
        f"validate_workspace.PRIVACY_TOKEN ({vw.PRIVACY_TOKEN!r}) has drifted from "
        f"the registry Growth folder ({growth_name!r}). Update PRIVACY_TOKEN — and "
        f"every agent prompt's privacy rule — to '{growth_name}/_private' (#752/#732)."
    )


def test_every_active_prompt_references_current_growth_private_path():
    """Each active agent workspace must reference `<growth>/_private` in an owner
    file — with the CURRENT registry folder name, not a stale hardcoded one."""
    growth_name = get_vault_folder_name("growth")
    expected = f"{growth_name}/_private"
    offenders: list[str] = []
    workspaces = vw.discover_workspaces(_AGENTS_ROOT)
    assert workspaces, "no agent workspaces discovered — scan is vacuously green"
    for ws in workspaces:
        present = any(
            expected in (ws / owner).read_text(encoding="utf-8")
            for owner in vw.PRIVACY_OWNER_FILES
            if (ws / owner).is_file()
        )
        if not present:
            offenders.append(ws.name)
    assert not offenders, (
        f"agent workspace(s) missing the current '{expected}' privacy pointer in "
        f"{list(vw.PRIVACY_OWNER_FILES)}: {offenders}. After a Growth-folder rename, "
        f"update the privacy rule in each prompt (#752 privacy-pointer guard)."
    )
