# Changelog

???+ warning "`Pre-1.0` Disclaimer"
    `scrape-do-python` follows [`Semantic Versioning`](https://semver.org/spec/v2.0.0.html), but `0.x` minor versions may contain breaking changes

???+ abstract "Format"
    The format below is based on [`Keep a Changelog`](https://keepachangelog.com/en/1.1.0/)

---

## `Unreleased`

### Added

- [`ScrapeDoJSONErrorMessage`][scrape_do.exceptions.ScrapeDoJSONErrorMessage] — pydantic model for the structured JSON error envelope returned by Scrape.do. Exposes `status_code`, `messages`, `url`, `possible_causes`, `error_type`, `error_code`, `contact` mapped from the API's uppercase keys (`StatusCode`, `Message`, `URL`, `PossibleCauses`, `ErrorType`, `ErrorCode`, `Contact`). The [`try_from_response`][scrape_do.exceptions.ScrapeDoJSONErrorMessage.try_from_response] classmethod returns an instance on a recognizable error response, `None` otherwise — never raises. [`is_auth_throttle`][scrape_do.exceptions.ScrapeDoJSONErrorMessage.is_auth_throttle] property detects the auth-throttle case. Public re-export from `scrape_do`.

- [`ScrapeDoResponse.__repr__`][scrape_do.models.response.ScrapeDoResponse.__repr__] — angle-bracket shorthand (`<ScrapeDoResponse [Status: ..., Proxy Error: ...]>`) for REPL inspection and log output. `__str__` falls back to `__repr__`.

- [`ScrapeDoResponse.to_dict`][scrape_do.models.response.ScrapeDoResponse.to_dict] and [`to_json`][scrape_do.models.response.ScrapeDoResponse.to_json] — flat dict / pretty-printed JSON of every public field. Excludes the wrapped [`httpx.Response`][] and originating [`PreparedScrapeDoRequest`][scrape_do.models.request.PreparedScrapeDoRequest] (recoverable via `httpx_response` / `request` attributes). Nested pydantic sub-models (`frames`, `network_requests`, `websocket_requests`, `action_results`, `screenshots`) are recursively serialized via `model_dump()`; empty lists render as `None`. `to_json` defaults to `indent=2, ensure_ascii=False`, overridable.

### Changed

- [`APIResponseError`][scrape_do.exceptions.APIResponseError] now uses [`ScrapeDoJSONErrorMessage.try_from_response`][scrape_do.exceptions.ScrapeDoJSONErrorMessage.try_from_response] for error-body extraction. The previous key-list parsing (`detail`, `Error`, `errorMessage`, `message`, `Message`) is replaced with the Scrape.do schema. The "Unknown API Error" fallback now reports status + body on separate lines.

- `requires-python = ">=3.9"` compatibility actually works: every source file that imported `Self` / `Unpack` / `TypeAlias` from `typing` (which are `3.11+` / `3.10+`) was migrated to [`typing_extensions`](https://typing-extensions.readthedocs.io/). Previously the package raised `ImportError` at import time on `3.9` / `3.10`.

- `Attributes:` block removed from the [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse] class docstring — Google-style places property documentation on each property's own docstring.

### Dependencies

- Added [`typing_extensions>=4.0`](https://typing-extensions.readthedocs.io/) as a direct runtime dependency.

## `0.2.0` — 2026-05-12

### Added

- [`ScrapeDoProxyClient`][scrape_do.proxy_client.ScrapeDoProxyClient] and [`AsyncScrapeDoProxyClient`][scrape_do.async_proxy_client.AsyncScrapeDoProxyClient] — route requests through Scrape.do's Proxy Mode (`proxy.scrape.do:8080`). Same request/response surface as the API-mode clients (`execute` / `request` / `get` / `post`), minus `execute_from_url` (no equivalent in proxy mode). The async variant is backed by [`httpx.AsyncClient`][] and uses `asyncio.sleep` for retry pauses.

- Per-(`api_token`, parameters) `httpx.Client` / `httpx.AsyncClient` pool with bounded LRU eviction (`max_pooled_clients=16` default, configurable). Two requests with the same parameters reuse the same TCP / TLS / HTTP-2 connection; the cookie jar on each pooled client is cleared after every request (Scrape.do owns the cookie lifecycle via `setCookies` / `scrape.do-cookies` / `sessionId`, so pooling is purely a transport concern).

- [`PreparedScrapeDoRequest.to_proxy_httpx_kwargs`][scrape_do.models.request.PreparedScrapeDoRequest.to_proxy_httpx_kwargs] — serializes the same data model into httpx kwargs that target the destination URL directly (the API token and Scrape.do parameters live in the proxy URL's userinfo segment, not the request).

- [`RequestParameters.to_proxy_url`][scrape_do.models.parameters.RequestParameters.to_proxy_url] — generates a `Scrape.do` Proxy-Mode connection string template (`http://{api_token}:<params>@proxy.scrape.do:8080`) for use with the proxy clients or with third-party tooling (Playwright / Selenium / curl).

- [`RequestParameters.validate_proxy_params`][scrape_do.models.parameters.RequestParameters.validate_proxy_params] — cross-validates Proxy-Mode-specific parameter quirks (`customHeaders` defaulting to true server-side, `setCookies` interaction, render-mode discouragement).

- [`SCRAPE_DO_CA_PATH`][scrape_do.constants.SCRAPE_DO_CA_PATH] and [`DEFAULT_PROXY_SSL_CONTEXT`][scrape_do.constants.DEFAULT_PROXY_SSL_CONTEXT] in `scrape_do.constants` — the bundled Scrape.do CA cert and an `ssl.SSLContext` preloaded with system CAs plus the bundled CA. Default `verify` source for the proxy-mode clients so HTTPS targets validate correctly through Scrape.do's MITM step without disabling TLS verification. `VERIFY_X509_STRICT` is cleared so chain validation accepts Scrape.do's self-signed root (which omits the optional AKI extension); all other verification checks remain intact.

- Scrape.do's CA certificate bundled with the wheel under `scrape_do.data` so the SDK ships everything needed for proxy-mode TLS verification.

- Public re-exports for [`ScrapeDoProxyClient`][scrape_do.proxy_client.ScrapeDoProxyClient] and [`AsyncScrapeDoProxyClient`][scrape_do.async_proxy_client.AsyncScrapeDoProxyClient] in [`scrape_do/__init__.py`](https://github.com/svdC1/scrape-do-python/blob/main/src/scrape_do/__init__.py).

- [`AsyncScrapeDoClient`][scrape_do.async_client.AsyncScrapeDoClient] backed by [`httpx.AsyncClient`][]. Near-1:1 of the synchronous client (smart routing, retry strategy, session validation, event hooks), with every IO-bound method `async`/`await`. Sleeps between retries use `asyncio.sleep` rather than `time.sleep`.

- [`AsyncClientEventHooks`][scrape_do.async_client.AsyncClientEventHooks] TypedDict and [`AsyncSessionValidator`][scrape_do.async_client.AsyncSessionValidator] type alias. Both are async-only — hooks return `Awaitable[None]` and validators return `Awaitable[bool]`, so they can perform I/O while the request executes.

- Public re-exports for [`AsyncScrapeDoClient`][scrape_do.async_client.AsyncScrapeDoClient], [`AsyncClientEventHooks`][scrape_do.async_client.AsyncClientEventHooks], and [`AsyncSessionValidator`][scrape_do.async_client.AsyncSessionValidator] in [`scrape_do/__init__.py`](https://github.com/svdC1/scrape-do-python/blob/main/src/scrape_do/__init__.py).

- [`ScrapeDoResponse.json(raw_response=True, **kwargs)`][scrape_do.models.response.ScrapeDoResponse.json] convenience method. With `raw_response=True` (default) it shortcuts to `httpx_response.json()`; with `raw_response=False` it returns `json.loads(self.text, **kwargs)` so the post-envelope path is reachable without manual parsing.

- Example block in the package-level docstring at [`src/scrape_do/__init__.py`](https://github.com/svdC1/scrape-do-python/blob/main/src/scrape_do/__init__.py) showcasing a typical request flow.

### Fixed

- [`ScrapeDoClient.post()`][scrape_do.client.ScrapeDoClient.post] now forwards the `session_validator` argument to [`request()`][scrape_do.client.ScrapeDoClient.request]. Previously the argument was accepted but silently ignored on POST calls. [`get()`][scrape_do.client.ScrapeDoClient.get] was unaffected.

[`0.2.0`](https://github.com/svdC1/scrape-do-python/releases/tag/v0.2.0)

## `0.1.1` — 2026-05-09

### Added

- Curated public re-exports in [`scrape_do/__init__.py`](https://github.com/svdC1/scrape-do-python/blob/main/src/scrape_do/__init__.py) so common imports work as `from scrape_do import ScrapeDoClient, RequestParameters, ...` rather than digging into submodules.
- `py.typed` PEP 561 marker so downstream type-checkers (`mypy`, `pyright`) consume the package's type hints.
- Trove classifiers in package metadata — PyPI's "Python" sidebar and shields.io's `pypi/pyversions` badge now populate correctly.

### Removed

- Empty `scrape_do/namespaces/` placeholder folder (was scaffolding from before the roadmap solidified; will be replaced by `plugins/` in `0.4+`).

### Documentation

- Planned package layout added to [`Roadmap`](roadmap.md)

[`0.1.1`](https://github.com/svdC1/scrape-do-python/releases/tag/v0.1.1)

## `0.1.0` — 2026-05-08

Initial release. Synchronous client surface.

### Added

- [`ScrapeDoClient`][scrape_do.client.ScrapeDoClient] synchronous client with [`request()`][scrape_do.client.ScrapeDoClient.request], [`get()`][scrape_do.client.ScrapeDoClient.get], [`post()`][scrape_do.client.ScrapeDoClient.post], [`execute()`][scrape_do.client.ScrapeDoClient.execute], and [`execute_from_url()`][scrape_do.client.ScrapeDoClient.execute_from_url] methods.

- Smart routing in [`ScrapeDoClient.request()`][scrape_do.client.ScrapeDoClient.request]: accepts kwargs, a pre-built [`RequestParameters`][scrape_do.models.parameters.RequestParameters], or a raw `api.scrape.do` URL — exactly one configuration shape per call.

- Automatic retries on Scrape.do gateway errors (`429` / `502` / `510`) with configurable backoff strategy (static `float` or `Callable`). Default is jittered exponential.

- [`session_validator`][scrape_do.client.SyncSessionValidator] callback for sticky-session rotation detection — when present and `session_id` is set, the validator decides whether to raise [`RotatedSessionError`][scrape_do.exceptions.RotatedSessionError].

- SDK-native event hooks via [`SyncClientEventHooks`][scrape_do.client.SyncClientEventHooks] TypedDict: `request` / `response` / `retry` lifecycle, distinct from `httpx` transport-level hooks.

- Pydantic-validated [`RequestParameters`][scrape_do.models.parameters.RequestParameters] covering the full Scrape.do API parameter surface, including [`browser-action models`](models/browser_actions.md).

- [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse] wrapper exposing the parsed JSON envelope, network requests, websocket frames, action results, screenshots, frames, plus a raw `status_code` passthrough.

- Cookie isolation between sequential requests on the underlying [`httpx.Client`][] (prevents cross-request bleed).

- Exception hierarchy: [`ScrapeDoError`][scrape_do.exceptions.ScrapeDoError] (base), [`APIConnectionError`][scrape_do.exceptions.APIConnectionError], [`TargetError`][scrape_do.exceptions.TargetError], [`RotatedSessionError`][scrape_do.exceptions.RotatedSessionError], plus the API-layer [`AuthenticationError`][scrape_do.exceptions.AuthenticationError], [`BadRequestError`][scrape_do.exceptions.BadRequestError], [`RateLimitError`][scrape_do.exceptions.RateLimitError], [`ServerError`][scrape_do.exceptions.ServerError], and [`AuthenticationThrottleError`][scrape_do.exceptions.AuthenticationThrottleError]

- Default request timeout raised to **60 seconds** (from `httpx`'s 5s default) to accommodate browser rendering and proxy round-trips.

[`0.1.0`](https://github.com/svdC1/scrape-do-python/releases/tag/v0.1.0)
