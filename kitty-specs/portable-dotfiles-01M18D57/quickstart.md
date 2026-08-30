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
~/repos/dotfiles/install.sh                     # 2. backs up, then links
exec zsh                                        # 3. new shell
verify-shell-env                                # 4. prove it
```

Then create `~/.config/secrets` using `secrets.example` as the shape — names only; that file is never committed and stays mode 600.

## Rollback

The installer's backup is independent of the repo, so this works even if the clone is gone:

```bash
ls -d ~/.dotfiles-backup-*        # pick the timestamp
cp -a ~/.dotfiles-backup-<ts>/. ~/
exec zsh
```

## Gotchas

- **Symlinks are local.** `~/.zshrc` points at `~/repos/dotfiles/core/zshrc` on the same disk. GitHub is transport between machines, not a symlink target.
- **`git pull` is still manual.** Editing is instantly visible to the repo; reaching the *other* machine is ordinary git. `verify-shell-env` fails when the clone is dirty or behind, so drift is caught rather than silent.
- **A deleted clone degrades, it does not lock you out.** Dangling symlinks mean zsh starts with defaults. Restore from backup above.
- **PATH lives in `.zshenv` on office4** because `ssh office4-kgale 'cmd'` reads only that file. Do not "tidy" it into `.zshrc`.
- **The work-repo list is a glob on purpose.** Converting it to an explicit list is what silently routed a work repo to the personal account.
