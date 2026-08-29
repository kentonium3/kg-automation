# Quickstart: verifying this mission landed correctly

**Phase**: 1 | **Date**: 2026-08-29

Run from the repository root with the venv active (direnv does this on `cd` once
kg-automation#923's setup is in place; otherwise prefix with `direnv exec .`).

## 1. Both validators pass

```bash
python3 tooling/scripts/validate_architecture_data.py --strict
```

`--strict` is not optional. Without it the validator is warn-only and exits 0
unconditionally, so the check could not fail.

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

## 4. All four recorded IPs match the live tailnet

Run **on any tailnet device** (not just office4 — this checks all four, so a reviewer
elsewhere can run it):

```bash
python3 - <<'EOF'
import json, subprocess
live = {}
for ln in subprocess.run(["tailscale","status"],capture_output=True,text=True).stdout.splitlines():
    f = ln.split()
    if len(f) >= 2 and f[0].count(".") == 3:
        live[f[1]] = f[0]
t = json.load(open("docs/design/architecture/data/network-topology.json"))
rec = {d["hostname"]: d["tailscale_ip"] for d in t["network"]["devices"]}
assert live == rec, f"MISMATCH\nlive={live}\nrecorded={rec}"
print("OK: all", len(rec), "devices match the live tailnet")
EOF
```

Expected today: `office2 100.92.197.90`, `kents-macbook-pro 100.71.19.66`,
`iphone-14-pro-max 100.109.208.6`, `office4 100.112.83.28`.

## 4b. office4's os and hardware came from the right sources

Run **on office4**. This is an authoring-time attestation, not a merge gate — a reviewer on
another machine cannot run it, and "not run" must not look like "passed":

```bash
cat /etc/os-release | grep -E '^(NAME|VERSION)='
```

```bash
cat /sys/devices/virtual/dmi/id/sys_vendor /sys/devices/virtual/dmi/id/product_name
```

Must match `hardware-inventory.json`'s office4 `os` and `hardware`. **Do not use
`uname -a`** — its `#28~24.04.1-Ubuntu` is the kernel build's provenance, not the distro,
and reading it as the distro is the exact error research.md R-4 records.

## 5. ADR 0008 exists and is registered in all four surfaces

```bash
ls docs/design/architecture/adr/0008-*.md
```

```bash
for f in docs/design/architecture/adr/README.md docs/INDEX.md \
         docs/DEVELOPER_PORTAL.md docs/design/architecture/README.md; do
  grep -q "0008-three-machine-model" "$f" || { echo "MISSING in $f"; exit 1; }
done; echo "OK: registered in all four"
```

A plain `grep -l "0008" a b c` would **not** work here: `grep -l` exits 0 if *any* file
matches, so it passes on `docs/INDEX.md` alone — and `"0008"` is a loose token that could
match an unrelated number. The loop above fails per-file, on the real artifact name.

## 5b. The adjacent surfaces no longer contradict the ADR

```bash
grep -n "office4" docs/design/architecture/glossary.md CLAUDE.md
```

```bash
python3 -c "
import json
m = json.load(open('docs/design/architecture/data/signal-to-doc-map.json'))
hits = [e for e in m.get('mappings', m.get('entries', [])) if 'hardware-inventory.json' in json.dumps(e)]
assert hits, 'hardware-inventory.json still missing from the signal-to-doc map'
print('OK: map now names hardware-inventory.json')
"
```

`glossary.md` must name four devices in its `Tailscale` entry and define all four canonical
terms; `CLAUDE.md`'s Platform table must include office4.

## 5c. Review-only affirmations exist

```bash
grep -n "Review-only affirmations" docs/design/architecture/adr/0008-*.md
```

Must list `adr/0004-tailscale-ssh-with-accept-acl.md` and
`docs/runbooks/phone-termius-setup.md`, and the ADR-0004 line must cite
`tailscale debug prefs` → `"RunSSH": false`. Without this the FR-011 distinction between
"read and unchanged" and "never opened" is unverifiable.

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

## 7. The rebaseline decision is recorded — on the RIGHT commit

⚠️ **Not checkable at mission close.** `spec-kitty merge` has no commit-message option and
the mission merges to `feat/office4-architecture-registration`, not `main`. The line rides
**Kent's `feat → main` merge commit**. Run this after that merge, on `main`:

```bash
git log -1 --format=%B | grep -i "^Rebaseline:"
```

Must read `Rebaseline: not required — documentation and architecture metadata only`.
Do **not** amend the spec-kitty merge commit to satisfy this — that is a prohibited manual
git workaround.

Docs CI has the same shape: `.github/workflows/docs-ci.yml` triggers only on `main`, so it
does not run on the mission merge either. At mission close the validators are covered by
the `.githooks` pre-commit gate; Docs CI is satisfied at Kent's push.

## 8. Issue #909 is corrected

`gh issue view 909 --repo kentonium3/kg-automation --comments` must show the comment
correcting the `hardware-inventory.json` premise, so the next reader is not misled by the
original success criterion.
