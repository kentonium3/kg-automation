# Decision Moment `01M65DEYQGJ955RRYWFD7WMBZ9`

- **Mission:** `vikunja-image-deploy-01M65D3V`
- **Origin flow:** `plan`
- **Slot key:** `plan.architecture.image-selection`
- **Input key:** `image_selection_mechanism`
- **Status:** `resolved`
- **Created:** `2026-10-30T03:25:39.952961+00:00`
- **Resolved:** `2026-10-30T03:27:16.511698+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How should the Compose file select the image so that a merge can never start the new image before the DB snapshot: a direct image-line change merged as the cutover, or an indirection tag whose target only the ACTIVATE entrypoint moves after the snapshot?

## Options

- Direct image line, merged as the cutover
- Local indirection tag moved by the entrypoint
- Other

## Final answer

Local indirection tag moved by the entrypoint

## Rationale

_(none)_

## Change log

- `2026-10-30T03:25:39.952961+00:00` — opened
- `2026-10-30T03:27:16.511698+00:00` — resolved (final_answer="Local indirection tag moved by the entrypoint")
