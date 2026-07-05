# Quickstart: Cross-Repo Standing Rules Sweep

## 1. Confirm Mission Checkout

```bash
git status --short --branch
```

Expected branch: `feat/cross-repo-standing-rules-sweep`.

## 2. Review Canonical Rule File

```bash
sed -n '1,220p' .agents/rules/cross-repo-standing-rules.md
```

## 3. Sweep Candidate Sources

```bash
rg -n "public post|copy approval|@mentions|dual-track|upstream|standing rules|universal|never .*CLAUDE|private|community skill|approval" CLAUDE.md CODEX.md AGENTS.md .agents docs scripts/openclaw/agents -g '*.md'
```

Use bounded reads for each candidate finding.

## 4. Apply Edits

Edit `.agents/rules/cross-repo-standing-rules.md` only for:

- universal short rules
- stale wording that conflicts with linked protocols
- links that need to point at canonical runbooks/templates

Do not edit global `~/.claude/CLAUDE.md`.

## 5. Validate

```bash
python tooling/scripts/validate_docs.py
rg -n "paste file|paste-buffer|generate.*external" .agents/rules/cross-repo-standing-rules.md
rg -n "Public-post copy approval|Local tracking tickets|issue reporting" .agents/rules/cross-repo-standing-rules.md
```

The stale paste-file check should produce no misleading live instruction. The
protection-heading check should find the three existing protection areas.
