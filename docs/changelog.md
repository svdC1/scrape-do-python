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

- `hasattr` guard for `ssl.VERIFY_X509_STRICT` just in case the OpenSSL backend doesn't expose it.

### Changed

- [`APIResponseError`][scrape_do.exceptions.APIResponseError] now uses [`ScrapeDoJSONErrorMessage.try_from_response`][scrape_do.exceptions.ScrapeDoJSONErrorMessage.try_from_response] for error-body extraction. The previous key-list parsing (`detail`, `Error`, `errorMessage`, `message`, `Message`) is replaced with the Scrape.do schema. The "Unknown API Error" fallback now reports status + body on separate lines.

- `requires-python = ">=3.9"` compatibility actually works: every source file that imported `Self` / `Unpack` / `TypeAlias` from `typing` (which are `3.11+` / `3.10+`) was migrated to [`typing_extensions`](https://typing-extensions.readthedocs.io/). Previously the package raised `ImportError` at import time on `3.9` / `3.10`.

- `Attributes:` block removed from the [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse] class docstring — Google-style places property documentation on each property's own docstring.

- [`ScrapeDoResponse.json(raw_response=False)`][scrape_do.models.response.ScrapeDoResponse.json] now extracts and parses the `content` key from the Scrape.do JSON envelope when present, falling back to `httpx.Response.json()` otherwise. The previous implementation always called `json.loads(self.text)`, which failed when `text` was HTML (e.g., `return_json=False`).

- README + docs landing page replaced the hardcoded `v0.1.0 — Early but functional` status callout with a [`Changelog`](changelog.md) pointer so the status doesn't go stale every release.

- `mkdocs.yml` now includes the [`typing-extensions`](https://typing-extensions.readthedocs.io/) inventory so docs cross-references to `Self` / `TypeAlias` / `Unpack` resolve.

### Fixed

- [`ScrapeDoFrame.url`][scrape_do.models.response.ScrapeDoFrame] and [`ScrapeDoNetworkRequest.url`][scrape_do.models.response.ScrapeDoNetworkRequest] relaxed from [`HttpUrl`][pydantic.HttpUrl] to `str`. These fields report URLs that Scrape.do observed on the rendered target page; real-world iframes / network calls produce technically-valid-but-quirky URLs (e.g., embeds with `?feature=oembed?wmode=transparent`) that pydantic-core's URL parser rejected, blowing up the whole response parse. The outbound [`RequestParameters.url`][scrape_do.models.parameters.RequestParameters] keeps `HttpUrl` since validation there is load-bearing.

- [`ScrapeDoResponse.cookies`][scrape_do.models.response.ScrapeDoResponse.cookies] regex no longer captures the structural whitespace after `; ` separators in the `scrape.do-cookies` header. The second-and-later cookie names previously came back with a phantom leading space (`{" user": "alice"}`). Captures themselves still preserve content verbatim.

- [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse] constructor: removed a duplicated unguarded `response.json()` call that bypassed the surrounding `try / except ValueError`. When `return_json=True` and Scrape.do crashed and returned HTML instead, the constructor used to crash with `JSONDecodeError` before [`is_proxy_error`][scrape_do.models.response.ScrapeDoResponse.is_proxy_error] could route the failure as a [`ServerError`][scrape_do.exceptions.ServerError].

- [`RequestParameters.to_proxy_url`][scrape_do.models.parameters.RequestParameters.to_proxy_url] now double-encodes the param string. [`httpx`](https://www.python-httpx.org/) transparently URL-decodes the proxy password during Basic auth header construction, so values with URL-reserved characters (notably the JSON-string `playWithBrowser` payload) used to arrive at Scrape.do unencoded and get fragmented by Scrape.do's `&` / `=` parser. Wrapping `urlencode`'s output in `quote(..., safe="=&")` preserves the `key=value&key=value` framing while escaping percent-encoded values one more time so `httpx`'s single decode round-trips back to canonical single-encoded form. Surfaced by the proxy-mode render integration tests.

### Dependencies

- Added [`typing_extensions>=4.0`](https://typing-extensions.readthedocs.io/) as a direct runtime dependency.

### Tests

- Integration test logging restructured. Pytest hooks emit `---> START` / `<--- PASS|FAIL|SKIPPED` boundaries tagged with `nodeid`; format collapsed from 4-line-per-entry blocks to single lines prefixed with `[<nodeid>]` driven by a [`ContextVar`][contextvars.ContextVar] + [`logging.Filter`][logging.Filter]. The `_validate_and_log_error_state` helper (previously duplicated across two test files and absent from the two proxy ones) consolidated into a `response_trace` fixture in `tests/integration/conftest.py`; the helper now uses [`ScrapeDoJSONErrorMessage.try_from_response`][scrape_do.exceptions.ScrapeDoJSONErrorMessage.try_from_response] instead of the stale hardcoded error-key list (`message` / `Error` / `detail` / `errorMessage` / `Message`).

- Integration coverage expanded from 22 → ~60 tests across all four client variants. New classes: `TestLiveResponseParsing` (every telemetry property, target-vs-scrape-do header filtering, cookie extraction, [`to_dict`][scrape_do.models.response.ScrapeDoResponse.to_dict] serialization), `TestLiveRenderEnvelope` (one full render + `return_json=true` smoke test per client), `TestLiveExceptionRouting` (bad-token → [`AuthenticationError`][scrape_do.exceptions.AuthenticationError], transparent 4xx → [`TargetError`][scrape_do.exceptions.TargetError], transparent 429 → [`TargetError(is_throttled=True)`][scrape_do.exceptions.TargetError], live [`ScrapeDoJSONErrorMessage`][scrape_do.exceptions.ScrapeDoJSONErrorMessage] schema check). Five missing parity tests added per proxy client.

- Unit test fixtures refactored. `mock_env_vars` (referenced 137× purely to clear `SCRAPE_DO_API_KEY`) renamed to `_clear_api_token_env` and made autouse function-scoped, removing all explicit references. `mock_headers` renamed to `full_scrape_do_telemetry_headers` with a new `telemetry_headers_subset` factory. `make_response` expanded with `scrape_do_headers` / `target_headers` kwargs. New `make_scrape_do_response(status_code, request_kwargs=None, **response_kwargs)` factory yields a ready-to-assert [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse] in one call. Fixtures reorganized by section (helpers → factories → autouse env → time mocks → sync → async).

- [`models/response.py`][scrape_do.models.response] lifted to 100% line coverage (was 97.04%). New tests cover the [`JSONDecodeError`][json.JSONDecodeError] swallow path when `return_json=true` returns HTML, the `request` property's identity passthrough, the `pure_cookies=True` jar branch, the unparseable `scrape.do-cookies` header → `None` branch, and the `json(raw_response=False)` envelope-without-`content` fallback. [`exceptions.py`][scrape_do.exceptions] empty-`messages` branch on [`ScrapeDoJSONErrorMessage.__str__`][scrape_do.exceptions.ScrapeDoJSONErrorMessage] also covered.

- `# pragma: no cover` annotation on the unreachable `raise RuntimeError("Execution loop exhausted...")` fallthrough at the bottom of every client's `execute()` loop. Unreachable for any non-negative `max_retries` — the for-loop always returns inside or raises on the final [`RequestError`][httpx.RequestError].

### CI

- `ci.yml` split into two jobs: `lint` (ruff + mypy, Python 3.13 only) and `test` (unit tests across a Python `3.9` / `3.10` / `3.11` / `3.12` / `3.13` matrix with `fail-fast: false`). Codecov uploads gated on `matrix.python-version == '3.13'` to avoid 5× duplicate submissions. `publish` job now gated on both `lint` and `test` so all five Python versions must pass before PyPI publishes. `docs.yml` and `integration_tests.yml` stay pinned to `3.13`.

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
