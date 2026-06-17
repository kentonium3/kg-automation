# Contracts: Felix exec host=gateway directive

This mission exposes **no APIs, endpoints, webhooks, or service contracts**, so
there are no machine-readable contract files here.

The single behavioral contract is a **prompt directive** governing the agent's
tool-call choice:

> **Contract (per Felix sub-agent):** For every OpenClaw `exec` tool call, the
> agent uses `host=gateway`. The agent never uses `host=node` (no node host is
> paired on office2, so `host=node` always errors).

Conformance is verified two ways:

1. **Static** — each of the four `AGENTS.md` files contains the directive with
   identical wording (grep check; see quickstart.md).
2. **Behavioral / observational** — over a 7-day post-deploy window, the OpenClaw
   gateway journal contains zero `exec host=node requires a paired node` errors
   (see quickstart.md).
