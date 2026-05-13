"""Synchronous HTTP client for the Scrape.do API.

Defines the primary `ScrapeDoClient` used for executing proxy
requests. Handles autonomic error routing, customizable retry strategies,
telemetry tracking, and secure, isolated connection pooling.
"""

import os
import time
import random
import logging
import ssl
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
    List,
    Optional,
    Any,
    Union,
    Callable,
    Literal,
    TypedDict
    )
from typing_extensions import Self, TypeAlias, Unpack
from types import TracebackType
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


# --- Type Definitions ---

SyncSessionValidator: TypeAlias = Callable[[ScrapeDoResponse], bool]
"""
Defines the expected signature of the custom function meant to be passed
to the `ScrapeDoClient.execute` method's `session_validator` argument
"""


class SyncClientEventHooks(TypedDict, total=False):
    """
    Configuration dictionary for SDK-native lifecycle hooks.

    Unlike native HTTPX event hooks which fire on every transport-level
    execution (and can corrupt telemetry during autonomic retries), these SDK
    hooks map cleanly to the logical request lifecycle.
    """

    request: List[
        Callable[[PreparedScrapeDoRequest], None]
        ]
    """
    Fires exactly once per logical execution, immediately before the retry
    loop begins. Receives the `PreparedScrapeDoRequest` object that will be
    used to exececute the request. Useful for logging the request being
    executed.
    """
    response: List[
        Callable[[ScrapeDoResponse], None]
        ]
    """
    Fires exactly once per logical execution, immediately after the proxy
    returns a response and the `session_validator` (if any) passes.
    Receives the request's `ScrapeDoResponse` object. Useful for
    logging only the final response after all retries, which can be either
    a successful response, a non-retryable error, or a final retryable error
    after `max_attempts` has been exhausted.
    """
    retry: List[
        Callable[
            [
                int,
                PreparedScrapeDoRequest,
                Optional[ScrapeDoResponse],
                Optional[Exception]
                ],
            None
            ]
        ]
    """
    Fires inside the execution loop ONLY when a proxy gateway error
    (or an httpx.RequestError) occurs and the SDK decides to retry. Receives
    the current attempt number, the prepared request, and either the failed
    response (if it exists) or the `httpx.RequestError` that caused the retry.
    Useful for tracking proxy instability or manually raising an exception to
    abort the retry loop.
    """


# --- Client Default Backoff Strategy ---


def default_backoff_strategy(attempt: int) -> float:
    """Calculates a jittered exponential backoff for rate-limit retries.

    This is the default function used by the `ScrapeDoClient` to determine how
    long to wait before retrying a rate-limited request when the
    `retry_backoff` parameter is set to `None`.

    Args:
        attempt (int): The number of retries made so far, starting from 0

    info: Additional Information
        The `jitter` here is a random number between 0.1 and 1 generated
        by the `random.uniform` function.

    Returns:
        The number of seconds to sleep, calculated as (2^attempt) + jitter.
    """

    return (2.0**attempt) + random.uniform(0.1, 1.0)


class ScrapeDoClient:
    """Synchronous HTTP client for executing Scrape.do API requests.

    Aims to facilitate interactions with the Scrape.do API by managing an
    `httpx.Client` instance to provide strict type-checking for request
    parameters, custom error parsing, and session tracking while keeping the
    network configurations as flexible as possible.

    abstract: Features
        - Local API parameter validation via the `RequestParameters` Pydantic
          model.

        - Status code error parsing and customisable retry intervals for
          rate-limited requests.

        - Strongly-typed interface for responses via the `ScrapeDoResponse`
          Pyadantic model.

    info: Concurrency Limit and Server Errors
        This client intercepts and manages Scrape.do's specific gateway errors
        (429, 502, 510), automatically applying a customisable retry strategy
        before the error can reach the application.

    tip: SDK Event Hooks (`event_hooks`)
        This client implements SDK-specific event hooks mimicking the
        structure of `httpx` native event hooks. See
        [`SyncClientEventHooks`][scrape_do.client.SyncClientEventHooks] for
        available lifecycle hooks and their required signatures.

    tip: Additional `httpx.Client` Configuration
        The following `httpx.Client` parameters can be provided as keyword
        arguments and will be passed directly to the underlying object.

        - `verify`
        - `cert`
        - `http1`
        - `http2`
        - `timeout`
        - `limits`
        - `transport`
        - `default_encoding`

        Additionally, the following `httpx.Client.request` parameters can be
        provided as keyword arguments during request execution.

        - `timeout` (`r_timeout`)
        - `extensions`

        For more information on their behaviour and default values, please
        consult the official
        [`httpx`](https://www.python-httpx.org/api/#client) documentation.

    warning: Unsupported HTTPX Client Arguments
        The underlying `httpx.Client` object is strictly managed by the
        instance to prevent invalid configurations from being sent to the
        Scrape.do API. For this reason, arguments not listed in the previous
        section are intentionally blocked and shouldn't be changed.

    Args:
        api_token (Optional[str]): The Scrape.do API key. If omitted, the
            client will attempt to load it from the 'SCRAPE_DO_API_KEY'
            environment variable.
        max_retries (int): The maximum number of retry attempts for retryable
            Scrape.do gateway errors (HTTP 429, 502, and 510).
        retry_backoff (Union[float, Callable[[int], float]]): The strategy
            used to calculate the delay between retries. Can be a static
            `float` (seconds) or a callable that accepts the current attempt
            number (0-indexed) and returns a float. Defaults to a jittered
            exponential backoff when set to `None`.
        event_hooks (Optional[SyncClientEventHooks]): A dictionary of
            SDK-native hooks to execute during different points of the request
            lifecycle.
        verify (Union[ssl.SSLContext, str, bool]): Configures SSL certificate
            verification. Defaults to True (secure).
        cert (Optional[CertTypes]): Client-side certificates for mutual TLS
            authentication.
        http1 (bool): Enable HTTP/1.1 support.
        http2 (bool): Enable HTTP/2 multiplexing for higher concurrency.
        timeout (TimeoutTypes): The default timeout (in seconds) applied to
            all network phases. Defaults to 60s, raised from httpx's 5s
            default to accommodate Scrape.do proxy round-trips
            (browser rendering, geo-routing, fingerprinting).
        limits (Limits): Configuration for maximum connection pool sizes.
        transport (Optional[BaseTransport]): A completely custom transport
            engine
        default_encoding (Union[str, Callable[[bytes], str]]): The fallback
            text encoding used if a target website omits a charset header.
    """
    def __init__(
        self,
        api_token: Optional[str] = None,
        max_retries: int = 3,
        retry_backoff: Optional[Union[float, Callable[[int], float]]] = None,
        event_hooks: Optional[SyncClientEventHooks] = None,
        *,
        verify: Union[ssl.SSLContext, str, bool] = True,
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

        self._http_client = Client(
            verify=verify,
            cert=cert,
            trust_env=False,
            http1=http1,
            http2=http2,
            timeout=timeout,
            limits=limits,
            transport=transport,
            default_encoding=default_encoding
            )

    def close(self) -> None:
        """Closes the underlying HTTPX connection pool.

        It is recommended to use the client as a context manager to ensure
        resources are released automatically.
        """
        self._http_client.close()

    def __enter__(self) -> Self:
        """Initializes the HTTPX connection pool and returns the context
        manager object.

        Returns:
            The `ScrapeDoClient` instance with an opened HTTPX connection pool
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        """Calls the `close` method to close the underlying HTTPX connection
        pool without swallowing any exceptions.

        Args:
            exc_type (Optional[type[BaseException]]): The type of the
                exception.
            exc_val (Optional[BaseException]): The instance of the exception.
            exc_tb (Optional[TracebackType]): The traceback information.

        Returns:
            `False`, since no exceptions are swallowed
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
        """Executes a fully prepared and validated Scrape.do request.

        Acts as the core execution funnel, applying the retry
        backoff logic, evaluating gateway errors and sessions,
        and isolating cookies between sequential executions.

        tip: Intended Usage
            Use this method if you have manually constructed a
            `PreparedScrapeDoRequest` object for bulk routing,
            custom configurations, or task reusability.

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
            request (PreparedScrapeDoRequest): The validated request payload.
            r_timeout (Union[TimeoutTypes, UseClientDefault]): A
                request-specific timeout override.
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions for this specific request.

        Returns:
            The `ScrapeDoResponse` object containing the target's data.

        Raises:
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided, the
                request was made with a `session_id` argument, and the
                `session_validator` returned `True`
        """

        # Fire Request Event Hooks
        if "request" in self.event_hooks:
            for req_hook in self.event_hooks["request"]:
                req_hook(request)

        httpx_kwargs = request.to_httpx_kwargs(token=self.api_token)
        session_id = request.api_params.session_id

        if r_timeout is not USE_CLIENT_DEFAULT:
            httpx_kwargs["timeout"] = r_timeout
        if extensions is not None:
            httpx_kwargs["extensions"] = extensions

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    raw_resp = self._http_client.request(**httpx_kwargs)
                    scrape_response = ScrapeDoResponse(request, raw_resp)

                    # Strictly aligned with Scrape.do documented gateway errors
                    is_retryable_status = (
                        raw_resp.status_code in (429, 502, 510)
                        )

                    if scrape_response.is_proxy_error and is_retryable_status:
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

                        # If attempt == max_retries, fall through
                        # to return the failed ScrapeDoResponse to the user.

                    # Call validator if session_id is not None
                    if (
                        session_validator is not None
                        and session_id is not None
                    ):
                        # Raise exception if validator returns True
                        if session_validator(scrape_response):
                            raise RotatedSessionError(
                                (
                                    f"User-Defined Session Validator Failed | "
                                    f"Status: {raw_resp.status_code}"
                                    ),
                                raw_resp,
                                request,
                                scrape_response
                                )

                    # Fires on a success, OR on a final 502 if
                    # retries are exhausted.
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
            # Prevent cookie bleed between requests
            self._http_client.cookies.clear()

    def execute_from_url(
        self,
        method: HttpMethod,
        full_url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Union[Dict[str, Any], str, bytes]] = None,
        payload_type: PayloadType = "json",
        session_validator: Optional[SyncSessionValidator] = None,
        *,
        r_timeout: Union[TimeoutTypes, UseClientDefault] = USE_CLIENT_DEFAULT,
        extensions: Optional[RequestExtensions] = None
    ) -> ScrapeDoResponse:
        """Executes a request using a raw, pre-configured `api.scrape.do` URL.

        tip: Intended Usage
            This method is designed for scenarios where you have generated a
            Scrape.do URL elsewhere and simply need to execute it. It parses
            the URL to extract and validate the parameters, and then passes the
            `PreparedScrapeDoRequest` to the `execute` method.

        info: URL Format
            The `api.scrape.do` URL can be either url-encoded or not. Both
            will have their parameters extracted and be properly re-encoded
            before the request is sent.

        Args:
            method (HttpMethod): The HTTP method to forward to the target
                website.
            full_url (str): The complete, pre-formatted `api.scrape.do`
                endpoint.
            headers (Optional[Dict[str, str]]): Custom HTTP headers to forward
                to the target.
            body (Optional[Union[Dict[str, Any], str, bytes]]): The payload to
                send to the target website.
            payload_type (PayloadType): Dictates how the client encodes the
                 `body` (e.g., 'json', 'data').
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception. (See
                `ScrapeDoClient.execute` docstring for more information)
            r_timeout (Union[TimeoutTypes, UseClientDefault]): A
                request-specific timeout override.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions.

        Raises:
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided, the
                request was made with a `session_id` argument, and the
                `session_validator` returned `True`

        Returns:
            The `ScrapeDoResponse` object containing the target's data.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters.from_url(full_url),
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
        """Interface for building and executing a Scrape.do request.

        Depending on the parameter configuration it either constructs a
        `PreparedScrapeDoRequest` object and passes it to the
        `execute` method, or calls the `execute_from_url` method on
        the `target_url`.

        info: Parameter Configuration
            This method provides smart routing based on the arguments provided.
            You can configure the request in three distinct ways:

            - **Keyword Arguments (Default) :** Pass the target URL and
              Scrape.do parameters directly as `**api_kwargs`
              (`render=True`, `geoCode="us"`).

            - **Pre-built Parameters :** Pass a fully validated
              `RequestParameters` object via the `params` argument.

            - **Raw Scrape.do URL :** Pass a full `api.scrape.do` URL as the
              `target_url`.

        warning: Parameter Restrictions
            To prevent silent overwrites and routing ambiguity, the client
            enforces that only one of the parameter configurations can be
            used at a time.

            - When using the default **Keyword Arguments** (`**api_kwargs`)
              configuration, passing a value to the `params` argument, or a
              `api.scrape.do` URL to the `target_url` argument will raise a
              `ValueError`

            - When using the **Pre-built Parameters** (`params`) configuration,
              passing any `**api_kwargs` argument, or an `api.scrape.do` URL
              to the `target_url` argument, will raise a `ValueError`

            - When using the **Raw Scrape.do URL** configuration, passing any
              `**api_kwargs` argument, or a value to the `params` argument,
              will raise a `ValueError`

        warning: Pre-built Parameters Configuration
            When passing an already constructed `RequestParameters` instance
            to the `params` argument, its `url` attribute will be ignored and
            replaced by the provided `target_url`.

        Args:
            method (HttpMethod): The HTTP method to forward to the target
                website.
            target_url (str): The destination website URL
                (or a raw Scrape.do endpoint).
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception. (See
                `ScrapeDoClient.execute` docstring for more information)
            headers (Optional[Dict[str, str]]): Custom HTTP headers to forward
                to the target.
            body (Optional[Union[Dict[str, Any], str, bytes]]): The payload to
                send to the target website.
            payload_type (PayloadType): Dictates how the client encodes the
                `body`.
            r_timeout (Union[TimeoutTypes, UseClientDefault]): Request-specific
                timeout override.
            extensions (Optional[RequestExtensions]): Advanced HTTPX
                extensions.
            **api_kwargs (Unpack[RequestParametersDict]): Scrape.do API
                configuration parameters (e.g., `render=True`).

        Returns:
            The `ScrapeDoResponse` object containing the target's data.

        Raises:
            ValueError: If configuration constraints are violated.
            APIConnectionError: If the underlying network transport drops
                entirely (e.g., DNS failure).
            RotatedSessionError: If a `session_validator` is provided, the
                request was made with a `session_id` argument, and the
                `session_validator` returned `True`
        """
        if "api.scrape.do" in target_url.lower():
            if params is not None or api_kwargs:
                raise ValueError((
                    "You provided a raw api.scrape.do URL but also provided "
                    "additional parameters. When using a raw Scrape.do URL, "
                    "it must be the single source of truth. Please remove the "
                    "kwargs/params or pass the target URL instead."
                ))
            return self.execute_from_url(
                method,
                target_url,
                headers,
                body,
                payload_type,
                session_validator,
                r_timeout=r_timeout,
                extensions=extensions
                )

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
        [`request`][scrape_do.client.ScrapeDoClient.request] method.

        Args:
            url (str): The target website URL (or raw Scrape.do URL).
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception. (See
                `ScrapeDoClient.execute` docstring for more information)
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
        [`request`][scrape_do.client.ScrapeDoClient.request] method.

        Args:
            url (str): The target website URL (or raw Scrape.do URL).
            params (Optional[RequestParameters]): A pre-validated parameter
                object.
            session_validator (Optional[SyncSessionValidator]): A custom
                function to be called in order to determine whether or not to
                raise a `RotatedSessionError` exception. (See
                `ScrapeDoClient.execute` docstring for more information)
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
