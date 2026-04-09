---
id: risk-register
title: Risk Register
doc_type: reference
level: reference
status: approved
owners:
  - "@kentonium3"
last_validated: 2026-04-06
last_updated: '2026-04-06'
revision: v0.2
audience: agents_and_humans
---
| ID | Risk | Likelihood | Impact | Owner | Mitigation | Status |
|----|------|------------|--------|-------|------------|--------|
| R-001 | **Supply chain compromise via OpenClaw or installed skills exfiltrates plaintext credentials** — precedent: prior OpenClaw incident allowed mass credential exfiltration from `/data/services/openclaw/secrets/`. All credentials currently stored as plaintext mode-600 files. | Medium | Critical | @kentonium3 | Short-term: Tailscale-only network posture, fail2ban, UFW, SSH hardening, and ClawHub install approval (Felix Constitution) reduce attack surface. Long-term: encrypt secrets at rest (e.g. `age`) as part of next Core Hub security cycle. Tracked under D06. | Open |
| R-002 | **Google OAuth refresh token revocation without warning** — Google revokes refresh tokens on password change, prolonged inactivity (6+ months), or security review. Affects F020+ calendar features. | Low | Medium | @kentonium3 | Re-authorization script at `scripts/google/authorize-calendar.py` is idempotent — re-run to restore access. Documented in `docs/runbooks/google-calendar-ops.md` (F020 deliverable). | Open |
| R-004 | **Dual-user ownership model causes silent operational failures** — office2 has two active users (`claude` for agents, `kgale` for human/system services). File ownership mismatches cause: Obsidian Sync crash-loops (wrong path in systemd unit, service runs as kgale but files modified by claude), cross-user permission denials, and debugging difficulty. The `secondbrain` shared group partially mitigates vault file access but does not cover all shared surfaces (`/data/services/`, systemd units, config files). | High | High | @kentonium3 | Short-term (done 2026-04-06): `secondbrain` group already exists with both users as members; vault directory setgid ensures new files inherit group. Obsidian Sync crash-loop root cause identified (wrong WorkingDirectory in systemd unit). Long-term: implement dedicated service account (`felix-ops`) that owns all shared operational state, with both users in the group for access. | Open |
| R-003 | **API key and token expiration untracked** — no inventory of expiry dates exists for any credential (Vikunja API token, Anthropic API key, Google OAuth, WhatsApp session, Restic password). Silent expiration causes agent failures with no advance warning. No calendar or scheduled review process exists. | High | High | @kentonium3 | Short-term (done 2026-04-06): expiry policies audited and documented in `credential-manifest.json` v1.1 — each credential now has `expiry_policy`, `review_cadence`, `expiry_notes`, and `last_reviewed` fields. No credential has a near-term expiry concern. Long-term: build an agent-readable expiry check into the security monitor or a dedicated credential health check. | Mitigated (short-term) |
