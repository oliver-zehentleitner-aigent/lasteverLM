# Changelog

All notable changes to this repository are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The
reasoning behind changes is in [`context/`](context/index.md).

## [Unreleased]

## [0.1.0] - 2026-10-12

### Added

- Root `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.dockerignore`; live dashboard badge and `dashboard-state`.
- Architecture v2: one repository with isolated Keep the Why contexts per service, containers only, Helm chart with automatic deploy on a tag, PostgreSQL as the job queue for the workers, rate limiting with blocks and bans, access log.
- Architecture v1 and v1.1: generated outputs (report, quiz, table, mind map, infographic, audio), sharing, ask-about-this, runtime contract; all-Vultr platform, six repositories, data model, API contract for account, ingest and rag, configuration, deployment, extension points.
- Agent working conventions in `AGENTS.md`, task board in `TASKS.md`.
- `docs/ui.md` (wizard, two-column notebook view, viewer, print, share) and `docs/repository-standard.md` (files, tests, workflows, versioning, documentation rule).
- Keep the Why setup with the family's `children` block and the first decisions in `context/`.
