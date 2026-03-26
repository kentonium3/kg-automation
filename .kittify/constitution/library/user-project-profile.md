# User Project Profile

- Mission: `software-dev`
- Interview profile: `comprehensive`

## Interview Answers

- **Project Intent**: Drive accountable action on personal and business goals through always-on automation, frictionless        capture, and proactive follow-up.
- **Languages Frameworks**: Python 3.11+, Bash, Docker, YAML/Markdown docs. Vikunja REST API, Anthropic Claude API, OpenClaw skills.   Obsidian for knowledge store.
- **Testing Requirements**: Validate all docs via validate_docs.py (frontmatter + secret scan) in CI. Python scripts must be tested   manually before merge. Add pytest coverage for any non-trivial Python modules as they emerge. No fixed       coverage target yet.
- **Quality Gates**: CI validation passes (validate_docs.py: frontmatter compliance + secret scan). PR required for all        changes to main. Self-review of diff before merge.
- **Review Policy**: Solo maintainer project. Self-review via PR diff before merge. Use Claude Code or Claude Desktop as       architectural review partner when changes touch the v0.3 spec or cross-cutting concerns.
- **Performance Targets**: Inbox processing completes within 60 seconds of trigger. WhatsApp command responses within 10 seconds.    CI validation under 30 seconds. Heartbeat schedules fire on time.
- **Deployment Constraints**: Production services run on office2 (Ubuntu 24.04 LTS). Mac is authoring only. All scripts and configs     target Linux unless explicitly noted. Services accessible via Tailscale only — never exposed to public     internet.
- **Documentation Policy**: All markdown files require YAML frontmatter (title, doc_type, status). Architecture decisions live in     docs/design/. Feature specs in docs/func-spec/ before implementation. Conventional commits (feat:, fix:,   docs:, chore:, ci:). Update docs when behavior changes.
- **Risk Boundaries**: 02-Growth/_private/ is never read, written, or referenced by any agent or script — no exceptions. No      credentials in code or committed files. Anthropic API called direct — no third-party proxies. No community   OpenClaw skills without source review. All services Tailscale-only. No untrusted code executes near          credentials or personal data.
- **Amendment Process**: Edit constitution.md directly, run spec-kitty constitution sync, commit via PR. Review diff to confirm    derived files reflect intent before merge.
- **Exception Policy**: Exceptions documented in PR description with rationale, scope, and expiration. No permanent exceptions    to privacy or security boundaries.

## Selected Doctrine

- Paradigms: docs-first, spec-driven
- Directives: DOCS_FIRST, SPEC_BEFORE_CODE
- Tools: git, python, pip, bash, docker, docker-compose, ssh, systemctl, spec-kitty, validate_docs.py, gh, curl, tailscale

