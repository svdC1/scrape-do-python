# Contributing

Thanks for your interest in `scrape-do-python`.

This page covers `local setup`, the `test/lint pipeline`, the `docs build`, and `PR conventions`.

??? info "Code of Conduct"
    By participating in this project you agree to abide by the [`Code of Conduct`](https://github.com/svdC1/scrape-do-python/blob/main/.github/CODE_OF_CONDUCT.md)
---

## Local Setup

```bash
git clone https://github.com/svdC1/scrape-do-python.git
cd scrape-do-python
pip install -e .[dev]
```

???+ note "Python Versions"
    - Requires Python `3.9+`
    - Unit tests run on a matrix of `3.9` / `3.10` / `3.11` / `3.12` / `3.13`
    - Lint, type-checking, and integration tests run on `3.13`

---

## Running Tests

=== "Unit"
    - Runs on Every `Push` and `PR`

    - Uses [`respx`](https://lundberg.github.io/respx/) to mock HTTP calls

    - They're fast and don't need any external dependencies

    ```bash
    pytest tests/unit/ --cov
    ```

    ???+ tip "Single-Test Invocation"
        ```bash
        pytest tests/unit/test_client.py::TestName -k pattern
        ```

=== "Integration"
    - Live tests against the real Scrape.do API.

    ```bash
    pytest tests/integration/ --cov
    ```

    ???+ warning "Requires `SCRAPE_DO_API_KEY`"
        - Integration tests are **skipped** if `SCRAPE_DO_API_KEY` is not set in the environment
        
        - CI provides it via repo secrets
        
        - For local runs, make sure to export it first

    ???+ note "Test target"
        - Defaults to `https://httpbin.co` (Scrape.do's documented playground target)
        
        - Override by setting the `HTTPBIN_BASE` environemnt variable to a different URL

???+ warning "PRs"
    - **Both** the `unit` and `integration` suites must pass for a PR to be merged
    - CI runs both on every PR

---

## Lint & Type-Check

```bash
ruff check .
mypy src/
```

???+ warning "CI Gate"
    - Both [`ruff`](https://docs.astral.sh/ruff/) and [`mypy`](https://mypy-lang.org/) must pass.
    - This project aims to ship strict typing, so try not to `# type: ignore` unless you've exhausted alternatives

---

## Documentation

```bash
pip install -e .[docs]
mkdocs serve
```

The docs site is built with [`mkdocs-material`](https://squidfunk.github.io/mkdocs-material/) and auto-generates the API reference from docstrings via [`mkdocstrings`](https://mkdocstrings.github.io/)

!!! tip "Keep The API Reference Updated"
    - New public symbols should ship with a [`Google-Style Docstring`](https://google.github.io/styleguide/pyguide.html) in the source.
    
    - [`mkdocstrings`](https://mkdocstrings.github.io/) picks them up automatically to build the documentation

---

## Pull Request Guidelines

- One concern per PR

- Refactors and feature additions belong in separate PRs from bug fixes

- Add `unit` tests for any new SDK behaviour or bug fix

- Integration tests are reserved for changes that interact with `Scrape.do`'s actual gateway behavior

- Update [`CHANGELOG`](changelog.md) under a `## [Unreleased]` section (create the section if it doesn't exist)

- One bullet under `### Added` / `### Changed` / `### Fixed` / `### Removed` as appropriate

- Update docstrings to keep this site's documentation updated

??? question "CHANGELOG Entries"
    - `Pre-1.0`, the `CHANGELOG` is the only source of truth for "what changed and why" between releases
    
    - PR titles and commit messages are searchable but not consolidated
    
    - `CHANGELOG` is meant to provide users with relevant information about changes so that they can decide whether or not to upgrade

---

## Reporting Bugs / Requesting Features

???+ tip "Use Templates"

    - :material-bug: [`Bug Report`](https://github.com/svdC1/scrape-do-python/issues/new?template=bug_report.md)
    - :material-lightbulb-on: [`Feature Request`](https://github.com/svdC1/scrape-do-python/issues/new?template=feature_request.md)

???+ note "Security Issues"
    - Don't open a public issue for security issues
    
    - See the [`Security Policy`](https://github.com/svdC1/scrape-do-python/blob/main/.github/SECURITY.md) for private reporting channels.
