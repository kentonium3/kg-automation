# Contract: crash-loop alerts, cleared entries, scope health and ledger lines

All emission goes through `scripts.common.alert_bus.emit` (C-003), which sends an ntfy notification and appends to the alert-bus ledger. In `run_pass` that is the injected `emit_fn`.

## 1. Crash-loop alert (episode start) — FR-006

```python
Alert(
    source="felix-canary:crash-loop:<scope>:<name>",       # e.g. felix-canary:crash-loop:system:obsidian-sync.service
    severity=Severity.ERROR,
    title="<name> crash-looping: <delta> restarts in <period>",   # period human-rendered, e.g. "16 min"
    description="<scope> unit <name> restarted <delta> times between <baseline_utc> and <now_utc> "
                "(restart count <restart_count>; threshold <threshold> in <window>). Current state: <state>.",
    action=None,                                          # detection only (C-005)
    details={"component_id": "crash-loop:<scope>:<name>", "kind": "alert", "scope": ..., "unit": ...,
             "delta": "<int>", "period_seconds": "<int>", "restart_count": "<int>", "state": ...,
             "episode_started_utc": ...},
)
```

When the period is longer than `2 × window_seconds`, the description adds: `(longer than the <window> window: canary ticks were missed, so the restarts may be spread over the whole period)`. See research R-05.

## 2. Re-remind — FR-007

The same shape as the alert, with `details.kind = "reremind"`. The title is prefixed `still `, and the description names `episode_started_utc`. It is emitted at most once per `dedup.DEFAULT_WINDOW` (6 h), and only on a tick that is over the threshold.

## 3. Cleared — FR-008

```python
Alert(source="felix-canary:crash-loop:<scope>:<name>", severity=Severity.INFO,
      title="<name> crash loop cleared",
      description="<scope> unit <name> has not restarted for <K> consecutive canary ticks; the episode that began <episode_started_utc> has ended. Current state: <state>.",
      action=None, details={..., "kind": "cleared"})
```

## 4. Scope health (could-not-check) — FR-011

Routed through the existing `_route` and dedup path as components `crash-loop:system`, `crash-loop:user` and `crash-loop:container`:

- read OK → outcome `healthy`, evidence `<n> watched (<m> ignored)`
- read failed or config invalid → outcome `unknown`, evidence `could not check: <error>`

The rendering is the existing canary rendering: `"<component_id> health: unknown"` (WARN), and `"recovered"` (INFO) on the transition back.

## 5. Canary ledger lines (`/data/services/felix-canary/ledger/<date>.jsonl`)

- One line per scope per tick (from `_route`, the existing record shape).
- One line per crash-loop event, in the existing record shape: `component_id = "crash-loop:<scope>:<name>"`, `outcome ∈ {"crash-loop", "crash-loop-reremind", "crash-loop-cleared"}`, `emitted = true`, and the evidence string as the description.
- No per-unit line on ticks without an event. The history is in `crash-loop.json`.

## 6. Pass summary (returned by `run_pass`; NOT persisted to `last-tick.json`)

`summary["crash_loop"] = {"enabled": bool, "watched": int, "ignored": int, "events": int, "scopes": {scope: outcome}}`. When it runs, the stage adds its emitted events to `emitted` and its scope components to `components_evaluated`. A stage fault appends `crash_loop:<Exc>:<msg>` to `errors`.

`last-tick.json` keeps exactly its current key set.
