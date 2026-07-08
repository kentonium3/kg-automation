---
id: decision-felix-workspace-api-vs-gog
doc_type: decision
title: "RFC #681 — Felix-owned Google Workspace API access vs OpenClaw's gog connector"
status: draft
level: 1
owners: [kent]
last_validated: 2026-07-07
version: 0.1
---

# RFC #681 — Felix Workspace APIs vs gog

**Tracking issue:** kentonium3/kg-automation#681 (P1-rfc, area/felix-core).
Part of the Felix Bedrock Stabilization program (#673), Foundation 0 line (#675).

**This is a research-and-decide artifact.** It records findings and decisions
for the accept-or-dismiss question. It does **not** by itself commit to a build;
a build is a separate feature/infra issue if this RFC is accepted.

## The question

Should Felix connect **directly to Google Workspace APIs** (Calendar, Gmail,
Drive, Docs, Sheets) via Felix-owned helpers, **instead of routing through
OpenClaw's bundled `gog` connector skill?** Motivation: gog being an
OpenClaw *skill owned by an agent* is what forces the broken agent-to-agent
delegation in #679 (inbox capture → felix-admin-calendar → gog). If Workspace
access were a deterministic **Felix helper** the agent invokes with one command,
the delegation problem, the agent-ownership problem, and most of Foundation 0's
Google-surface containment dissolve into ordinary code governance.

---

## Decisions recorded

### D1 — Felix's Google identity = an **`@intentional.biz` (in-org) account**, Internal OAuth app  _(2026-07-07)_

Kent chose the **Internal-app path**: Felix authenticates as an account inside
the `intentional.biz` Workspace org, against an **Internal**-user-type OAuth app
owned by that org.

**Why:** Internal apps (a) issue **long-lived refresh tokens** (no 7-day expiry),
and (b) **skip Google verification entirely** — restricted and sensitive scopes
need no review. This is the cleanest architecture and delivers #572 "Option A"
as a byproduct.

**The hard constraint that drove the choice** (see F1 below): an Internal app
*structurally rejects any account outside the org* (`Error 403: org_internal`).
It therefore **cannot** authorize the consumer account `kentgale@gmail.com` that
gog drives today. The alternative (keep `kentgale@gmail.com` via an **External +
In-production** app) escapes the 7-day token too, but pays Google's brand +
scope verification tax (and restricted Gmail scopes risk an annual CASA audit).
Kent rejected that in favor of the clean in-org path.

**What this means for data location:**
- **Calendar (Calendar-first, per D2):** Felix's personal calendar stays on
  `kentgale@gmail.com`; the in-org Felix account reaches it via **cross-account
  calendar sharing** ("Make changes to events"). Long-lived token + no
  verification **and** it still drives the personal calendar. This cleanly
  fixes #679.
- **Gmail (later, F024):** Gmail **cannot** be bridged cross-account. When the
  Mail phase arrives, either Felix's mail surface lives in the Workspace mailbox,
  or that phase re-opens the personal-vs-Workspace identity question with more
  context. **Deliberately deferred** — it does not block Calendar-first.
  **Standing constraint (Kent, 2026-07-07):** Kent currently runs *a lot of
  business conversation out of `kentgale@gmail.com`*, so "which mailbox is
  Felix's / where does business email live" is a genuine personal quandary he
  must resolve independent of Felix — the F024 Gmail-identity decision is
  entangled with that and must not be forced early. Calendar-first is chosen
  precisely because it sidesteps this.

**Sub-note (identity granularity, not yet decided):** the spike can be validated
with the existing `kent@intentional.biz` account (zero new-seat cost). Whether
production uses `kent@intentional.biz` or a **dedicated `felix@intentional.biz`**
service identity (cleaner traceability, mirrors the office2 `claude`-vs-`kgale`
split, but consumes a Workspace seat) is a small open decision folded into Q5.

### D2 — Sequencing = **Calendar-first**  _(per #681 Q4, unchanged)_

Calendar-first proof → Mail (F024) → Drive/Docs/Sheets later (tie to
second-brain ingestion). Take on only what Felix uses, phased. Calendar is the
right first move because it (a) cleanly fixes #679 and (b) is the one surface
that bridges cross-account, so it validates the whole Internal-app path without
forcing the Gmail identity question.

---

## Q1 findings — auth (authoritative, sourced 2026-07-07)

**F1 — Internal app ⇒ org-members only (the crux).** An Internal OAuth app
rejects any account outside the org directory with `Error 403: org_internal`.
`kentgale@gmail.com` (consumer) can never consent to an intentional.biz Internal
app. Bridging the personal *calendar* works via calendar sharing; Gmail cannot
be bridged. → drove D1.
Source: [App Audience (support 15549945)](https://support.google.com/cloud/answer/15549945?hl=en),
[Error 403 org_internal](https://support.google.com/accounts/thread/47040097)

**F2 — The 7-day token is External + _Testing_ specifically.** Two escapes:
Internal (chosen), or External + "In production". Internal also skips
verification. gog's current pain is External+Testing (#572).
Source: [OAuth 2.0 refresh-token expiration](https://developers.google.com/identity/protocols/oauth2)

**F3 — Internal skips verification.** "For apps used only internally by your
Google Workspace organization … use of restricted or sensitive scopes doesn't
require further review by Google." No brand review, no CASA.
Source: [Configure the OAuth consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent)

**F4 — Scopes Felix needs** (gog set: calendar, gmail, drive, docs, sheets, contacts):

| Purpose | Scope | Class (moot under Internal) |
|---|---|---|
| Calendar read+write events | `https://www.googleapis.com/auth/calendar.events` | sensitive |
| Calendar full | `https://www.googleapis.com/auth/calendar` | sensitive |
| Gmail read | `https://www.googleapis.com/auth/gmail.readonly` | **restricted** |
| Gmail modify | `https://www.googleapis.com/auth/gmail.modify` | **restricted** |
| Gmail send | `https://www.googleapis.com/auth/gmail.send` | sensitive |
| Drive per-file | `https://www.googleapis.com/auth/drive.file` | non-sensitive |
| Drive read-all | `https://www.googleapis.com/auth/drive.readonly` | **restricted** |
| Docs | `https://www.googleapis.com/auth/documents` | sensitive |
| Sheets | `https://www.googleapis.com/auth/spreadsheets` | sensitive |

Restricted/sensitive classes only matter if we ever fall back to External; under
Internal they're free. (If an External fallback ever happens, prefer `gmail.send`
+ `drive.file` to stay out of restricted-scope/CASA territory.)
Source: [OAuth 2.0 Scopes](https://developers.google.com/identity/protocols/oauth2/scopes)

**F5 — Client type = Desktop (installed) app** with a loopback redirect
(`http://127.0.0.1:PORT`). Run consent once interactively on the Mac
(`InstalledAppFlow.run_local_server`), capture the refresh token, transport to
office2. Web-app client also works but adds redirect ceremony.
Source: [OAuth for native apps](https://developers.google.com/identity/protocols/oauth2/native-app)

**F6 — Token longevity is structural, not observable.** A refresh token carries
no exposed expiry. The guarantee is *configuration* (Internal user type). Verify
by (a) confirming the console shows User type = Internal + org-owned project, and
(b) exercising a refresh grant daily past day 7 (it won't flip to `invalid_grant`
the way an External+Testing token does). No way to force-age faster than
wall-clock.

**Reliability flags (apply even to Internal):** refresh tokens with **Gmail
scopes die on account password change**; `invalid_grant` is overloaded (7-day
expiry / revoke / Gmail-password-change all look identical → log full error
bodies); ~100 live refresh tokens per client/account max; unused-for-6-months
expiry.

## Q2 findings — cost/quota

**~$0 within quota, confirmed.** Calendar: 1M req/day/project, 600/min/user.
Gmail: unit-based, ~80M units/day, 6000 units/min/user (send=100 units).
A few-hundred-calls/day system is ~4 orders of magnitude under daily ceilings;
only realistic exposure is per-user-per-minute bursts → mitigate with backoff.
**Watch:** Google signaled possible over-quota billing "later in 2026" and a new
quota regime for projects created ≥2026-05-01 — pin the live quota page.
Sources: [Calendar quota](https://developers.google.com/workspace/calendar/api/guides/quota),
[Gmail quota](https://developers.google.com/workspace/gmail/api/reference/quota)

## Q3 findings — build vs buy  _(decided post-spike, 2026-07-08)_

**Decision: BUILD a thin Felix-owned Calendar helper** on Google's official
`google-api-python-client`, rather than adopting a third-party or self-hosted
Workspace MCP server — at least for the Calendar-first phase.

Rationale:
- **The spike already proved the whole path** (auth → create/update/read) in
  ~150 lines of official-client code. The build cost is low, the surface is
  narrow, and it's our code — testable and deterministic (matches
  `engineering-principles.md`: deterministic mechanics belong in a helper the
  agent invokes; judgment stays in the LLM).
- **A self-hosted Workspace MCP server is the same trust category as gog** — a
  broad connector exposing many tools to the model. Adopting one now would
  reintroduce exactly the "broad surface visible to the model" problem F0 (#675)
  is closing, trading a narrow owned surface for a wide one.
- **Maintenance is bounded** to the endpoints we actually use (events
  create/update/list/delete + read). No third-party release cadence to track.
- **Revisit "buy" only if** we later need many Workspace surfaces
  (Drive/Docs/Sheets/Gmail) and the per-app build cost compounds — then a
  self-hosted MCP per-app could amortize. Calendar alone doesn't justify it.

Shape: a deterministic helper under `scripts/` exposing the calendar mechanics;
the calendar agent keeps only the judgment layer (NL date parsing, disambiguation,
follow-ups). Credentials follow the `~/.config/felix/` pattern (production home
under the office2 `claude` user).

## Q4 — scope + sequencing

Decided (D2): Calendar-first → Mail (F024) → Drive/Docs/Sheets later.

## Q5 — fate of felix-admin-calendar + identity  _(recommendation post-spike, 2026-07-08)_

Two sub-questions: **(a) agent fate** and **(b) Felix's production Google identity**.

**(a) felix-admin-calendar shrinks to a judgment-only layer.** It keeps the NL
comprehension (parse "next Tuesday 3pm", disambiguate, ask follow-ups) and
delegates all mechanics to the deterministic Calendar helper (Q3). It **stops
calling gog.** This directly resolves the #679/#680 wall: capture invokes the
helper (directly, or via the calendar agent's judgment layer) instead of doing
cross-agent `gog` delegation — which is precisely the haiku-can't-delegate
failure that broke #679. gog stays **only** for not-yet-migrated Google surfaces
(mail/drive) during transition, then retires as those migrate (F024+).

**(b) Provision a dedicated `felix@intentional.biz` for production.** The spike
authorized as `kent@intentional.biz`; production should use a dedicated in-org
account so Felix's API actions are attributable and separable from Kent's, and so
rotating/revoking Felix's access never touches Kent's account. Cost: one Workspace
seat (small). The Stage-B bridge means `felix@` can still manage Kent's **personal**
calendar via cross-account sharing — no need to authorize as the consumer account.
Decision deferred to build-time but recommended.

Open at build-time: the helper's token home on office2 (mirror `~/.config/felix/`
under the `claude` user) and the helper↔gog coexistence window (both can run;
the helper is the migrated path).

---

## Q1 execution runbook (Kent runs the console steps)

**Precondition — confirm the org owns a GCP org.** Sign into
[console.cloud.google.com](https://console.cloud.google.com) as an
`intentional.biz` account. In the project/resource picker, confirm an
**Organization** named `intentional.biz` exists (not "No organization"). If it
does, the **Internal** user-type option will be available. (A Workspace auto-gets
a Cloud Organization on first GCP access by an org admin.)

1. **(Stage B only) Share the personal calendar.** As `kentgale@gmail.com` in
   [calendar.google.com](https://calendar.google.com) → Settings → *your
   calendar* → "Share with specific people or groups" → add the account you'll
   authorize as (`kent@intentional.biz` for the spike, or `felix@intentional.biz`)
   → permission **"Make changes to events"**. (Skip for the Stage-A auth-only
   proof.)
2. **Create the GCP project under the org.** New project; set **Organization =
   intentional.biz** (not "No organization"). Name e.g. `felix-workspace`.
3. **Configure OAuth consent** (APIs & Services → *OAuth consent screen* / now
   "Google Auth Platform"): **User type = Internal**; app name `Felix`; support
   email = your address. Save.
4. **Enable the Calendar API** (APIs & Services → Library → "Google Calendar
   API" → Enable). (Add Gmail/Drive/Docs/Sheets later, per phase.)
5. **Create the OAuth client** (APIs & Services → Credentials → Create
   credentials → OAuth client ID → **Application type = Desktop app**). Download
   the JSON → save it as `client_secret.json` (path you'll pass to the script).
6. **Run the spike** (next section). Do it on the **Mac** (needs a browser for
   the one-time consent). Authorize as the in-org account from step 1.

**Identity for the spike:** use your existing **`kent@intentional.biz`** (no new
Workspace seat). Provisioning a dedicated `felix@intentional.biz` is a
production-time choice (Q5).

## Q1 spike script

`scripts/google/workspace_auth_spike.py` (see below in the repo). Proves the full
chain: Internal-app OAuth → refresh token → live Calendar API call.

**Secrets handling (learned 2026-07-08):** put `client_secret.json` in a
user-only dir OUTSIDE the repo — `~/.config/felix/` (`chmod 700`), which the
script defaults to (override with `FELIX_GOOGLE_DIR`). Do **not** leave it in
`~/Downloads` (macOS TCC blocks the terminal from reading Downloads → the OAuth
open fails `PermissionError`; move it out with Finder or grant the terminal Full
Disk Access) or in `/tmp` (world-readable + wiped on reboot). The minted
`token.json` (a real refresh token) is written to the same dir at `0600`; it must
never be committed (repo `.gitignore` also excludes `token.json` as belt-and-suspenders).

```bash
# one-time, on the Mac
mkdir -p ~/.config/felix && chmod 700 ~/.config/felix
mv ~/Downloads/client_secret_*.json ~/.config/felix/client_secret.json  # via Finder if TCC blocks
python3 -m venv ~/.venvs/felix-gspike && source ~/.venvs/felix-gspike/bin/activate  # durable, not /tmp
PIP_USER=0 pip install google-api-python-client google-auth-oauthlib      # PIP_USER=0 if user-site is forced

# Stage A — auth + API proof on the authorizing account's own calendar
python scripts/google/workspace_auth_spike.py --stage a

# Stage B — cross-account bridge: create on the shared personal calendar
python scripts/google/workspace_auth_spike.py --stage b --target-calendar kentgale@gmail.com

# F6 longevity — re-run daily past day 7; success = token still refreshes
python scripts/google/workspace_auth_spike.py --refresh-only
```

Success criteria:
- **SC-A** Stage A creates + reads back an event on the authorizing account's
  primary calendar; a refresh token is saved to `token.json`.
- **SC-B** Stage B creates an event on `kentgale@gmail.com`'s shared calendar
  from the in-org token (proves the personal-calendar bridge → fixes #679's
  need for gog on that surface).
- **SC-F6** `--refresh-only` still succeeds on day 8+ (no `invalid_grant`) →
  confirms long-lived Internal-app token.

---

## Spike results — Q1 auth PROVEN _(2026-07-08)_

Both stages passed on the first run against a fresh Internal OAuth app on the
`intentional.biz` org, authorized as `kent@intentional.biz`:

- **SC-A ✓** — Internal app minted a **long-lived refresh token**
  (`refresh_token present=True`) and created + read back an event on
  `kent@intentional.biz`'s primary calendar. Confirms D1's core claim (Internal
  app ≠ the 7-day Testing-app behavior of #572) and the #572 Option A auth model.
- **SC-B ✓** — the in-org token created + read back an event on the **personal
  `kentgale@gmail.com`** calendar via cross-account sharing ("Make changes to
  events"). Confirms the personal-calendar bridge → removes gog from that path.
- **SC-F6 (in progress)** — daily `--refresh-only`; verdict ~**2026-07-16**. No
  `invalid_grant` = the Internal-app token is durable.

**RFC status: cleared to ACCEPT pending the F6 durability confirmation.** The
make-or-break uncertainty (auth) is resolved empirically; Q2 (cost ~$0), Q3
(build), Q4 (calendar-first), Q5 (judgment-layer agent + dedicated identity) are
all decided or recommended above.

## Open items / next

- [x] Kent runs the console runbook (project + Internal consent + Calendar API +
      Desktop OAuth client). _(2026-07-08)_
- [x] Run spike Stage A → SC-A; Stage B → SC-B. _(both green 2026-07-08)_
- [ ] F6 daily longevity check → verdict ~2026-07-16.
- [ ] On F6 green: mark RFC **accepted** and convert to a **feature issue** for
      the Calendar-helper build (deterministic helper on `google-api-python-client`
      per Q3; judgment-only calendar agent + `felix@intentional.biz` per Q5).
