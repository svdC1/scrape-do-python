[![PyPI](https://img.shields.io/pypi/v/scrape-do-python?style=flat&logo=pypi&logoColor=white)](https://pypi.org/project/scrape-do-python/)
[![Python](https://img.shields.io/pypi/pyversions/scrape-do-python?style=flat&logo=python&logoColor=white)](https://pypi.org/project/scrape-do-python/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-lightgrey?style=flat&logo=materialformkdocs&logoColor=black&logoSize=auto)](https://svdc1.github.io/scrape-do-python)
[![codecov](https://img.shields.io/codecov/c/github/svdC1/scrape-do-python?flag=unit&style=flat&logo=codecov&label=unit)](https://app.codecov.io/gh/svdC1/scrape-do-python?flags%5B0%5D=unit)
[![codecov](https://img.shields.io/codecov/c/github/svdC1/scrape-do-python?flag=integration&style=flat&logo=codecov&label=integration)](https://app.codecov.io/gh/svdC1/scrape-do-python?flags%5B0%5D=integration)

# scrape-do-python

A Python SDK for the [`Scrape.do`](https://scrape.do) web-scraping proxy API.

Built on [`httpx`](https://github.com/encode/httpx) and [`pydantic v2`](https://github.com/pydantic/pydantic), with strict request validation, automatic retries on gateway errors, sticky-session validation, and SDK-native lifecycle hooks.

## Status
> `v0.1.0` &rarr; Early but functional

> Synchronous client is shipped

> Async and Proxy-Mode clients are on the [`Roadmap`](.github/ROADMAP.md)

> Breaking changes are possible between `0.x` minor versions.

## Installation

```bash
pip install scrape-do-python
```

## Quickstart

```python
from scrape_do.client import ScrapeDoClient

# API Token pulled from SCRAPE_DO_API_KEY env variable
# Can also be provided via 'api_token' argument

with ScrapeDoClient() as client:
    response = client.get(
        "https://example.com",
        super=True,
        render=True,
        return_json=True,
        show_frames=True,
        )
    
    print(response.is_proxy_error)

    print(response.frames[0].url)
    
    print(response.remaining_credits)
```

## Features

### Type-Checked Request Parameters

Request parameters are fully type-checked and automatically validated via the [`RequestParameters`](https://svdc1.github.io/scrape-do-python/models/parameters/#scrape_do.models.parameters.RequestParameters) pydantic model

### Smart Routing
[`ScrapeDoClient.request()`](https://svdc1.github.io/scrape-do-python/client/#scrape_do.client.ScrapeDoClient.request) accepts either `**api_kwargs`, a pre-built `RequestParameters`, or a raw `api.scrape.do` URL for request parameters

### Automatic Retries

[`ScrapeDoClient`]((https://svdc1.github.io/scrape-do-python/client/#scrape_do.client.ScrapeDoClient.session_validator)) can automatically retry requests on Scrape.do gateway errors (`429` / `502` / `510`) with `customizable backoff` (static or callable) 

### Sticky-Session Validation

Supply a [`session_validator`](https://svdc1.github.io/scrape-do-python/client/#scrape_do.client.SyncSessionValidator) callback to detect proxy node rotations and raise [`RotatedSessionError`](https://svdc1.github.io/scrape-do-python/exceptions/#scrape_do.exceptions.RotatedSessionError)

### SDK-Native Event Hooks

[`request / response / retry`](https://svdc1.github.io/scrape-do-python/client/#scrape_do.client.SyncClientEventHooks) lifecycle hooks, distinct from httpx's transport-level hooks.

### Strongly-Typed Responses

[`ScrapeDoResponse`](https://svdc1.github.io/scrape-do-python/models/response/#scrape_do.models.response.ScrapeDoResponse) exposes the parsed JSON envelope, browser action results, screenshots, and network/websocket logs.

### Browser Automation

Pydantic models for [`Browser Actions`](https://svdc1.github.io/scrape-do-python/models/browser_actions/) providing validation and type-hinting for the `playWithBrowser` API parameter

## Documentation

[`Full API Reference`](https://svdc1.github.io/scrape-do-python)

## Roadmap

See [`ROADMAP`](.github/ROADMAP.md) for the upcoming `Async Client`, `Proxy-Mode Clients`, `Async-API Support`, and `Plugin Support`

## Contributing

Pull Requests, Bug Reports, and Feature Requests are all welcome.

See [`CONTRIBUTING`](.github/CONTRIBUTING.md) for local setup, test commands, and PR conventions

## Community

Participation is governed by our [`Code of Conduct`](.github/CODE_OF_CONDUCT.md). To privately report a security issue, see the [`Security Policy`](.github/SECURITY.md).

## License

`scrape-do-python` is released under the [`MIT License`](LICENSE)
