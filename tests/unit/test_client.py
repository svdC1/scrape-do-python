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


class TestClientSessionState:

    @respx.mock
    def test_consistent_rid_no_action(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures that multiple requests keeping the same RID do not trigger
        warnings.
        """
        req1 = make_request(session_id=10)
        req2 = make_request(session_id=10)

        # The rid remains "node-A" for both requests
        respx.get(url__startswith="https://api.scrape.do").respond(
            status_code=200,
            headers={"scrape.do-rid": "node-A"}
        )

        mock_sync_client.execute(req1)
        mock_sync_client.execute(req2)

        assert len(mock_sync_client._active_sessions["10"]) == 1
        assert mock_sync_client._active_sessions["10"][-1] == "node-A"

    @respx.mock
    def test_rotated_rid_logs_warning_by_default(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a session rotation logs a warning when
        raise_on_rid_rotation=False.
        """
        req1 = make_request(session_id=10)
        req2 = make_request(session_id=10)

        # Spy on the client's internal logger
        mock_logger = mocker.patch("scrape_do.client.logger.warning")

        route = respx.get(url__startswith="https://api.scrape.do")

        # Simulate the proxy rotating the session
        route.side_effect = [
            httpx.Response(200, headers={"scrape.do-rid": "node-A"}),
            httpx.Response(200, headers={"scrape.do-rid": "node-B"})
        ]

        mock_sync_client.execute(req1)
        mock_sync_client.execute(req2)
        session_id_hist = mock_sync_client._active_sessions["10"]
        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]

        assert "Previous RID: node-A" in log_msg
        assert "New RID: node-B" in log_msg
        # The history should now contain both RIDs
        assert session_id_hist == ["node-A", "node-B"]

    @respx.mock
    def test_rotated_rid_raises_exception_when_configured(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a node rotation raises RotatedSessionError when configured to
        do so.
        """
        mock_sync_client.raise_on_rid_rotation = True

        req1 = make_request(session_id=10)
        req2 = make_request(session_id=10)

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.Response(200, headers={"scrape.do-rid": "node-A"}),
            httpx.Response(200, headers={"scrape.do-rid": "node-B"})
        ]

        # First request establishes the session
        mock_sync_client.execute(req1)

        # Second request detects the rotation and halts
        with pytest.raises(RotatedSessionError) as exc_info:
            mock_sync_client.execute(req2)

        # Verify the exception's telemetry data
        err = exc_info.value
        assert err.last_known_rid == "node-A"
        assert err.new_rid == "node-B"
        assert err.session_id == 10
        assert err.response is not None

    @respx.mock
    def test_no_session_id_skips_tracking(
        self,
        mock_sync_client: ScrapeDoClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures that tracking is bypassed completely if no session_id is
        requested.
        """
        req1 = make_request(session_id=None)
        req2 = make_request(session_id=None)

        route = respx.get(url__startswith="https://api.scrape.do")
        route.side_effect = [
            httpx.Response(200, headers={"scrape.do-rid": "node-A"}),
            httpx.Response(200, headers={"scrape.do-rid": "node-B"})
        ]

        mock_sync_client.execute(req1)
        mock_sync_client.execute(req2)

        assert len(mock_sync_client._active_sessions) == 0
