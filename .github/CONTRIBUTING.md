# Contributing

Thanks for your interest in `scrape-do-python`. This guide covers local setup, running checks, and PR conventions.

> By participating in this project you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Local setup

```bash
git clone https://github.com/svdC1/scrape-do-python.git
cd scrape-do-python
pip install -e .[dev]
```

> *Requires Python 3.9+*

> *Unit tests run on a matrix of 3.9 / 3.10 / 3.11 / 3.12 / 3.13; lint and integration tests run on 3.13*

## Running tests

```bash
# Unit Tests
pytest tests/unit/ --cov
# Integration Tests - Requires SCRAPE_DO_API_KEY in ENV
pytest tests/integration/ --cov
```

### Unit Tests
> [`respx`](https://lundberg.github.io/respx/) is used to mock HTTP requests

> CI runs them on every push

---
### Integration Tests
> Hits the real `Scrape.do API` 

> Skipped if `SCRAPE_DO_API_KEY` is not set

> Defaults to `https://httpbin.co` as the test target

> Test target can be changed by setting the `HTTPBIN_BASE` enviroment variable

### PRs
> **Integration** + **Unit** tests must pass for PR to be accepted. CI runs both on every PR

---
### Single Test Invocation
```bash
pytest tests/unit/test_client.py::TestName -k pattern
```

## Lint & type-check

```bash
ruff check .
mypy src/
```

Both must pass for a PR to be accepted. CI runs them on every push.

## Documentation

```bash
pip install -e .[docs]
mkdocs serve
```

- Docs are built with [`mkdocs-material`](https://squidfunk.github.io/mkdocs-material/) and auto-generate the API reference from docstrings via [`mkdocstrings`](https://mkdocstrings.github.io/).

- New public symbols should ship with a **Google-style docstring**

## Pull Request Guidelines

- One concern per PR.

- Refactors and feature additions belong in separate PRs from bug fixes.

- Add unit tests for any new SDK behavior or bug fix.

- Integration tests are reserved for changes that interact with Scrape.do's actual gateway behavior.

- Update `CHANGELOG.md` under a `## [Unreleased]` section (create the section if it doesn't exist).

- One bullet under `### Added` / `### Changed` / `### Fixed` / `### Removed` as appropriate.

- Update docstrings accordingly — the docs site is generated from them.


## Reporting Bugs / Requesting Features

### Issue Templates

- [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md)

- [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md)