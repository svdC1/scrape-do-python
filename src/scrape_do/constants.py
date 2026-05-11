"""
Defines constants with valid parameter values expected by the Scrape.do API
and runtime resources bundled with the package (e.g. Scrape.do's CA cert).

Attributes:
    _SUPER_SUPPORTED_COUNTRIES (set[str]): The complete list of ISO 3166-1
        alpha-2 country codes supported when `super=True`.

    _DATACENTER_SUPPORTED_COUNTRIES (set[str]): The restricted list of ISO
        3166-1 alpha-2 country codes supported when `super=False`.

    _ZIPCODE_FORMATS (dict[str, re.Pattern]): Pre-compiled regular expressions
        mapping lowercase country codes to their strict regional postal code
        formats.

    _SUPER_ONLY_COUNTRIES (set[str]): ISO 3166-1 alpha-2 country codes
        supported only when `super=True`

    _ZIPCODE_ALLOWED_COUNTRIES (set[str]): Set of country codes for which the
        `postal_code` parameter is allowed

    _ZIPCODE_NOT_ALLOWED_COUNTRIES (set[str]): Set of country codes for which
        the `postal_code` parameter is not allowed

    SCRAPE_DO_CA_PATH (str): Filesystem path to Scrape.do's bundled CA
        certificate, used by `DEFAULT_PROXY_SSL_CONTEXT` and exposed for
        third-party tooling that needs to trust the same root.

    DEFAULT_PROXY_SSL_CONTEXT (ssl.SSLContext): Default SSL context used by
        the proxy-mode clients. Loads system CAs plus Scrape.do's bundled
        CA so HTTPS targets validate through Scrape.do's MITM step.
"""

import re
import ssl
from importlib.resources import files


_SUPER_SUPPORTED_COUNTRIES = {
    "ad", "ae", "af", "ag", "al", "am", "ao", "ar", "as", "at",
    "au", "aw", "az", "ba", "bb", "bd", "be", "bf", "bg", "bh",
    "bi", "bj", "bm", "bn", "bo", "br", "bs", "bt", "bw", "by",
    "bz", "ca", "cd", "cf", "cg", "ch", "ci", "cl", "cm", "cn",
    "co", "cr", "cu", "cv", "cy", "cz", "de", "dj", "dk", "dm",
    "do", "dz", "ec", "ee", "eg", "er", "es", "et", "fi", "fj",
    "fm", "fr", "ga", "gb", "gd", "ge", "gh", "gi", "gm", "gn",
    "gq", "gr", "gt", "gu", "gw", "gy", "hk", "hn", "hr", "ht",
    "hu", "id", "ie", "il", "in", "iq", "ir", "is", "it", "jm",
    "jo", "jp", "ke", "kg", "kh", "ki", "km", "kn", "kp", "kr",
    "kw", "ky", "kz", "la", "lb", "lc", "li", "lk", "lr", "ls",
    "lt", "lu", "lv", "ly", "ma", "mc", "md", "me", "mg", "mh",
    "mk", "ml", "mm", "mn", "mo", "mq", "mr", "mt", "mu", "mv",
    "mw", "mx", "my", "mz", "na", "ne", "ng", "ni", "nl", "no",
    "np", "nr", "nz", "om", "pa", "pe", "pg", "ph", "pk", "pl",
    "pr", "pt", "pw", "py", "qa", "ro", "rs", "ru", "rw", "sa",
    "sb", "sc", "sd", "se", "sg", "si", "sk", "sl", "sn", "so",
    "sr", "ss", "st", "sv", "sy", "sz", "td", "tg", "th", "tj",
    "tl", "tm", "tn", "to", "tr", "tt", "tv", "tw", "tz", "ua",
    "ug", "us", "uy", "uz", "vc", "ve", "vg", "vi", "vn", "vu",
    "ws", "ye", "za", "zm", "zw"
    }


_DATACENTER_SUPPORTED_COUNTRIES = {
    "ae", "al", "ar", "at", "au", "br", "ca", "ch", "cl", "cn",
    "cr", "cy", "cz", "de", "dk", "ee", "eg", "es", "fi", "fr",
    "gb", "gr", "hr", "ie", "it", "jp", "lt", "lv", "mt", "nl",
    "no", "pk", "pl", "pt", "ro", "rs", "ru", "se", "sg", "si",
    "sk", "tr", "ua", "us", "za"
    }

_ZIPCODE_FORMATS = {
    "us": re.compile(r"^\d{5}$"),
    "gb": re.compile(r"^[A-Z0-9\s]{2,8}$", re.IGNORECASE),
    "de": re.compile(r"^\d{5}$"),
    "fr": re.compile(r"^\d{5}$"),
    "ca": re.compile(r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$", re.IGNORECASE),
    "au": re.compile(r"^\d{4}$"),
    "in": re.compile(r"^\d{6}$"),
    "nl": re.compile(r"^\d{4}[A-Z]{2}$", re.IGNORECASE),
    "it": re.compile(r"^\d{5}$"),
    "es": re.compile(r"^\d{5}$"),
    "br": re.compile(r"^(\d{5}|\d{8})$"),
    "jp": re.compile(r"^\d{3}-?\d{4}$")
    }

_SUPER_ONLY_COUNTRIES = {c for c in _SUPER_SUPPORTED_COUNTRIES
                         if c not in _DATACENTER_SUPPORTED_COUNTRIES
                         }

_ZIPCODE_ALLOWED_COUNTRIES = set(_ZIPCODE_FORMATS.keys())

_ZIPCODE_NOT_ALLOWED_COUNTRIES = {c for c in _SUPER_SUPPORTED_COUNTRIES
                                  if c not in _ZIPCODE_ALLOWED_COUNTRIES
                                  }


# --- Bundled runtime resources ---


SCRAPE_DO_CA_PATH: str = str(files("scrape_do.data") / "scrapedo_ca.crt")
"""Filesystem path to Scrape.do's bundled CA certificate.

The cert is shipped under the `scrape_do.data` package so it travels with
the wheel; resolved at import time via `importlib.resources.files()`.

tip: Use Cases
    - Default `verify` source for the proxy-mode clients (see
      [`DEFAULT_PROXY_SSL_CONTEXT`][scrape_do.constants.DEFAULT_PROXY_SSL_CONTEXT]).

    - Configuring third-party tooling (e.g. Selenium / Playwright) to
      trust Scrape.do's MITM cert when using proxy mode.

    - Mirroring the SDK's default proxy-mode TLS behavior in custom HTTP
      clients.
"""


def _build_default_proxy_ssl_context() -> ssl.SSLContext:
    """Builds the module-level `DEFAULT_PROXY_SSL_CONTEXT` singleton.

    Returns:
        An `ssl.SSLContext` configured with system CAs plus Scrape.do's
            bundled CA loaded via `SCRAPE_DO_CA_PATH`.
    """
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=SCRAPE_DO_CA_PATH)
    return ctx


DEFAULT_PROXY_SSL_CONTEXT: ssl.SSLContext = _build_default_proxy_ssl_context()
"""SSL context loaded with system CAs plus Scrape.do's bundled CA.

Used as the default `verify` value on
[`ScrapeDoProxyClient`][scrape_do.proxy_client.ScrapeDoProxyClient] and
[`AsyncScrapeDoProxyClient`][scrape_do.async_proxy_client.AsyncScrapeDoProxyClient]
so HTTPS targets validate correctly through Scrape.do's MITM step without
forcing users to disable TLS verification.

tip: Overriding The Default
    - `verify=True` &rarr; system CAs only (for users who've installed
      Scrape.do's CA into their OS keychain).

    - `verify=False` &rarr; disable TLS verification entirely (discouraged).

    - `verify=<path>` or `verify=<ssl.SSLContext>` &rarr; custom certificate
      bundle or context for mutual-TLS / corporate CAs.

warning: Shared Instance
    - This context is process-shared and treated as immutable

    - Safe to assign as the default in client constructors

    - Mutating it (loading additional locations, changing verify-mode, etc.)
      affects every proxy client instance constructed afterwards.
"""
