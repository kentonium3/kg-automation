VERDICT: APPROVE — Codex read-only review (gpt-6-astra), WP08 cycle 5 on lane-h @089f3f2d, 2026-09-26; design-lead delta read APPROVE (bus 20260926T001046518503Zf8dbf4b55a).

Codex: no findings; 226 tests passed; 68 further adversarial CLI probes produced the ruled outcomes with no uncaught exception; the real substrate gate rejected a chat-template mismatch; absent or unusable template fields recorded `could_not_check`.

Cycle record: c1 REJECT (3 MAJOR, 2 MINOR) → c2 REJECT (1 MAJOR, 2 MINOR) → c3 REJECT (2 MAJOR) → c4 REJECT (2 MAJOR; re-run after a Codex service outage 22:46Z–23:5xZ on both machines, fixed on office4 by `codex logout` + `codex login --device-auth`) → c5 APPROVE. Design-lead findings folded along the way: W8-1 (refusal by identity, plus its string half), W8-2, the two riders on gate records and the strict `>` ceiling, the chat-template authority (cached tokenizer; the pre-c4 comparison could never fail), and the /props cross-check.
Deferred by ruling to post-merge items (rubric §10): C4, C8, C9 (with W8-3), C11. A single design-lead rider (skipped GGUF verification only on SKIP_GATES_SHA ledgers) follows as cycle 6.
