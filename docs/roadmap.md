# Roadmap

???+ warning "*This Document Might Change*"
    *Items may be reordered or rescoped based on user feedback and design discoveries.*
---

## 0.2 — Async + Proxy Mode

!!! abstract "Status &rarr; `Planned`"

- Next Minor

- No Change To The Existing Sync API Surface

### `AsyncScrapeDoClient`

- Very similar to the current synchronous client, backed by [`httpx.AsyncClient`](https://www.python-httpx.org/async/)

- Same smart-routing, validator, and event-hook semantics, with `async` / `await`

### `ScrapeDoProxyClient` + `AsyncScrapeDoProxyClient`

- Wraps [`Scrape.do's Proxy Mode`](https://scrape.do/documentation/proxy-mode/) at `proxy.scrape.do`, instead of the current  API mode.

- Reuses the existing [`RequestParameters`][scrape_do.models.RequestParameters] data models.

- Differs in URL construction and client-level network handling.

---

## 0.3 — Scrape.do Async API

!!! abstract "Status &rarr; `Planned`"

- Sub-package wrapping the [`Scrape.do Async API`](https://scrape.do/documentation/async-api/) at `q.scrape.do`

- New data models for `job_id`, `polling state`, and `result fetching`

- Unlike the in-process async client of 0.2, this targets Scrape.do's `server-side async job queue`

---

## 0.4 — Google Plugin

!!! abstract "Status &rarr; `Planned`"

- Sub-package wrapping [`Scrape.do's Google Scraper API`](https://scrape.do/documentation/google-scraper-api/) with new data models specific to search/results.

---

## 0.5 — Amazon Plugin

!!! abstract "Status &rarr; `Planned`"

- Sub-package wrapping [`Scrape.do's Amazon Scraper API`](https://scrape.do/documentation/amazon-scraper-api/) with new data models specific to product/listing data.

---

## 1.0 — Surface Freeze

???+ success "Stability Commitment"
    - Stabilize the public API across `sync`, `async`, `proxy`, `async-API`, and `plugin` namespaces
    
    - Post-1.0, breaking changes follow strict [`Semantic Versioning`](https://semver.org/)

---

## Suggestions Are Welcome

???+ tip "Influence The Roadmap"
    - If a feature you need isn't here, open a [`Feature Request`](https://github.com/svdC1/scrape-do-python/issues/new?template=feature_request.md)
    
    - The roadmap reorders based on what real users need
