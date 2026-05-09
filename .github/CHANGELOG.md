# Changelog

All notable changes to this project will be documented in this file.

- The format is based on [`Keep a Changelog`](https://keepachangelog.com/en/1.1.0/), and this project adheres to [`Semantic Versioning`](https://semver.org/spec/v2.0.0.html)

- Pre-1.0 minor versions may contain breaking changes.

## [0.1.1] — 2026-05-09

### Added

- Curated public re-exports in `scrape_do/__init__.py` so common imports work as `from scrape_do import ScrapeDoClient, RequestParameters, ...` rather than digging into submodules.

- `py.typed` PEP 561 marker so downstream type-checkers (`mypy`, `pyright`) consume the package's type hints.

- Trove classifiers in package metadata — PyPI's "Python" sidebar and shields.io's `pypi/pyversions` badge now populate correctly.

### Removed

- Empty `scrape_do/namespaces/` placeholder folder (was scaffolding from before the roadmap solidified; will be replaced by `plugins/` in `0.4+`).

### Documentation

- Planned package layout added to `ROADMAP`.

[`0.1.1`](https://github.com/svdC1/scrape-do-python/releases/tag/v0.1.1)

## [0.1.0] — 2026-05-08

Initial release. Synchronous client surface.

### Added

- `ScrapeDoClient` synchronous client with `request()`, `get()`, `post()`, `execute()`, and `execute_from_url()` methods.

- Smart routing in `ScrapeDoClient.request()`: accepts kwargs, a pre-built `RequestParameters`, or a raw `api.scrape.do` URL — exactly one configuration shape per call.

- Automatic retries on Scrape.do gateway errors (429 / 502 / 510) with configurable backoff strategy (static float or callable). Default is jittered exponential.

- `session_validator` callback (`SyncSessionValidator`) for sticky-session rotation detection — when present and `session_id` is set, the validator decides whether to raise `RotatedSessionError`.

- SDK-native event hooks via `SyncClientEventHooks` TypedDict: `request` / `response` / `retry` lifecycle, distinct from httpx transport-level hooks.

- Pydantic-validated `RequestParameters` covering the full Scrape.do API parameter surface, including browser-action models (`ClickAction`, `WaitAction`, `FillAction`, `ExecuteAction`, `ScreenShotAction`, scrolling, request-completion waits).

- `ScrapeDoResponse` wrapper exposing the parsed JSON envelope, network requests, websocket frames, action results, screenshots, frames, plus a raw `status_code` passthrough.

- Cookie isolation between sequential requests on the underlying `httpx.Client` (prevents cross-request bleed).

- Exception hierarchy: `ScrapeDoError` (base), `APIConnectionError`, `TargetError`, `RotatedSessionError`, plus the API-layer `AuthenticationError`, `BadRequestError`, `RateLimitError`, `ServerError`, and `AuthenticationThrottleError`.

- Default request timeout raised to 60 seconds (from httpx's 5s default) to accommodate browser rendering and proxy round-trips.

[`0.1.0`](https://github.com/svdC1/scrape-do-python/releases/tag/v0.1.0)
