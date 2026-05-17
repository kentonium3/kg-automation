---
affected_files: []
cycle_number: 1
mission_slug: felix-bot-vikunja-provisioning-01KRT3N4
reproduction_command:
reviewed_at: '2026-05-17T05:32:38Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1**: The comment-write attribution checkpoint does not enforce `created_by.username == "felix-bot"`.

`validate_attribution()` currently uses `_extract_username(comment_obj, "author", "created_by")` for the write response, so a response with `author.username == "felix-bot"` and `created_by.username == "kent"` is accepted. The explicit WP02 review gate requires `created_by.username == "felix-bot"` at all three distinct checkpoints: task creation, comment write, and comment readback. The readback path also falls back to `author`, which can mask the same class of failure.

Fix: make the comment-write checkpoint read and validate only `comment_obj["created_by"]["username"]`, make the readback checkpoint validate only `found["created_by"]["username"]`, update the summary field names/log messages to reflect `created_by`, and add regression tests where `author.username` is `felix-bot` but `created_by.username` is missing or wrong for both comment write and readback. Those tests should exit 1.
