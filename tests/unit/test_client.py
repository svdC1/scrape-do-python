import pytest
import httpx
from unittest.mock import patch
import respx
from scrape_do.client import ScrapeDoClient
from scrape_do.models import (
    RequestParameters,
    PreparedScrapeDoRequest
    )
from scrape_do.exceptions import (
    APIConnectionError,
    RotatedSessionError
    )

pytestmark = pytest.mark.unit


class TestClientInitialization:

    def test_missing_api_token_raises(self, mock_env_vars):
        """
        Ensures that initializing the client without an API token
        raises a ValueError. Environment variables are cleared
        via the `mock_env_vars` pytest fixture.
        """

        with pytest.raises(
            ValueError,
            match="token must be provided"
        ):
            ScrapeDoClient()

    def test_api_token_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """
        Ensures that API token is correctly acquired from environment variable
        """

        monkeypatch.setenv("SCRAPE_DO_API_KEY", "env_api_token")

        with ScrapeDoClient(retry_backoff=10) as client:
            assert client.api_token == "env_api_token"

    def test_api_token_from_arg(self, mock_env_vars):
        """
        Ensures that API token is correctly acquired from argument
        """
        with ScrapeDoClient("arg_api_token") as client:
            assert client.api_token == "arg_api_token"

    def test_httpx_client_default_values(self, mock_env_vars):
        """
        Ensures that all keyword arguments to the underlying `httpx.Client`
        instance are passed down correctly
        """
        httpx_kwargs = {
            "verify": True,
            "cert": None,
            "http1": True,
            "http2": False,
            "timeout": httpx.Timeout(15),
            "limits": httpx.Limits(max_connections=50),
            "event_hooks": {"request": [], "response": []},
            "transport": None,
            "default_encoding": "utf-8"
        }

        with ScrapeDoClient("api_token", **httpx_kwargs) as client:
            _client = client._http_client
            transport: httpx.HTTPTransport = _client._transport

            assert _client.timeout == httpx_kwargs["timeout"]
            assert _client.event_hooks == httpx_kwargs["event_hooks"]
            assert _client._default_encoding == "utf-8"
            assert not _client.trust_env
            assert transport._pool._http1
            assert not transport._pool._http2
            assert transport._pool._max_connections == 50

    def test_default_timeout_is_60_seconds(self, mock_env_vars):
        """
        Ensures the SDK's default timeout (60s across all phases) overrides
        httpx's 5s default to comfortably accommodate proxy round-trips.
        """
        with ScrapeDoClient(api_token="test") as client:
            timeout = client._http_client.timeout
            assert timeout.connect == 60.0
            assert timeout.read == 60.0
            assert timeout.write == 60.0
            assert timeout.pool == 60.0

    def test_explicit_close(self, mock_env_vars, mocker):
        """
        Ensures calling client.close() delegates to the httpx.Client
        """
        client = ScrapeDoClient(api_token="test")
        spy_close = mocker.spy(client._http_client, "close")

        client.close()
        spy_close.assert_called_once()

    def test_context_manager_enter(self, mock_env_vars):
        """
        Ensures the context manager returns the client instance
        """
        with ScrapeDoClient(api_token="test") as client:
            assert isinstance(client, ScrapeDoClient)
            assert client.api_token == "test"

    def test_context_manager_exit_returns_false(self, mock_env_vars):
        """
        Ensures __exit__ returns False to signal exceptions are not swallowed.
        """
        client = ScrapeDoClient(api_token="test")
        result = client.__exit__(None, None, None)
        assert result is False

    def test_context_manager_closes_underlying_client(
        self,
        mock_env_vars,
        mocker
    ):
        """
        Ensures exiting the context manager automatically cleans up sockets
        """
        spy_close = mocker.spy(httpx.Client, "close")

        with ScrapeDoClient(api_token="test"):
            pass

        spy_close.assert_called_once()


class TestClientRouting:

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
    def test_request_param_constraints(
        self,
        request_kwargs,
        error_match,
        mock_env_vars,
        mock_sync_client: ScrapeDoClient
    ):
        """
        Ensures that multiple parameter configurations for the `request`
        method can't be used simultaneously
        """

        with patch.object(
            mock_sync_client,
            "execute",
            autospec=True
        ):
            with pytest.raises(
                ValueError,
                match=error_match
            ):
                mock_sync_client.request(**request_kwargs)

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
    def test_request_param_valid_config(
        self,
        request_kwargs,
        mock_env_vars,
        mock_sync_client: ScrapeDoClient
    ):
        """
        Ensures that the resulting `PreparedScrapeDoRequest` is correctly
        formatted across all parameter configurations
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
            mock_sync_client,
            "execute",
            autospec=True
        ) as mock_execute:
            mock_sync_client.request(**request_kwargs)

            args, kwargs = mock_execute.call_args
            real_req: PreparedScrapeDoRequest = args[0]

            assert expected_request == real_req

    def test_get_routing(
        self,
        mock_env_vars,
        mock_sync_client: ScrapeDoClient
    ):
        """
        Ensures that GET requests are properly routed to the request method
        """

        with patch.object(
            mock_sync_client,
            "request",
            autospec=True
        ) as mock_execute:
            mock_sync_client.get("https://example.com", render=True)

            args, kwargs = mock_execute.call_args

            assert args[0] == "GET"

    def test_post_routing(
        self,
        mock_env_vars,
        mock_sync_client: ScrapeDoClient
    ):
        """
        Ensures that POST requests are properly routed to the request method
        """

        with patch.object(
            mock_sync_client,
            "request",
            autospec=True
        ) as mock_execute:
            mock_sync_client.post("https://example.com", render=False)

            args, kwargs = mock_execute.call_args

            assert args[0] == "POST"


class TestClientExecutionEngine:

    @respx.mock
    def test_successful_request(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a standard 200 OK response passes through without retrying.
        """
        req = make_request()

        # Mock the API endpoint
        route = respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            json={"html": "<html>Success</html>"}
        )

        response = mock_sync_client.execute(req)

        assert response.scrape_do_status_code == 200
        assert route.call_count == 1

    @respx.mock
    def test_retry_on_gateway_errors_success(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
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

        response = mock_sync_client.execute(req)

        assert response.scrape_do_status_code == 200
        assert route.call_count == 3

    @respx.mock
    def test_max_retries_exhausted_returns_error_response(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the client gives up after max_retries and returns the final
        failed response.
        """

        # Test float retry_backoff

        mock_sync_client.retry_backoff = 10.0

        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do").respond(502)
        response = mock_sync_client.execute(req)

        assert response.scrape_do_status_code == 502
        assert response.is_proxy_error is True
        # 1 initial attempt + 3 retries = 4 total calls
        assert route.call_count == 4

    @respx.mock
    def test_non_retryable_error_returns_immediately(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures that client errors (e.g., 401 Unauthorized, 403 Forbidden) do
        NOT trigger retries.
        """
        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = httpx.Response(403)

        response = mock_sync_client.execute(req)

        assert response.scrape_do_status_code == 403
        assert route.call_count == 1

    @respx.mock
    def test_network_error_raises_api_connection_error(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures transport failures (like DNS resolution) raise
        APIConnectionError.
        """
        mock_sync_client.max_retries = 1
        req = make_request()

        route = respx.get(url__startswith="https://api.scrape.do")
        # Simulate a total socket drop
        route.side_effect = [
            httpx.ConnectError("Failed to establish a connection"),
            httpx.ConnectError("Failed to establish a connection")
            ]

        with pytest.raises(APIConnectionError) as exc_info:
            mock_sync_client.execute(req)

        assert "Network transport failed" in str(exc_info.value)
        assert route.call_count == 2

    @respx.mock
    def test_cookies_are_cleared_after_execution(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
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

        mock_sync_client.execute(req)

        assert route.call_count == 1
        assert len(mock_sync_client._http_client.cookies) == 0

    @respx.mock
    def test_request_level_overrides_applied(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_sleep,
        mock_env_vars
    ):
        """
        Ensures specific timeout and extensions overrides are passed to HTTPX.
        """
        req = make_request()

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        # Spy on the underlying httpx.Client.request method
        spy_request = mocker.spy(mock_sync_client._http_client, "request")

        # Execute with explicit overrides
        mock_sync_client.execute(
            req,
            r_timeout=12.5,
            extensions={"trace": True}
            )

        # Verify overrides were injected into the kwargs
        assert spy_request.call_count == 1
        call_kwargs = spy_request.call_args.kwargs

        assert call_kwargs.get("timeout") == 12.5
        assert call_kwargs.get("extensions") == {"trace": True}

    @respx.mock
    def test_custom_callable_backoff_is_executed(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a custom backoff function is actually invoked during retries.
        """
        mock_backoff = mocker.MagicMock(return_value=0.01)
        mock_sync_client.retry_backoff = mock_backoff
        mock_sync_client.max_retries = 2

        req = make_request()

        # 2. Force the client to retry twice
        respx.get(url__startswith="https://api.scrape.do").respond(429)

        mock_sync_client.execute(req)

        assert mock_backoff.call_count == 2
        mock_backoff.assert_has_calls([mocker.call(0), mocker.call(1)])


class TestClientSessionValidator:

    @respx.mock
    def test_validator_true_raises_rotated_session_error(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the SDK raises RotatedSessionError when the user-provided
        validator detects a lost session.
        """
        req = make_request(session_id=10)

        respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            json={"html": "<html>Logged out</html>"}
        )

        def detect_logged_out(response):
            return "Logged out" in response.httpx_response.text

        with pytest.raises(RotatedSessionError) as exc_info:
            mock_sync_client.execute(req, detect_logged_out)

        err = exc_info.value
        assert err.request is req
        assert err.response is not None
        assert err.raw_response is not None

    @respx.mock
    def test_validator_false_returns_response_unchanged(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a validator that returns False yields the response as normal.
        """
        req = make_request(session_id=10)

        respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            json={"html": "<html>Still logged in</html>"}
        )

        response = mock_sync_client.execute(req, lambda _: False)

        assert response.scrape_do_status_code == 200

    @respx.mock
    def test_validator_skipped_when_no_session_id(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the validator is never invoked when session_id is None,
        even if a validator is provided.
        """
        req = make_request(session_id=None)

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        validator = mocker.MagicMock(return_value=True)
        response = mock_sync_client.execute(req, validator)

        validator.assert_not_called()
        assert response.scrape_do_status_code == 200

    @respx.mock
    def test_no_validator_returns_response(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a stateful request without a validator returns the response
        as-is, with no implicit session checking.
        """
        req = make_request(session_id=10)

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        response = mock_sync_client.execute(req)

        assert response.scrape_do_status_code == 200


class TestClientEventHooks:

    @respx.mock
    def test_request_hook_fires_once_regardless_of_retries(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the request hook fires exactly once before the retry loop,
        even when the SDK retries a 429/502 chain.
        """
        req = make_request()
        request_hook = mocker.MagicMock()
        mock_sync_client.event_hooks = {"request": [request_hook]}

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(502),
            httpx.Response(200)
            ]

        mock_sync_client.execute(req)

        request_hook.assert_called_once_with(req)

    @respx.mock
    def test_response_hook_fires_once_on_success(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the response hook fires exactly once when a request succeeds.
        """
        req = make_request()
        response_hook = mocker.MagicMock()
        mock_sync_client.event_hooks = {"response": [response_hook]}

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        response = mock_sync_client.execute(req)

        response_hook.assert_called_once_with(response)

    @respx.mock
    def test_response_hook_fires_after_retries_exhausted(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the response hook fires for the final response when the
        retry budget is exhausted on a retryable status.
        """
        req = make_request()
        response_hook = mocker.MagicMock()
        mock_sync_client.event_hooks = {"response": [response_hook]}

        respx.get(url__startswith="https://api.scrape.do").respond(502)

        response = mock_sync_client.execute(req)

        response_hook.assert_called_once_with(response)
        assert response.scrape_do_status_code == 502

    @respx.mock
    def test_retry_hook_fires_with_response_on_retryable_status(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the retry hook receives (attempt, request, response, None)
        when the SDK retries on a 429/502/510 status.
        """
        req = make_request()
        retry_hook = mocker.MagicMock()
        mock_sync_client.event_hooks = {"retry": [retry_hook]}

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200)
            ]

        mock_sync_client.execute(req)

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
    def test_retry_hook_fires_with_exception_on_request_error(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the retry hook receives (attempt, request, None, exc) when
        the SDK retries due to an httpx.RequestError.
        """
        mock_sync_client.max_retries = 1
        req = make_request()
        retry_hook = mocker.MagicMock()
        mock_sync_client.event_hooks = {"retry": [retry_hook]}

        route = respx.get(url__startswith="https://api.scrape.do")
        connect_err = httpx.ConnectError("transport down")
        route.side_effect = [connect_err, httpx.Response(200)]

        mock_sync_client.execute(req)

        retry_hook.assert_called_once()
        attempt, hook_request, hook_response, hook_exc = (
            retry_hook.call_args[0]
            )
        assert attempt == 0
        assert hook_request is req
        assert hook_response is None
        assert hook_exc is connect_err

    @respx.mock
    def test_no_event_hooks_default_does_not_break(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Regression: a client constructed without event_hooks must execute
        cleanly without raising AttributeError on the hook call sites.
        """
        req = make_request()
        # mock_sync_client is constructed with event_hooks=None; the SDK
        # should normalize this to an empty dict at construction time.
        assert mock_sync_client.event_hooks == {}

        respx.get(url__startswith="https://api.scrape.do").respond(200)

        response = mock_sync_client.execute(req)

        assert response.scrape_do_status_code == 200
