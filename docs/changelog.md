# Changelog

???+ warning "`Pre-1.0` Disclaimer"
    `scrape-do-python` follows [`Semantic Versioning`](https://semver.org/spec/v2.0.0.html), but `0.x` minor versions may contain breaking changes

???+ abstract "Format"
    The format below is based on [`Keep a Changelog`](https://keepachangelog.com/en/1.1.0/)

---

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
