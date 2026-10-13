# Changelog

All notable changes to this repository are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The
reasoning behind changes is in [`context/`](context/index.md).

## [Unreleased]

## [0.3.1] - 2026-10-13

### Changed

- `docs/architecture.md`: the credit check applies to admins as well; the exemption from 0.3.0 is reversed (maintainer decision).

## [0.3.0] - 2026-10-13

### Changed

- `docs/architecture.md`: admins are exempt from the credit check (`has_credit`, `is_admin`, `admin_only` in core); `request-link` answers 403 `not_allowed` instead of a silent 202; allowlist of domains and single addresses edited per entry; voucher list and one `/admin/stats` per service (account, ingest, rag) with their shapes.
- Wording: "provide documents" instead of "upload documents" in the README, the docs site, AGENTS.md and the walkthrough script, because sources are files, links and images; the login page follows in web.

### Changed

- README and docs home: the tagline "Please explain this to me" opens the description instead of standing alone below it; the docs home lists its own address next to the live system and the code.

## [0.2.1] - 2026-10-13

### Security

- `ci.yml` and `ktw-lint.yml` limit the `GITHUB_TOKEN` to read access (CodeQL `actions/missing-workflow-permissions`).

### Added

- `black.yml`: a black workflow of its own (one `black --check` per Python directory, each with its own `pyproject.toml`) with the badge in the README; `make check` in every directory still runs black as before.

### Changed

- `docs/architecture.md`: the SMTP configuration comes from the environment (Secret `lasteverlm-smtp`) and is read-only in the admin panel; the settings table keeps only the allowlist.
- README: the docs-site badge replaces the static Keep the Why badge; the live dashboard badge stays.
- Python is formatted with black (line length 100) in every service; ruff keeps linting (`context/workflow.md`).

## [0.2.0] - 2026-10-13

### Added

- Docs site: `mkdocs.yml` and `docs/index.md`, built by `pages.yml` next to the Keep the Why dashboard exports; the README links the site and the live system.
- `docs/walkthrough.md`: the script of the ten-minute recorded tour — live demo first, then architecture, then how the fleet built it — with the preparation list and what to do when something fails on camera.

### Changed

- Architecture: retention of the rate-limit tables settled by the maintainer — access log, expired blocks and lifted bans go after `RETENTION_DAYS` (30), an active ban survives that purge and falls after `BAN_MAX_DAYS` (90) at the latest; the account service runs the purge at start.
- Architecture: the audio output contract — `usage.kind` gains `tts` priced per input character, output files live at `<notebook_id>/<output_id>/<name>` in object storage, the stored `{"key"}` is served as a one-hour presigned URL on every read, the object-storage client moves into core, `TTS_VOICE` joins the configuration.

## [0.1.0] - 2026-10-12

### Added

- Root `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.dockerignore`; live dashboard badge and `dashboard-state`.
- Architecture v2: one repository with isolated Keep the Why contexts per service, containers only, Helm chart with automatic deploy on a tag, PostgreSQL as the job queue for the workers, rate limiting with blocks and bans, access log.
- Architecture v1 and v1.1: generated outputs (report, quiz, table, mind map, infographic, audio), sharing, ask-about-this, runtime contract; all-Vultr platform, six repositories, data model, API contract for account, ingest and rag, configuration, deployment, extension points.
- Agent working conventions in `AGENTS.md`, task board in `TASKS.md`.
- `docs/ui.md` (wizard, two-column notebook view, viewer, print, share) and `docs/repository-standard.md` (files, tests, workflows, versioning, documentation rule).
- Keep the Why setup with the family's `children` block and the first decisions in `context/`.
