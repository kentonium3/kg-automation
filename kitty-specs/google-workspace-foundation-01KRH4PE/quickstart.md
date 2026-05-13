# Quickstart: Google Workspace foundation

**Mission**: `google-workspace-foundation-01KRH4PE`

End-to-end verification recipe for the implementer and the post-merge operator.

---

## 1. Local verification (Mac)

```bash
cd /Users/kentgale/repos/kg-automation
python3 tooling/scripts/validate_docs.py
```

**Expect**: `validate_docs: OK`. This is the only automated check — there's no test suite for docs content; the load-bearing review is human reading + the codex reviewer pass.

## 2. Self-review of the runbook

The runbook is the load-bearing deliverable. Spot-check it does the following without requiring memory of the 2026-05-13 setup chain:

- A future operator on a fresh machine can follow the setup procedure linearly to a working `gog auth list` showing their account + 6 scopes.
- The three known pitfalls are each documented with: symptom (exactly what error message the operator sees), root cause (one sentence), fix (one command or one console action).
- The "Adding a second Google account (Intentional)" section is enough to set up the business account when Kent gets there, without re-deriving the personal-account flow.

## 3. Architecture-state spot-check

After the mission's edits land:

- `docs/design/architecture/service-inventory.md` — `google-workspace` entry visible, matches the JSON.
- `docs/design/architecture/data/service-inventory.json` — `google-workspace` service entry with all fields populated; top-level `last_updated` bumped.
- `docs/design/architecture/credentials-and-secrets.md` — entries for `google-workspace-client.json`, `gog-keyring-password`, gog-managed refresh token; legacy `google-calendar-*` entries marked deprecated.
- `docs/design/architecture/data/credential-manifest.json` — matches; `deprecated_at` field present on the legacy entries.
- `docs/design/architecture/identity-model.md` — personal-account section + Intentional stub.
- `docs/archive/scripts/authorize-calendar.py` — exists; `scripts/google/authorize-calendar.py` is gone (or banner-in-place per FR-005 — confirm which).
- `docs/INDEX.md` — new runbook registered; archive move reflected.
- `docs/design/architecture/data/doc-domain-map.json` — runbook under `area/ea`; `last_updated` bumped; `updated_by` extended.

## 4. Post-merge operator verification (SC-002, SC-003)

These are regression guards. Already verified live 2026-05-13; this just confirms the setup hasn't regressed after merge.

On office2 as claude (fresh shell to pick up bashrc changes):

```bash
openclaw skills info gog
```

**Expect**: `🎮 gog ✓ Ready`.

```bash
gog auth list
```

**Expect**: `kentgale@gmail.com default calendar,contacts,docs,drive,gmail,sheets <ISO timestamp> oauth`.

```bash
gog calendar colors
```

**Expect**: Event Colors table (11 rows) + Calendar Colors table (24 rows).

```bash
gog gmail search 'newer_than:1d' --max 1
```

**Expect**: zero or one Gmail thread row.

```bash
gog drive search "x" --max 1
```

**Expect**: zero or one Drive file row.

```bash
gog contacts list --max 1
```

**Expect**: zero or one contact row.

If any fail, the failure is either (a) an API enablement reverted, (b) the refresh token expired, or (c) a config drift — the runbook's troubleshooting section covers each.

## 5. Rollback (if needed)

```bash
git revert <merge-commit-hash>
```

Documentation-only mission; revert restores the prior docs/structure. No deploy implication. The legacy `authorize-calendar.py` returns to `scripts/google/` if it was moved.
