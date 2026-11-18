---
title: Vikunja startup-lock sandbox evidence (Compose v5.3.1, office2)
doc_type: reference
status: approved
tags: [1087]
---

# Vikunja startup-lock sandbox evidence

**Verdict: FAIL-CLOSED: CONFIRMED**

Mission `vikunja-image-deploy-01M65D3V`, work package WP05, research R-22. The run was 2026-10-30 from 03:46Z on office2, under the CLAUDE.md sandbox carve-out. Records outside the run transcript:
- **Account:** the run was executed through the `ssh office2-claude` alias. The same alias's `id` at 2026-10-30 inspection returned `uid=1001(claude)`, in the `docker` group.
- **Prior record:** the sandbox record was posted to #1087 before the run (issue comment 6514456782, 03:46:15Z; the run started 03:46:45Z), after Kent approved the run in the mission session.
- **Image store:** the classic overlay2 store was captured separately (research R-13: `docker info` Driver `overlay2`, no containerd snapshotter).
- **Unused source image:** `vikunja/vikunja:0.24.6` (`cec159e222f5`) was listed but not used by any container at the 2026-10-30 inspection; production runs `60fe1ee8…`.

## Question

The release design uses the local tag `office2.local/vikunja:active` as a startup lock: untagged means held. Does Docker Compose on office2 fail `up -d` closed when a service's image tag is missing and `pull_policy: never` is set? Failing closed means a non-zero exit, no container created or running, and no pull. And does untagging after `down` keep the underlying image?

## Environment

Docker 29.6.2 (classic overlay2 store), Docker Compose 5.3.1. Project `vikunja-lock-sandbox`, from `/tmp/vikunja-lock-sandbox/compose.yml`:

```yaml
services:
  probe:
    image: ${SANDBOX_IMAGE}
    pull_policy: never
    restart: unless-stopped
    mem_limit: 64m
    command: ["version"]
```

The sandbox had no ports and no mounts. Its images were `office2.local/sandbox:absent` (never existed) and `office2.local/sandbox:present`, a temporary tag on the unused `vikunja/vikunja:0.24.6` (`cec159e222f5`). `docker events --filter type=image` ran throughout to catch any pull.

## Results

| Case | Command | Exit | Containers after | Notes |
|---|---|---|---|---|
| (b) missing tag | `up -d` with `office2.local/sandbox:absent` | **1** | none | `Error response from daemon: No such image: office2.local/sandbox:absent`. The project network was created before the failure. |
| (c) positive control | `docker tag cec159e222f5 office2.local/sandbox:present`, then `up -d` | 0 | `probe-1` running on `office2.local/sandbox:present` | The engine starts the service when the tag exists. |
| (c) untag after down | `down`, then `docker image rm office2.local/sandbox:present` | 0 / 0 | none | `cec159e222f5` is still present as `vikunja/vikunja:0.24.6`: untag removes the tag only. |
| (d) lock held | `up -d` again with the now-missing tag | **1** | none | `No such image: office2.local/sandbox:present`, the same as (b). |

Image events during the whole run were one `tag` and one `untag`, with **`pull_count=0`**. This is an observation of daemon image events only. It shows that no pull event was recorded. It does not by itself exclude a failed registry request. That no registry is contacted is an inference from `pull_policy: never` plus the daemon's "No such image" error. The error is raised for a local lookup; a failed pull would instead report a registry or resolution error.

Residue after teardown: no containers, no networks and no `office2.local/sandbox` tags. The temp folder was removed.

Production was unchanged. The `vikunja` container was `ba8ffc0cf368…` on image `sha256:60fe1ee8…`, `running`, started `2026-10-14T15:07:01Z`, both before and after.

## Consequences for the design

- **Observed:** a missing `active` tag with `pull_policy: never` makes `compose up -d` exit 1 with "No such image", and no container is created. **Inferred:** no registry is contacted (see the note under Results). The startup lock in research R-9 and R-21 rests on this observed behaviour.
- Compose creates the project's default network before it discovers the missing image. For the `vikunja` project that network already exists and carries no state, so this side effect is harmless. It is recorded so nobody reads "fails closed" as "creates nothing".
- `docker image rm <tag>` on a tag whose image has another reference removes only the tag. Releasing the lock never deletes the 2.4.0 or release image while another tag holds it.
- **Boot path, inferred and not exercised:** the sandbox did not run systemd, a Docker daemon restart or a reboot. `vikunja.service` runs the same `docker compose … up -d` command, with `Restart=on-failure`. With the lock held, the same failure is therefore expected at boot. This holds **only after** `compose down` has removed the container and its absence has been verified:
  - `restart: unless-stopped` cannot recreate a removed container;
  - an existing container keeps its image ID even after its tag is removed, so the lock does not stop an existing container from restarting.
  The ACTIVATE and rollback order (`down`, then untag, then verify no container) depends on this. The crash windows accepted in research R-21 (between `down` and untag, and after the release is tagged) remain as stated there.

## Appendix A — exact script executed (verbatim)

Run from office4 as `ssh -o BatchMode=yes office2-claude 'bash -s' < sandbox.sh`. This is the original file, not a reconstruction.

```bash
set -u
D=/tmp/vikunja-lock-sandbox; PJ=vikunja-lock-sandbox; L=com.docker.compose.project=$PJ
echo "== host $(hostname) $(date -u +%FT%TZ) docker $(docker version --format '{{.Server.Version}}') compose $(docker compose version --short)"
echo "== prod-before $(docker inspect vikunja --format '{{.Id}} {{.Image}} {{.State.Status}} {{.State.StartedAt}}')"
test -e $D && { echo "ABORT: $D exists"; exit 9; }
umask 077; mkdir $D
cat > $D/compose.yml <<'Y'
services:
  probe:
    image: ${SANDBOX_IMAGE}
    pull_policy: never
    restart: unless-stopped
    mem_limit: 64m
    command: ["version"]
Y
C="docker compose -p $PJ -f $D/compose.yml"
docker events --since "$(date -u +%FT%TZ)" --filter type=image --format '{{.Action}} {{.Actor.ID}}' > $D/events.txt 2>&1 & EV=$!
sleep 1
echo "== (b) up with ABSENT tag"; SANDBOX_IMAGE=office2.local/sandbox:absent timeout 120 $C up -d > $D/b.out 2>&1; echo "rc=$?"; sed 's/^/   /' $D/b.out | tail -5
echo "   containers: $(docker ps -a --filter label=$L --format '{{.Names}}:{{.State}}' | tr '\n' ' ')"; echo "   networks: $(docker network ls --filter label=$L --format '{{.Name}}' | tr '\n' ' ')"
SANDBOX_IMAGE=office2.local/sandbox:absent $C down --remove-orphans >/dev/null 2>&1
echo "== (c) positive control: up with PRESENT tag"; docker tag cec159e222f5 office2.local/sandbox:present
SANDBOX_IMAGE=office2.local/sandbox:present timeout 120 $C up -d > $D/c.out 2>&1; echo "rc=$?"; sleep 3
echo "   containers: $(docker ps -a --filter label=$L --format '{{.Names}}:{{.State}}:{{.Image}}' | tr '\n' ' ')"
SANDBOX_IMAGE=office2.local/sandbox:present timeout 120 $C down > /dev/null 2>&1; echo "   down rc=$?"
docker image rm office2.local/sandbox:present > /dev/null; echo "   untag rc=$?"
echo "   image cec159e222f5 still present: $(docker image inspect cec159e222f5 --format '{{.Id}} {{json .RepoTags}}' 2>&1)"
echo "== (d) up again after untag (lock held)"; SANDBOX_IMAGE=office2.local/sandbox:present timeout 120 $C up -d > $D/d.out 2>&1; echo "rc=$?"; sed 's/^/   /' $D/d.out | tail -5
echo "   containers: $(docker ps -a --filter label=$L --format '{{.Names}}:{{.State}}' | tr '\n' ' ')"
echo "== teardown"; SANDBOX_IMAGE=office2.local/sandbox:present $C down --remove-orphans >/dev/null 2>&1; echo "down rc=$?"
sleep 1; kill $EV 2>/dev/null; wait $EV 2>/dev/null
echo "== image events during run (pull would appear here):"; sed 's/^/   /' $D/events.txt; echo "   pull_count=$(grep -c '^pull' $D/events.txt)"
echo "== residue: containers=[$(docker ps -a --filter label=$L -q | tr '\n' ' ')] networks=[$(docker network ls --filter label=$L -q | tr '\n' ' ')] tags=[$(docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -c '^office2.local/sandbox')]"
echo "== prod-after  $(docker inspect vikunja --format '{{.Id}} {{.Image}} {{.State.Status}} {{.State.StartedAt}}')"
rm -rf $D; echo "== tmpdir removed: $(test -e $D && echo NO || echo yes)"
```

## Appendix B — raw transcript (verbatim)

```text
== host office2 2026-10-30T03:46:45Z docker 29.6.2 compose 5.3.1
== prod-before ba8ffc0cf3684b3bf119a00d4937624998d50f5ed18a7d0a1461fa63d690842e sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2 running 2026-10-14T15:07:01.361710623Z
== (b) up with ABSENT tag
rc=1
    Network vikunja-lock-sandbox_default Creating 
    Network vikunja-lock-sandbox_default Created 
    Container vikunja-lock-sandbox-probe-1 Creating 
    service:probe:1 Error response from daemon: No such image: office2.local/sandbox:absent 
   Error response from daemon: No such image: office2.local/sandbox:absent
   containers: 
   networks: vikunja-lock-sandbox_default 
== (c) positive control: up with PRESENT tag
rc=0
   containers: vikunja-lock-sandbox-probe-1:running:office2.local/sandbox:present 
   down rc=0
   untag rc=0
   image cec159e222f5 still present: sha256:cec159e222f578ece7447b56cb451178b13da2903c403ef26bea00c30e42c30f ["vikunja/vikunja:0.24.6"]
== (d) up again after untag (lock held)
rc=1
    Network vikunja-lock-sandbox_default Creating 
    Network vikunja-lock-sandbox_default Created 
    Container vikunja-lock-sandbox-probe-1 Creating 
    service:probe:1 Error response from daemon: No such image: office2.local/sandbox:present 
   Error response from daemon: No such image: office2.local/sandbox:present
   containers: 
== teardown
down rc=0
== image events during run (pull would appear here):
   tag sha256:cec159e222f578ece7447b56cb451178b13da2903c403ef26bea00c30e42c30f
   untag sha256:cec159e222f578ece7447b56cb451178b13da2903c403ef26bea00c30e42c30f
   pull_count=0
== residue: containers=[] networks=[] tags=[0]
== prod-after  ba8ffc0cf3684b3bf119a00d4937624998d50f5ed18a7d0a1461fa63d690842e sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2 running 2026-10-14T15:07:01.361710623Z
== tmpdir removed: yes
```
