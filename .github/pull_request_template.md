## What changed and why

## Linked issue

Closes #

## Checklist

Details are in [CONTRIBUTING.md](https://github.com/maltemindedal/snaffle/blob/main/CONTRIBUTING.md).

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run ty check`
- [ ] `uv run python -X dev -W error -m unittest discover tests`
- [ ] User-visible changes are in `CHANGELOG.md` under `Unreleased`.
- [ ] A dependency change in `pyproject.toml` comes with a matching `uv lock`.
