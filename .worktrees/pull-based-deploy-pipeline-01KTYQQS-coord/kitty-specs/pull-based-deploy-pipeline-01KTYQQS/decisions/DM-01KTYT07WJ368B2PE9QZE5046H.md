# Decision Moment `01KTYT07WJ368B2PE9QZE5046H`

- **Mission:** `pull-based-deploy-pipeline-01KTYQQS`
- **Origin flow:** `plan`
- **Slot key:** `plan.concurrency.locking_model`
- **Input key:** `concurrency_locking_model`
- **Status:** `resolved`
- **Created:** `2026-06-12T20:57:28.210549+00:00`
- **Resolved:** `2026-06-12T20:59:49.020607+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How should the applier prevent overlapping ticks if a deploy takes longer than the poll interval?

## Options

- systemd_type_oneshot_natural
- explicit_lock_file_fcntl
- git_branch_serialization
- Other

## Final answer

systemd_type_oneshot_natural

## Rationale

_(none)_

## Change log

- `2026-06-12T20:57:28.210549+00:00` — opened
- `2026-06-12T20:59:49.020607+00:00` — resolved (final_answer="systemd_type_oneshot_natural")
