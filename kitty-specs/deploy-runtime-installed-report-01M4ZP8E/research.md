# Research: Deploys report what they installed

All facts were read from source on 2026-10-15.

## Facts

- **F1, where expectations come from today.** `rebaseline.observe(base, head)` runs `git diff --name-only base..head`, then `match_surfaces(changed, registry)`, and unions the matched surfaces' `affected_baselines` into the token (`rebaseline.py:256–360`). `_tick` collects `declared_baselines` from each *successfully* applied manifest's `expected_baselines` (`_tick.py:602–628`). After observe and before reconcile, it calls `fold_manifest_baselines(declared_baselines, ...)` (`_tick.py:759`), which unions them into the token or creates one (`rebaseline.py:456–532`).
- **F2, 0029's shape.** Range `6da932fc..6373721a` held only the manifest and the entrypoint, so only `deploy-pipeline` matched (`affected_baselines: []`). The audit then drifted `systemd-user-unit-contents.txt`, and reconcile returned `unexpected_drift`. The unit files are now under the `systemd-user-units` surface (#1065), so reported paths would map to its four baselines.
- **F3, apply.** `dry_run_then_apply_gate` runs `_run_shell([entrypoint, "--dry-run"])` then `_run_shell([entrypoint, "--apply"])` with `subprocess.run(..., shell=False)` and no `env` (`apply.py:75–130, 253–275`).
- **F4, the library.** `userunits.install_units` (#1066) writes each changed file with `mkstemp` and `os.replace`, and is the only path new unit installers may use (guard test). Its only adopter so far is the 0031 entrypoint.
- **F5, the tick harness.** `tests/deploy/test_tick_rebaseline.py` drives the real `_tick` with fake git (`_git_mock`), seams (`_wp04_seams`) and a `fake_repo_with_manifest` fixture. A 0029 replay can use it with a real entrypoint script in `tmp_path`.

## Decisions

### R1 — Report format: JSON lines of absolute source paths

- **Decision**: one JSON object per line, `{"path": "<str(Path(src).resolve())>"}`, appended (opened `"a"`, one `write` per line). The deployer, not the library, decides what is repo-relative.
- **Rationale**: the library cannot know which repository the deployer considers authoritative; the deployer has `repo_root`. Absolute resolved paths let the deployer reject out-of-repo paths and symlink escapes (C-002). Appending is robust to partial installs: lines exist only for files that landed.
- **Alternatives**: repo-relative paths written by the library were rejected, because they trust the entrypoint's notion of the root. A single JSON document was rejected, because a crash mid-install would leave it unparseable.

### R2 — Report only changed files

A byte-identical file causes no drift (`systemd-user-unit-contents.txt` hashes contents). Reporting it would only widen the expectation, which C-002 forbids.

### R3 — Only `--apply` gets the location

Dry runs install nothing, and verification commands are shell strings that must not inherit an install channel. Each manifest gets its own `mkdtemp` directory (FR-002); it is removed after the read.

### R4 — Defensive reader in `apply.py`, mapping in `rebaseline.py`

The reader handles file shape: a 1 MiB cap, per-line JSON, `path` must be a string, and at most 10,000 entries. It returns raw absolute strings and warnings. Mapping, meaning repo containment and surface matching, belongs in `rebaseline.py` next to `observe`, so there is one matcher (C-001).

### R5 — Fold reported baselines even on a failed apply (FR-007)

Declared baselines fold only on apply success, by design (Codex HIGH-1 in the pipeline mission: the declaration expresses intent for a *completed* deploy). Reported baselines are evidence of what *actually landed*, which is true regardless of the exit code. A failed apply that installed a unit will drift; not expecting it would page a false security alert on top of the real deploy failure.

### R6 — Failure isolation

Each manifest's report handling is wrapped. Any exception leaves a `rebaseline_reported` warning and contributes nothing. A registry read failure behaves the same way (as `observe` already does).

## Open risks for reviewers

- R5 widens when expectations can grow (failed applies). Does any failure mode report a file that did not land? No: the line is written after `os.replace`. Reviewers should still check this.
- Environment inheritance: `--apply` gets `os.environ` plus the report variable. Verify that nothing else changes for existing entrypoints.
