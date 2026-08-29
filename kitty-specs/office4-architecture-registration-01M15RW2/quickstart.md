# Quickstart: verifying this mission landed correctly

**Phase**: 1 | **Date**: 2026-08-29

Run from the repository root with the venv active (direnv does this on `cd` once
kg-automation#923's setup is in place; otherwise prefix with `direnv exec .`).

## 1. Both validators pass

```bash
python3 tooling/scripts/validate_architecture_data.py --strict
```

```bash
python3 tooling/scripts/validate_docs.py
```

Expect `validate_architecture_data: OK (0 findings)` and `validate_docs: OK`, each
exiting 0. These are the same checks the pre-commit gate and Docs CI run.

## 2. Four devices, four hosts, one rich entry

```bash
python3 -c "
import json
t = json.load(open('docs/design/architecture/data/network-topology.json'))
h = json.load(open('docs/design/architecture/data/hardware-inventory.json'))
dev = {d['hostname']: d for d in t['network']['devices']}
hosts = {x['hostname']: x for x in h['hosts']}
print('devices:', sorted(dev))
print('hosts:  ', sorted(hosts))
assert 'office4' in dev and 'office4' in hosts
assert len(dev) == 4 and len(hosts) == 4
rich = [n for n, x in hosts.items() if 'disks' in x or 'bios' in x]
assert rich == ['office2'], rich
assert set(hosts) >= set(dev)
print('OK: 4 devices, 4 hosts, only office2 rich, hostnames agree')
"
```

## 3. office4 runs no service (contract of omission)

```bash
python3 -c "
import json
d = json.load(open('docs/design/architecture/data/service-inventory.json'))
hosts = {s.get('host') for s in d['services']}
assert hosts == {'office2'}, hosts
print('OK: all', len(d['services']), 'services on office2 only')
"
```

## 4. The recorded IP matches the live host

Run **on office4**:

```bash
tailscale ip -4
```

Must equal the `tailscale_ip` recorded in both JSON files (`100.112.83.28` at authoring).

## 5. ADR 0008 exists and is registered

```bash
ls docs/design/architecture/adr/0008-*.md
```

```bash
grep -l "0008" docs/INDEX.md docs/DEVELOPER_PORTAL.md docs/design/architecture/README.md
```

All three files must match — the ADR is reachable from the documentation map, the
developer portal, and the architecture README.

## 6. The ADR answers its five questions

Not mechanically checkable — this is the review step. Read
`docs/design/architecture/adr/0008-*.md` and confirm a reader can answer, without
leaving the document:

1. Which of the three machines is managed?
2. Where does a given workload belong? (apply the test to a data-loss case and an
   annoyance case — both must resolve)
3. Why is office4 not a managed host? (five citations, each resolving to real content)
4. What must office4 never hold, and why?
5. Why no `claude`/`codex` Unix users on office4?

## 7. The merge commit records the rebaseline decision

```bash
git log -1 --format=%B | grep -i "^Rebaseline:"
```

Must read `Rebaseline: not required — documentation and architecture metadata only`
(research.md R-5 confirms architecture-data JSON is not an audited surface).

## 8. Issue #909 is corrected

`gh issue view 909 --repo kentonium3/kg-automation --comments` must show the comment
correcting the `hardware-inventory.json` premise, so the next reader is not misled by the
original success criterion.
