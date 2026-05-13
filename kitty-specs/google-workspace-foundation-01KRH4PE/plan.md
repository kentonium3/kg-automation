# Implementation Plan: Google Workspace foundation

**Branch**: `main` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)
**Source issue**: [#100](https://github.com/kentonium3/kg-automation/issues/100) Phase 2

## Summary

Pure docs/architecture mission. Deliverables: one new runbook, three architecture-doc updates (service-inventory, credentials-and-secrets + manifest, identity-model), one legacy script deprecation, two index/map registrations (INDEX.md, doc-domain-map.json), one validation pass.

No new code. No tests beyond `validate_docs.py`. No deploy step. No agent prompt changes.

## Technical Context

**Language/Version**: N/A — docs only. Validation via Python 3.10+ (validate_docs.py).
**Primary Dependencies**: existing repo doc tooling (`tooling/scripts/validate_docs.py`).
**Storage**: filesystem under `docs/`; legacy script move to `docs/archive/scripts/`.
**Testing**: `python3 tooling/scripts/validate_docs.py` (validates all doc frontmatter, link integrity, JSON shape, etc.).
**Target Platform**: repo-local. No office2 deploy required for the mission's deliverables (the artifacts ARE the deliverables).
**Project Type**: docs-only.
**Performance Goals**: N/A.
**Constraints**: NFR-001 self-contained runbook; NFR-002 three known pitfalls documented; NFR-003 no new code.
**Scale/Scope**: 1 new runbook (~400 lines including the three pitfall sections); 4 modified architecture docs; 2 modified registry files; 1 legacy-script move.

## Charter Check

Charter loaded compact. Tier 4 (Auto-Commit) per `change-risk-taxonomy.json` — pure schema/metadata/docs changes, no code or service surface. No pre-flight checklist required. **Gate**: PASS.

## Project Structure

### Documentation (this feature)

```
kitty-specs/google-workspace-foundation-01KRH4PE/
├── plan.md
├── research.md          # No new research; references ADR-0001 + 2026-05-13 setup-log findings
├── quickstart.md        # Operator-self-check recipe
├── spec.md
├── meta.json
├── checklists/requirements.md
└── tasks/               # Populated by /spec-kitty.tasks
```

### Source Code / Docs (repository root)

```
docs/runbooks/
└── google-workspace-ops.md                       # NEW (~400 lines)

docs/design/architecture/
├── service-inventory.md                          # MODIFY: add gog entry
├── credentials-and-secrets.md                    # MODIFY: register new creds, mark legacy deprecated
├── identity-model.md                             # MODIFY: add personal Google account section
└── data/
    ├── service-inventory.json                    # MODIFY: matching JSON entry
    └── credential-manifest.json                  # MODIFY: matching JSON entries
    └── doc-domain-map.json                       # MODIFY: add runbook + any archive moves

docs/INDEX.md                                     # MODIFY: register runbook + archive moves

docs/archive/scripts/
└── authorize-calendar.py                         # MOVED from scripts/google/  (legacy cleanup)

scripts/google/
└── authorize-calendar.py                         # REMOVED (moved to archive)
```

**Structure Decision**: Standard docs/architecture surface. Legacy script moves to `docs/archive/scripts/` matching the repo's existing archive convention (compare `docs/archive/` for prior precedent). Per FR-005 the implementer can alternatively leave the script in place with a deprecation banner; archive-move is preferred for cleanliness.

## Complexity Tracking

*No Charter Check violations. Section intentionally empty.*

## Phase 0: Research / Alignment

See [research.md](research.md). No new research beyond consolidating findings from:

1. ADR-0001 (`docs/design/architecture/adr/0001-google-workspace-via-gog.md`) — the decision record.
2. The live 2026-05-13 setup chain on office2 — what worked, what failed, what the fixes were.

Specifically the three pitfalls discovered live become the load-bearing content of the runbook's "Common pitfalls" section.

## Phase 1: Design

### `docs/runbooks/google-workspace-ops.md` structure

Sections:

1. **Overview** — what gog is, what it provides, which Google services it covers, who runs it (claude on office2).
2. **One-time setup procedure** — step-by-step (mirrors what we did 2026-05-13):
   1. Install Linuxbrew (as kgale, with sudo).
   2. Install gog (`brew install steipete/tap/gogcli`).
   3. Persist brew in claude's bashrc.
   4. Set up Google Cloud Console (new project, enable 6 APIs, OAuth consent screen, OAuth Client ID for Desktop app, download `client_secret.json`).
   5. scp client_secret.json to office2 at `/data/services/openclaw/secrets/google-workspace-client.json`; chmod 600.
   6. Set up the gog keyring file backend (random passphrase to `/data/services/openclaw/secrets/gog-keyring-password`; export GOG_KEYRING_BACKEND + GOG_KEYRING_PASSWORD in claude's bashrc).
   7. Run `gog auth credentials <path>`.
   8. Run `gog auth add <email> --services gmail,calendar,drive,contacts,docs,sheets --remote` two-step flow.
   9. Smoke test (`gog calendar colors`, `gog gmail search 'newer_than:1d' --max 1`, etc.).
3. **Common pitfalls** (load-bearing — NFR-002):
   - **Calendar MCP API trap**: searching "Calendar" in the API library returns "Calendar MCP API" — that's NOT what gog needs. Enable "Google Calendar API" (the classic one). Verify all 6 enabled in APIs Dashboard before proceeding.
   - **D-Bus SecretService failure on headless**: gog's default keyring backend fails on Ubuntu server without a desktop session. Symptom: "keyring connection timed out after 10s". Fix: set `GOG_KEYRING_BACKEND=file` + `GOG_KEYRING_PASSWORD=<value>` env vars. Note: the OAuth `code=` is consumed even when keyring write fails, so the user must restart from step 1 of `--remote` flow after fixing the backend.
   - **Per-user brew PATH**: Linuxbrew's installer only updates the installing user's bashrc. claude's bashrc must be updated separately. Symptom: `gog: command not found` when running as claude after a fresh ssh session. Fix: `echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc` as claude.
4. **Common commands** — copy from `/usr/lib/node_modules/openclaw/skills/gog/SKILL.md` (Gmail search, Calendar list/create, Drive search, Contacts list, Sheets get/update, Docs cat). Link to gog's homepage for the full reference.
5. **Adding a second Google account (Intentional)** — procedure for the next Google project: same Cloud Console setup against the Intentional account, separate Client ID, `gog auth credentials --client intentional <path>` (or similar alias), `gog auth add intentional@example.com --client intentional --services ... --remote`. Verifies via `gog auth list` showing both accounts.
6. **Health checks / troubleshooting** — `gog auth doctor`, `gog auth list`, `openclaw skills info gog`, checking refresh-token expiry, scope-expansion procedure (re-run `gog auth add` with broader `--services`).
7. **References** — ADR-0001, gog homepage, SKILL.md location on office2.

### `docs/design/architecture/service-inventory.md` + `data/service-inventory.json`

Add an entry for the Google Workspace integration in the appropriate section (likely under Felix Core or as a peer integration). Fields:

- name: `google-workspace`
- type: `cli-integration`
- host: `office2`
- agent: not bound to a specific agent — usable by any Felix agent
- deployed_by: `#100` (ADR-0001)
- updated_by: `#100-google-workspace-foundation`
- status: `active`
- purpose: "Google Workspace API access (Gmail, Calendar, Drive, Contacts, Sheets, Docs) via the gog CLI"
- runbook: `docs/runbooks/google-workspace-ops.md`
- risk_tier: 3
- config_files: list `client_secret.json`, `gog-keyring-password`, gog config file
- dependencies: openclaw-gateway:18789 (skill discovery), Google APIs (external)

### `docs/design/architecture/credentials-and-secrets.md` + `data/credential-manifest.json`

Register:

- `google-workspace-client.json` (path `/data/services/openclaw/secrets/`, mode 600, owner claude:felix, purpose "OAuth 2.0 Desktop client_secret for Google Workspace via gog")
- `gog-keyring-password` (path `/data/services/openclaw/secrets/`, mode 600, owner claude:felix, purpose "gog keyring encryption passphrase — file backend")
- gog-managed refresh-token (path `/home/claude/.config/gogcli/credentials.json`, managed by gog itself, contains encrypted refresh tokens)

Mark legacy as deprecated:

- `google-calendar-client-id`, `google-calendar-client-secret`, `google-calendar-refresh-token` — all `status: deprecated`, `deprecated_at: 2026-05-13`, `replaced_by: google-workspace-client.json + gog keyring`. Files remain on disk pending operator deletion (per C-003).

### `docs/design/architecture/identity-model.md`

Add a "Google Workspace accounts" section with subsections:

- **Personal account (kentgale@gmail.com)**: active. gog client alias `default`. All 6 scopes granted. Stored in gog keyring.
- **Intentional business account**: stub. Will be added via separate setup procedure (see runbook). Will use a separate Google Cloud project, separate OAuth Client, and a non-default gog `--client` alias.

### `scripts/google/authorize-calendar.py` → `docs/archive/scripts/authorize-calendar.py`

Move via `git mv`. The file content stays the same. Add a one-line header comment noting deprecation date + replacement (`gog auth credentials` + `gog auth add`). Per FR-005, archive-move is preferred over banner-in-place.

### `docs/INDEX.md` and `data/doc-domain-map.json`

- INDEX.md: register the new runbook under the runbooks section; register the archive move.
- doc-domain-map.json: add `docs/runbooks/google-workspace-ops.md` to `area/ea` (Executive Assistant area, since calendar/email serve that capability area). Bump `last_updated` and `updated_by`.

### Validation

`python3 tooling/scripts/validate_docs.py` after all edits. Must report OK.

## Charter Re-check (post-design)

No new gates raised. Tier 4 Auto-Commit, no service/credential/topology runtime changes. **Gate**: PASS.

## Next Steps

Run `/spec-kitty.tasks` to materialize this plan into work packages.

**Branch contract**: `main` → `main` ✓.
