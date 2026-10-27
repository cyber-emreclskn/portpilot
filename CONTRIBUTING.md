# Contributing to PortPilot

Thanks for taking the time to contribute! 🎉

## Getting set up

You need [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/<you>/portpilot.git
cd portpilot
uv sync
uv run pre-commit install
```

## Making a change

1. Create a branch: `git checkout -b feat/short-description`
2. Make your change and add tests under `tests/`:
   - `test_core.py` – port discovery / kill logic (no UI)
   - `test_cli.py` – CLI commands via `click.testing.CliRunner`
   - `test_app.py` – the TUI, driven headlessly with Textual's `Pilot`
   The `listener` fixture starts a real throwaway process on a random port, so
   tests can safely list and kill it.
3. Run the checks (pre-commit runs most of them for you):
   ```bash
   uv run pytest --cov
   uv run ruff check . && uv run ruff format .
   uv run mypy
   ```
4. Open a pull request against `main`. CI runs the full matrix
   (Linux / macOS / Windows × Python 3.10–3.14).

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). They drive
the changelog and version numbers automatically:

| Prefix | Example | Release effect |
|--------|---------|----------------|
| `feat:` | `feat: add --sort option to list` | minor bump |
| `fix:` | `fix: handle IPv6-only listeners` | patch bump |
| `docs:`, `test:`, `ci:`, `chore:`, `refactor:` | `docs: clarify macOS notes` | no release |
| `feat!:` / `BREAKING CHANGE:` footer | `feat!: rename --json to --format json` | breaking |

Pull requests are squash-merged, so the **PR title** is what counts.

## How releases work (maintainers)

1. Merging to `main` makes [release-please](https://github.com/googleapis/release-please)
   open or update a *release PR* with the new version and `CHANGELOG.md` entries.
2. Merging that release PR creates the tag and GitHub Release.
3. The release workflow builds the wheel/sdist and publishes to PyPI with
   **Trusted Publishing** — no API tokens are stored anywhere.

## Reporting bugs and ideas

Use the issue templates. For security problems, see [SECURITY.md](SECURITY.md).
