---
title: 'Handoff: office3 onboarding and the two-persona split'
doc_type: note
audience: agents_and_humans
status: active
last_updated: '2026-09-12'
---

# Handoff — office3 onboarding and the two-persona split

**Written 2026-09-12 on office3, Kent's Windows 11 Home machine, during its first working
session.** Two commits landed; two issues are open; one decision is tracked in `spec-kitty-qa`
under the work hat, deliberately not here.

---

## Prompt — paste this to start

> office3 is on the tailnet and reaches office2 and office4 keyless. Read
> `docs/handoff/2026-09-12-office3-onboarding.md`, then finish #971's architecture documentation
> updates: register office3 in `network-topology.json`, correct the device count in
> `security-posture.md`, and reconcile ADR-0008's three-machine model with what is now four.

---

## What office3 is

Windows 11 **Home**, build 10.0.26200, on the LAN with office2 at sub-millisecond latency.
Kent's third working machine alongside the MacBook Pro and office4. It is an attended,
unmanaged peer, the same placement class as office4. Not a felix-deployer target.

Tailnet device five, at **100.94.189.92**.

## Landed this session

| Commit | What |
|---|---|
| `d68fa4ba` | office4 Tailscale SSH doc corrections. Closed #972. |
| `42635794` | spec-kitty bug-reporting runbook v1.6 and all three templates. |

Also deleted `docs/Spec Kitty Issue 21 resolution.md`, an untracked November 2025 bake-tracker
transcript that failed the docs validator. Kent confirmed it was not needed.

## Open: #971, office3 onboarding

Connectivity is done and verified. The **architecture documentation updates are untouched** and
are the whole remaining scope:

- `data/network-topology.json` does not list office3. Add it with `"os": "windows"`.
- `security-posture.md` still says the tailnet has four devices. It has five.
- ADR-0008 records a three-machine model. There are now four machines. Amend or supersede;
  ADR bodies are frozen, so superseding is likely correct.
- `CLAUDE.md` says "Windows is not a supported platform." office3 is not a deploy target but is
  now an authoring surface, so that line needs qualifying rather than deleting.
- `docs/INDEX.md` and `DEVELOPER_PORTAL.md` per `signal-to-doc-map.json`, change class
  `network-topology-changed`.

## Closed: #972, the office4 contradiction

`security-posture.md` and `physical-topology.md` both said office4 does not run Tailscale SSH.
It has since 2026-08-29 per #932. Fixed. `physical-topology.md` also carried two further stale
claims in the same bullet, both corrected: that the `accept` action passes through to sshd, and
the pre-#932 users list containing `root`.

ADR-0008 keeps its `RunSSH: false` block deliberately. It was true when written and ADR bodies
are frozen. ADR-0004's change log is the pointer.

## Facts established by measurement, not assumption

- **Tailscale on Windows runs as a `LocalSystem` service.** One node identity per machine,
  usable by every Windows account on it. This is load-bearing for the persona split below.
- **office3 reaches office2 as `claude`, `codex`, or `kgale`, and office4 as `kgale`, keyless.**
  No key material exists on office3 and none was created. The ACL authorises on device identity
  with `src: autogroup:member`, so joining the tailnet granted all of this with no ACL edit.
- **spec-kitty here is `uv tool install` from a PyPI wheel**, version 3.2.7. No `direct_url.json`
  exists, which is how you know it did not come from git. Build ID is
  `3.2.7 (pinned tag SHA fb4e8fa98)`, resolved from the upstream tag because a published wheel
  carries no commit reference.
- **Windows 11 Home has no Hyper-V.** It ships with Pro and above.
- **`ssh` is already present** twice, the Windows built-in and the Git for Windows copy. Git's
  wins the PATH race. Both read `C:\Users\Kent\.ssh\config`, which now holds `office2-claude`,
  `office2-codex`, `office2-kgale`, and `office4`.

## The two-persona decision, tracked elsewhere

office3 serves two roles and Kent is splitting them by Windows user account:

- **Customer persona**, his normal login. Static environment, uv plus PyPI, upgraded a release
  at a time, used to develop Felix. No Team Kitty.
- **QA persona**, a new account named **`sk-test-win-env`**. Fresh installs, build testing,
  upgrade testing, manual QA, and eventually an unattended test node in the spec-kitty QA
  Pipeline driven by a controller on EXE.dev.

**This is tracked in `spec-kitty-qa` under Kent's work hat, not in kg-automation.** Do not open
a kg-automation issue for it. An issue already exists there; the repo is not cloned on office3
and should land in the QA account when it is, not in Kent's personal profile.

Two findings that shaped it, worth not rediscovering:

1. **A Windows account does not partition tailnet identity.** Tailscale is machine-wide, so a
   process under any account on office3 can shell into office2 as `kgale`, which has sudo. An
   unattended QA node here would therefore have a standing path to the Felix production hub, and
   the account split does not close it. Tagging cannot fix it either, because tagging office3
   would drop it out of `autogroup:member` and revoke the customer persona's own office2 access.
2. **The likely resolution is a Windows Pro upgrade.** That unlocks Hyper-V, lets the prototype
   be built against the target environment rather than an intermediate needing a port, and gives
   the node its own tailnet identity that can be tagged out of the SSH rule. Until then, keep
   payload execution attended.

## Papercut

`GITHUB_TOKEN` is set and invalid in long-running shells started before Kent removed it. It
shadows the working keyring credential and makes `gh` fail with a 401. It is **gone from disk**:
not in `HKCU\Environment`, not in `HKLM`, not in any shell profile, and there is no gh config
directory. Any session started fresh is clean. Older ones need `unset GITHUB_TOKEN` per command.
