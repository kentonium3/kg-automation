# Quickstart: Portable shell config

**Mission**: `portable-dotfiles-01M18D57`

## Everyday use

**Change something.** Edit `~/.zshrc` as usual. It is a symlink into the clone, so you are editing the repo — `git status` in `~/repos/dotfiles` shows it immediately. No copy, sync, or re-install step.

```bash
cd ~/repos/dotfiles && git add -p && git commit && git push
```

**Pick it up elsewhere.**

```bash
cd ~/repos/dotfiles && git pull      # symlinks already point here; new shells see it
```

**Check the machine is sane.**

```bash
verify-shell-env            # 0 = every assertion passed
verify-shell-env --verbose  # resolved values too; use before/after a change
```

## Bringing up a new machine

Order matters — the repo is **private**, so authentication precedes configuration.

```bash
gh auth login                                   # 1. auth FIRST
git clone git@github.com:kentonium3/dotfiles ~/repos/dotfiles
~/repos/dotfiles/install.sh                     # 2. preflight, manifest, backup, link
cp ~/repos/dotfiles/secrets.example ~/.config/secrets   # 3. fill in values
chmod 600 ~/.config/secrets
exec zsh                                        # 4. new shell
verify-shell-env                                # 5. prove it
```

**Secrets come before verification, not after.** Startup tolerates the file's absence silently, but `verify-shell-env` asserts it exists with mode 600 and defines every name in `secrets.example` — so running it first reports a failure whose cause is simply "not created yet".

Add `--platform kg_office4` to `install.sh` if hostname detection is ambiguous; it refuses rather than guessing.

## Rollback

The installer's backup is independent of the repo, so this works even if the clone is gone:

```bash
ls -d ~/.dotfiles-backup-*             # pick the timestamp
~/.dotfiles-backup-<ts>/restore.sh     # generated per install; self-contained
exec zsh
```

Do **not** use `cp -a ~/.dotfiles-backup-<ts>/. ~/`. It copies *through* live symlinks into the clone, and cannot delete entries that did not exist before the install — `.bashrc`, typically. `restore.sh` reads the manifest, removes managed entries first, restores prior type and mode, and deletes what was absent.

## Gotchas

- **Symlinks are local.** `~/.zshrc` points at `~/repos/dotfiles/core/zshrc` on the same disk. GitHub is transport between machines, not a symlink target.
- **`git pull` is still manual.** Editing is instantly visible to the repo; reaching the *other* machine is ordinary git. `verify-shell-env` fails when the clone is dirty or behind, so drift is caught rather than silent.
- **A deleted clone degrades, it does not lock you out.** Dangling symlinks mean zsh starts with defaults. Restore from backup above.
- **PATH lives in `.zshenv` on office4** because `ssh office4-kgale 'cmd'` reads only that file. Do not "tidy" it into `.zshrc`.
- **The work-repo list is a glob on purpose.** Converting it to an explicit list is what silently routed a work repo to the personal account.
