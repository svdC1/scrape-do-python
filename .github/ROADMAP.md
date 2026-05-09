# Roadmap

Items may be reordered or rescoped based on user feedback and design discoveries.

## 0.2 — Async + Proxy Mode

### **`AsyncScrapeDoClient`**

> Very similar to the current synchronous client, backed by `httpx.AsyncClient`

> Same smart-routing, validator, and event-hook semantics with `async`/`await`.

### **`ScrapeDoProxyClient`** + **`AsyncScrapeDoProxyClient`**

> Wraps [`Scrape.do's Proxy Mode`](https://scrape.do/documentation/proxy-mode/) at `proxy.scrape.do`, instead of the current API mode.

> Reuses the existing `RequestParameters` data models

> Differs in URL construction and client-level network handling.

## 0.3 — Scrape.do Async API

> Sub-package wrapping the [`Scrape.do Async API`](https://scrape.do/documentation/async-api/) at `q.scrape.do`.

> New data models for `job_id`, polling state, and result fetching.

> Unlike the in-process async client of 0.2, this targets Scrape.do's server-side async job queue.

## 0.4 — Google Plugin

> Sub-package wrapping [`Scrape.do's Google Scraper API`](https://scrape.do/documentation/google-scraper-api/) with new data models

## 0.5 — Amazon Plugin

> Sub-package wrapping [`Scrape.do's Amazon Scraper API`](https://scrape.do/documentation/amazon-scraper-api/) with new data models

## 1.0 — Surface Freeze

> Stabilize the public API across `sync`, `async`, `proxy`, `async-API`, and `plugin` namespaces.

> Post-1.0, breaking changes follow strict semver feature work targets minor bumps, breaking changes target a deprecation cycle.

## Planned Package Layout

> View [`Documentation Site Roadmap`](svdc1.github.io/scrape-do-python/roadmap/)

## Suggestions Are Welcome

> If a feature you need isn't here, open a [`Feature   Request`](https://github.com/svdC1/scrape-do-python/issues/new?template=feature_request.md)
