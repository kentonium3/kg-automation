---
name: doc-audit
description: >-
  How felix-doc-auditor reads and acts on Doc Audit and Weekly Doc Audit
  GitHub issues. Encodes the audit workflow, the high-confidence vs
  judgment threshold, the docs-debt issue template, the audit commit
  format, and per-failure-mode error handling. Use when processing any
  issue titled "Doc audit:" or "Weekly doc audit —".
  Does NOT handle: agent identity (IDENTITY.md), agent standing orders
  (AGENTS.md), runtime orchestration (OpenClaw cron), the GitHub-CLI
  invocation surface (TOOLS.md), or the GitHub Actions workflows that
  create the audit issues in the first place. Approval at Level 1 is
  via GitHub issue labels (v1.2.0+); the previous WhatsApp flow was
  replaced — see #207. As of v1.5.0 (#245), frontmatter-only edits
  (Tier A per §4.1.a) auto-commit without the Level-1 approval gate;
  content-touching edits (Tier B per §4.1.b) continue to require
  approval.
version: 1.5.0
---

# Doc-Audit Skill

This skill encodes the complete audit logic the `felix-doc-auditor` agent uses
to process documentation audit issues. It is **self-contained** — an agent
reading this skill plus `docs/design/architecture/data/doc-domain-map.json`
can run a full audit without consulting any other reference.

## 1. What This Skill Is

A documentation audit playbook for the `felix-doc-auditor` OpenClaw agent.
Given an audit issue number, it tells the agent how to:

- Determine in-scope docs from the issue's `area/*` labels and the domain map
- Compare each doc against the canonical system-state JSON sources
- Classify findings as high-confidence edits (commit directly) or judgment
  gaps (file as `docs-debt` issues)
- Detect missing artifacts (deployed agents/services/skills without docs)
- Format the commit, the debt issues, and the audit summary comment
- Recover from per-doc, per-API, and per-message failure modes

This skill does NOT cover identity, standing orders, runtime orchestration,
or message transport. Those live in `IDENTITY.md`, `AGENTS.md`, and
`TOOLS.md` of the consuming agent's workspace.

## 2. Inputs

Every invocation of this skill receives:

| Input | Source | Notes |
|---|---|---|
| Audit issue number | OpenClaw cron tick | E.g., `186`. The issue selected per `AGENTS.md` § "Trigger and queue management". |
| Domain map path | hardcoded | `docs/design/architecture/data/doc-domain-map.json` — the scope contract per spec C-005 |
| System-state sources | enumerated below | Read once at start of audit; cached for the audit's duration only |
| Repo working directory | OpenClaw env | The local clone the agent edits (`/home/claude/kg-automation/` on office2) |
| Current autonomy level | `agent-registry.json` | Determines whether Level 1 GitHub-issue approval gate applies |

**System-state sources** (all read-only from this skill's perspective):

- `docs/design/architecture/data/service-inventory.json` — services + versions
- `docs/constitution/agent-registry.json` — agents + autonomy
- `docs/design/architecture/data/hardware-inventory.json` — hosts, OS, GPU
- `docs/design/architecture/data/network-topology.json` — bindings, ports
- `docs/design/architecture/data/credential-manifest.json` — credentials inventory
- `docs/design/architecture/data/data-flows.json` — data-flow definitions
- `docs/INDEX.md` — doc index (used for missing-artifact detection)
- `git log` / `git show <sha>` — recent commits and the triggering diff

## 3. Workflow

Execute these steps in order. Steps map 1:1 to the lifecycle in
`kitty-specs/felix-doc-auditor-agent-01KR7JK9/data-model.md`.

1. **Read the audit issue** — `gh issue view <#> --json number,title,body,labels`.
   Extract the triggering commit SHA from the title (per-merge audits use
   `Doc audit: <sha> (<domains>)`); collect every `area/*` label.
2. **Determine in-scope docs** — load the domain map. If one or more
   `area/*` labels are present, in-scope = union of `domains[<label>]`. If
   no `area/*` labels, in-scope = the union of all values (full-scope —
   typical for weekly audits).
3. **Read system-state sources** (Section 2 list). Cache in memory for the
   audit's duration only; never persist between cron ticks.
4. **Read the triggering diff** (per-merge audits only) via `git show <sha>`.
   This is a **prioritization hint**, not a scope filter. Stale audits are
   still meaningful: compare current docs against current system state
   regardless of how old the diff is.
5. **Per-doc evaluation** — for each in-scope doc, read it and apply the
   comparison rules in Section 5. Build an Edit Proposal (data-model E-004)
   per finding with: `doc_path`, `change_type`, `current_value`,
   `proposed_value`, `evidence_source`, `confidence` ∈ {high, judgment}.
6. **Missing-artifact detection** (Section 6) — runs on every audit
   regardless of scope.
7. **File docs-debt and missing-artifact issues autonomously** (no gate at
   any autonomy level — these are tracked-work artifacts, not file
   mutations, and are fully reversible by closing the issue). Apply
   labels per Section 8 and cross-reference the originating audit.
8. **Branch on remaining outcome:**
   - **Empty audit** (zero high-confidence edits, zero debt, zero
     missing): post an empty audit-summary comment on the originating
     audit, close the audit, release the `status:in-progress` label.
     Done.
   - **Debt-only audit** (zero high-confidence edits, but debt and/or
     missing-artifact issues already filed in step 7): post the
     audit-summary comment listing what was filed, close the originating
     audit, release the lock. Done. **No human gate required** at any
     autonomy level — debt issues are themselves the deferred work.
   - **Edit-bearing audit** (one or more high-confidence edits proposed):
     proceed to step 8.5.

8.5. **Tier A auto-commit pass (v1.5.0+, no approval gate).** Partition the
   proposed high-confidence edits into **Tier A** (per §4.1.a — frontmatter
   metadata only) and **Tier B** (per §4.1.b — content-touching).

   - **If any Tier A edits exist**: commit them atomically per §7 commit
     format. The subject line includes `[tier-a]` to mark the bypass;
     the body lists the bumped fields. This commit lands directly with
     no `audit-pending-approval` issue.
   - **After the Tier A commit** (or if there were no Tier A edits):
     - If Tier B is empty: post the audit summary comment listing any
       Tier A edits applied + any debt/missing issues filed, close the
       originating audit, release the lock. Done.
     - If Tier B is non-empty: proceed to step 9. The Tier A commit (if
       any) is referenced in the pending-approval issue so Kent can see
       what already landed.

   Constitutional and scope guardrails (§4.3) apply unchanged — a Tier A
   edit that targets a forbidden path is **never** auto-committed; it is
   converted to a debt issue per §4.3.

9. **Level 1 approval gate (GitHub issue) — Tier B only.** Assisted
   level only. Skip this and steps 10–11 at Level 2+ (commit directly,
   then jump to step 12).

   At Level 1, file an **"Audit #N: pending approval"** issue per the
   contract at
   `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/audit-pending-approval-issue.template.md`.
   The issue body lists each proposed Tier B edit as a numbered
   before/after diff block, cross-references the originating audit + any
   debt issues just filed + any Tier A commit already landed, and
   includes the label-based decision instructions. Apply labels:
   `audit-pending-approval`, plus the matching `area/*` labels.

   Comment on the originating audit issue: "Pending review at #<new>"
   and **leave the audit open** with the `status:in-progress` label
   intact — the audit remains locked until the decision lands.

   **Exit the agent's turn here.** Decision processing happens on a
   subsequent cron tick (Section 8.6). The agent does **not** poll or
   wait synchronously — Kent decides asynchronously and the agent
   picks up the decision on its next run.
10. (Reserved for cron-tick decision processing — see Section 8.6.)
11. (Reserved.)
12. **At Level 2+, after committing**: post the audit summary comment on
    the originating audit, close it, release the lock.
13. **Append an activity log entry** (NFR-008) — record what was filed,
    what's pending approval, what was committed (if Level 2+).

## 4. Confidence Threshold Rules

The high-confidence vs judgment threshold is the heart of this skill.
Misclassifying a judgment gap as high-confidence risks committing the
wrong content; misclassifying a high-confidence edit as judgment floods
the debt queue with trivia. Apply these rules verbatim.

### 4.1 High-confidence edits

The following edit types are **deterministic** — the correct value is
unambiguous given the system-state source — and qualify as high
confidence. They split into two tiers based on whether the edit touches
content or only frontmatter metadata.

#### 4.1.a Tier A — auto-commit (v1.5.0+, no approval gate)

Pure frontmatter / metadata edits. No content, paths, values, or
references substantively change. These auto-commit at Level 1 without
filing a pending-approval issue, per §3 step 8.5.

1. **Frontmatter `last_updated` / `last_validated` / `revision` updates**
   after a confirmed change to the doc's subject (e.g., the inventory
   was modified — bump its frontmatter date).
4. **`updated_by` references for new entries** — when adding a
   newly-confirmed entry to a JSON inventory, populate `updated_by` with
   the issue or mission ID that introduced it. (Sequential numbering
   preserved from the original §4.1 enumeration for cross-reference
   stability.)

Tier A scope is intentionally narrow: only fields where the correct
value is **a date Kent already determined** (today) or **an audit-trail
ID Kent already chose** (the originating issue/mission). The agent does
not invent these — it copies them from the audit's own metadata. Risk
is bounded to "wrong date / wrong attribution," both trivially
self-correcting on the next cycle and visible in `git log`.

The forbidden-path guardrail in §4.3 applies unchanged — a frontmatter
bump targeting any forbidden file is **never** auto-committed.

#### 4.1.b Tier B — Level-1 approval required

Edits whose correct value has a "right answer" beyond date arithmetic
or audit-trail ID propagation. These continue through the standard
pending-approval issue gate at Level 1.

2. **Service version numbers** in `service-inventory.json` when the
   triggering diff confirms an upgrade. Cross-check against the running
   container if a `docker ps`-equivalent source is available.
3. **File paths** after a confirmed rename. The diff must show the move
   (`R100  old/path -> new/path`); the new path must be unambiguous in
   the rest of the repo.
5. **Removing dead references after a file deletion** — when the diff
   shows `D    old/path`, edit any docs that link to that path to remove
   the link or replace it with the surviving reference.
6. **Adding a new agent registry entry** when the diff shows a new agent
   was deployed (workspace files added under `scripts/openclaw/agents/`,
   `openclaw.json` updated). Use the `agent-registry-entry.template.md`
   contract.
7. **Updating an agent's autonomy level** when the diff has an explicit
   governance decision (e.g., a commit titled `docs(governance): promote
   <agent> to <level>` referencing a Felix Constitution promotion review).

These seven categories are exhaustive at v1.5.0. Any edit outside this
list is **judgment**, not high confidence — even if it feels obvious.
Add new high-confidence categories by versioning this skill, not by
extrapolation in flight.

### 4.2 NOT high confidence (file as docs-debt)

The following findings always require human judgment. File them as
`docs-debt` issues (Section 8) regardless of how clear the gap appears:

1. **Architectural prose** — any paragraph rewriting, restructuring, or
   addition of explanatory text to architecture or design docs.
2. **New runbook sections or procedures** — adding a new "Troubleshooting"
   section, a new health-check procedure, etc.
3. **Constitutional principle updates** — anything touching the Felix
   Constitution's directives, autonomy lattice, or decision rules.
4. **Ambiguous source-of-truth conflicts** — JSON and markdown disagree
   and it is not clear which is authoritative; or two JSON sources give
   different values for the same field.
5. **Interpretation-of-intent edits** — anything requiring a judgment of
   "should this be reflected here too?" (e.g., a new service is added —
   the runbook needs new sections, but which sections, in what order?).

### 4.3 Constitutional guardrails (NEVER edit, regardless of confidence)

The agent must never autonomously edit any of the following, **even if
the change appears trivial and would otherwise qualify as high confidence**:

1. `docs/constitution/FELIX-CONSTITUTION.md` — the constitution itself
2. `CLAUDE.md` — at any path in the repo
3. **Credential files** — `.env`, `credentials.json`, anything matching
   patterns in `docs/design/architecture/data/credential-manifest.json`
4. `kitty-specs/` and `.kittify/` — managed exclusively by spec-kitty

If the audit surfaces a finding against a guardrailed file, file a
`docs-debt` issue describing the finding. Do not edit. Do not include
the proposed change in any pending-approval issue. The constitution's
authority over its own contents is absolute.

## 5. Comparison Rules

Pick the right system-state source for the doc you are auditing:

| Doc type | Authoritative source(s) | View(s) — keep in sync |
|---|---|---|
| `service-inventory.md` | `service-inventory.json` (+ live `docker ps` on office2 if reachable) | The markdown narrative is a view of the JSON; JSON wins per CLAUDE.md "Documentation Standards" |
| `hardware-inventory.json` | manual / commit history | Cross-reference recent commits for hardware changes (e.g., GPU install issue #80) |
| `physical-topology.md`, `network-topology.md` | `network-topology.json` | Markdown is a view; JSON is authoritative |
| `AGENT-REGISTRY.md` | `agent-registry.json` | Markdown narrative is a view; JSON is authoritative; keep `transition_history` consistent |
| Runbooks (`docs/runbooks/*.md`) | the deployed reality on office2 + the relevant inventory entry | Cross-reference what currently exists; gaps become debt issues |
| `docs/INDEX.md` | the actual files in `docs/` and `scripts/openclaw/skills/` | Missing-artifact detection (Section 6) lives here |
| Anything else listed in the domain map | the matching JSON source if one exists; otherwise the doc itself | If no JSON source exists, the doc is its own source; flag as judgment |

When the markdown narrative and JSON source conflict, the JSON wins
(per CLAUDE.md "Documentation Standards" and Felix Constitution
Directive 5). Update the markdown view to match JSON, never the reverse.

## 6. Missing-Artifact Detection (FR-004)

Run on every audit regardless of scope. Compare what is **deployed**
against what is **documented**:

1. **Agents** — for each entry in `agent-registry.json`, verify a runbook
   exists at the path documented in `docs/INDEX.md`. A deployed agent
   without a runbook is a missing artifact.
2. **Services** — for each entry in `service-inventory.json`, verify a
   matching narrative entry in `service-inventory.md` and a runbook (if
   the service warrants one). A deployed service without an entry is a
   missing artifact.

### What is NOT a missing artifact

The audit check is for **human-navigable documentation**. Files that
are agent-readable contracts (discovered or bound through other
mechanisms) MUST NOT be flagged as missing INDEX entries.

Specifically excluded from missing-artifact detection:

- **`scripts/openclaw/skills/*/SKILL.md`** — skills are auto-discovered
  by OpenClaw (`openclaw skills list`) and bound to consumers via each
  agent's own `AGENTS.md` / `TOOLS.md` (`cat ~/.openclaw/skills/<name>/SKILL.md`
  pattern). They have a separate registry and should NOT be in
  `docs/INDEX.md`. Front-matter recognition: `name:` + `version:`
  fields without `doc_type` ⇒ skill, exclude.

- **`scripts/openclaw/agents/*/{IDENTITY,SOUL,TOOLS,USER,AGENTS}.md`** —
  agent workspace files are bound via `openclaw.json` registration and
  loaded by the OpenClaw runtime; they are not human-navigable docs.

- **Anything under `kitty-specs/` or `.kittify/`** — managed exclusively
  by spec-kitty, never INDEX-tracked.

- **Anything under `docs/archive/`** — archival; INDEX explicitly marks
  archived items but the archived files themselves are not active docs.

**Heuristic for ambiguity**: if a file's front-matter has `doc_type` set
(e.g., `reference`, `runbook`, `guide`), expect it in INDEX. If the
front-matter is `name:` + `version:` with no `doc_type`, treat as a
skill or agent contract, do not flag.

A doc is **missing** only if absent. Thin or stale docs are judgment
gaps (Section 4.2), not missing artifacts. File one debt issue per
missing artifact (Section 8).

## 7. Commit Format

Two commit shapes share one format. Tier A auto-commits (§3 step 8.5)
and Tier B post-approval commits (§3 step 9) both use:

```
chore(doc-audit): <one-line summary> (audit: #<N>)

- <doc-relative-path>: <one-line change description>
- <doc-relative-path>: <one-line change description>

Refs #<audit-issue-number>.

Co-Authored-By: felix-doc-auditor <noreply@kg-automation.local>
```

The full contract lives at
`kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/commit-message.template.md`.

Rules:

- Subject ≤72 chars where possible.
- For **Tier A auto-commits**, prefix the summary with `[tier-a]`. Example:
  `chore(doc-audit): [tier-a] bump last_updated on 3 docs (audit: #181)`.
  This makes the bypass visible in `git log` at a glance and lets
  reviewers filter for them when auditing the auditor.
- For **Tier B approved commits**, no prefix. Example:
  `chore(doc-audit): correct service version in service-inventory.json (audit: #181)`.
- Body is a bullet list of edits — one bullet per file (group sub-changes
  under one bullet if they touch the same file).
- Footer always includes `Refs #<N>.` and the `Co-Authored-By` line.
- One commit per audit per tier — if an audit has both Tier A and Tier B
  edits, the Tier A commit lands in step 8.5 and the Tier B commit lands
  later in step 12 after approval. They reference the same audit issue.
- If zero edits qualify (or all are debt/missing), no commit is made.

## 8. Docs-Debt Issue Template

For each judgment gap and missing artifact, create one issue using
`.github/ISSUE_TEMPLATE/docs-debt.md`. Populate **all six** sections:

1. **Artifact** — repo-relative path to the doc (existing or proposed).
2. **Gap description** — what's missing/outdated/incorrect, specifically.
3. **Area** — checked items match the audit issue's `area/*` labels.
4. **Cross-references** — `Refs #<audit-issue-number>` plus links to
   related docs and commits.
5. **Draft outline** — **the load-bearing field**. Specific enough that a
   downstream Claude Code session can act on it without further research.
   This is the FR-003 success criterion (SC-003): if a downstream session
   needs a separate research pass before writing the fix, the outline was
   not specific enough.
6. **Success criteria** — 2–4 verifiable bullet points.

Apply labels: `P2-debt`, the matching `area/*` label(s), and `type/debt`.

**Special case `area/biz-ops`** (per spec C-006): prefix the title with
`Docs (biz-ops): ` and include a body line:
> ⚠ Human confirmation required before action — biz-ops docs may be
> intentionally private or informal.

**One issue per gap** — never bundle. Bundling dilutes the draft outline.

### 8.5 Level 1 Approval Gate (GitHub issue, label-based decisions)

At Level 1 (Assisted), the agent files a single "Audit #N: pending
approval" issue containing the proposed high-confidence edits as
before/after diff blocks. **Only file mutations are gated** — debt
issues and missing-artifact issues are filed autonomously in workflow
step 7, regardless of approval state.

#### 🛑 ABSOLUTE RULE — labels the agent NEVER applies

When filing a pending-approval issue, the agent applies **only**:

- `audit-pending-approval` (the discoverability marker)
- The matching `area/*` label(s), copied from the originating audit

The agent **NEVER, under any circumstance**, applies any of the
following labels:

- `audit-approve`
- `audit-reject`
- `audit-skip`

These three labels are **reserved for Kent** (or any other authorized
human reviewer). They represent the human's gating decision. An agent
that applies them to its own pending-approval issue has bypassed the
Level-1 autonomy boundary — a critical gate violation. Refuse to
apply any of these three labels in ANY of the agent's GitHub
operations, including (and especially) at issue-creation time and
during the cron-tick decision processing (Section 8.6).

If the agent encounters a pending-approval issue it filed that lacks a
decision label, it MUST exit its turn and wait for the next cron tick.
The agent does NOT self-approve to "be helpful."

Kent decides asynchronously by applying ONE of three labels to the
pending-approval issue. The agent picks up the decision on its next
cron tick (Section 8.6).

| Decision label | Action |
|---|---|
| `audit-approve` | Apply all proposed edits, commit atomically (Section 7), post the audit summary on the originating audit, close both pending-approval and originating audit, release the `status:in-progress` lock. |
| `audit-reject` | Do not commit. Demote each proposed edit to a separate `docs-debt` issue (with the proposed before/after as evidence), close both pending-approval and originating audit, release the lock. Activity log records the rejection. |
| `audit-skip` | Close both pending-approval and originating audit with a skip note. No commit, no demotion, no further debt issues. Release the lock. Activity log records the skip. |

**No timeout.** Decisions are asynchronous — pending-approval issues
stay open indefinitely until Kent applies a label. The originating
audit's `status:in-progress` lock blocks the cron from picking up the
same audit again, but does not gate other audits.

**Why not `audit-approve N,M` (partial approve)?** The original WhatsApp
flow supported partial approval. Under the GitHub flow, if Kent wants
only some of the edits, he can either (a) apply `audit-approve` after
striking out the unwanted lines from the issue body and noting the
exclusion, or (b) apply `audit-reject` and let the agent file all of
them as debt issues, then approve the desired ones individually as
follow-up. Partial-approve via additional labels is deferred unless
operationally needed.

### 8.6 Cron-Tick Decision Processing

On every cron tick, **before** scanning for new audit issues, the agent
checks for pending-approval issues with a decision label applied:

```
gh issue list --repo kentonium3/kg-automation \
  --label "audit-pending-approval" --state open \
  --json number,title,labels,body
```

For each result, examine its labels:

- If a decision label (`audit-approve`, `audit-reject`, `audit-skip`)
  is present → **perform the actor-verification check below**, then
  apply that decision per the table in Section 8.5
- If no decision label → leave alone; Kent hasn't decided yet
- If multiple decision labels → treat as ambiguous, post a clarifying
  comment, do nothing else

#### 🛡 Actor-verification check (defense in depth)

Before applying any decision label, the agent MUST verify that the
**most recent** decision-label event was applied by a human, not by
the agent's own GitHub identity:

```bash
# 1. Resolve the agent's own GitHub identity (the bot account)
SELF_LOGIN=$(gh api user --jq .login)

# 2. Query the issue timeline; select the MOST RECENT decision-label event
LATEST_DECISION=$(gh api repos/kentonium3/kg-automation/issues/<N>/timeline \
  --jq '[.[] | select(.event == "labeled" and (.label.name == "audit-approve" or .label.name == "audit-reject" or .label.name == "audit-skip"))] | last | {label: .label.name, actor: .actor.login, at: .created_at}')

# 3. Inspect the actor of the most recent decision-label event
```

**If the most recent event's `actor.login == SELF_LOGIN`**: this is a
**GATE VIOLATION** — the agent applied the decision to its own issue
and no subsequent human event supersedes it. The agent MUST:

- NOT process the decision (no commit, no demotion, no close)
- Post a comment on the pending-approval issue explaining the
  detected gate violation (cite this section)
- Remove the offending decision label (`gh issue edit <N> --remove-label <decision-label>`)
- Log the violation to the activity log as an `error`-severity entry
  with full context (pending-approval issue #, originating audit #,
  decision label that was self-applied, timestamps)
- Exit the cron tick. Do NOT proceed to new-audit scanning. The next
  tick may proceed normally after the human investigates.

**If the most recent event's `actor.login != SELF_LOGIN`** (a human
applied the latest decision): proceed with applying the decision per
Section 8.5.

**Historical self-applies** — if any *earlier* decision-label event in
the timeline has `actor.login == SELF_LOGIN` but a later legitimate
human event supersedes it, the human's intent stands and processing
proceeds. The historical self-apply MUST still be logged as a
violation and surfaced via a comment on the pending-approval issue
(citing this section) so the anomaly is not hidden from the audit
trail.

Apply each decision in order (oldest pending-approval first), then
proceed to the new-audit scan.

**Why "most recent" matters**: the human may correct an erroneous
self-apply by re-applying the same decision label from their own
account. The timeline then contains both events — the self-apply at
t1 and the human re-apply at t2. The human's intent at t2 is the
operative decision. Selecting the most recent event resolves this
case without discarding the legitimate decision, while the
historical-violation logging ensures the earlier self-apply remains
visible. This codifies the dual-apply handling first exercised during
the v1.3.0 canary on 2026-05-11 (pending-approval #219 / audit #218,
both processed correctly under v1.3.0 but per agent judgment rather
than spec'd behavior — issue #222).

**Why this check exists**: the agent and Kent may share infrastructure
identity in some configurations (e.g., shared `gh` auth tokens). The
actor check on the labeled event is a code-level verification that
the gate was crossed by a human, not by the agent acting on itself.
Combined with the absolute rule in Section 8.5 (agent never applies
decision labels), this is two-layer defense against the
self-approval class of bug exposed by audit #169 / pending-approval
#213 on 2026-05-10 (see issue #215).

**Race condition note**: if Kent applies a decision label while the
agent is mid-tick processing a different audit, the next tick picks it
up. No special handling required — the cron is idempotent and the
audit lock prevents collisions.

**Empty audits** (zero of all categories): the agent posts the empty
audit-summary comment on the originating audit issue and closes it
unconditionally — the no-op close is the audit completing cleanly, not
an action that needs ratification. No pending-approval issue is filed.

**Debt-only audits**: in v1.2.0 these no longer require an approval
gate. Debt issues are filed autonomously in workflow step 7, the audit
summary is posted, and the audit is closed in step 8. Previous
versions gated debt-only audits behind a WhatsApp reply; v1.2.0 drops
this gate because debt issues are tracked-work artifacts, not
mutations, and are individually reviewable / closeable post-hoc.

## 8.7 Lock Lifecycle

Every audit is protected by a `status:in-progress` GitHub label on the
audit issue. This is the concurrency control (R-009) — multiple cron
ticks must not double-process the same audit.

### Acquire

At the start of every audit run, after § 3 issue selection:

```bash
gh issue edit <#> --repo kentonium3/kg-automation \
  --add-label "status:in-progress"
```

Failure modes: see § 9 (rate-limit retry, etc.).

### Persist

At Level 1, when an audit produces edit proposals, the lock spans
multiple cron ticks: acquired on the audit-run tick, persists across
the wait for Kent's decision label, and is released alongside issue
closure on the post-decision tick (per § 8.6).

For empty audits and debt-only audits the lock is acquired and
released in the same tick.

### Release

On any exit path — success, failure, or skip:

```bash
gh issue edit <#> --repo kentonium3/kg-automation \
  --remove-label "status:in-progress"
```

Use a try/finally pattern. If release fails (transient API error):
retry with exponential backoff (30s, 60s, 120s). Still failing → log
and exit. Next tick sees the stale lock per the rule below.

### Stale-lock detection

If § 3 selection encounters an audit issue with `status:in-progress`:

- **Has a referenced pending-approval issue with no decision label** →
  not stale; this is the expected Level 1 wait state. Skip this audit
  and continue to the next selection candidate.
- **No referenced pending-approval issue** → prior tick crashed
  mid-processing. Do NOT silently resume. Skip the audit; manual
  cleanup is documented in `docs/runbooks/doc-auditor-ops.md`.

## 9. Error Handling

| Failure mode | Response |
|---|---|
| Doc unreadable / locked / missing | Log to audit summary's "Items requiring human review"; skip this doc; continue with the rest. **Never** abort the whole audit (NFR-003). |
| `git push` fails (rebase needed) | `git pull --rebase origin main`. If clean, retry push. If the rebase produces conflicts, abort the commit (`git rebase --abort`), demote ALL proposals from this audit to debt issues, record the conflict in the summary's "Items requiring human review". Never resolve conflicts manually — that is judgment work. |
| GitHub API rate limit (HTTP 403 with rate-limit headers) | Exponential backoff: 30s, 60s, 120s. After 3 failed retries, leave the audit at `status:in-progress` and exit; the next cron tick (60 min) retries. |
| `gh issue create` fails (Level 1 pending-approval filing) | Do NOT commit. Leave the audit at `status:in-progress`. Log the failure to the activity log including the proposed-edits block. Next cron tick retries. Recovery is via the runbook. |
| `gh` decision-label query/apply fails (§ 8.6) | Log; skip that pending-approval issue this tick; continue to § 3 selection. Next tick retries. Originating audit lock is unaffected. |
| Domain map missing / unreadable | **Critical.** Post a comment on the audit issue stating the map could not be read, and that the map is the scope contract (C-005). Do not mutate anything else. Release the lock. |
| Skill missing / unreadable | Same handling as domain map missing. Post a comment, do not proceed, release the lock. |
| Stale lock detected (own label from prior crashed tick) | Do NOT silently resume. Skip this audit; the runbook documents manual cleanup. |
| Any unexpected exception | Catch broadly, log class + message, release the lock, exit cleanly. Next tick is the retry. Do NOT attempt creative recovery. |

## 10. Output Contracts

The following contracts are **authoritative** for the formats this skill
produces. The skill defers to them — when format details disagree, the
contract files win. Do not duplicate their content; reference them.

- Audit pending-approval issue (Level 1 only):
  `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/audit-pending-approval-issue.template.md`
- Audit summary GitHub comment (posted on the originating audit at close):
  `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/audit-summary-comment.template.md`
- WhatsApp templates (DEPRECATED in v1.2.0; retained for archival):
  `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/whatsapp-summary.template.md`,
  `whatsapp-reply-vocabulary.md`. Replaced by GitHub-issue approval per
  issue #207.
- Agent registry entry (used when a missing-artifact run produces a new
  agent registration that becomes a high-confidence registry-entry-add):
  `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/agent-registry-entry.template.md`
- Commit message format:
  `kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/commit-message.template.md`

## 11. Examples

Each example shows a real recent commit, the audit it would have
triggered, and the classification the skill produces.

### Example A — Frontmatter `last_updated` bump (high confidence)

**Triggering commit**: `9b942ae` — `fix: sync agent-registry.json with
AGENT-REGISTRY.md (add escalation agent)`.

**Audit triggered**: per-merge audit, `area/felix-core` scope; in-scope
docs include `docs/constitution/AGENT-REGISTRY.md` and
`docs/constitution/agent-registry.json`.

**Finding**: the commit added the `felix-admin-escalation` agent entry
to the JSON. The JSON's `last_updated` field is older than the commit
date.

**Classification**: high confidence — `last_updated` field type is
enumerated in Section 4.1 #1.

**Action**: edit `agent-registry.json` to set `last_updated` to the
commit date and `updated_by` to `#131` (the originating issue). Commit:

```
chore(doc-audit): bump agent-registry last_updated (audit: #<N>)

- docs/constitution/agent-registry.json: bump last_updated to 2026-04-06; updated_by to #131

Refs #<N>.

Co-Authored-By: felix-doc-auditor <noreply@kg-automation.local>
```

### Example B — Missing runbook for new agent (missing artifact)

**Triggering commit**: `55f5549` — `feat(WP01): create felix-doc-auditor
agent workspace files`.

**Audit triggered**: per-merge audit, `area/felix-core` scope; in-scope
docs include `docs/INDEX.md` and `docs/constitution/AGENT-REGISTRY.md`.

**Finding**: missing-artifact detection (Section 6) flags that
`scripts/openclaw/agents/felix-doc-auditor/` exists but
`docs/runbooks/doc-auditor-ops.md` does not.

**Classification**: missing artifact (Section 6).

**Action**: file a `docs-debt` issue. Title: `Docs: missing operations
runbook for felix-doc-auditor`. Draft outline: section headers
(Overview, Cron Schedule, Manual Trigger, Domain Map Maintenance,
Confidence Threshold Tuning, Stale-Lock Cleanup, Troubleshooting),
each with 1–2 sentences of intent. Cross-references include the
originating audit issue and `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md`.

### Example C — Prose rewrite needed (judgment, NOT high confidence)

**Triggering commit**: `f5c7bda` — `feat: WP02/WP03 validation — inbox
PASS, habits/escalation FAIL (#135)` (mission 021 model tiering).

**Audit triggered**: per-merge audit, `area/felix-core` scope; in-scope
docs include `docs/runbooks/openclaw-agent-setup.md`.

**Finding**: the runbook's "Choosing a Model" section pre-dates model
tiering and does not reflect the new Pinned/Optimizable distinction.
Adding the new content requires several paragraphs of new prose plus a
worked example; the right placement within the section is a judgment
call.

**Classification**: NOT high confidence (Section 4.2 #2 — new runbook
section requiring prose).

**Action**: file a `docs-debt` issue. Title: `Docs: openclaw-agent-setup
runbook missing model-tiering guidance`. Draft outline: insert a new
subsection "Choosing a Model Tier" between "Choosing an Agent Name"
and the verification checklist; explain Pinned vs Optimizable, link to
the Model Assignment Policy in `AGENT-REGISTRY.md`, give one Pinned
example (judgment-heavy) and one Optimizable example. Cross-reference
mission 021 plan and the agent-registry policy section.

### Example D — Service version bump (high confidence)

**Triggering commit**: `f8f9215` — `feat: WP04/WP05 deploy tiered config
and update registry (#135)`.

**Audit triggered**: per-merge audit, `area/felix-core` scope; in-scope
includes `docs/design/architecture/data/service-inventory.json`.

**Finding**: the diff confirms an OpenClaw config update changing the
model assignment for `felix-admin-inbox` from Sonnet to Haiku. The
service entry's `last_updated` is older than the commit and `updated_by`
does not reference issue #135.

**Classification**: high confidence — Section 4.1 #1 (frontmatter date)
and #4 (`updated_by` for the changed entry).

**Action**: edit `service-inventory.json` to bump `last_updated` and
`updated_by`. Single commit, atomic per FR-002.

### Example E — Skill file is NOT a missing artifact (exclusion)

**Triggering commit**: `bb2018d` — `feat(kitty/mission-felix-doc-auditor-agent-01KR7JK9): squash merge of mission`. The merge created `scripts/openclaw/skills/doc-audit/SKILL.md`.

**Audit triggered**: weekly full-scope audit (#186, 2026-04-19).

**Finding**: missing-artifact detection scans `scripts/openclaw/skills/*/SKILL.md` and finds 6 SKILL.md files (doc-audit, escalation, skill-author, task-intelligence, vikunja-api, whisper). None of them appear in `docs/INDEX.md`.

**Classification**: **NOT a missing artifact** — these are skill contracts excluded per Section 6 "What is NOT a missing artifact". Skills are auto-discovered by OpenClaw (`openclaw skills list`) and bound to consumers via per-agent standing orders. They have a separate registry and should NOT be in `docs/INDEX.md`.

**Action**: do not file debt issues. Mention in the audit summary's "Items requiring human review" only if the auditor wants to confirm the policy applies (e.g., on first run after a heuristic update). Otherwise silently skip.

**Why this rule was added (v1.1.0)**: the v1.0.0 heuristic flagged these 6 files during audit #186, producing false-positive debt issues. Refined per issue #201 to exclude SKILL.md files and agent workspace files from the missing-INDEX check.

---

**End of skill.** A reviewer should verify: confidence rules in
Section 4.1 cover all 7 spec FR-002 categories verbatim; workflow steps
in Section 3 map 1:1 to the lifecycle in `data-model.md`; constitutional
guardrails (Section 4.3) are restated as absolute; and every example
exercises a different rule category.
