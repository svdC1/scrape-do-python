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

## Planned Package Layout

???+ warning "*Speculative*"
    - A starting point, not a commitment
    
    - Each milestone may surface design constraints that justify deviation
    
    - Version slots above are firmer than the file paths below

```yaml title="File Structure"
src/scrape_do/
│
├─ __init__.py  # (1)!
├─ py.typed  # (2)!
├─ exceptions.py  # (3)!
├─ constants.py
├─ abc.py
│
│ # (4)!
├─ client.py  # (5)!
├─ async_client.py # (6)!
├─ proxy_client.py # (7)!
├─ async_proxy_client.py # (8)!
├─ models/ # (9)!
│
├─ async_api/ # (10)!
│  │
│  ├─ __init__.py
│  ├─ client.py
│  ├─ async_client.py
│  ├─ models/ # (11)!
│  └─ exceptions.py # (12)!
│
│
└─ plugins/ # (13)!
   │
   ├─ __init__.py
   ├─ google/ # (14)!
   │  │
   │  ├─ __init__.py
   │  ├─ client.py
   │  ├─ async_client.py
   │  └─ models/ # (15)!
   │
   └─ amazon/        
      │    
      ├─ __init__.py 
      ├─ client.py
      ├─ async_client.py
      └─ models/ # (16)!
```

1. Curated Public Re-Exports
2. PEP 561 Marker
3. Base Hierarchy (sub-packages may extend)
4. `0.1` + `0.2` - api.scrape.do + proxy.scrape.do 
5. ScrapeDoClient (sync, api.scrape.do) — `0.1`
6. AsyncScrapeDoClient — `0.2`
7. ScrapeDoProxyClient (proxy.scrape.do) — `0.2`
8. AsyncScrapeDoProxyClient — `0.2`
9. Request / Response models for the four above
10. `0.3` - q.scrape.do — Different API surface (server-side job queue)
11. `job_id`, `polling`, `results`, ...
12. Queue-Specific (if needed)
13. `0.4` + `0.5` - Each plugin is a sub-package
14. `0.4`
15. Search-Specific
16. Product/Listing-Specific
    
---

## Suggestions Are Welcome

???+ tip "Influence The Roadmap"
    - If a feature you need isn't here, open a [`Feature Request`](https://github.com/svdC1/scrape-do-python/issues/new?template=feature_request.md)
    
    - The roadmap reorders based on what real users need
