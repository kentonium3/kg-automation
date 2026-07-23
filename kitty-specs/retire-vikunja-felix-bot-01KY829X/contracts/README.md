# Contracts — none for this mission

This is a **behavior-preserving refactor** (Phase 1 of #860): it migrates existing runtime
Felix→Vikunja consumers onto the shared `VikunjaClient` with **no change to identity, token, base
URL, or observable Vikunja effects**. It introduces no new API surface, no new service endpoint, and
(per FR-004 / §11 discipline) **no abstract `TaskService` port/adapter**.

The relevant "contract" is `VikunjaClient`'s existing method + error model (`scripts/common/vikunja_client.py`),
extended in WP01 with `patch()`, `replace_task_fields`, `update_task_fields`, `get_task`,
`create_task_in_project`, `create_comment`, `list_task_comments` — each covered by unit tests in
`tests/common/test_vikunja_client.py`. There are therefore no separate contract artifacts to record here.
