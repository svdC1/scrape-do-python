# Changelog

All notable changes to this project will be documented in this file.

- The format is based on [`Keep a Changelog`](https://keepachangelog.com/en/1.1.0/), and this project adheres to [`Semantic Versioning`](https://semver.org/spec/v2.0.0.html)

- Pre-1.0 minor versions may contain breaking changes.

## [Unreleased]

### Added

- `RequestParameters.to_proxy_url()` — generates a `Scrape.do` Proxy-Mode connection string template (`http://{api_token}:<params>@proxy.scrape.do:8080`) for use with the upcoming proxy clients or with third-party tooling (Playwright / Selenium / curl).

- `RequestParameters.validate_proxy_params()` — cross-validates Proxy-Mode-specific parameter quirks (`customHeaders` defaulting to true server-side, `setCookies` interaction, render-mode discouragement).

- `SCRAPE_DO_CA_PATH` and `DEFAULT_PROXY_SSL_CONTEXT` in `scrape_do.constants` — the bundled Scrape.do CA cert and an `ssl.SSLContext` preloaded with system CAs plus the bundled CA. Default `verify` source for the proxy-mode clients so HTTPS targets validate correctly through Scrape.do's MITM step.

- Scrape.do's CA certificate bundled with the wheel under `scrape_do.data` so the SDK ships everything needed for proxy-mode TLS verification.

- `AsyncScrapeDoClient` backed by `httpx.AsyncClient`. Near-1:1 of the synchronous client (smart routing, retry strategy, session validation, event hooks), with every IO-bound method `async`/`await`. Sleeps between retries use `asyncio.sleep` rather than `time.sleep`.

- `AsyncClientEventHooks` TypedDict and `AsyncSessionValidator` type alias. Both are async-only — hooks return `Awaitable[None]` and validators return `Awaitable[bool]`, so they can perform I/O while the request executes.

- Public re-exports for `AsyncScrapeDoClient`, `AsyncClientEventHooks`, and `AsyncSessionValidator` in `scrape_do/__init__.py`.

- `ScrapeDoResponse.json(raw_response=True, **kwargs) -> Any` convenience method. With `raw_response=True` (default) it shortcuts to `httpx_response.json()`; with `raw_response=False` it returns `json.loads(self.text, **kwargs)` so the post-envelope path is reachable without manual parsing.

- Example block in the package-level docstring at [`src/scrape_do/__init__.py`](https://github.com/svdC1/scrape-do-python/blob/main/src/scrape_do/__init__.py) showcasing a typical request flow.

### Fixed

- `ScrapeDoClient.post()` now forwards the `session_validator` argument to `request()`. Previously the argument was accepted but silently ignored on POST calls. `get()` was unaffected.

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
