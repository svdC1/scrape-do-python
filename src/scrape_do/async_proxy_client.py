"""Asynchronous HTTP client for `Scrape.do's Proxy Mode`.

Defines `AsyncScrapeDoProxyClient`, the asyncio-native version of
[`ScrapeDoProxyClient`][scrape_do.proxy_client.ScrapeDoProxyClient].
Configures `httpx.AsyncClient` instances with `Scrape.do's Proxy Mode`
endpoint (`proxy.scrape.do:8080`) and reuses the same
`retry / hook / validator` semantics as the API-mode async client.

Because Scrape.do encodes per-request parameters into the proxy URL's
password field, each unique (token, params) combination needs its own
`httpx.AsyncClient`. This module maintains a bounded LRU pool of clients
keyed on the formatted proxy URL — repeated requests with the same
params reuse the same `TCP / TLS / HTTP-2` connection state. An
`asyncio.Lock` guards the miss/eviction critical section so concurrent
coroutines don't race to construct redundant clients.
"""

import os
import asyncio
import logging
import ssl
from collections import OrderedDict
from pydantic import HttpUrl
from httpx import (
    AsyncClient,
    AsyncBaseTransport,
    Limits,
    RequestError
    )
from httpx._config import DEFAULT_LIMITS
from httpx._types import (
    TimeoutTypes,
    CertTypes,
    RequestExtensions
)
from httpx._client import (
    UseClientDefault,
    USE_CLIENT_DEFAULT
)

from typing import (
    Dict,
    Optional,
    Any,
    Union,
    Callable,
    Literal,
    )
from typing_extensions import Self, Unpack
from types import TracebackType
from .client import default_backoff_strategy
from .async_client import (
    AsyncSessionValidator,
    AsyncClientEventHooks,
)
from .constants import DEFAULT_PROXY_SSL_CONTEXT
from .models import (
    RequestParameters,
    PreparedScrapeDoRequest,
    ScrapeDoResponse,
    PayloadType,
    HttpMethod,
    RequestParametersDict
    )
from .exceptions import APIConnectionError, RotatedSessionError


logger = logging.getLogger("scrape_do")


class AsyncScrapeDoProxyClient:
    """Asynchronous HTTP client for `Scrape.do's Proxy Mode`.

    asyncio-native version of
    [`ScrapeDoProxyClient`][scrape_do.proxy_client.ScrapeDoProxyClient],
    backed by `httpx.AsyncClient`. Routes requests through
    `proxy.scrape.do:8080` instead of calling `api.scrape.do` directly.
    Reuses the same
    [`RequestParameters`][scrape_do.models.parameters.RequestParameters]
    model, the same retry strategy, the same async event hooks
    ([`AsyncClientEventHooks`][scrape_do.async_client.AsyncClientEventHooks]),
    and the same session-validation contract
    ([`AsyncSessionValidator`][scrape_do.async_client.AsyncSessionValidator]).

    abstract: Features
        - Local API parameter validation via the
          [`RequestParameters`][scrape_do.models.parameters.RequestParameters]
          Pydantic model, plus the proxy-mode-specific cross-checks in
          [`validate_proxy_params`][scrape_do.models.parameters.RequestParameters.validate_proxy_params].

        - Status code error parsing and customisable retry intervals for
          rate-limited requests. Non-blocking sleeps via
          `await asyncio.sleep(...)`.

        - Strongly-typed interface for responses via the
          [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse]
          Pydantic model.

        - Connection reuse via a bounded LRU pool of `httpx.AsyncClient`
          instances keyed on the formatted proxy URL, with an
          `asyncio.Lock` guarding the miss/eviction critical section.

    info: Concurrency Limit and Server Errors
        This client intercepts and manages Scrape.do's specific gateway
        errors (429, 502, 510), automatically applying a customisable
        retry strategy before the error can reach the application.

    tip: SDK Event Hooks (`event_hooks`)
        This client reuses the asynchronous
        [`AsyncClientEventHooks`][scrape_do.async_client.AsyncClientEventHooks]
        TypedDict — same shape, same lifecycle, same async-only callback
        signatures as the API-mode async client.

    tip: TLS Verification
        - `Scrape.do's Proxy Mode` upgrades and forwards HTTPS requests on
          your behalf (MITM-style), so HTTPS target validation against the
          normal system CAs would fail

        - The default `verify` value is
          [`DEFAULT_PROXY_SSL_CONTEXT`][scrape_do.constants.DEFAULT_PROXY_SSL_CONTEXT],
          an `ssl.SSLContext` preloaded with system CAs + Scrape.do's
          bundled CA, so HTTPS targets validate correctly through the
          proxy

        - Pass `verify=True` if you've installed Scrape.do's CA into
          your OS keychain, or `verify=False` to disable validation
          entirely (discouraged).

    tip: Additional `httpx.AsyncClient` Configuration
        The following `httpx.AsyncClient` parameters can be provided as
        keyword arguments and will be passed directly to every pooled
        client.

        - `verify`
        - `cert`
        - `http1`
        - `http2`
        - `timeout`
        - `limits`
        - `transport`
        - `default_encoding`

        Additionally, the following `httpx.AsyncClient.request` parameters
        can be provided as keyword arguments during request execution.

        - `timeout` (`r_timeout`)
        - `extensions`

        For more information on their behaviour and default values, please
        consult the official
        [`httpx`](https://www.python-httpx.org/api/#asyncclient) documentation.

    warning: Unsupported HTTPX Client Arguments
        The underlying `httpx.AsyncClient` instances are strictly managed
        by the pool to prevent invalid configurations from being sent to
        Scrape.do. For this reason, arguments not listed in the previous
        section are intentionally blocked and shouldn't be changed.

    warning: Connection Pool
        - Each unique formatted proxy URL gets its own `httpx.AsyncClient`

        - Two requests with the same `RequestParameters` reuse the same
          pooled client (and therefore the same TCP / TLS / HTTP-2
          state) for transport-level efficiency.

        - Two requests with different parameters get different clients

        - When `max_pooled_clients` is exceeded, the least-recently-used
          client is closed.

        - Cookies are **not** preserved across requests on the pooled
          client - the jar is cleared after every call. Scrape.do owns
          the cookie lifecycle through `setCookies` (in),
          `scrape.do-cookies` / `pureCookies=true` (out), and
          `sessionId` (server-side session jars). Pooling is purely a
          transport concern.

    Args:
        api_token (Optional[str]): The Scrape.do API key. If omitted, the
            client will attempt to load it from the 'SCRAPE_DO_API_KEY'
            environment variable.
        max_retries (int): The maximum number of retry attempts for
            retryable Scrape.do gateway errors (HTTP 429, 502, and 510).
        retry_backoff (Union[float, Callable[[int], float]]): The
            strategy used to calculate the delay between retries. Can be
            a static `float` (seconds) or a callable that accepts the
            current attempt number (0-indexed) and returns a float.
            Defaults to a jittered exponential backoff when set to
            `None`.
        event_hooks (Optional[AsyncClientEventHooks]): A dictionary of
            SDK-native async hooks to execute during different points of
            the request lifecycle.
        max_pooled_clients (int): Maximum number of `httpx.AsyncClient`
            instances to keep alive in the LRU pool. Defaults to 16.
        verify (Union[ssl.SSLContext, str, bool]): SSL verification
            configuration. Defaults to
            [`DEFAULT_PROXY_SSL_CONTEXT`][scrape_do.constants.DEFAULT_PROXY_SSL_CONTEXT]
            which trusts both system CAs and Scrape.do's bundled CA.
        cert (Optional[CertTypes]): Client-side certificates for mutual
            TLS authentication.
        http1 (bool): Enable HTTP/1.1 support.
        http2 (bool): Enable HTTP/2 multiplexing for higher concurrency.
        timeout (TimeoutTypes): The default timeout (in seconds) applied
            to all network phases. Defaults to 60s.
        limits (Limits): Configuration for maximum connection pool sizes
            *within each pooled* `httpx.AsyncClient`.
        transport (Optional[AsyncBaseTransport]): A completely custom
            async transport engine.
        default_encoding (Union[str, Callable[[bytes], str]]): The
            fallback text encoding used if a target website omits a
            charset header.
    """
    def __init__(
        self,
        api_token: Optional[str] = None,
        max_retries: int = 3,
        retry_backoff: Optional[Union[float, Callable[[int], float]]] = None,
        event_hooks: Optional[AsyncClientEventHooks] = None,
        max_pooled_clients: int = 16,
        *,
        verify: Union[ssl.SSLContext, str, bool] = DEFAULT_PROXY_SSL_CONTEXT,
        cert: Optional[CertTypes] = None,
        http1: bool = True,
        http2: bool = False,
        timeout: TimeoutTypes = 60.0,
        limits: Limits = DEFAULT_LIMITS,
        transport: Optional[AsyncBaseTransport] = None,
        default_encoding: Union[str, Callable[[bytes], str]] = "utf-8"
    ) -> None:
        self.api_token = api_token or os.getenv("SCRAPE_DO_API_KEY")
        if not self.api_token:
            raise ValueError(
                "Scrape.do API token must be provided explicitly or set via"
                " the 'SCRAPE_DO_API_KEY' environment variable."
                )

        self.max_retries = max_retries

        if retry_backoff is not None:
            self.retry_backoff = retry_backoff
        else:
            self.retry_backoff = default_backoff_strategy

        self.event_hooks: AsyncClientEventHooks = event_hooks or {}
        self.max_pooled_clients = max_pooled_clients

        # Stored httpx kwargs applied to every pooled client.
        self._verify = verify
        self._cert = cert
        self._http1 = http1
        self._http2 = http2
        self._timeout = timeout
        self._limits = limits
        self._transport = transport
        self._default_encoding = default_encoding

        self._client_pool: OrderedDict[str, AsyncClient] = OrderedDict()
        self._pool_lock = asyncio.Lock()

    async def _get_or_create_client(self, proxy_url: str) -> AsyncClient:
        """Returns a pooled `httpx.AsyncClient` for the given proxy URL.

        info: Pool Behavior
            **Fast path (cache hit)**

            - dict lookup + `move_to_end` don't await, so no other coroutine
              can preempt. The lock is skipped.

            - `move_to_end` bumps the entry to the back of the LRU ordering
                    before returning.

            **Slow path (cache miss)**

            - Acquires `self._pool_lock` and re-checks the pool
              (double-checked locking).

            - A concurrent coroutine that won the lock first may have
              populated the entry while we were waiting. If so, return that
              client.

            - Otherwise evict (if full) and construct a new one.

        warning: Why The Lock Matters
            - Two coroutines racing on a cache miss for the same URL
              would each construct a fresh `httpx.AsyncClient`.

            - Only one wins the dict write. The other leaks (asyncio GC
              does not auto-`aclose`, so the connection state stays open
              until OS cleanup).

            - The lock serializes creation to prevent this.

        Args:
            proxy_url (str): The formatted proxy URL (with `api_token`
                inserted and parameters URL-encoded into the password
                field) returned by
                `RequestParameters.to_proxy_url().format(...)`.

        Returns:
            A pooled `httpx.AsyncClient` configured for the given proxy
                URL.
        """
        # Fast path: lock-free LRU + return.
        if proxy_url in self._client_pool:
            self._client_pool.move_to_end(proxy_url)
            return self._client_pool[proxy_url]

        async with self._pool_lock:
            # Re-check inside the lock — another coroutine may have
            # populated the entry while we were waiting.
            if proxy_url in self._client_pool:
                self._client_pool.move_to_end(proxy_url)
                return self._client_pool[proxy_url]

            if len(self._client_pool) >= self.max_pooled_clients:
                _, evicted = self._client_pool.popitem(last=False)
                await evicted.aclose()

            new_client = AsyncClient(
                proxy=proxy_url,
                verify=self._verify,
                cert=self._cert,
                trust_env=False,
                http1=self._http1,
                http2=self._http2,
                timeout=self._timeout,
                limits=self._limits,
                transport=self._transport,
                default_encoding=self._default_encoding,
            )
            self._client_pool[proxy_url] = new_client
            return new_client

    async def aclose(self) -> None:
        """Closes every pooled `httpx.AsyncClient` and clears the pool.

        It is recommended to use the client as an async context manager
        to ensure resources are released automatically.
        """
        while self._client_pool:
            _, client = self._client_pool.popitem(last=True)
            await client.aclose()

    async def __aenter__(self) -> Self:
        """Async context manager entry. Returns the
        `AsyncScrapeDoProxyClient` instance. The pool starts empty.

        Returns:
            The `AsyncScrapeDoProxyClient` instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        """Closes every pooled `httpx.AsyncClient` without swallowing
        exceptions.

        Args:
            exc_type (Optional[type[BaseException]]): The type of the
                exception.
            exc_val (Optional[BaseException]): The instance of the exception.
            exc_tb (Optional[TracebackType]): The traceback information.


        Returns:
            `False`, since no exceptions are swallowed.
        """
        await self.aclose()
        return False

    async def execute(
        self,
        request: PreparedScrapeDoRequest,
        session_validator: Optional[AsyncSessionValidator] = None,
        *,
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None
    ) -> ScrapeDoResponse:
        """Executes a fully prepared and validated `Scrape.do` request
        through `Proxy Mode`, asynchronously.

        tip: Intended Usage
            Use this method if you have manually constructed a
            `PreparedScrapeDoRequest` object for bulk routing, custom
            configurations, or task reusability.

        warning: Sessions (`sessionId`)
            If you configure a request with a `session_id`, Scrape.do will
            attempt to route your traffic through the same proxy address.
            However, it can still silently rotate this address for various
            reasons. If it rotates during a multi-step scraping task, any
            target-specific WAF state or cookies accumulated will be lost,
            which may cause the task to fail.

        tip: Validating Sessions (`session_validator`)
            - In order to prevent unexpected errors due to dropped sessions,
              you can pass a custom async function to the client's `execute`
              method `session_validator` argument.

            - This function will be `await`-ed internally by the client after
              each stateful request (`sessionId is not None`) to determine
              whether or not a `RotatedSessionError` exception should be
              raised to signal that this session is no longer valid.

            - The function should take the current request's `ScrapeDoResponse`
              object as its only argument, and return `Awaitable[bool]`.

            - If the awaited value is `True`, this method will raise the
              `RotatedSessionError` instead of returning the response object.
              (The request's `ScrapeDoResponse` object can still be accessed
              later on using the exception's `response` attribute.) Otherwise,
              no additional action is taken.


        Args:
            request (PreparedScrapeDoRequest): The validated request
                payload.
            session_validator (Optional[AsyncSessionValidator]): A custom
                async function called to determine whether or not to raise
                a `RotatedSessionError` exception.
            r_timeout (Union[TimeoutTypes, UseClientDefault]): A
                request-specific timeout override.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions for this specific request.

        Returns:
            The `ScrapeDoResponse` object containing the target's data.

        Raises:
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided,
                the request was made with a `session_id` argument, and
                the awaited `session_validator` returned `True`.
            ValueError: If the `request.api_params` `RequestParameters`
                instance contains an invalid parameter configuration for
                `Proxy Mode`
        """

        # Fire Request Event Hooks
        if "request" in self.event_hooks:
            for req_hook in self.event_hooks["request"]:
                await req_hook(request)

        # Build the formatted proxy URL — validate_proxy_params runs
        # inside to_proxy_url and may raise on misconfiguration.
        proxy_url = request.api_params.to_proxy_url().format(
            api_token=self.api_token
            )

        # Acquire (or create) the pooled client for this proxy URL.
        client = await self._get_or_create_client(proxy_url)

        httpx_kwargs = request.to_proxy_httpx_kwargs()
        session_id = request.api_params.session_id

        if r_timeout is not USE_CLIENT_DEFAULT:
            httpx_kwargs["timeout"] = r_timeout
        if extensions is not None:
            httpx_kwargs["extensions"] = extensions

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    raw_resp = await client.request(**httpx_kwargs)
                    scrape_response = ScrapeDoResponse(request, raw_resp)

                    # Strictly aligned with Scrape.do documented gateway
                    # errors
                    is_retryable_status = (
                        raw_resp.status_code in (429, 502, 510)
                        )

                    if (
                        scrape_response.is_proxy_error
                        and is_retryable_status
                    ):
                        if attempt < self.max_retries:

                            # Fire retry hook and pass response
                            if "retry" in self.event_hooks:
                                for retry_hook in self.event_hooks["retry"]:
                                    await retry_hook(
                                        attempt,
                                        request,
                                        scrape_response,
                                        None
                                        )

                            if callable(self.retry_backoff):
                                await asyncio.sleep(
                                    self.retry_backoff(attempt)
                                    )
                            else:
                                await asyncio.sleep(
                                    float(self.retry_backoff)
                                    )
                            continue

                        # If attempt == max_retries, fall through to
                        # return the failed ScrapeDoResponse to the user.

                    # Call validator if session_id is not None
                    if (
                        session_validator is not None
                        and session_id is not None
                    ):
                        if await session_validator(scrape_response):
                            raise RotatedSessionError(
                                (
                                    f"User-Defined Session Validator "
                                    f"Failed | "
                                    f"Status: {raw_resp.status_code}"
                                    ),
                                raw_resp,
                                request,
                                scrape_response
                                )

                    # Fires on a success, OR on a final 502 if retries
                    # are exhausted.
                    if "response" in self.event_hooks:
                        for resp_hook in self.event_hooks["response"]:
                            await resp_hook(scrape_response)

                    return scrape_response

                except RequestError as e:
                    if attempt == self.max_retries:
                        raise APIConnectionError(
                            f"Network transport failed: {str(e)}",
                            request
                            ) from e

                    # Fire retry hook and pass the exception
                    if "retry" in self.event_hooks:
                        for retry_hook in self.event_hooks["retry"]:
                            await retry_hook(
                                attempt,
                                request,
                                None,
                                e
                                )

                    if callable(self.retry_backoff):
                        await asyncio.sleep(self.retry_backoff(attempt))
                    else:
                        await asyncio.sleep(float(self.retry_backoff))

            # max_retries < 0
            raise RuntimeError(
                "Execution loop exhausted without returning a response."
                )
        finally:
            # Prevent cookie bleed between requests on the pooled
            # client. Scrape.do owns the cookie lifecycle (setCookies in,
            # scrape.do-cookies / pureCookies out, sessionId for server-
            # side session jars), so any cookies httpx accumulates here
            # would silently bypass the user's parameter contract on the
            # next request through the same pooled client.
            client.cookies.clear()

    async def request(
        self,
        method: HttpMethod,
        target_url: str,
        params: Optional[RequestParameters] = None,
        session_validator: Optional[AsyncSessionValidator] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Union[Dict[str, Any], str, bytes]] = None,
        payload_type: PayloadType = "json",
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None,
        **api_kwargs: Unpack[RequestParametersDict]
    ) -> ScrapeDoResponse:
        """Builds and executes a `Scrape.do` request through `Proxy Mode`,
        asynchronously.

        info: Parameter Configuration
            Like
            [`AsyncScrapeDoClient.request`][scrape_do.async_client.AsyncScrapeDoClient.request],
            this method provides smart routing based on the arguments
            provided. You can configure the request in two distinct ways:

            - **Keyword Arguments (Default) :** Pass the target URL and
              Scrape.do parameters directly as `**api_kwargs`
              (`render=False`, `geoCode="us"`).

            - **Pre-built Parameters :** Pass a fully validated
              `RequestParameters` object via the `params` argument.

        warning: Raw `api.scrape.do` URLs Are Not Accepted
            - Unlike the API-mode client, proxy mode has no equivalent of
              a raw `api.scrape.do/?...` URL.

            - Passing one as `target_url` simply targets that URL through the
              Scrape.do proxy, which is almost certainly not what you want.

        warning: Parameter Restrictions
            To prevent silent overwrites, the client enforces that only
            one of the parameter configurations can be used at a time.
            Mixing `params` with `**api_kwargs` raises `ValueError`.

        warning: Pre-built Parameters Configuration
            When passing an already constructed `RequestParameters`
            instance to the `params` argument, its `url` attribute will
            be ignored and replaced by the provided `target_url`.

        Args:
            method (HttpMethod): The HTTP method to forward to the target
                website.
            target_url (str): The destination website URL.
            params (Optional[RequestParameters]): A pre-validated
                parameter object.
            session_validator (Optional[AsyncSessionValidator]): A custom
                async function called to determine whether or not to raise
                a `RotatedSessionError` exception. See
                `AsyncScrapeDoProxyClient.execute` docstring for more
                information
            headers (Optional[Dict[str, str]]): Custom HTTP headers to
                forward to the target.
            body (Optional[Union[Dict[str, Any], str, bytes]]): The
                payload to send to the target website.
            payload_type (PayloadType): Dictates how the client encodes
                the `body`.
            r_timeout (Union[TimeoutTypes, UseClientDefault]):
                Request-specific timeout override.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions.
            **api_kwargs (Unpack[RequestParametersDict]): Scrape.do API
                configuration parameters (e.g., `render=False`).

        Returns:
            The `ScrapeDoResponse` object containing the target's data.

        Raises:
            ValueError: If configuration constraints are violated
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided,
                the request was made with a `session_id` argument, and
                the awaited `session_validator` returned `True`.
        """
        if params is not None and api_kwargs:
            raise ValueError(
                "You cannot provide both a 'RequestParameters' object and "
                "explicit **api_kwargs. Choose one method of configuration."
                )

        if params is None:
            params = RequestParameters.model_validate(
                {"url": target_url, **api_kwargs})
        else:
            params.url = HttpUrl(target_url)

        req = PreparedScrapeDoRequest(
            api_params=params,
            method=method,
            headers=headers,
            body=body,
            payload_type=payload_type
            )
        return await self.execute(
            req,
            session_validator,
            r_timeout=r_timeout,
            extensions=extensions
            )

    # --- Method Wrappers ---

    async def get(
        self,
        url: str,
        params: Optional[RequestParameters] = None,
        session_validator: Optional[AsyncSessionValidator] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None,
        **api_kwargs: Unpack[RequestParametersDict]
    ) -> ScrapeDoResponse:
        """Async wrapper for executing a GET request through `Proxy Mode`.

        Inherits the smart routing logic, parameter validation, and execution
        constraints of the base
        [`request`][scrape_do.async_proxy_client.AsyncScrapeDoProxyClient.request]
        method.

        Args:
            url (str): The target website URL.
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[AsyncSessionValidator]): A custom
                async function to be called in order to determine whether or
                not to raise a `RotatedSessionError` exception. (See
                `AsyncScrapeDoProxyClient.execute` docstring for more
                information)
            headers (Optional[Dict[str, str]]): Custom HTTP headers to forward.
            r_timeout (Union[TimeoutTypes, UseClientDefault]): Request-specific
                timeout override.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions.
            **api_kwargs (Unpack[RequestParametersDict]): Scrape.do API
                configuration parameters.

        Raises:
            ValueError: If configuration constraints are violated.
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided, the
                request was made with a `session_id` argument, and the
                awaited `session_validator` returned `True`

        Returns:
            The `ScrapeDoResponse` object containing the target's data.
        """
        return await self.request(
            "GET",
            url,
            params=params,
            session_validator=session_validator,
            headers=headers,
            r_timeout=r_timeout,
            extensions=extensions,
            **api_kwargs
            )

    async def post(
        self,
        url: str,
        params: Optional[RequestParameters] = None,
        session_validator: Optional[AsyncSessionValidator] = None,
        *,
        body: Optional[Union[Dict[str, Any], str, bytes]] = None,
        headers: Optional[Dict[str, str]] = None,
        payload_type: PayloadType = "json",
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None,
        **api_kwargs: Unpack[RequestParametersDict]
    ) -> ScrapeDoResponse:
        """Async wrapper for executing a POST request through `Proxy Mode`.

        Inherits the smart routing logic, parameter validation, and execution
        constraints of the base
        [`request`][scrape_do.async_proxy_client.AsyncScrapeDoProxyClient.request]
        method.

        Args:
            url (str): The target website URL.
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[AsyncSessionValidator]): A custom
                async function to be called in order to determine whether or
                not to raise a `RotatedSessionError` exception. (See
                `AsyncScrapeDoProxyClient.execute` docstring for more
                information)
            body (Optional[Union[Dict[str, Any], str, bytes]]): The payload to
                send to the target website.
            headers (Optional[Dict[str, str]]): Custom HTTP headers to forward.
            payload_type (PayloadType): Dictates how the client encodes the
                `body`.
            r_timeout (Union[TimeoutTypes, UseClientDefault]): Request-specific
                timeout override.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions.
            **api_kwargs (Unpack[RequestParametersDict]): Scrape.do API
                configuration parameters.

        Raises:
            ValueError: If configuration constraints are violated.
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided, the
                request was made with a `session_id` argument, and the
                awaited `session_validator` returned `True`

        Returns:
            The `ScrapeDoResponse` object containing the target's data.
        """
        return await self.request(
            "POST",
            url,
            params=params,
            session_validator=session_validator,
            headers=headers,
            body=body,
            payload_type=payload_type,
            r_timeout=r_timeout,
            extensions=extensions,
            **api_kwargs
            )
