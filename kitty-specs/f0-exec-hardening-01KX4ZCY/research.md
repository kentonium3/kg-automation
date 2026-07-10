# Research — Foundation-0 Exec-Hardening Feasibility & Reconcile Ground Truth

**Method:** live office2 probe (OpenClaw 2026.6.11), session trajectory analysis, and reading
the version-matched bundled docs. All findings below are empirical, captured 2026-07-10.

---

## Decision 1 — Exec allowlist cannot hard-contain `gog` without breaking the workers

**Decision:** Do **not** deploy a per-agent exec allowlist for hard containment. Record the
finding; recommend **sandbox** as the correct hard-containment lever; defer to a follow-up.

**Rationale (the evidence):**

The intended Step 3 was `tools.exec.security: allowlist` on the non-owner workers with a host
approvals allowlist of exactly their helper commands (excluding `gog`), making `gog`
technically unreachable. Two independent facts make this infeasible with the allowlist alone.

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
(Docker backend, `network: none` by default). A sandbox lets a worker run arbitrary code
*inside the sandbox* while the `gog` binary and Google network egress are simply absent —
containment without enumerating every command. This is the boundary-doc §8 Step 5 lever,
promoted to the correct Step-3 tool by this finding.

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

**Drift to correct in `service-inventory.json`:**

1. **Model drift (confirmed):** habits and tasker are recorded as `anthropic/claude-sonnet-4-6`;
   live runs both on `anthropic/claude-haiku-4-5`. (escalation and main are correctly
   `sonnet-4-6`; capture and calendar correctly `haiku` — no change.)
2. **Skills fiction → real Step-2 sets:** the inventory's per-agent `skills` arrays predate
   the Step-2 deploy. Bring each into line with the live table above. In particular
   **`felix-admin-calendar.skills` must become `[]`** — the prior `["calendar","gog"]` was
   doubly fictional: `calendar` is not a real OpenClaw skill, and **#699 removed `gog` from
   calendar** when it migrated calendar onto the direct Google Calendar API helper.
3. **`gog` ownership is stale in the docs.** Post-#699, **`gog` is used by `main` only**
   (email `gog gmail` + `gog drive`); *no worker uses `gog`*. The #675 issue body and
   boundary-doc §6.1 that call `felix-admin-calendar` the "sole gog owner" are outdated —
   correct them. This also means hard-containing the workers is now pure defense-in-depth
   (no worker has a legitimate gog use), which further supports deferring it to sandbox.

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

- Empirically prove `agents.defaults.sandbox.mode: "non-main"` on the Docker backend contains
  `gog`/Google-network egress while each worker's real cron job still runs (the live
  apply-test this mission deliberately does not do).
- Decide `main`'s treatment (it legitimately needs `gog`; sandbox `non-main` leaves it out by
  design — consistent with main being the documented exception until #680).
- Fold in Step 4 (`skills.allowBundled`) if still wanted after sandbox.
