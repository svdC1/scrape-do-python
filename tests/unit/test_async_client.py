import pytest
import httpx
from unittest.mock import patch
import respx
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.models import (
    RequestParameters,
    PreparedScrapeDoRequest
    )
from scrape_do.exceptions import (
    APIConnectionError,
    RotatedSessionError
    )

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class TestAsyncClientInitialization:

    async def test_missing_api_token_raises(self):
        """
        Ensures that initializing the async client without an API token
        raises a ValueError.
        """

        with pytest.raises(
            ValueError,
            match="token must be provided"
        ):
            AsyncScrapeDoClient()

    async def test_api_token_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """
        Ensures that API token is correctly acquired from environment variable
        """

        monkeypatch.setenv("SCRAPE_DO_API_KEY", "env_api_token")

        async with AsyncScrapeDoClient(retry_backoff=10) as client:
            assert client.api_token == "env_api_token"

    async def test_api_token_from_arg(self):
        """
        Ensures that API token is correctly acquired from argument
        """
        async with AsyncScrapeDoClient("arg_api_token") as client:
            assert client.api_token == "arg_api_token"

    async def test_httpx_client_default_values(self):
        """
        Ensures that all keyword arguments to the underlying
        `httpx.AsyncClient` instance are passed down correctly.
        """
        httpx_kwargs = {
            "verify": True,
            "cert": None,
            "http1": True,
            "http2": False,
            "timeout": httpx.Timeout(15),
            "limits": httpx.Limits(max_connections=50),
            "transport": None,
            "default_encoding": "utf-8"
        }

        async with AsyncScrapeDoClient(
            "api_token",
            **httpx_kwargs
        ) as client:
            _client = client._http_client
            transport: httpx.AsyncHTTPTransport = _client._transport

            assert _client.timeout == httpx_kwargs["timeout"]
            assert _client._default_encoding == "utf-8"
            assert not _client.trust_env
            assert transport._pool._http1
            assert not transport._pool._http2
            assert transport._pool._max_connections == 50

    async def test_default_timeout_is_60_seconds(self):
        """
        Ensures the SDK's default timeout (60s across all phases) overrides
        httpx's 5s default to comfortably accommodate proxy round-trips.
        """
        async with AsyncScrapeDoClient(api_token="test") as client:
            timeout = client._http_client.timeout
            assert timeout.connect == 60.0
            assert timeout.read == 60.0
            assert timeout.write == 60.0
            assert timeout.pool == 60.0

    async def test_explicit_aclose(self, mocker):
        """
        Ensures calling client.aclose() delegates to the httpx.AsyncClient.
        """
        client = AsyncScrapeDoClient(api_token="test")
        spy_aclose = mocker.spy(client._http_client, "aclose")

        await client.aclose()
        spy_aclose.assert_called_once()

    async def test_async_context_manager_enter(self):
        """
        Ensures the async context manager returns the client instance.
        """
        async with AsyncScrapeDoClient(api_token="test") as client:
            assert isinstance(client, AsyncScrapeDoClient)
            assert client.api_token == "test"

    async def test_async_context_manager_exit_returns_false(self):
        """
        Ensures __aexit__ returns False to signal exceptions are not
        swallowed.
        """
        client = AsyncScrapeDoClient(api_token="test")
        result = await client.__aexit__(None, None, None)
        assert result is False

    async def test_async_context_manager_closes_underlying_client(
        self,
        mocker
    ):
        """
        Ensures exiting the async context manager automatically cleans up
        sockets.
        """
        spy_aclose = mocker.spy(httpx.AsyncClient, "aclose")

        async with AsyncScrapeDoClient(api_token="test"):
            pass

        spy_aclose.assert_called_once()


class TestAsyncClientRouting:

    @pytest.mark.parametrize(
        "request_kwargs, error_match",
        [
            # **api_kwargs + params
            ({
                "method": "GET",
                "target_url": "https://example.com",
                "params": RequestParameters(url="https://example.com"),
                "render": True
                },
             "Choose one method of configuration"
             ),
            # **api_kwargs + scrape.do URL
            ({
                "method": "GET",
                "target_url": "https://api.scrape.do/",
                "render": True
                },
             "Please remove the kwargs/params"
             ),
            # params + scrape.do URL
            ({
                "method": "GET",
                "target_url": "https://api.scrape.do/",
                "params": RequestParameters(url="https://example.com"),
                },
             "Please remove the kwargs/params"
             )
        ]
    )
    async def test_request_param_constraints(
        self,
        request_kwargs,
        error_match,
        mock_async_client: AsyncScrapeDoClient,
        mocker
    ):
        """
        Ensures that multiple parameter configurations for the `request`
        method can't be used simultaneously.
        """

        with patch.object(
            mock_async_client,
            "execute",
            new_callable=mocker.AsyncMock
        ):
            with pytest.raises(
                ValueError,
                match=error_match
            ):
                await mock_async_client.request(**request_kwargs)

    @pytest.mark.parametrize(
        "request_kwargs",
        [{
            "method": "GET",
            "target_url": "https://example.com",
            "params": RequestParameters(
                url="https://example.com",
                super=True,
                device="desktop",
                render=True,
                return_json=True
                ),
            },
         {
             "method": "GET",
             "target_url": "https://example.com",
             "super": True,
             "device": "desktop",
             "render": True,
             "return_json": True
             },
         {
             "method": "GET",
             "target_url": ("https://api.scrape.do/?url=https://example.com"
                            "&super=true&device=desktop&render=true&"
                            "returnJSON=true"
                            )
             }
         ]
        )
    async def test_request_param_valid_config(
        self,
        request_kwargs,
        mock_async_client: AsyncScrapeDoClient,
        mocker
    ):
        """
        Ensures that the resulting `PreparedScrapeDoRequest` is correctly
        formatted across all parameter configurations.
        """
        expected_params = RequestParameters(
            url="https://example.com",
            super=True,
            device="desktop",
            render=True,
            return_json=True
            )

        expected_request = PreparedScrapeDoRequest(
            api_params=expected_params,
            method="GET"
            )

        with patch.object(
            mock_async_client,
            "execute",
            new_callable=mocker.AsyncMock
        ) as mock_execute:
            await mock_async_client.request(**request_kwargs)

            args, kwargs = mock_execute.call_args
            real_req: PreparedScrapeDoRequest = args[0]

            assert expected_request == real_req

    async def test_get_routing(
        self,
        mock_async_client: AsyncScrapeDoClient,
        mocker
    ):
        """
        Ensures that GET requests are properly routed to the request method.
        """

        with patch.object(
            mock_async_client,
            "request",
            new_callable=mocker.AsyncMock
        ) as mock_execute:
            await mock_async_client.get(
                "https://example.com",
                render=True
                )

            args, kwargs = mock_execute.call_args

            assert args[0] == "GET"

    async def test_post_routing(
        self,
        mock_async_client: AsyncScrapeDoClient,
        mocker
    ):
        """
        Ensures that POST requests are properly routed to the request method.
        """

        with patch.object(
            mock_async_client,
            "request",
            new_callable=mocker.AsyncMock
        ) as mock_execute:
            await mock_async_client.post(
                "https://example.com",
                render=False
                )

            args, kwargs = mock_execute.call_args

            assert args[0] == "POST"

    async def test_post_forwards_session_validator(
        self,
        mock_async_client: AsyncScrapeDoClient,
        mocker
    ):
        """
        Regression guard for the sync-side bug fixed alongside this client:
        post() must forward session_validator to request(), not drop it.
        """

        async def _validator(_):
            return False

        with patch.object(
            mock_async_client,
            "request",
            new_callable=mocker.AsyncMock
        ) as mock_request:
            await mock_async_client.post(
                "https://example.com",
                session_validator=_validator,
                render=False,
                )

            kwargs = mock_request.call_args.kwargs
            assert kwargs.get("session_validator") is _validator


class TestAsyncClientExecutionEngine:

    @respx.mock
    async def test_successful_request(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures a standard 200 OK response passes through without retrying.
        """
        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            json={"html": "<html>Success</html>"}
        )

        response = await mock_async_client.execute(req)

        assert response.scrape_do_status_code == 200
        assert route.call_count == 1

    @respx.mock
    async def test_retry_on_gateway_errors_success(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures the client retries on Scrape.do proxy errors (429, 502) and
        eventually succeeds.
        """
        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do")
        # Simulate: 429 (Rate Limit) -> 502 (Bad Gateway) -> 200 (Success)
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(502),
            httpx.Response(200)
            ]

        response = await mock_async_client.execute(req)

        assert response.scrape_do_status_code == 200
        assert route.call_count == 3

    @respx.mock
    async def test_max_retries_exhausted_returns_error_response(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures the client gives up after max_retries and returns the final
        failed response.
        """

        # Test float retry_backoff
        mock_async_client.retry_backoff = 10.0

        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do").respond(502)
        response = await mock_async_client.execute(req)

        assert response.scrape_do_status_code == 502
        assert response.is_proxy_error is True
        # 1 initial attempt + 3 retries = 4 total calls
        assert route.call_count == 4

    @respx.mock
    async def test_non_retryable_error_returns_immediately(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures that client errors (e.g., 401 Unauthorized, 403 Forbidden) do
        NOT trigger retries.
        """
        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = httpx.Response(403)

        response = await mock_async_client.execute(req)

        assert response.scrape_do_status_code == 403
        assert route.call_count == 1

    @respx.mock
    async def test_network_error_raises_api_connection_error(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures transport failures (like DNS resolution) raise
        APIConnectionError.
        """
        mock_async_client.max_retries = 1
        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.ConnectError("Failed to establish a connection"),
            httpx.ConnectError("Failed to establish a connection")
            ]

        with pytest.raises(APIConnectionError) as exc_info:
            await mock_async_client.execute(req)

        assert "Network transport failed" in str(exc_info.value)
        assert route.call_count == 2

    @respx.mock
    async def test_cookies_are_cleared_after_execution(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures the client cleans cookies after every request.
        """
        req = make_request()

        # Simulate a target website returning a tracking cookie
        route = respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            headers={"Set-Cookie": "target_tracking_id=xyz789; Path=/"}
        )

        await mock_async_client.execute(req)

        assert route.call_count == 1
        assert len(mock_async_client._http_client.cookies) == 0

    @respx.mock
    async def test_request_level_overrides_applied(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures specific timeout and extensions overrides are passed to HTTPX.
        """
        req = make_request()

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        # Spy on the underlying httpx.AsyncClient.request method
        spy_request = mocker.spy(mock_async_client._http_client, "request")

        await mock_async_client.execute(
            req,
            r_timeout=12.5,
            extensions={"trace": True}
            )

        assert spy_request.call_count == 1
        call_kwargs = spy_request.call_args.kwargs

        assert call_kwargs.get("timeout") == 12.5
        assert call_kwargs.get("extensions") == {"trace": True}

    @respx.mock
    async def test_custom_callable_backoff_is_executed(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures a custom backoff function is actually invoked during retries.
        Note: the backoff function itself is sync (returns float); the SDK
        awaits asyncio.sleep on its result.
        """
        mock_backoff = mocker.MagicMock(return_value=0.01)
        mock_async_client.retry_backoff = mock_backoff
        mock_async_client.max_retries = 2

        req = make_request()

        # Force the client to retry twice
        respx.get(url__startswith="https://api.scrape.do").respond(429)

        await mock_async_client.execute(req)

        assert mock_backoff.call_count == 2
        mock_backoff.assert_has_calls([mocker.call(0), mocker.call(1)])


class TestAsyncClientSessionValidator:

    @respx.mock
    async def test_validator_true_raises_rotated_session_error(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures the SDK raises RotatedSessionError when the user-provided
        async validator detects a lost session.
        """
        req = make_request(session_id=10)

        respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            json={"html": "<html>Logged out</html>"}
        )

        async def detect_logged_out(response):
            return "Logged out" in response.httpx_response.text

        with pytest.raises(RotatedSessionError) as exc_info:
            await mock_async_client.execute(req, detect_logged_out)

        err = exc_info.value
        assert err.request is req
        assert err.response is not None
        assert err.raw_response is not None

    @respx.mock
    async def test_validator_false_returns_response_unchanged(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures an async validator that returns False yields the response as
        normal.
        """
        req = make_request(session_id=10)

        respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            json={"html": "<html>Still logged in</html>"}
        )

        async def _always_false(_):
            return False

        response = await mock_async_client.execute(req, _always_false)

        assert response.scrape_do_status_code == 200

    @respx.mock
    async def test_validator_skipped_when_no_session_id(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures the validator is never awaited when session_id is None,
        even if a validator is provided.
        """
        req = make_request(session_id=None)

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        validator = mocker.AsyncMock(return_value=True)
        response = await mock_async_client.execute(req, validator)

        validator.assert_not_called()
        assert response.scrape_do_status_code == 200

    @respx.mock
    async def test_no_validator_returns_response(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Ensures a stateful request without a validator returns the response
        as-is, with no implicit session checking.
        """
        req = make_request(session_id=10)

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        response = await mock_async_client.execute(req)

        assert response.scrape_do_status_code == 200


class TestAsyncClientEventHooks:

    @respx.mock
    async def test_request_hook_fires_once_regardless_of_retries(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures the request hook is awaited exactly once before the retry
        loop, even when the SDK retries a 429/502 chain.
        """
        req = make_request()
        request_hook = mocker.AsyncMock()
        mock_async_client.event_hooks = {"request": [request_hook]}

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(502),
            httpx.Response(200)
            ]

        await mock_async_client.execute(req)

        request_hook.assert_called_once_with(req)

    @respx.mock
    async def test_response_hook_fires_once_on_success(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures the response hook is awaited exactly once when a request
        succeeds.
        """
        req = make_request()
        response_hook = mocker.AsyncMock()
        mock_async_client.event_hooks = {"response": [response_hook]}

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        response = await mock_async_client.execute(req)

        response_hook.assert_called_once_with(response)

    @respx.mock
    async def test_response_hook_fires_after_retries_exhausted(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures the response hook fires for the final response when the
        retry budget is exhausted on a retryable status.
        """
        req = make_request()
        response_hook = mocker.AsyncMock()
        mock_async_client.event_hooks = {"response": [response_hook]}

        respx.get(url__startswith="https://api.scrape.do").respond(502)

        response = await mock_async_client.execute(req)

        response_hook.assert_called_once_with(response)
        assert response.scrape_do_status_code == 502

    @respx.mock
    async def test_retry_hook_fires_with_response_on_retryable_status(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures the retry hook receives (attempt, request, response, None)
        when the SDK retries on a 429/502/510 status.
        """
        req = make_request()
        retry_hook = mocker.AsyncMock()
        mock_async_client.event_hooks = {"retry": [retry_hook]}

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200)
            ]

        await mock_async_client.execute(req)

        retry_hook.assert_called_once()
        attempt, hook_request, hook_response, hook_exc = (
            retry_hook.call_args[0]
            )
        assert attempt == 0
        assert hook_request is req
        assert hook_response is not None
        assert hook_response.scrape_do_status_code == 429
        assert hook_exc is None

    @respx.mock
    async def test_retry_hook_fires_with_exception_on_request_error(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mocker,
        mock_async_sleep
    ):
        """
        Ensures the retry hook receives (attempt, request, None, exc) when
        the SDK retries due to an httpx.RequestError.
        """
        mock_async_client.max_retries = 1
        req = make_request()
        retry_hook = mocker.AsyncMock()
        mock_async_client.event_hooks = {"retry": [retry_hook]}

        route = respx.get(url__startswith="https://api.scrape.do")
        connect_err = httpx.ConnectError("transport down")
        route.side_effect = [connect_err, httpx.Response(200)]

        await mock_async_client.execute(req)

        retry_hook.assert_called_once()
        attempt, hook_request, hook_response, hook_exc = (
            retry_hook.call_args[0]
            )
        assert attempt == 0
        assert hook_request is req
        assert hook_response is None
        assert hook_exc is connect_err

    @respx.mock
    async def test_no_event_hooks_default_does_not_break(
        self,
        mock_async_client: AsyncScrapeDoClient,
        make_request,
        mock_async_sleep
    ):
        """
        Regression: a client constructed without event_hooks must execute
        cleanly without raising AttributeError on the hook call sites.
        """
        req = make_request()
        # mock_async_client is constructed with event_hooks=None; the SDK
        # should normalize this to an empty dict at construction time.
        assert mock_async_client.event_hooks == {}

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        response = await mock_async_client.execute(req)

        assert response.scrape_do_status_code == 200
