# scrape-do-python

[![PyPI](https://img.shields.io/pypi/v/scrape-do-python?style=flat&logo=pypi&logoColor=white)](https://pypi.org/project/scrape-do-python/)
[![Python](https://img.shields.io/pypi/pyversions/scrape-do-python?style=flat&logo=python&logoColor=white)](https://pypi.org/project/scrape-do-python/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat)](https://github.com/svdC1/scrape-do-python/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-lightgrey?style=flat&logo=materialformkdocs&logoColor=black&logoSize=auto)](https://svdc1.github.io/scrape-do-python)
[![codecov](https://img.shields.io/codecov/c/github/svdC1/scrape-do-python?flag=unit&style=flat&logo=codecov&label=unit)](https://app.codecov.io/gh/svdC1/scrape-do-python?flags%5B0%5D=unit)
[![codecov](https://img.shields.io/codecov/c/github/svdC1/scrape-do-python?flag=integration&style=flat&logo=codecov&label=integration)](https://app.codecov.io/gh/svdC1/scrape-do-python?flags%5B0%5D=integration)

A Python SDK for the [`Scrape.do`](https://scrape.do) web-scraping proxy API.

Built on [`httpx`](https://github.com/encode/httpx) and [`pydantic v2`](https://github.com/pydantic/pydantic), with strict request validation, automatic retries on gateway errors, sticky-session validation, and SDK-native lifecycle hooks.

???+ info "Status"
    Check the [`Changelog`](changelog.md) for the latest changes and project status

---

## Installation

```bash
pip install scrape-do-python
```

???+ note "Requires Python 3.9+"
    - CI runs on Python `3.13`
    - Earlier `3.9` – `3.12` are supported but not tested yet

---

## Quickstart

???+ example "Making a Request"
    ```python
    from scrape_do import ScrapeDoClient
    
    # API token is pulled from the SCRAPE_DO_API_KEY env variable;
    # can also be provided via the api_token argument.
    
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

???+ tip "How It Works"
    [`client.get()`][scrape_do.client.ScrapeDoClient.get] routes the keyword arguments through Pydantic-validated [`RequestParameters`][scrape_do.models.parameters.RequestParameters], builds the proxied URL, executes through [`httpx`](https://www.python-httpx.org/), and wraps the result in a strongly-typed [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse].

---

## Features

=== "Typing And Validation"
    ???+ abstract "Type-Checked Request Parameters"
        Request parameters are fully type-checked and automatically validated via the [`RequestParameters`][scrape_do.models.parameters.RequestParameters] Pydantic model.
    
    ???+ abstract "Strongly-Typed Responses"
        [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse] exposes the parsed JSON envelope, browser action results, screenshots, and network/websocket logs as Pydantic models — no manual JSON spelunking.
    
    ???+ abstract "Browser Automation"
        Pydantic models for [Browser Actions](models/browser_actions.md) provide validation and type-hinting for the `playWithBrowser` API parameter.

=== "Client Features"
    ???+ abstract "Smart Routing"
        [`ScrapeDoClient.request()`][scrape_do.client.ScrapeDoClient.request] accepts either `**api_kwargs`, a pre-built `RequestParameters` object, or a raw `api.scrape.do` URL.

    ???+ abstract "Automatic Retries"
        The client retries Scrape.do gateway errors (`429` / `502` / `510`) with a configurable backoff strategy (static `float` or `Callable`). Default is jittered exponential.
    
    ???+ abstract "Sticky-Session Validation"
        Supply a [`session_validator`][scrape_do.client.SyncSessionValidator] callback to detect proxy node rotations and raise [`RotatedSessionError`][scrape_do.exceptions.RotatedSessionError] when your target's session state is lost.

    ???+ abstract "SDK-Native Event Hooks"
        [`request / response / retry`][scrape_do.client.SyncClientEventHooks] lifecycle hooks fire at the *logical* execution boundary, distinct from `httpx`'s transport-level hooks (which would fire on every retry attempt and corrupt telemetry).





---

## Additional Information

### Project
???+ tip "Status"
    - [`Roadmap`](roadmap.md) &rarr; What's Coming Next
   
    - [`Changelog`](changelog.md) &rarr; What's Already Shipped
   
???+ tip "How To Help"
    - [`Contributing`](contributing.md) &rarr; `Local Setup`, `PR Guidelines`, `Tests`

### Usage

#### Building and Sending a Request
???+ tip "The Basics"
    Start with [`RequestParameters`](models/parameters.md) and [`ScrapeDoClient`](client.md) for detailed information on how requests are sent and how parameter validation works.

#### Handling Request Responses

???+ tip "How To Use The Response Model" 
    [`ScrapeDoResponse`](models/response.md) walks through every field on the wrapper, including the parsed nested models for browser-action runs.

#### Browser Actions
???+ tip "Making Requests With The `playWithBrowser` Parameter"
    See [`Browser Actions`](models/browser_actions.md) for the full set of `Click` / `Wait` / `Fill` / `Execute` / `Screenshot` / `Scroll` models.

#### Errors
???+ tip "Learn How To Catch Specific Exceptions"
    [`Exceptions`](exceptions.md) covers the full hierarchy and which to catch when.
