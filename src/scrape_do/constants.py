"""
Defines constants with valid parameter values expected by the Scrape.do API

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
"""

import re


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
