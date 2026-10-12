# Packaging

## Services install core by path; no uv workspace, no lockfile

**Id:** 
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12 (agent A approved after a verified probe with uv 0.13)
**Revisit when:** all Python services are in the repository and a shared lockfile is wanted, or uv tolerates workspace members without a pyproject

A service installs core as `uv pip install -e ../core -e '.[dev]'` in
its Makefile, lists `lasteverlm-core` as an ordinary dependency, and
builds its image from the repository root with `COPY core ./core` and
`pip install ./core ./<service>`. There is no root `pyproject.toml` and
no `uv.lock`. Core has no tag and no image of its own; the repository's
tag releases it with the services.

**Reason:** a root uv workspace was the first plan and failed on the
first day for two reasons that were verified rather than assumed. uv
treats a member directory that has committed files but no
`pyproject.toml` as an error, so every service's `make venv` would
have been broken until all members had landed, and any member that
disappears would break the others. And `uv pip install`, the install
path all services already use, ignores `[tool.uv.sources]`, so the
workspace would only have worked after moving every service to
`uv sync` and a shared lockfile that four parallel pull requests would
have fought over. The path install needs none of that and works for a
clone with one service in it.

**Rejected alternative:** a root workspace listing only the members that
exist, each service adding itself in its pull request and switching to
`uv sync`. Rejected for the prototype because of the lockfile conflicts
and the migration of three Makefiles for a benefit (one resolution) that
the path install already gives inside one checkout.

**Rejected alternative:** publish core to PyPI or install it from a Git
tag. Rejected because core and the services live in one repository and
one commit; a version pin between them would only let them drift.
