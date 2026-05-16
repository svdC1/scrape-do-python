from mkdocs.config.defaults import MkDocsConfig


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """
    This hook enables the `auto-refs` mkdocs plugin to
    automatically link `httpx` objects to their respective page
    in the library's documentation website.

    Currently, `httpx` does not provide a `objects.inv` file for its
    documentation, so the pages specified here are manually selected
    with the intention of facilitating access to the relevant information
    about the objects.

    Args:
        config (MkDocsConfig): The current MKDocs configuration object

    Returns:
        MkDocsConfig: The altered MKDocs configuration object
    """

    autorefs = config.plugins.get("autorefs")
    base_url = "https://www.python-httpx.org"

    # Manually map objects to their respective pages
    httpx_mappings = {
        "httpx.Client": "/api/#client",
        "httpx.AsyncClient": "/api/#asyncclient",
        "httpx.Response": "/api/#response",
        "httpx.Request": "/api/#request",
        "httpx.URL": "/api/#url",
        "httpx.Proxy": "/api/#proxy",
        "httpx.Headers": "/api/#headers",
        "httpx.Cookies": "/api/#cookies",
        "httpx.request": "/api/#helper-functions",
        "httpx.RequestError": "/exceptions/#exception-classes",
        "httpx.Timeout": "/advanced/timeouts/",
        "httpx._types.CertTypes": "/advanced/ssl/",
        "httpx._types.TimeoutTypes": "/advanced/timeouts/",
        "httpx._types.RequestExtensions": "/advanced/extensions",
        "httpx.BaseTransport": "/advanced/transports/",
        "httpx.AsyncBaseTransport": "/advanced/transports/",
        "httpx.Limits": "/advanced/resource-limits/",
        "httpx._client.UseClientDefault": "/api/#client",
        "httpx._config.DEFAULT_LIMITS": "/api/#client",
        "httpx._client.USE_CLIENT_DEFAULT": "/api/#client"
    }

    # Register external urls for autorefs
    for identifier, url in httpx_mappings.items():
        autorefs.register_url(identifier, base_url + url)

    return config
