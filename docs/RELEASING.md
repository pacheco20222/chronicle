# Releasing to PyPI

The distribution is named **`chronicle-memory`** (the name `chronicle` is taken
on PyPI by an unrelated project). The command stays `chronicle`.

Nothing is published until you do the one-time setup below and push a tag.

## One-time setup

1. Create a PyPI account and enable 2FA.
2. On pypi.org, add a **pending trusted publisher** (Account > Publishing) for a
   new project `chronicle-memory`: owner `pacheco20222`, repository `chronicle`,
   workflow `release.yml`, environment `pypi`.
3. In the GitHub repo, create an environment named `pypi` (Settings >
   Environments). Add yourself as a required reviewer if you want a manual
   approval before each publish.

No API token is stored anywhere; the workflow uses OIDC.

## Each release

1. Bump `version` in `pyproject.toml` and `.claude-plugin/plugin.json`, run
   `uv lock`, and add the version to `CHANGELOG.md`.
2. Make sure `Tests` is green on `main`.
3. Dry run: Actions > Release > "Run workflow". It builds the dashboard, bundles
   it, builds the wheel and smoke-tests it in a clean virtualenv, but does not
   publish.
4. Tag and push: `git tag v3.2.0 && git push origin v3.2.0`. The same workflow
   builds again and then publishes.
5. Verify in a clean shell: `uv tool install chronicle-memory` and
   `chronicle --version`.

## What the wheel contains

The package carries everything it needs at runtime: database migrations
(`chronicle/migrations`), `docker-compose.yml` for optional semantic search, and
the built dashboard (`chronicle/dashboard_dist`, copied in by the release
workflow; a plain `uv build` from a checkout without it still works, the
dashboard just shows build instructions). `scripts/smoke_wheel.py` installs a
built wheel into a clean virtualenv and checks all of this.

## Keep two files in sync

`src/chronicle/docker-compose.yml` must equal the root `docker-compose.yml`
(a test enforces it).
