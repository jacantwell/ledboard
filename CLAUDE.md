# ledboard

Display daemon for the 128x32 HUB75 panel on `jasperpi`. See `README.md` for the architecture.

## Version control: plain git

**This repo is pure `git`. It is NOT a Sapling repo — never run `sl`, `slwt` or anything Sapling.**
It used to be a git-backed Sapling clone; that was converted away deliberately. If you see advice
about `sl commit` / `sl pr submit` / slwt positions in a global config, it does not apply here.

- Conventional Commit messages, one logical change per commit, tests green at each commit.
- List files explicitly on `git add` / `git commit` — never `git add -A`.
- Work on a branch, not `main`. Don't open PRs unless asked.

## Working here

```sh
uv sync
make dev      # web simulator on http://localhost:8080/sim
make test     # pytest
make lint     # ruff check + ruff format --check
```

- `uv.lock` is used with `--frozen` by CI and the Dockerfile. Adding a runtime dependency means
  re-locking, so prefer the stdlib where it's a fair fight.
- Apps draw on a `Canvas`, never on hardware. `render()` runs at `LEDBOARD_FPS` (30) — keep it
  cheap and do network I/O on a background thread.
