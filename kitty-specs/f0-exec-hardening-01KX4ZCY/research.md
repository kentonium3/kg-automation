# Research — Foundation-0 Exec-Hardening Feasibility & Reconcile Ground Truth

**Method:** live office2 probe (OpenClaw 2026.6.11), session trajectory analysis, and reading
the version-matched bundled docs. All findings below are empirical, captured 2026-07-10.

---

## Decision 1 — Exec approvals are guardrails, not isolation; an allowlist can't hard-contain this fleet without helper refactors or human approvals

**Decision:** Do **not** deploy a per-agent exec allowlist as the hard-containment control.
Record the finding; recommend **sandbox** as the correct hard-containment lever; defer to a
follow-up.

**Framing (important — the claim is not "no narrower config exists"):** OpenClaw *does* offer
narrower knobs — per-agent `safeBins`/`safeBinProfiles`, allowlist entries with `argPattern`,
and `strictInlineEval`. The correct claim is stronger and more honest: **exec approvals are
best-effort operator guardrails, not a strong isolation boundary**, and *no allowlist that is
simultaneously (a) tight enough to deny `gog`, (b) non-breaking for the workers' real
behavior, and (c) free of human-in-the-loop approvals exists for this fleet as it behaves
today.* OpenClaw's own security docs say exec approvals do not semantically model every
runtime/interpreter path and recommend sandbox/host isolation for a real boundary.

**Explicit disposition of the narrower knobs:**

- **`argPattern`-scoped `python3 -m scripts.<domain>.*`** — would permit the clean helper form
  only, but (i) relies on the `-m` interpreter binding that OpenClaw may deny as "not one
  concrete local file" (unproven), and (ii) does nothing about the workers' *other* real forms
  (redirection, heredoc, curl) which then break. Rejected as non-breaking control.
- **`strictInlineEval: true`** — makes inline eval (`python3 -c`, `python3 << EOF`) require an
  *explicit approval*, not impossible. In a no-human, cron-driven fleet an approval that never
  comes is a denial → breaks calendar's heredoc + capture's `-c`. Rejected as non-breaking.
- **`safeBins`/`safeBinProfiles`** — stdin-only text filters (`cut`, `wc`…); the docs
  explicitly forbid adding interpreters (`python3`, `bash`) here. Irrelevant to `gog`/helper
  containment. Rejected as inapplicable.
- **`ask=on-miss` (approval on allowlist miss)** — reintroduces human-in-the-loop for every
  non-listed command; incompatible with the autonomous cron fleet. Rejected.

**The two facts that force the conclusion:**

The intended Step 3 was `tools.exec.security: allowlist` on the non-owner workers with a host
approvals allowlist of exactly their helper commands (excluding `gog`), making `gog`
technically unreachable. Two independent facts make this unworkable as a *no-human,
no-breakage* control.

### 1a. The workers do not invoke a fixed, enumerable helper set

Per-agent `exec` invocations observed in
`~/.openclaw/agents/<agent>/sessions/*.trajectory.jsonl`:

| Agent | Clean `python3 -m` forms | Also uses (breaks a strict allowlist) |
|---|---|---|
| capture | `cd … && python3 -m scripts.inbox.prescan` | `python3 -c "…"` (inline eval); `cat >> …/inbox-processing-*.md << EOF` (redirection) |
| habits | `python3 -m scripts.habits.{morning_checkin_list,record_completion,parse_morning_reply}` | `cat > /tmp/weekly_report.py << EOF` then runs the scratch script |
| calendar | `python3 -m scripts…` (helper) | `python3 << EOF … EOF` (heredoc inline eval); `python …/log_action.py` |
| tasker | (little/none in sample) | `curl -s -X DELETE -H … <vikunja>` (direct API) |
| escalation | (little/none in sample) | `curl -s -H … <vikunja>` (many); `cat state/…`, `grep`, `date` |

### 1b. Allowlist mode denies exactly those forms

From bundled `~/.local/lib/node_modules/openclaw/docs/tools/exec-approvals-advanced.md`
(OpenClaw 2026.6.11):

- **Redirections are unsupported in allowlist mode** → capture's `cat >> log` append and
  habits' `cat > /tmp/x.py` break.
- **Command substitution `$()`/backticks are rejected** during allowlist parsing.
- **Interpreter inline eval** (`python3 -c`, `python3 << EOF`) is denied under
  `tools.exec.strictInlineEval: true` (the setting you must enable to close the escape hatch)
  → calendar's heredoc and capture's `-c` break.
- **Interpreter binding requires "exactly one concrete local file."** The `python3 -m
  <module>` form does **not** resolve to a direct file path; the doc states that when OpenClaw
  "cannot identify exactly one concrete local file … approval-backed execution is denied
  instead of claiming semantic coverage it does not have." So even the *legitimate* helper
  form is at risk of denial under allowlist mode — its viability is unproven.

**Conclusion:** An allowlist strict enough to deny `gog` also denies inline eval, heredocs,
redirection, and non-allowlisted script paths — i.e. much of what the workers actually do. A
looser allowlist that permits `python3` broadly reintroduces the `gog` escape hatch (an
allowlisted `python3 -c` can `subprocess.run(["gog", …])`). There is no clean middle with the
allowlist alone.

**Recommended alternative (for the follow-up):** `agents.defaults.sandbox.mode: "non-main"`
(Docker backend). A sandbox lets a worker run arbitrary code *inside the sandbox* while the
`gog` binary is simply absent — containment without enumerating every command. This is the
boundary-doc §8 Step 5 lever, promoted to the correct Step-3 tool by this finding.

**Sandbox is NOT free — the follow-up must prove three things separately (network:none ≠ no
network):** the workers legitimately use `curl` against the Vikunja API and run repo helpers
that need the checkout + venv mounted. A naïve `network: none` sandbox would break Vikunja
access. So the follow-up issue must demonstrate, independently:
1. **`gog` binary is absent/unreachable** inside the worker sandbox;
2. **Google egress is blocked** (the actual containment goal) — which is *not* the same as
   blocking all network;
3. **Required internal paths still work** — Vikunja API reachable, the kg-automation checkout
   + Python venv bind-mounted, state dirs writable — i.e. each worker's real cron job still
   runs. This needs an explicit network policy (egress allowlist to Vikunja/host, deny Google)
   plus bind-mount + workspace-access design, not just `mode: non-main`.

**Alternatives considered:**
- *Strict allowlist + refactor every worker to helper-only exec* — rejected: a large
  behavioral change to five agents (essentially the Bedrock "determinize the agents" thrust),
  far beyond this mission, and still brittle against the `-m` binding uncertainty.
- *Loose `python3` allowlist* — rejected: reintroduces the gog escape hatch; not containment.
- *Ship nothing, leave undocumented* — rejected: wastes the completed research; the next
  person re-probes office2 from scratch.

---

## Decision 2 — Reconcile target: the live config ground truth (2026-07-10)

**Decision:** Reconcile `service-inventory.json` (+ narrative) to this captured live state.

**Live `openclaw.json` per-agent state** (`agents.defaults.model.primary = haiku`, `skills` unset):

| Agent | Live model | Live `skills` | Live `tools.exec` |
|---|---|---|---|
| main | `anthropic/claude-sonnet-4-6` | *(unset → inherits)* | *(unset → security=full)* |
| felix-admin-capture | `anthropic/claude-haiku-4-5` | `["vikunja_api","github"]` | unset → full |
| felix-admin-habits | `anthropic/claude-haiku-4-5` | `["vikunja_api"]` | unset → full |
| felix-admin-tasker | `anthropic/claude-haiku-4-5` | `["task_intelligence","vikunja_api"]` | unset → full |
| felix-admin-escalation | `anthropic/claude-sonnet-4-6` | `["escalation","vikunja_api"]` | unset → full |
| felix-admin-calendar | `anthropic/claude-haiku-4-5` | `[]` | unset → full |

`openclaw exec-policy show` confirms every scope is `security=full, ask=off` (approvals file
missing) — no per-agent exec restriction exists.

**Drift to correct in `service-inventory.json` (deeper than model+skills — a full sweep):**

1. **Model drift (confirmed):** habits and tasker are recorded as `anthropic/claude-sonnet-4-6`;
   live runs both on `anthropic/claude-haiku-4-5`. (escalation and main are correctly
   `sonnet-4-6`; capture and calendar correctly `haiku` — no change.)
2. **Skills fiction → real Step-2 sets:** the inventory's per-agent `skills` arrays predate
   the Step-2 deploy. Bring each into line with the live table above. In particular
   **`felix-admin-calendar.skills` must become `[]`** — the prior `["calendar","gog"]` was
   doubly fictional: `calendar` is not a real OpenClaw skill, and **#699 removed `gog` from
   calendar** when it migrated calendar onto the direct Google Calendar API helper.
3. **Stale per-agent narrative fields #699 missed (Codex Major 3).** #699 reconciled the
   `felix-calendar-helper` service entry and *one* notes field (line ~2332 already says "As of
   #699 … the CALENDAR surface no longer flows through gog … inbox reaches the calendar inline
   via `route_calendar_event --create`") — that entry is the **model of correctness**. But the
   *per-agent* fields still describe the retired pre-#699 gog path and MUST be reconciled:
   - **capture `notes`** (~line 398): "calendar events … delegated to Felix main for `gog
     calendar create`" → now inline `route_calendar_event --create`, no main hop.
   - **`route/validate_calendar_event` component `purpose`** (~line 527): "delegate to Felix
     main for `gog calendar create`" → emits the create envelope consumed inline by the helper.
   - **calendar agent `purpose`** (~line 646): "event creation via `gog`/Google Calendar …
     executes `gog calendar create`" → judgment layer that invokes the Felix calendar helper
     (google-api-python-client); does **not** run gog.
   - **main agent `purpose`** (~line 684): "main now routes calendar work to felix-admin-
     calendar via openclaw-agent dispatch" → calendar is reached inline from capture; main is
     not in the calendar-create path. main's remaining gog use is **gmail + drive only**.
   Also reconcile any `depends_on`/`components[].purpose` that names calendar↔gog.
4. **`gog` ownership is stale across the docs.** Post-#699, **`gog` is used by `main` only**
   (email `gog gmail` + `gog drive`, plus contacts/sheets/docs); *no worker — including
   calendar — uses `gog`*. The #675 issue body and boundary-doc §§2/4/6/6.1/8 that call
   `felix-admin-calendar` the "sole gog owner" / "only gog holder" are outdated. This also
   means hard-containing the workers is now pure defense-in-depth (no worker has a legitimate
   gog use), which further supports deferring it to sandbox.
5. **Version drift (Codex Minor 2):** live gateway is **OpenClaw 2026.6.11 (e085fa1)** (pkg
   `~/.local/lib/node_modules/openclaw` version `2026.6.11`); the inventory's OpenClaw-gateway
   entry records `v2026.6.5`. Update it to `2026.6.11`.

**Rationale:** live config is the source of truth (CLAUDE.md: "when machine-readable and
narrative conflict, the machine-readable version wins" — and when the doc and live config
conflict, live config wins for "what is deployed").

---

## Decision 3 — No `openclaw.json` change → no Tier-2 deploy, no rebaseline

**Decision:** This mission touches repo docs + one GitHub issue only. `openclaw.json` is
byte-unchanged.

**Rationale:** the audited-surface rebaseline obligation (#557) and the Tier-2 snapshot
requirement are triggered by a change to `openclaw.json`. Since we make none, none apply
(NFR-004 asserts zero new audit drift). This is the key risk reduction from the operator's
"bank the doc wins" decision: the mission drops from Tier-2 (out-of-band config edit +
manual rebaseline) to effectively Tier-4 docs + a Tier-3 issue.

**Alternatives considered:** deploying skill-array *tidy-ups* to `openclaw.json` to match the
docs — rejected: the live config is already correct; it's the *docs* that are wrong. Changing
live config to match stale docs would be backwards and would trigger a needless rebaseline.

---

## Open items handed to the follow-up (sandbox) issue

- Empirically prove the three separate properties of Decision 1's sandbox recommendation:
  `gog` binary absent, Google egress blocked, and Vikunja/internal/helper paths still work
  (the live apply-test this mission deliberately does not do).
- Decide `main`'s treatment (it legitimately needs `gog` for gmail/drive; sandbox `non-main`
  leaves it out by design — consistent with main being the documented exception until #680).
- **Step 4 (`skills.allowBundled`) disposition (Codex Minor 1):** fold the allowBundled
  decision *into the sandbox follow-up issue explicitly* as a named sub-item, so it is not
  left as an untracked "separate follow-up." (It is a global default-deny for newly-bundled
  skill packs — naturally decided alongside the sandbox hardening.)

## Tracker disposition for #675 (Codex Major 6)

#675 asked for *technical* hard containment. This mission intentionally does not deliver it
(allowlist infeasible; sandbox deferred). To avoid "docs + issue" reading as hard-containment
*completion*, the recommended disposition is: **close #675 as rescoped** — "allowlist
hard-containment found infeasible; the finding + doc reconcile landed; the remaining hard
boundary is superseded by sandbox follow-up #\<N\>" — with the sandbox issue linked as the
continuation. (Operator confirms the close-vs-keep-open call at merge.)
