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
| R-003 | **API key and token expiration untracked** — no inventory of expiry dates exists for any credential (Vikunja API token, Anthropic API key, Google OAuth, WhatsApp session, Restic password). Silent expiration causes agent failures with no advance warning. No calendar or scheduled review process exists. | High | High | @kentonium3 | Short-term (done 2026-04-06): expiry policies audited and documented in `credential-manifest.json` v1.1 — each credential now has `expiry_policy`, `review_cadence`, `expiry_notes`, and `last_reviewed` fields. No credential has a near-term expiry concern. Long-term: build an agent-readable expiry check into the security monitor or a dedicated credential health check. | Mitigated (short-term) |
