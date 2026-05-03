"""Type aliases, literals, and enumerations

Defines the static, permissible values for Scrape.do's various
configuration parameters. It ensures that IDEs and static analyzers can provide
strict autocomplete and validation for expected parameter values
"""

from __future__ import annotations
from typing import (
    TypeAlias,
    Literal
    )

RegionCodeType: TypeAlias = Literal[
    'europe',
    'asia'
    'africa'
    'oceania',
    'northamerica',
    'southamerica'
    ]
"""
Defines the valid strings that can be passed to the
`regional_geo_code` parameter in the `RequestParameters`
model
"""

WaitUntilType: TypeAlias = Literal[
    'domcontentloaded',
    'networkidle0',
    'networkidle2',
    'load'
    ]
"""
Defines the valid strings that can be passed to the
`wait_until` parameter in the `RequestParameters`
model
"""

DeviceType: TypeAlias = Literal[
    'desktop',
    'mobile',
    'tablet'
    ]
"""
Defines the valid strings that can be passed to the
`device` parameter in the `RequestParameters`
model
"""

OutputType: TypeAlias = Literal['raw', 'markdown']
"""
Defines the valid strings that can be passed to the
`output` parameter in the `RequestParameters`
model
"""

HttpMethod: TypeAlias = Literal[
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS"
    ]
"""
Defines the valid HTTP methods that can be passed to the
`method` parameter in the `PreparedScrapeDoRequest` model
"""

PayloadType: TypeAlias = Literal["json", "form", "raw"]
"""
Defines the valid types of payload that can be passed to the
`payload_type` parameter in the `PreparedScrapeDoRequest` model
"""
