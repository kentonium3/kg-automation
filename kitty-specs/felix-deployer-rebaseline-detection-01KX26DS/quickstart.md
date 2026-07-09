# Quickstart: Verifying Robust Felix-Deployer Rebaseline Detection

This mission is **pure applier code + manifest schema**; it deploys by merging to `main`
(office2's felix-deployer self-pulls). Verification is therefore test-driven, with a
passive live confirmation on the next natural deploy.

## 1. Run the test suites (primary verification)

```bash
cd /Users/kentgale/repos/kg-automation
python -m pytest tests/deploy/test_rebaseline.py tests/deploy/test_tick_rebaseline.py -v
python -m pytest tests/deploy/ -k manifest -v
python -m pytest tests/deploy/ --cov=scripts.deploy --cov-branch
```

Expected: all green, coverage gate met. Key cases (map to SC-001..005):

- **SC-001 / Scenario 1** — out-of-band repro: tick where `pre_pull_head == post_pull_head`
  but the watermark is older and the range contains a `scripts/office2/*.service` add ⇒
  a pending token is armed and reconcile reaches `completed`.
- **SC-002 / Scenario 2** — manifest declares `openclaw-cron.txt`; after apply, reconcile
  classifies the cron drift as `completed`, **not** `unexpected_drift`.
- **SC-004 / Scenario 3** — idle ticks including the deployer's own `deploy(applied)`
  commit ⇒ `observe` range empty ⇒ `not_required`; no spurious token.
- **FR-002/FR-004** — missing watermark → `pre_pull_head` fallback; unreachable SHA →
  no crash, watermark self-heals.
- **FR-007** — a manifest with `expected_baselines: ["bogus.txt"]` fails validation;
  `["openclaw-cron.txt"]` without `audited_surface: true` fails validation.

## 2. Static sanity checks

```bash
# Manifest schema round-trips and the CI reminder consumer still imports cleanly:
python -c "import json; json.load(open('deploys/schema/manifest-v1.schema.json'))"
python -m pytest tests/ -k audited_surface -v

# Known-baseline union is still 14 (validation source of truth):
python -c "
import json; d=json.load(open('docs/design/architecture/data/audited-surfaces.json'))
b=set()
[b.update(s.get('affected_baselines',[])) for s in d['audited_surfaces']]
[b.add(n['name']) for n in d['non_repo_baselines']]
assert len(b)==14, b; print('known baselines OK:', len(b))
"
```

## 3. Passive live confirmation (after merge to main)

No office2 action is required to deploy. After `fix/… → main` merges and office2's next
tick pulls it:

```bash
# Confirm the watermark file appears after a tick or two:
ssh office2-claude 'cat /data/services/felix-deployer/state/rebaseline-observed-head.json 2>/dev/null || echo "not yet written"'

# On the NEXT real audited-surface deploy, confirm the happy path:
#   - a pending token is armed even if the tick's own pull was a no-op
#   - reconcile reaches `completed`
#   - baselines mtime advances without any manual `rm baselines/* && audit.sh`
ssh office2-claude 'tail -40 /data/services/felix-deployer/logs/$(date +%Y-%m-%d).jsonl | grep rebaseline'
```

Success = the daily security audit reports "All clear" after such a deploy with **zero**
operator actions (SC-003).
