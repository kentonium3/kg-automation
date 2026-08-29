---
affected_files: []
cycle_number: 5
mission_slug: office4-architecture-registration-01M15RW2
reproduction_command:
reviewed_at: '2026-08-29T05:24:40Z'
reviewer_agent: user
wp_id: WP02
---

# WP02 Review Feedback — cycle 4

**Verdict**: REQUEST-CHANGES

Q4 is now answerable — the cycle-3 defect is genuinely closed. But the answer rests on a
false claim, which the ADR then contradicts three times downstream.

## MODERATE — "the path cannot exist there" is false, and it inverts the ADR's own argument

The new text says: *"**The two constraints are mutually reinforcing:** because office4 has no
`claude` user, the path felix-deployer resolves cannot exist there."*

**Directory existence is independent of the passwd database.** `mkdir -p /home/claude/...`
works with no `claude` account. Verified — **office4 is its own counterexample right now**:

```
$ ls -la /home/
drwxr-xr-x 3 root root 4096 ... linuxbrew
$ getent passwd linuxbrew   → exit 2 (no such user)
```

A `/home` directory named for a nonexistent user is the live state of the machine this ADR is
about.

The causal chain is absent in code too: `scripts/deploy/felix-deployer/` and
`scripts/deploy/lib/` contain **zero** occurrences of `import pwd`, `getpwnam`, `expanduser`,
`getent`, or `os.getlogin`. `DEFAULT_REPO_ROOT` is a bare `pathlib.Path` constant. User
identity is not merely insufficient to prevent the path — it is causally unrelated to it.

This is blocking because of what it does to the rest of the document:

1. **Contradicts the next paragraph**: *"Nothing enforces this mechanically… will not be
   stopped by a guard — only by having read this."*
2. **Contradicts Consequences**: *"Both constraints above are documentation, not guards. This
   ADR is the only thing standing between them and an accidental breach."*
3. **Makes its own third bite-clause vacuous**: *"…or otherwise arranges for office4 to
   present a checkout at the path the deployer resolves."*

And the failure mode is the worst one available here. The ADR argues, correctly and
repeatedly, that it is the *only* barrier. A sentence telling the reader the breach is
impossible is exactly the belief that stops anyone checking.

**Note on provenance**: this reasoning originated in cycle 3's feedback — written by the
orchestrator — and was implemented faithfully. Fidelity to bad feedback does not rescue it.
The feedback was wrong and the artifact inherited it.

**Required fix**: keep the true, weaker form — nothing occupies that path *today*, that is
current state rather than a guard, and the no-`claude`-user constraint removes the *reason*
anyone would create it, not the *ability*.

## MINOR — the second `_tick.py` citation drops the qualifier R-3 mandates

Citation 3 correctly says `DEFAULT_REPO_ROOT` **defaults to** office2's path, because line 404
makes it overridable. The new paragraph presents it as a fixed value. Since that paragraph is
*defining* "recognisable", the precise form matters: **the path the deployer's `repo_root`
resolves to — by default `/home/claude/kg-automation`**. Stating it that way also makes the
"relocates the deployer's repo root" bite-clause self-explanatory instead of orphaned.

## NIT — one sentence editorialises about the ADR's own drafting

*"Stating the safe case matters as much as the unsafe one: a constraint a reader can only
satisfy by accident is not a constraint."* That is review rhetoric lifted verbatim into the
artifact — it justifies the drafting rather than recording the decision. Belongs in the commit
message.

## Clean

No prose damage across five cycles of edits; wrapping 91-92 cols; both gates green; heading
hierarchy intact; links resolve; frontmatter agrees with the `**Date**` line; Q1/Q2/Q3/Q5
still answerable. Whole read still coheres — the only seam is the finding above.
