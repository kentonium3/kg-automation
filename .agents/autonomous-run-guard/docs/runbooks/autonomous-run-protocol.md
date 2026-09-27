---
id: autonomous-run-protocol
doc_type: runbook
title: Autonomous / Overnight Run Protocol
status: active
level: reference
owners: [kgale]
last_validated: 2026-08-25
version: 1.7.0
---

# Autonomous / Overnight Run Protocol

**What this is.** The operating parameters for an unattended run **in any repo we operate in**.
Kent names the **queue**; he does not restate the **rules**. They are these.

**Scope: repo-agnostic.** Everything in §1–§7 applies wherever an autonomous run happens. The
handful of things that genuinely vary by repo are isolated in **§8 Per-repo parameters** — that is
the only section a new repo needs to fill in. Nothing else should be re-derived per repo.

> **Authoring convention.** This file is authored in `spec-kitty-qa` and is **read-only from any
> other context** — same convention as `docs/spec-kitty-issues.md`. If you are working from another
> repo, read it and do not edit it; report corrections rather than making them here.

> **Promoted from project memory 2026-08-24, and generalised from one repo to all.** These rules
> were agreed 2026-08-07, were written as if they governed only `spec-kitty-qa`, and lived only in
> the agent's memory directory — which is **not git-tracked**, has no history and no backup, and is
> readable from exactly one account on one machine. That is too fragile for the rules that govern an
> unattended run, and it is why they were nearly presumed lost. **This file is now the source of
> truth**; memory should point here, not duplicate.

**Why it exists.** Kent sets a run up at bedtime and cannot answer questions. Re-negotiating the
envelope wastes the window, and **a run that halts on something with a known answer wastes the whole
night.**

---

## 0. Prep — the upstream sweep (before EVERY mission)

**Run this before the first mission of a run, not after.** It costs a few minutes and it buys three
things: **workarounds we no longer need are dropped**, **faults we are about to hit are recognised
instead of re-diagnosed**, and the register and memory stop drifting from reality.

> ⚠ **Measured 2026-08-24: of the 54 upstream issues referenced in `docs/spec-kitty-issues.md`,
> 27 were already CLOSED upstream.** (The register now carries 53 distinct references, each
> qualified with its repository.) Half the register had never been checked against upstream
> state. Every stale row is a workaround we may still be applying to something already fixed — and
> a workaround applied to a fixed defect is not neutral: it adds steps, it can mask the real
> behaviour, and it teaches the next reader a false constraint.

### The three queries

> ⚠ **Which repositories.** We file into `spec-kitty/spec-kitty`,
> `spec-kitty/spec-kitty-saas` and `spec-kitty/spec-kitty-planning`. (Updated 2026-09-27: the
> former `EXPERIMENTAL-*` names are retired; `EXPERIMENTAL-spec-kitty` is ARCHIVED and does not
> redirect, so sweeping it returned silence rather than an error.)
> **These names are expected to change again at the rename**, and this file is not the authority
> for them — `UPSTREAM_TARGETS` in `scripts/hooks/_hook_lib.py` is. If the two disagree, the code
> is right and this section is stale; fix it here rather than working around it.
>
> ⚠ **Query 3 does not name a repository at all, and that is the point.** Each reference in the
> register carries its own (`Priivacy-ai/spec-kitty#3594`), because most of our history lives
> under the retiring organisation while new filings do not. Sweeping bare numbers against one
> hard-coded repository is what produced the failure below.

```bash
# 1. What WE reported, and where it now stands (filings are authored by the operator account)
gh issue list --repo spec-kitty/spec-kitty --author @me --state all \
  --json number,title,state
gh issue list --repo spec-kitty/spec-kitty-saas --author @me --state all \
  --json number,title,state
gh issue list --repo spec-kitty/spec-kitty-planning --author @me --state all \
  --json number,title,state

# 2. What closed upstream recently — the fixes we may now be entitled to
gh issue list --repo spec-kitty/spec-kitty --state closed --limit 100 \
  --search "closed:>=<date-of-last-sweep>" --json number,title,closedAt

# 3. Cross-check every upstream ref the register cites, each against its OWN repository
for ref in $(grep -oE "[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#[0-9]+" docs/spec-kitty-issues.md | sort -u); do
  gh issue view "${ref#*#}" --repo "${ref%#*}" --json number,state,title
done
```

> ⚑ **Two measured defects this block used to carry.** Both were live until 2026-08-26, and both
> are the kind that a reading cannot find.
>
> 1. **It named the retiring organisation.** Run verbatim against the new one, **49 of 53**
>    references did not resolve — and the 4 that did were *coincidental number collisions* that
>    returned a confident, plausible status belonging to an unrelated item. Our `#140` (the
>    `auto_commit` opt-out) came back `MERGED`, from a PR about a MissionCreated emitter. A check
>    that cannot find its subject is visible; a check that finds the **wrong** subject is not.
> 2. **Query 3 could never earn its own marker.** The old shape was
>    `echo "$n $(gh issue view …)"`, and under `shlex` a command substitution inside a quoted
>    string is a **single argument to `echo`** — so the guard's `positional[1:3]` never saw
>    `["issue", "view"]`. An operator following this runbook literally earned 3 of 4 markers and
>    was refused, with the guard printing the same instruction they had just followed. The bare
>    `gh issue view` above is the command in the loop body precisely so the tokeniser sees it.
>
> ✅ **Both halves verified by running them, not by reading.** Against the live session ledger
> (`$(git rev-parse --git-common-dir)/spec-kitty-hooks/sessions/`): the repaired query 3 took
> `sweep.register_refs` from 3 to **4** and resolved **53 of 53** references; the old shape,
> run immediately afterwards, incremented `register.read` and left `sweep.register_refs` at 4 —
> it printed plausible states the whole time and earned nothing.

### What to do with the answers

1. **A register row whose upstream is CLOSED is a candidate for retirement — not an automatic
   delete.** Closed is not the same as fixed-in-our-build. Apply the row's own retirement condition:
   confirm the fix is in the build we actually run, then **verify the symptom is gone**, then delete
   the row. ⚠ Do not delete on the issue state alone — that is deriving, not measuring.
2. **Some rows cite a closed issue on purpose** (e.g. "closed — this *is* the fix", or a decision
   pinned by a test). Those stay. Read the row before acting on it.
3. **Open issues become the fault forecast.** Anything open that touches the surfaces this mission
   will use is a fault to *anticipate* — recognised on sight instead of diagnosed from scratch, and
   already carrying its workaround.
4. **Update the local tracker and memory** so the next run starts from the corrected picture.

A register that only grows is one people stop trusting. This step is what keeps it honest, and it is
the trigger the register's own "Retiring a row" section has always assumed but never had.

---

## 1. The two things that actually end a run

Both are avoidable. Neither is exotic.

### 1a. A tooling fault with no documented workaround

Governed by [`spec-kitty-workflow-fault-protocol.md`](spec-kitty-workflow-fault-protocol.md),
which **narrows** the always-on "stop on any unexpected spec-kitty behaviour" rule for this repo set
(`spec-kitty-qa` included). Its autonomy contract: diagnose + track satisfies the evidence duty;
**halting is not required.** Only two stops — `[STOP-A]` before posting upstream copy, `[STOP-B]`
when no *documented* workaround exists.

⚠ **"Pre-known" means documented** — in `docs/spec-kitty-issues.md`, an upstream issue, or project
memory. An improvised workaround is a *silent* workaround and is prohibited.

### 1b. ⚑ A mission input question — the usual culprit

**Presenting three or four options with one marked "recommended", instead of acting.** This halts a
run as surely as a crash, and it is the most common way these runs have died.

The answer is neither *ask the operator* nor *decide it yourself*. Per the cross-repo autonomous-run
contract (in `kg-automation`, under `.agents/autopilot/`), it is to **re-queue**:

- **Pick the lightest vehicle you are confident needs no operator input.** *"If the agent is not
  confident the fix needs no operator input, it does NOT start it — it surfaces the decision and
  moves to the next queue item."*
- **Blocked needing operator input mid-item** → back the tree out to the last clean `main`, drop the
  item, pick a different one. **Never leave a dirty tree or a half-merged mission.**
- **Surface genuine judgment calls in the running report, not as a blocking question**
  (non-negotiable: *surface judgment calls; do not decide the operator's decisions*).
- At an ordinary implementation fork, decide per **D-1** (durable + safe; back up untracked mutable
  state first) and **log the decision + rationale**.

> **Corollary — the queue must be over-provisioned.** "Move to the next item" only works if there is
> a next item. An overnight queue sized to be *completed* has nothing to fall through to, so the
> first genuine decision ends the night. **Always queue more than the night can consume.**

---

## 2. Detour latitude

**Granted** for the repo set named in §8. Where granted, treat the repo as inside the
detour-protocol set. On any spec-kitty or
sibling-tooling fault: fully diagnose, capture the evidence (exact command + error + build SHA),
track it, apply a **known/documented** workaround, and continue.

This narrows *where you halt*. It never licenses a silent or improvised workaround, and it never
removes the duty to preserve evidence.

**Halt the run only on:** no known workaround · a call that genuinely needs Kent's judgment ·
a Tier-0 host change · git surgery · a usage limit · a failed deploy that rolled back.

---

## 3. Resolved decisions (Kent, 2026-08-24)

Both of these were recorded as open conflicts. They are now settled, with the reasoning, because a
rule without its reason gets re-litigated at 3am.

### D-1 — the fork rule is **"reversible / safe"**. Not "minimal".

**"Minimal" was the word creating the conflict, and it is dropped.** There was never a real
disagreement with the quality bar once it went.

- **Prefer the more durable, more universal, more maintainable solution.** This is the same
  direction as §5, not a competing one.
- **"Reversible" does not mean "smaller scope."** It is a narrow, concrete precaution: **before
  changing a data store or a mutable runner file that is not already version-tracked in git, back
  it up.** That is all it means.
- So at a fork: take the durable option, and take the backup first. Log the decision + rationale.

⚠ **Do not read "reversible" as licence to pick the cheaper change.** That misreading is what
produced a draft envelope instructing "choose the smaller scope", which is precisely the shortcut
§5 exists to prevent.

### D-2 — a **full spec-kitty mission is the default** where the scope justifies it

The cross-repo contract calls an unattended full mission *"rare"*. **That characterisation is
superseded here**, and the reason it existed matters:

- It dates from a period when the mission workflow was **markedly buggier**. Workflow faults were
  inflating mission overhead by **2–4×**, which genuinely degraded the value equation. That is
  improving, so the guidance built on it no longer holds.
- **kitty-light is not reliably cheaper.** Its lower rigour has produced less well-designed and
  less well-implemented solutions; the reviews then catch them, and the rework costs cycles. The
  "lighter" vehicle frequently loses on total cost.
- **A full mission carries the most rigour** in planning and in review, which is the point.

**And the decisive argument is that mission ceremony is not pure overhead — it is also work
product.** Running full missions is *the most active QA we currently do on the spec-kitty CLI*. It
surfaces real issues, and the P0/P1 ones are being addressed quickly upstream. A mission therefore
buys rigour **and** CLI coverage from the same spend.

> **Corollary — why the build-currency policy exists.** This is why spec-kitty is kept on the
> latest build as much as possible: the missions are the instrument, so the instrument has to be
> pointed at current code for its findings to be worth filing.

**Operative rule:** choose the vehicle by **scope**, not by fear of ceremony. Full mission when the
scope justifies it; kitty-light only when the change is genuinely small *and* the investigation was
short *and* both review point-cuts will actually run.

### D-3 — capture-and-continue replaces stop-on-fault (**IN FORCE**)

**Agreed in principle 2026-08-24. IN FORCE from 2026-09-27**, by Kent's direction to the team-lead:
*"All your working agents should follow the autonomous run runbook and especially that D-3 protocol."*
Relayed to every working agent on the felix-graph-692 channel at 2026-09-27T01:59:38Z
(`20260927T015938729917Z61ae361ba8`). The precondition text below is retained as the record of what
was originally required; it is no longer gating.

**The new stance.** On a spec-kitty workflow fault: capture all the evidence, drill into root
cause, find a workaround, and **record all of that in a tracking issue — then continue the
mission**. After the mission, the accumulated issues are prepared for dedupe and formatting as a
**batch**.

**Why it is better, and why the old stance existed.** "Stop on any fault" dates from a period with
less experience and less procedure around capturing bugs; halting was simply the only tool reached
for to preserve evidence. It is no longer the best one:

- It is **more efficient** — one batched dedupe/format pass instead of N interruptions.
- It costs **no diagnostic information**, because the capture is what preserves evidence, not the
  halt.
- ⚑ **And halting actually LOSES evidence.** A mission stopped at its first fault never reaches the
  faults it would have hit later. The rule meant to preserve evidence was suppressing the rest of
  it.

**⚑ And it is the STRICTER stance, not the looser one.** This is the argument that should settle
any doubt about "less blocking" meaning "less rigorous":

- **Stopping requires no diagnosis.** Under stop-on-fault you may halt and hand over an
  uninvestigated symptom. The rule permits undiagnosed escalation.
- **Continuing requires a diagnosis.** You cannot write the tracking issue without inspecting root
  cause, and you cannot continue at all without a workaround. Capture-and-continue *forces* both.
- ⚑ **The workaround is self-proving.** A workaround proposed at a halt is never exercised. One
  that lets the mission continue has been **exercised by construction** — if it had not worked, the
  mission could not have proceeded. Proof comes free with the mechanism.

**⚠ Diagnose COMPLETELY at the moment of the fault — the evidence is perishable.**

⚑ **Applying the workaround can destroy the evidence.** The workaround mutates the very state that
proves what happened — git state, worktree, event log, file contents, the exact failing output. Once
the mission has moved on, that state is gone, and a diagnosis deferred to "later" may be a diagnosis
of something that no longer exists. **Complete each diagnostic step and capture its evidence into
the tracking issue as the need arises, before continuing.**

**On "time pressure" — there is none, and inventing one is the actual failure mode.** An earlier
draft of this section blamed false root causes on mid-mission time pressure. That pressure does not
come from the operator. It comes from **goal-completion orientation** — treating the fault as an
obstacle between the run and a finished mission, and therefore doing the cheapest diagnosis that
lets the run continue.

**The fix is to redefine the goal, not to manage the pressure.** Robustly capturing any workflow
fault **is part of completing the mission**, not a detour from it. Stated that way the pressure
dissolves: there is no race between diagnosing and finishing, because the diagnosis is the finishing.

⚠ Measured this session, as the cost of getting this wrong: **#257 and #258 were both filed with
root causes that later measurement disproved** — #257 blamed a dead daemon's stale lock when nothing
held the lock at all.

**What is genuinely deferrable, and what is not:**

| | When | Why |
|---|---|---|
| **Perishable — do it AT the fault** | Capture exact command, error, build SHA, and the surrounding state **before** applying the workaround. Drill to root cause. Prove the workaround. Write it into the tracking issue. | Continuing destroys the state that proves it. |
| **Non-perishable — batch it after** | Dedupe against the register and the upstream queue (open *and* closed); the intent check against the tooling's own test suite; formatting to the template. | Reads code and issues that are still there afterwards, and genuinely benefits from being done in one pass. |

**Why completeness and accuracy are the point.** These reports are consumed upstream — sometimes by
machine before a human reads them. **A complete, accurate report is what lets upstream resolve it
quickly**; an incomplete one buys a round trip, and an inaccurate one buys distrust of everything
else we file. That is the return on diagnosing properly at the moment the evidence exists.

**⚠ Precondition — the stance changes only when the SOP reliably wraps EVERY mission.** Without
that, capture-and-continue degrades into continue-and-forget, which is strictly worse than stopping:
the mission proceeds *and* the evidence is gone. An instruction is not a mechanism.

**What "reliably" must mean here — and its honest limit.** The enforcement pattern already exists
and is proven in this repo: `scripts/hooks/upstream_filing_guard.py` is a `PreToolUse` hook that
regex-matches a risky command, keeps a per-session ledger of which prerequisite steps were observed,
and **denies** the action when they are missing. It works — it blocked a filing during this very
session until the dedup and attribution steps had actually run.

The same shape applies at mission terminus: gate `spec-kitty merge` (and/or mission-branch
`gh pr create`) on the mission's fault ledger being **reconciled** — either an explicit *"no faults
encountered"* assertion, or every recorded fault carrying a tracking issue.

> ⚠ **State the limit plainly, as that guard's own text does: a gate proves a step ran; it cannot
> prove the judgment was sound.** It cannot know a fault occurred and went unrecorded. What it
> guarantees is that the run had to *answer the question* before merging — the same guarantee level
> already accepted for upstream filings, and far stronger than relying on recall.

**Until that gate exists, `[STOP-B]` and §2's halt conditions stand as written.**

## 4. Merge and gate discipline

- **Auto-merge to `main` IS authorised** when green (pytest + spec-kitty gates) **and** both Codex
  checkpoints are clean.
- **Never merge red.** One branch per mission, off green `main`. Scoped `git add`.
- **Both Codex checkpoints run** (post-plan, post-merge), with **Opus `reviewer-renata` as the
  automatic fallback** when Codex rate-limits. The review discipline is never dropped for lack of
  Codex hours.
- Suite floor is the last known-green count; never merge below it. Run
  `.venv/bin/python -m pytest` — the bare console script fails at plugin import.

## 5. The quality bar

**Resilient, accurate, maintainable, extensible, secure, adherent to best programming practice. No
shortcuts. The foundation must be solid — the system is heading toward production use.**

This is the tie-breaker when a **design** question arises mid-run: prefer the explicit, tested, more
durable option over the cheaper one, and record why. **Kent would rather the run go slower than land
a shortcut.** (See **D-1** — the fork rule points the same way once "minimal" is dropped.)

**Report honestly.** A partial pass reported as complete is a defect. If something could not be
proven, say what was not proven.

## 6. Non-negotiables — never overridden by any risk posture

1. **Product bugs are findings, never fixes.** Fix only the repo you were sent to work in; never
   edit the product-under-test's code (see §8 for which repo that is).
2. Never merge red. Never force-push. Never leave a dirty tree or half-merged mission on stop.
3. Scoped `git add`, never `-A`. No secrets in files, logs, or session output.
4. Tier-0 host changes are off-limits autonomously.
5. **Outward copy needs Kent's sign-off** — anything to a public tracker, Slack, or a colleague.
   Draft it, keep going, and it waits for morning. The copy-gate exception, where one exists, covers
   only our own private repo (§8).
6. Never `--delete-branch` a lower PR of a stack (this auto-closed #88 once).
7. In a spec-kitty-managed repo, `.kittify/` and `kitty-specs/` flow through workflow commands.

## 7. Overload survival — be resumable, not overload-proof

Server overload cannot be prevented, so make a halt cheap.

- **Value order, not dependency order** — a run that dies at 30% should have delivered the best 30%.
- **One unit = one branch = one PR.** Checkpoint after every unit: commit → push → PR → update the
  run's progress log. A halt then costs at most one unit.
- **Cap concurrency.** Each concurrent subagent multiplies the request rate into the overload; two
  is a sane ceiling.
- **On 429/529: wait and retry twice** before treating it as a blocker.
- Hold `caffeinate -i -w $$` for the block. It does **not** prevent lid-close sleep.
- Keep the **resume-anchor memory current as the run progresses**, so a compaction or restart picks
  up cleanly.

## 8. Per-repo parameters — the ONLY part that varies

Fill this in per repo; do not re-derive §1–§7.

| Parameter | `spec-kitty-qa` (reference instance) |
|---|---|
| **Detour latitude granted?** | Yes — and the repo is named in the fault protocol's scope line. |
| **Product-under-test (never edit)** | `spec-kitty-saas`. Bugs there are **findings**. |
| **Copy-gate exception** | Issues/PRs/comments that stay inside a repository we own need no pre-review. Anything to an **upstream** repository does — and upstream now means *anything not in `OURS`*, so `Priivacy-ai/*`, `spec-kitty/EXPERIMENTAL-*` and any name they are renamed to are all covered without editing a list. The ownership set is `OURS` in `scripts/hooks/_hook_lib.py`. |
| **Suite command + floor** | `.venv/bin/python -m pytest` (the bare console script fails at plugin import). Floor = last known-green count, currently **2230 passed, 6 skipped**. |
| **Gate** | GitHub Actions `pytest` on every PR. |
| **Workaround register** | `docs/spec-kitty-issues.md` — **read at mission start.** |
| **Drafts staging** | `docs/drafts/` — delete on posting. |
| **Auto-merge to main** | Authorised when green **and** both Codex checkpoints clean. |
| **Vehicle default** | **Full spec-kitty mission** for code where scope justifies it (**D-2**). |

For a new repo, copy the row set and answer each line **before** the run starts. An unanswered row
is an operator decision, and per §1b that means the item does not start — it gets surfaced.

## 9. Layering — what fires, what carries, what explains

Adapted from Lynn's multi-mission pattern (Claude Desktop, coordinator + owned missions). Her method
targets **parallelism and coordination**; this section takes the parts that also serve **reliability**.

| Layer | Role | Reliability |
|---|---|---|
| **Hook** (`PreToolUse` / `PostToolUse` / `PostToolUseFailure`) | **Fires.** The only mechanism that runs without anyone deciding to run it. | Proven here — `scripts/hooks/upstream_filing_guard.py` denied a filing until dedup + attribution had actually run. |
| **spec-kitty's own gates** | Fire at lane transitions (issue-matrix verdicts, acceptance matrix, path conventions). | Proven — repeatedly blocked a merge until each was satisfied. |
| **Mission brief** ([`../templates/mission-brief-template.md`](../templates/mission-brief-template.md)) | **Carries.** A payload that travels with the work, so obligations arrive *with* the assignment. | Better than a skill for the "what": the executing agent does not have to decide to load anything. |
| **This runbook** | **Explains.** The detail and the reasoning, too long to inject. | Inert on its own — a document only helps someone who opens it. |
| **Coordinator** | **Holds the map** — the plan, the progress log, and what is owed at terminus. | Survives an executing agent's compaction; the obligation does not evaporate with its context. |

⚠ **Documents, skills and agents do not fire.** They need something to invoke them, which is the
same unreliability being fixed. **Hooks and gates are the enforcement floor; everything else is
payload.** An agent is the wrong shape for enforcement — it runs *beside* the orchestrator and
cannot compel it.

**The mission lifecycle already provides the trigger points:**

| Timing | Trigger | Hook |
|---|---|---|
| **Before** — §0 sweep, §8 params | mission `create` / `specify` | `PreToolUse`: deny unless the sweep is marked |
| **During** — only on a fault | a `spec-kitty` command exits non-zero | `PostToolUseFailure`: inject the §D-3 capture SOP while the evidence is still alive. **Not `PostToolUse`** — that event fires only after a tool *succeeds*, so a non-zero exit never reaches it and this checkpoint would never fire at all |
| **After** — batch dedupe/format, register + memory updates | `spec-kitty merge` | **No hook. Not built.** The merge checkpoint was specified and then cut from the mission that built the other two, so nothing reads the fault ledger at merge time. The §D-3 obligation stands; the trigger for it does not exist yet |

⚠ **The during-checkpoint is not a gate, and reading three rows as three gates would be
wrong.** `PostToolUseFailure` fires *after* the tool has already run, so it has no power to
refuse anything — the only response it may return is `additionalContext`. It is
record-plus-notify: it puts the §D-3 capture SOP in front of you while the evidence is
still alive. What would have *enforced* §D-3 is the merge checkpoint in the row above, and
that row is empty. Until it exists, §D-3 compliance rests on the operator reading the
injected SOP and acting on it.

⚠ **Open caveats, both checkable:**

1. **The wiring travels now, but a fresh clone is wired rather than enforcing.** The two
   mission-lifecycle entries above live in this repository's `.claude/settings.json`, tracked
   with `git add -f` (`.claude/` sits in a spec-kitty auto-managed ignore block, and a `!`
   negation is inert because git cannot re-include a file under an excluded directory). So the
   wiring arrives with the clone — **and it does not run yet**. Project hooks require each
   person cloning the repository to accept the **workspace-trust dialog** first; until they do,
   the CLI logs `Skipping <event> hook execution - workspace trust not accepted` and the gate
   sits idle. **First-run step, per machine and per clone: open an interactive session in the
   repository and accept workspace trust.** A `-p` run does not count as acceptance.
   Two further limits worth knowing:
   - `scripts/hooks/upstream_filing_guard.py` is still wired **only** in
     `~/.claude-work/settings.json`, so that guard remains operator-local and does not travel.
   - Hook entries **merge** across settings levels, so the in-repo entries compose with an
     operator's own rather than replacing them. On a machine that also wires the gate locally,
     the hook can therefore fire twice. That is harmless for a deny-gate — denials are
     idempotent — but it is **unverified**, not measured.

   To see the current state on any machine rather than assuming it:

   ```bash
   python3 scripts/hooks/check_wiring.py            # add --include-user to read ~/.claude too
   ```

   That report reads settings files. There is no documented runtime way to list the hooks a
   live session has active, so it tells you what references a script — never that a hook fired.
2. **Whether hooks fire in Claude Desktop cowork is unverified.** Adopting that pattern wholesale
   could trade the only proven enforcement for coordination. Verify before migrating.

**Cross-session coordination — FULL ROUND TRIP PROVEN 2026-08-25.** Lynn's premise is that separate
CLI sessions "don't interact reliably enough". **Messaging is not the weak link** — the complete
coordinator round trip works, so her pattern is available **without leaving the environment where
our hooks fire**. What *is* unreliable is discovery, and three signals along the way mean less than
they appear to. Measured with a second CLI session on the same machine.

**What works — the whole loop:**

1. Coordinator sends; the peer receives the body **verbatim**, wrapped with `from=`,
   `from-name=` and `from-mode=` attributes.
2. The peer replies by copying the `from=` value into its own `to` — the documented path.
3. The reply lands back in the coordinator's session. Confirmed from **both** ends.

Same-machine transport is a unix domain socket, one per session: `/tmp/cc-socks/<pid>.sock`.
Parent→subagent messaging was already proven separately.

⚠ **Four caveats. The first is the one that will bite.**

1. ⚑ **`ListAgents` discovery is unreliable, and asymmetric.** A headless `claude -p` peer reported
   **"No reachable agents"** — it could not enumerate the coordinator that had just messaged it. And
   the coordinator could not see *that* peer either, despite a live process and a live socket (an
   earlier peer had been visible within a second). **Do not build on the roster.**
   **The workaround, which worked:** address the socket directly. `ls /tmp/cc-socks/` shows one
   `<pid>.sock` per live session; passing `uds:/tmp/cc-socks/<pid>.sock` as `to` delivered
   successfully when the peer was absent from the roster entirely.
2. ⚑ **Delivery is not prompt — never assume it lands at the next tool round.** The peer reported
   that **nine** consecutive inter-call drain points passed with an empty queue; the message
   surfaced only after its tenth tool call. A coordinator that sends and then checks once has
   measured nothing.
3. ⚑ **`SendMessage` returned `success: true` for a peer `ListAgents` reported as `offline`**, with
   no indication whether the message was queued or dropped. The send result attests that **the call
   was accepted, not that anything was delivered.** This is our own *success-reported-over-a-gap*
   class inside the coordination layer. **The only sound delivery signal is an explicit reply from
   the peer** — which is why the round trip above, not the send result, is what was measured.
4. **`SendMessage` is a deferred tool in a spawned session.** The peer had to call `ToolSearch`
   before it could reply. Budget a tool round for it, and grant `ListAgents,SendMessage` in
   `--allowedTools`.

⚠ **Untested: cross-machine.** Only same-machine `uds:` was exercised; a Remote Control peer is a
different transport and the `offline` behaviour in caveat 3 was observed on exactly that path.

**Reproducing this:** `/tmp/peer-reply-test.sh` in the session scratchpad notes; the harness
**blocks standalone `sleep`**, so keep a peer alive with repeated real commands (`ping -c 5`)
rather than sleeping, and note that launching a peer with `SendMessage` in `--allowedTools` is
**denied by the auto-mode classifier** — the operator must run it.

## Cross-references

- Tooling faults: [`spec-kitty-workflow-fault-protocol.md`](spec-kitty-workflow-fault-protocol.md)
- Workaround register — **read at mission start**: [`../spec-kitty-issues.md`](../spec-kitty-issues.md)
- Filing mechanics: [`spec-kitty-bug-reporting.md`](spec-kitty-bug-reporting.md)
- Upstream source of the autonomy contract: `kg-automation`, `.agents/autopilot/` — the
  repo-agnostic operating contract these rules were adapted from. **This runbook is the operative
  source for spec-kitty repos**; consult that one only when changing the doctrine itself.
- The proven step-by-step mission motion ("THE MISSION PLAYBOOK", steps 1–16) still lives in project
  memory at `overnight-run-2026-08-02-operator-smoothing` — **a candidate for promotion here next.**
