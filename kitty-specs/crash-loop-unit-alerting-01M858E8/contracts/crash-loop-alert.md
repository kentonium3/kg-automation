# Contract: crash-loop alerts, cleared entries, scope health and ledger lines

> **Ruling, Kent, 2026-11-24 (in-mission, after the post-merge Codex review round 4): count ticks, not time.** This supersedes every wall-clock interval rule in this file: the proven-crossing (pigeonhole) rule, the observation-time bracket, clock-regression handling, and history compaction. Earlier text is kept as history.
> - **Page rule.** For each watched unit or container, page when its persistent restart counter has **risen by ≥3 since the previous canary tick** (ticks are 15 min apart), **or has risen (by ≥1) on 2 consecutive ticks**.
> - **What stays.** A counter decrease, or a boot-ID or container-ID change, sets a new baseline with no alert. First sight sets a baseline. "Could not check" never reads as healthy. One alert per episode. A re-remind on the canary's 6-hour cadence, driven by fresh evidence (WP02 ruling). Cleared after K=2 quiet ticks. The ignore list. A cap of 3 alerts per tick, plus one aggregate.
> - **Timestamps** may appear in alert text and the ledger as information only. They are never an input to the decision.
> - **Expected outcomes.** The 2026-11-23 loop pages on the next tick. A steady loop of 2 restarts per tick pages on its 2nd tick. A single restart never pages.


All emission goes through `scripts.common.alert_bus.emit` (C-003), which sends an ntfy notification and appends to the alert-bus ledger. In `run_pass` it goes through the injected `emit_fn`. Every emission, cleared included, is accounted for like `_route`: `getattr(result, "ok", True) is False` increments `alerts_undelivered`, which feeds the off-host dead-man.

## 1. Crash-loop alert (episode start), FR-006

```python
Alert(
    source="felix-canary:crash-loop:<scope>:<name>",       # e.g. felix-canary:crash-loop:system:obsidian-sync.service
    severity=Severity.ERROR,
    title="<name> crash-looping: <delta> restarts in <period>",   # period human-rendered, e.g. "16 min"
    description="<scope> unit <name> restarted <delta> times between <baseline_at> and <observed_at> "
                "(restart count <baseline_count> -> <current_count>), which proves at least <threshold> "
                "restarts within <window>. Current state: <state>.",
    action=None,                                          # detection only (C-005)
    details={"component_id": "crash-loop:<scope>:<name>", "kind": "alert", "scope": ..., "unit": ...,
             "delta": "<int>", "period_seconds": "<int>", "baseline_count": "<int>", "current_count": "<int>",
             "m": "<int>", "bound": "<int>",
             "state": ..., "episode_started_utc": ...},
)
```

`details` values are strings, following the bus's convention.

## 2. Re-remind, FR-007

The same shape as the alert, with `details.kind = "reremind"`. The title is prefixed `still `, and the description names `episode_started_utc`. A re-remind is due only when `last_alert_utc` (the last attempt) is at least `dedup.DEFAULT_WINDOW` (6 h) old **and** a proven crossing holds on that tick.

There is no retry on failed delivery. This is the existing canary policy (research R-08): the failure is counted in `alerts_undelivered`, so the dead-man pings `fail`.

## 3. Cleared, FR-008

```python
Alert(source="felix-canary:crash-loop:<scope>:<name>", severity=Severity.INFO,
      title="<name> crash loop cleared",
      description="<scope> unit <name> has not restarted for <K> consecutive canary ticks; the episode that "
                  "began <episode_started_utc> has ended. Current state: <state>.",
      action=None, details={..., "kind": "cleared"})
```

A failed delivery is counted and not retried (the same as every other emission).

## 4. Aggregate alert (per-tick cap), research R-15

When a tick has more than `max_alerts_per_tick` events (default 3), the first `max_alerts_per_tick` are sent individually, ordered alert, then reremind, then cleared, then by key. **All** remaining events fold into one alert, so a tick makes at most 4 bus calls:

```python
Alert(source="felix-canary:crash-loop:aggregate", severity=ERROR if any alert/reremind else INFO,
      title="<n> more crash-loop events this tick",
      description="<key> <kind> +<delta>/<period> <state>; ...",   # entries appended while total <= 900 chars,
                                                                 # then "... and <k> more - see canary ledger <date>"
      action=None, details={"kind": "aggregate", "count": "<n>", "units_listed": "<shown>"})
```

The 900-character budget sits under the bus's `DESCRIPTION_MAX` (1000), so the bus never truncates the aggregate silently. Every folded event still gets its own canary-ledger line. The aggregate's delivery result is recorded on each of those lines.

## 5. Scope health (could-not-check), FR-011

Scope health is routed through the existing `_route` and dedup path as components `crash-loop:system`, `crash-loop:user` and `crash-loop:container`:

- complete read → outcome `healthy`, evidence `<n> watched, <i> ignored, <x> excluded, <ms> ms`
- incomplete read, deadline overrun or config invalid → outcome `unknown`, evidence `could not check: <reason>`

The rendering is the canary's existing one: `"<component_id> health: unknown"` (WARN, F5 persistence rule) and `"recovered"` (INFO) on the transition back.

## 6. Canary ledger lines (`/data/services/felix-canary/ledger/<date>.jsonl`)

- One line per scope per tick, from `_route`, in the existing record shape.
- One line per crash-loop event: the existing keys (`component_id = "crash-loop:<scope>:<name>"`, `outcome`, `evidence`, `emitted`, `suppressed_dedup`, `evaluated_at`) **plus** `delivered` (bool) and an `interval` object `{baseline_count, baseline_at, current_count, observed_at, delta, period_seconds, m, bound}`. `outcome` is one of `crash-loop`, `crash-loop-reremind`, `crash-loop-cleared`.
- One line per unverified rise: `outcome = "crash-loop-unverified"`, `emitted = false`, `delivered = false`, plus the `interval` object (research R-05).
- No per-unit line on a tick without an event. The history is kept in `crash-loop.json`.
- Nothing is written in `dry_run`.

## 7. Pass summary (returned by `run_pass`; NOT persisted to `last-tick.json`)

```text
summary["crash_loop"] = {"enabled": bool, "watched": int, "ignored": int, "events": int, "unverified": int,
                         "scopes": {scope: outcome}, "elapsed_ms": int}
```

When the stage runs, crash-loop emissions add to `emitted` and `alerts_undelivered`, and scope components add to `components_evaluated`. A stage fault or a held lock appends `crash_loop:<reason>` to `errors`.

`last-tick.json` keeps exactly its current key set: the persisted signal still excludes `component_lines` and `alerts_undelivered`, and now also `crash_loop`.

## Amendment 2026-11-24: shapes under Kent's tick-counting ruling (shipped in 5582a3105). These supersede §1, §2, §6 and §7 where they differ.

- **§1 alert.** The text states the rise since the previous canary tick, for example "restarted 39 times since the previous canary tick (16 min ago)", or a consecutive-rise run such as "(+2, +2)". The minutes are information only. `details` carries `delta`, `previous_count`, `current_count` and `rose_last_tick`. There are no `m`, `bound` or `period_seconds` fields.
- **§2 re-remind.** A re-remind is due when the trigger holds on a tick at least `reremind_ticks` (24) ticks after the last page. No time comparison is involved.
- **§4 aggregate entry.** `<key> <kind> +Δ <state>`, still bounded to 900 characters.
- **§6 ledger.** `interval` is `{previous_count, current_count, delta, rose_last_tick, previous_seen_at, observed_at}`. The timestamps are informational. The `crash-loop-unverified` outcome is retired: a rise below the rule writes no event line, and the unit's state records it.
- **§7 summary.** `unverified` is removed.
