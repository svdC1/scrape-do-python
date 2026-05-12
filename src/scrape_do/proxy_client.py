"""Synchronous HTTP client for `Scrape.do's Proxy Mode`.

Defines `ScrapeDoProxyClient`, the proxy-mode counterpart of
[`ScrapeDoClient`][scrape_do.client.ScrapeDoClient]. Configures
`httpx.Client` instances with `Scrape.do's Proxy Mode` endpoint
(`proxy.scrape.do:8080`) and reuses the same `retry / hook / validator`
semantics as the API-mode client.

Because Scrape.do encodes per-request parameters into the proxy URL's
password field, each unique (token, params) combination needs its own
`httpx.Client`. This module maintains a bounded LRU pool of clients
keyed on the formatted proxy URL — repeated requests with the same
params reuse the same `TCP / TLS / HTTP-2` connection state.
"""

import os
import time
import logging
import ssl
from collections import OrderedDict
from pydantic import HttpUrl
from httpx import (
    Client,
    Limits,
    BaseTransport,
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
    Self,
    Any,
    Union,
    Unpack,
    Callable,
    Literal,
    )
from types import TracebackType
from .client import (
    default_backoff_strategy,
    SyncSessionValidator,
    SyncClientEventHooks,
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


class ScrapeDoProxyClient:
    """Synchronous HTTP client for `Scrape.do's Proxy Mode`.

    Counterpart of [`ScrapeDoClient`][scrape_do.client.ScrapeDoClient]
    that routes requests through `proxy.scrape.do:8080` instead of
    calling `api.scrape.do` directly. Reuses the same
    [`RequestParameters`][scrape_do.models.parameters.RequestParameters]
    model, the same retry strategy, the same event hooks
    ([`SyncClientEventHooks`][scrape_do.client.SyncClientEventHooks]),
    and the same session-validation contract
    ([`SyncSessionValidator`][scrape_do.client.SyncSessionValidator]).

    abstract: Features
        - Local API parameter validation via the
          [`RequestParameters`][scrape_do.models.parameters.RequestParameters]
          Pydantic model, plus the proxy-mode-specific cross-checks in
          [`validate_proxy_params`][scrape_do.models.parameters.RequestParameters.validate_proxy_params].

        - Status code error parsing and customisable retry intervals for
          rate-limited requests.

        - Strongly-typed interface for responses via the
          [`ScrapeDoResponse`][scrape_do.models.response.ScrapeDoResponse]
          Pydantic model.

        - Connection reuse via a bounded LRU pool of `httpx.Client`
          instances keyed on the formatted proxy URL.

    info: Concurrency Limit and Server Errors
        This client intercepts and manages Scrape.do's specific gateway
        errors (429, 502, 510), automatically applying a customisable
        retry strategy before the error can reach the application.

    tip: SDK Event Hooks (`event_hooks`)
        This client reuses the synchronous
        [`SyncClientEventHooks`][scrape_do.client.SyncClientEventHooks]
        TypedDict — same shape, same lifecycle, same callback signatures
        as the API-mode client.

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

    tip: Additional `httpx.Client` Configuration
        The following `httpx.Client` parameters can be provided as
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

        Additionally, the following `httpx.Client.request` parameters can
        be provided as keyword arguments during request execution.

        - `timeout` (`r_timeout`)
        - `extensions`

        For more information on their behaviour and default values, please
        consult the official
        [`httpx`](https://www.python-httpx.org/api/#client) documentation.

    warning: Unsupported HTTPX Client Arguments
        The underlying `httpx.Client` instances are strictly managed by
        the pool to prevent invalid configurations from being sent to
        Scrape.do. For this reason, arguments not listed in the previous
        section are intentionally blocked and shouldn't be changed.

    warning: Connection Pool
        - Each unique formatted proxy URL gets its own `httpx.Client`

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
        event_hooks (Optional[SyncClientEventHooks]): A dictionary of
            SDK-native hooks to execute during different points of the
            request lifecycle.
        max_pooled_clients (int): Maximum number of `httpx.Client`
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
            *within each pooled* `httpx.Client`.
        transport (Optional[BaseTransport]): A completely custom
            transport engine.
        default_encoding (Union[str, Callable[[bytes], str]]): The
            fallback text encoding used if a target website omits a
            charset header.
    """
    def __init__(
        self,
        api_token: Optional[str] = None,
        max_retries: int = 3,
        retry_backoff: Optional[Union[float, Callable[[int], float]]] = None,
        event_hooks: Optional[SyncClientEventHooks] = None,
        max_pooled_clients: int = 16,
        *,
        verify: Union[ssl.SSLContext, str, bool] = DEFAULT_PROXY_SSL_CONTEXT,
        cert: Optional[CertTypes] = None,
        http1: bool = True,
        http2: bool = False,
        timeout: TimeoutTypes = 60.0,
        limits: Limits = DEFAULT_LIMITS,
        transport: Optional[BaseTransport] = None,
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

        self.event_hooks: SyncClientEventHooks = event_hooks or {}
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

        self._client_pool: OrderedDict[str, Client] = OrderedDict()

    def _get_or_create_client(self, proxy_url: str) -> Client:
        """Returns a pooled `httpx.Client` for the given proxy URL.

        info: Pool Behavior
            **Cache hit**

            - Bumps the entry to the back of the LRU ordering (most recently
              used) and returns the existing client.

            **Cache miss + pool full**

            - evicts the least-recently-used entry, closes it, then constructs
              a new client.

            **Cache miss + pool has room**

            - constructs a new client and stores it.

        Args:
            proxy_url (str): The formatted proxy URL (with `api_token`
                inserted and parameters URL-encoded into the password
                field) returned by
                `RequestParameters.to_proxy_url().format(...)`.

        Returns:
            A pooled `httpx.Client` configured for the given proxy URL.
        """
        if proxy_url in self._client_pool:
            self._client_pool.move_to_end(proxy_url)
            return self._client_pool[proxy_url]

        if len(self._client_pool) >= self.max_pooled_clients:
            _, evicted = self._client_pool.popitem(last=False)
            evicted.close()

        new_client = Client(
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

    def close(self) -> None:
        """Closes every `httpx.Client` in the pool and clears it.

        It is recommended to use the client as a context manager to
        ensure resources are released automatically.
        """
        while self._client_pool:
            _, client = self._client_pool.popitem(last=True)
            client.close()

    def __enter__(self) -> Self:
        """Context manager entry. Returns the `ScrapeDoProxyClient`
        instance. The pool starts empty.

        Returns:
            The `ScrapeDoProxyClient` instance.
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        """Closes every pooled `httpx.Client` without swallowing
        exceptions.

        Args:
            exc_type (Optional[type[BaseException]]): The type of the
                exception.
            exc_val (Optional[BaseException]): The instance of the exception.
            exc_tb (Optional[TracebackType]): The traceback information.


        Returns:
            `False`, since no exceptions are swallowed.
        """
        self.close()
        return False

    def execute(
        self,
        request: PreparedScrapeDoRequest,
        session_validator: Optional[SyncSessionValidator] = None,
        *,
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None
    ) -> ScrapeDoResponse:
        """Executes a fully prepared and validated `Scrape.do` request
        through `Proxy Mode`.

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
              you can pass a custom function to the client's `execute` method
              `session_validator` argument.

            - This function will be called internally by the client after each
              stateful request (`sessionId is not None`) to determine whether
              or not a `RotatedSessionError` exception should be raised to
              signal that this session is no longer valid.

            - The function should take the current request's `ScrapeDoResponse`
              object as its only argument, and return a single `bool` value.

            - If the function evaluates to `True`, this method will raise the
              `RotatedSessionError` instead of returning the response object.
              (The request's `ScrapeDoResponse` object can still be accessed
              later on using the exception's `response` attribute.) Otherwise,
              no additional action is taken.


        Args:
            request (PreparedScrapeDoRequest): The validated request
                payload.
            session_validator (Optional[SyncSessionValidator]): A custom
                function called to determine whether or not to raise a
                `RotatedSessionError` exception.
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
                the `session_validator` returned `True`.
            ValueError: If the `request.api_params` `RequestParameters`
                instance contains an invalid parameter configuration for
                `Proxy Mode`
        """

        # Fire Request Event Hooks
        if "request" in self.event_hooks:
            for req_hook in self.event_hooks["request"]:
                req_hook(request)

        # Build the formatted proxy URL — validate_proxy_params runs
        # inside to_proxy_url and may raise on misconfiguration.
        proxy_url = request.api_params.to_proxy_url().format(
            api_token=self.api_token
            )

        # Acquire (or create) the pooled client for this proxy URL.
        client = self._get_or_create_client(proxy_url)

        httpx_kwargs = request.to_proxy_httpx_kwargs()
        session_id = request.api_params.session_id

        if r_timeout is not USE_CLIENT_DEFAULT:
            httpx_kwargs["timeout"] = r_timeout
        if extensions is not None:
            httpx_kwargs["extensions"] = extensions

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    raw_resp = client.request(**httpx_kwargs)
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
                                    retry_hook(
                                        attempt,
                                        request,
                                        scrape_response,
                                        None
                                        )

                            if callable(self.retry_backoff):
                                time.sleep(self.retry_backoff(attempt))
                            else:
                                time.sleep(float(self.retry_backoff))
                            continue

                        # If attempt == max_retries, fall through to
                        # return the failed ScrapeDoResponse to the user.

                    # Call validator if session_id is not None
                    if (
                        session_validator is not None
                        and session_id is not None
                    ):
                        if session_validator(scrape_response):
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
                            resp_hook(scrape_response)

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
                            retry_hook(
                                attempt,
                                request,
                                None,
                                e
                                )

                    if callable(self.retry_backoff):
                        time.sleep(self.retry_backoff(attempt))
                    else:
                        time.sleep(float(self.retry_backoff))

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

    def request(
        self,
        method: HttpMethod,
        target_url: str,
        params: Optional[RequestParameters] = None,
        session_validator: Optional[SyncSessionValidator] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Union[Dict[str, Any], str, bytes]] = None,
        payload_type: PayloadType = "json",
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None,
        **api_kwargs: Unpack[RequestParametersDict]
    ) -> ScrapeDoResponse:
        """Builds and executes a `Scrape.do` request through `Proxy Mode`.

        info: Parameter Configuration
            Like
            [`ScrapeDoClient.request`][scrape_do.client.ScrapeDoClient.request],
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
            session_validator (Optional[SyncSessionValidator]): A custom
                function called to determine whether or not to raise a
                `RotatedSessionError` exception. See
                `ScrapeDoProxyClient.execute` docstring for more information
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
                the `session_validator` returned `True`.
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
        return self.execute(
            req,
            session_validator,
            r_timeout=r_timeout,
            extensions=extensions
            )

    # --- Method Wrappers ---

    def get(
        self,
        url: str,
        params: Optional[RequestParameters] = None,
        session_validator: Optional[SyncSessionValidator] = None,
        *,
        headers: Optional[Dict[str, str]] = None,
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None,
        **api_kwargs: Unpack[RequestParametersDict]
    ) -> ScrapeDoResponse:
        """Wrapper for executing a GET request.

        Inherits the smart routing logic, parameter validation, and execution
        constraints of the base
        [`request`][scrape_do.proxy_client.ScrapeDoProxyClient.request]
        method.

        Args:
            url (str): The target website URL.
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception. (See
                `ScrapeDoProxyClient.execute` docstring for more information)
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
                `session_validator` returned `True`

        Returns:
            The `ScrapeDoResponse` object containing the target's data.
        """
        return self.request(
            "GET",
            url,
            params=params,
            session_validator=session_validator,
            headers=headers,
            r_timeout=r_timeout,
            extensions=extensions,
            **api_kwargs
            )

    def post(
        self,
        url: str,
        params: Optional[RequestParameters] = None,
        session_validator: Optional[SyncSessionValidator] = None,
        *,
        body: Optional[Union[Dict[str, Any], str, bytes]] = None,
        headers: Optional[Dict[str, str]] = None,
        payload_type: PayloadType = "json",
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None,
        **api_kwargs: Unpack[RequestParametersDict]
    ) -> ScrapeDoResponse:
        """Wrapper for executing a POST request.

        Inherits the smart routing logic, parameter validation, and execution
        constraints of the base
        [`request`][scrape_do.proxy_client.ScrapeDoProxyClient.request] method.

        Args:
            url (str): The target website URL.
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception. (See
                `ScrapeDoProxyClient.execute` docstring for more information)
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
                `session_validator` returned `True`

        Returns:
            The `ScrapeDoResponse` object containing the target's data.
        """
        return self.request(
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
