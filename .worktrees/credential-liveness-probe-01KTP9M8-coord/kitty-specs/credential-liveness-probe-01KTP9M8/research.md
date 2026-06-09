# Research — Credential Liveness Probe

**Mission**: `credential-liveness-probe-01KTP9M8`
**Phase**: 0 — Outline & Research

This document captures design decisions where multiple viable approaches exist, the chosen approach, and the rejected alternatives. Decisions are anchored in the spec's FRs; rationale references CLAUDE.md, the Felix Constitution, and the operator's stated Option C from `reference_gog_credential_health_gap.md`.

---

## Decision 1: Probe call shape (cheap read against gog)

**Decision**: `gog --account <email> calendar list -j --max-results 1` with a 15s subprocess timeout.

**Rationale**:
- A successful return (exit 0) confirms the OAuth refresh token can mint a fresh access token AND the access token can reach the Google API. End-to-end liveness in one call.
- Returns minimal data (one calendar entry, JSON envelope only), well under any quota concern.
- `gog calendar list` is the same surface I used during this session's investigation to verify gog auth; pattern is proven.
- `-j` produces JSON for stable parsing; we don't actually parse the JSON, but the structured-output flag is the documented "for scripting" path per `gog --help`.
- 15s timeout is generous for a typical Google Calendar API call (real-world p95 ~1s on office2) but tolerates one slow round-trip without false-positive `probe-error`.

**Alternatives considered**:
- `gog gmail labels list -j --max-results 1` — same end-to-end coverage; rejected because Calendar is the primary surface for Felix's inbox-routing calendar flow (the failure mode that surfaced #572).
- `gog auth doctor` — gog's built-in self-check; rejected because it tests credential decryption only, not whether the refresh token actually works against Google's servers. Self-check would have passed at 2026-06-08 when the real token was dead.
- `gog drive about -j` — about endpoint is cheap; rejected because the inbox-calendar flow doesn't touch Drive and we want the probe to exercise the call path that fails first in practice.
- Direct HTTP call to `https://oauth2.googleapis.com/tokeninfo` with the access token — rejected: adds a separate auth path, bypasses `gog`'s keyring handling, and would require re-implementing OAuth refresh logic. Defeats the purpose of using gog as the integration boundary.

---

## Decision 2: Cycle vs unexpected classification window (±24h)

**Decision**: A probe failure is classified `dead-routine-7day` when `mtime(keyring-file) + 7d` is within ±24h of probe-time NOW. Otherwise `dead-unexpected`.

**Rationale**:
- Google's documented Testing-app refresh-token TTL is exactly 7 days from issue. The keyring file mtime is set when `gog auth add` writes the new token — a reliable proxy for "when this token was minted."
- ±24h covers natural variance: NTP drift, probe-cadence offset from mint timing (probe runs every 6h; mint timing is operator-chosen), and Google's grace before they actually revoke the token at the edge (their server time vs ours).
- A token that died ≥24h before its scheduled 7-day expiration is genuinely unexpected — could be password change, manual revoke, Google security review. Different operator response (investigate at myaccount.google.com/permissions before re-auth).
- A token that died ≥24h AFTER its scheduled 7-day expiration is also unexpected — would mean Google extended TTL beyond 7d, which contradicts their docs. Worth flagging.

**Alternatives considered**:
- ±48h window — wider tolerance; rejected because it would absorb genuinely-unexpected revocations into the routine bucket and lose the signal Kent specifically wanted (per #572 comment update: "should distinguish routine 7-day re-auth due from unexpected revocation").
- ±12h window — tighter; rejected because the natural variance (probe cadence + operator mint-time offset) can already be ≥12h. False classification would result.
- No classification, treat all failures the same — rejected per FR-009 (operator wants the distinction).

---

## Decision 3: Probe cadence (6h)

**Decision**: `OnCalendar=*-*-* 00,06,12,18:00:00` (every 6 hours) on a new dedicated systemd timer.

**Rationale**:
- The token's 7-day TTL means the maximum lag from expiration to detection is bounded by the cadence interval. 6h cadence gives ≤6h detection lag — well within the operator's "see it the day it dies" target.
- Quota cost: 4 calls/day × 1 credential = 4 calendar reads/day. Google Calendar API quota is 1,000,000 reads/day per project — six orders of magnitude under the limit. Future expansion to N credentials × 4 calls = 4N/day stays in budget for any reasonable N.
- Per the #572 update comment: "Liveness probe cadence target: every 6 hours minimum (faster surfacing of the weekly cycle's failure window without thrashing rate limits)."
- `Persistent=true` ensures missed firings catch up after a reboot or maintenance window.

**Alternatives considered**:
- 1h cadence — 24× the call volume; rejected as overkill (operator can act within hours not minutes, and the 7-day window means 6h is plenty).
- 12h cadence — half the call volume; rejected because 12h detection lag means an expiration at 06:00 wouldn't surface until 18:00; user-facing failure could surface first (defeats the purpose).
- 24h cadence (match existing `credential-health-check.timer`) — rejected: the existing daily cadence is what *missed* this for 7 days. The whole point is faster detection.
- Variable cadence (more frequent near expected expiration, less frequent otherwise) — rejected: complexity not justified for 4 vs ~24 calls/day savings.

---

## Decision 4: Output surface — GitHub issue vs direct WhatsApp

**Decision**: Reuse the existing `github_writer.dedup_check` / `file_alert` path; do NOT emit WhatsApp directly from the probe.

**Rationale**:
- `credential_health_check` already files GitHub issues for cadence + staleness alerts. The pattern is proven; the dedup logic is reusable; the issue surface is searchable + auditable.
- WhatsApp is a downstream concern: the existing felix-admin-escalation agent (or a future digest channel) reads GitHub issues and decides whether to surface them via WhatsApp. Keeping that separation means: (a) the probe doesn't need to know about WhatsApp connection state; (b) one channel (GH issues) covers operators who consume via UI, digest, and WhatsApp.
- The issue body carries the concrete recovery command (`ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh`), so even the GH-UI-only surface is actionable.
- Reduces blast radius if WhatsApp itself is the failing channel (per `whatsapp_session_signal`); GH-issue path is independent.

**Alternatives considered**:
- Emit direct WhatsApp from probe — rejected: couples the probe to channel state; duplicates `whatsapp_session_signal` logic; adds a new failure mode (probe spams pings if dedup fails).
- File GH issue AND emit WhatsApp from the probe — rejected: redundancy + double-failure modes; downstream digest already handles GH→WhatsApp escalation per the felix-admin-escalation agent's documented role.
- Vikunja task surface — rejected: `credential_health_check.vikunja_writer` exists but the cadence-alert path writes Vikunja tasks only (not staleness). Staleness uses GH issues. Liveness is closer to staleness (per-tick observation), so GH issues match the precedent.

---

## Decision 5: Separate timer vs extending the existing daily

**Decision**: New dedicated `credential-liveness-probe.timer` at 6h cadence. The existing `credential-health-check.timer` (daily at 13:00 UTC) is UNCHANGED.

**Rationale**:
- Per FR-017: "The existing `credential-health-check.timer` cadence (daily at 13:00 UTC) and existing signals are UNCHANGED."
- Different cadence requirements: liveness wants 6h; existing cadence/staleness checks are appropriately daily (file mtime, expiry math don't move that fast).
- Separation of concerns: a bug in the new liveness path can't affect the existing daily signals.
- Testing + rollback: the new timer can be enabled/disabled independently; rolling back doesn't touch the existing unit's state.
- Marginal cost: two systemd units vs one, with the existing deploy pattern already proven.

**Alternatives considered**:
- Increase existing `credential-health-check.timer` to 6h cadence and put liveness inside the same cycle — rejected: forces other signals (cadence math, file presence) to run 4× more often for no benefit. Tightly couples concerns.
- Run liveness as a parallel goroutine/thread inside the existing cycle — rejected: Python helper is `Type=oneshot`; concurrency complexity not warranted.
- Embed liveness as an additional CLI flag on `credential-health-check.timer` and let one timer drive both — rejected: same overhead problem as option 1.

---

## Decision 6: Manifest schema — opt-in `liveness_probe` block per credential

**Decision**: Add a new optional per-credential block:
```json
"liveness_probe": {
  "enabled": true,
  "gog_account": "kentgale@gmail.com",
  "keyring_file": "/home/claude/.config/gogcli/keyring/_gogcli_key_v1_dG9rZW46ZGVmYXVsdDprZW50Z2FsZUBnbWFpbC5jb20",
  "recovery_command": "ssh -t office2-claude /home/claude/kg-automation/scripts/security/gog-reauth.sh"
}
```

Credentials without the block are skipped from liveness (logged INFO once per cycle).

**Rationale**:
- Per FR-013: backward-compat is mandatory (NFR-006). Opt-in via presence of the block satisfies that.
- Per-credential `gog_account` and `keyring_file` parameterize the probe so future Workspace-internal migration (Option A path) plugs in by adding a record + block, not by code change.
- `recovery_command` lives in the manifest so the issue-body author doesn't hardcode it (per C-007: the recovery command "MUST exactly match the deployed `gog-reauth.sh` invocation path"). If the script's invocation path changes, the manifest update is the migration boundary.
- `enabled: true` (vs implicit "presence of block means enabled") gives a clean disable switch without removing the configuration.

**Alternatives considered**:
- New top-level `liveness_probes: []` array, separate from credentials — rejected: harder to keep in sync; one credential could have multiple liveness configs and that confuses the dedup-by-credential-name pattern.
- Per-credential `type: oauth2-with-liveness` (vs current `type: oauth2`) — rejected: forces a type-level distinction for a per-instance config choice. Less flexible.
- No manifest change; hardcode the gog probe inside `liveness.py` — rejected: scales to N=1 only; defeats the Option A migration story.

---

## Decision 7: Test strategy — mock subprocess + filesystem; no real gog calls in pytest

**Decision**: All `liveness.py` tests use `monkeypatch.setattr(subprocess, "run", fake_run)` and `monkeypatch.setattr(Path, "stat", fake_stat)` to control probe outcomes deterministically. The existing pytest pattern in `tests/security/credential_health_check/` is reused. NO real `gog` calls during pytest.

**Rationale**:
- Pytest must run hermetically on Mac and CI; real `gog` requires office2 credentials.
- Subprocess mocking lets us exercise every branch of the probe (alive, invalid_grant, timeout, gog-binary-missing, network-error) without depending on Google's API state.
- Filesystem mtime mocking lets us pin "now - 6.9 days" vs "now - 3 days" exactly at the ±24h boundary; integration with real files would be flaky.
- Matches existing patterns in `test_signals.py` (which mocks `tailscale status` JSON output rather than calling tailscale).

**Alternatives considered**:
- Integration tests calling real `gog` on office2 — rejected per `[[feedback_live_integration_tests]]`: "don't propose --live-probe integration modes as mitigation for mock-only contract gaps; document quirks instead." End-to-end probe verification happens at deploy-smoke-test time (FR-009 in spec.md's Success Criteria), not in pytest.
- `pytest-subprocess` library — rejected: new third-party dep; existing `monkeypatch` is sufficient.

---

## Decision 8: Phone-recovery testing — defer UX tweaks until testing reveals need

**Decision**: Do NOT proactively modify `scripts/security/gog-reauth.sh` for phone UX. Test as-is via Termius + Tailscale on Kent's phone (FR-021, SC-11). If friction is observed, fold targeted tweaks into the same mission's diff.

**Rationale**:
- The script is bash + standard `read -r`; Termius is a normal terminal emulator. The mechanical capability should work without changes.
- Premature UX optimization for a single test could regress the Mac-side flow we just validated.
- Speculative tweaks (e.g., compact URL output, larger paste prompts) might address non-issues while missing real friction (e.g., URL line-wrapping on small screens, hidden characters in pasted URLs).
- Per Felix Constitution Directive 10 (preference for guardrails over speculative defenses): the test is the guardrail; tweaks come from observed friction, not imagination.

**Alternatives considered**:
- Pre-emptively compact the URL output / add a "look for this" marker so the URL is easier to find in scrollback — rejected as speculative; if testing reveals this is real friction, tweak then.
- Add a `--phone-mode` flag with denser UI — rejected: branches the script unnecessarily; if friction is real, fix it in the default flow rather than gating on a flag.
- Write a dedicated phone-companion script — rejected as a workaround for friction not yet observed; do the test first.

---

## Decision 9: Recovery command attribution

**Decision**: The recovery command in the GH issue body is the exact `gog-reauth.sh` invocation. No additional context paragraph; rely on the script's own output for the rest.

**Rationale**:
- One-liner is copy-pasteable. The issue body should NOT explain the OAuth flow; the runbook does that.
- `gog-reauth.sh` already prints prerequisites, browser-side steps, and verification — duplicating that in the issue body creates drift.
- Issue body stays compact; downstream WhatsApp digest doesn't have to scroll a long message.
- Per the issue dedup model: title prefix + minimal body keeps the dedup signal clean.

**Alternatives considered**:
- Embed the full §2.8 procedure in the issue body — rejected: 50+ lines of doc duplicated per failure; drift risk.
- Link to the runbook URL only — rejected: doesn't survive offline browsing or low-bandwidth WhatsApp pings.

---

## Cross-decision: nothing about the existing capture/inbox flow changes

This mission deliberately touches zero agent-prompt surfaces. Per C-003 (Directive 6): probes are 100% deterministic helpers. The `felix-admin-capture` AGENTS.md, the inbox-processing flow, and the openclaw agent runtime are untouched. The only Felix-system observation Kent gets back is a GitHub issue when the probe fails — same pattern as the existing cadence/staleness signals.

---

## Open questions remaining

None. All FRs in spec.md have a clear implementation path. Phase 1 will produce data-model.md / contracts/ / quickstart.md to make the chosen approach concrete.
