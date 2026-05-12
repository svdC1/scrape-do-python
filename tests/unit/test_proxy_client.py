import ssl
import pytest
import httpx
from unittest.mock import patch
import respx
from scrape_do.proxy_client import ScrapeDoProxyClient
from scrape_do.constants import DEFAULT_PROXY_SSL_CONTEXT
from scrape_do.models import (
    RequestParameters,
    PreparedScrapeDoRequest
    )
from scrape_do.exceptions import (
    APIConnectionError,
    RotatedSessionError
    )

pytestmark = pytest.mark.unit


class TestProxyClientInitialization:

    def test_missing_api_token_raises(self, mock_env_vars):
        """
        Ensures that initializing the proxy client without an API token
        raises a ValueError.
        """
        with pytest.raises(
            ValueError,
            match="token must be provided"
        ):
            ScrapeDoProxyClient()

    def test_api_token_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """
        Ensures the API token is correctly acquired from the env variable.
        """
        monkeypatch.setenv("SCRAPE_DO_API_KEY", "env_api_token")

        with ScrapeDoProxyClient(retry_backoff=10) as client:
            assert client.api_token == "env_api_token"

    def test_api_token_from_arg(self, mock_env_vars):
        """
        Ensures the API token is correctly acquired from the argument.
        """
        with ScrapeDoProxyClient("arg_api_token") as client:
            assert client.api_token == "arg_api_token"

    def test_default_verify_uses_bundled_ca_context(self, mock_env_vars):
        """
        Ensures the proxy client defaults `verify` to the bundled-CA
        SSL context — the key behavioral difference vs the API-mode
        client.
        """
        with ScrapeDoProxyClient(api_token="test") as client:
            assert client._verify is DEFAULT_PROXY_SSL_CONTEXT

    def test_explicit_verify_overrides_default(self, mock_env_vars):
        """
        Ensures user-provided `verify` values are stored verbatim.
        """
        with ScrapeDoProxyClient(api_token="test", verify=True) as client:
            assert client._verify is True
        with ScrapeDoProxyClient(api_token="test", verify=False) as client:
            assert client._verify is False
        custom_ctx = ssl.create_default_context()
        with ScrapeDoProxyClient(
            api_token="test",
            verify=custom_ctx
        ) as client:
            assert client._verify is custom_ctx

    def test_default_max_pooled_clients(self, mock_env_vars):
        """
        Ensures the pool size defaults to 16 and is overridable.
        """
        with ScrapeDoProxyClient(api_token="test") as client:
            assert client.max_pooled_clients == 16
        with ScrapeDoProxyClient(
            api_token="test",
            max_pooled_clients=4
        ) as client:
            assert client.max_pooled_clients == 4

    def test_pool_starts_empty(self, mock_env_vars):
        """
        Ensures the client pool is empty at construction time —
        clients are created lazily inside `execute()`.
        """
        with ScrapeDoProxyClient(api_token="test") as client:
            assert len(client._client_pool) == 0

    def test_context_manager_enter_returns_self(self, mock_env_vars):
        """
        Ensures the context manager returns the client instance.
        """
        with ScrapeDoProxyClient(api_token="test") as client:
            assert isinstance(client, ScrapeDoProxyClient)
            assert client.api_token == "test"

    def test_context_manager_exit_returns_false(self, mock_env_vars):
        """
        Ensures __exit__ returns False so exceptions propagate.
        """
        client = ScrapeDoProxyClient(api_token="test")
        result = client.__exit__(None, None, None)
        assert result is False


class TestProxyClientPool:
    """Behavioral tests for the LRU client pool."""

    @respx.mock
    def test_pool_caches_client_per_proxy_url(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures two requests with the same params reuse the same
        pooled `httpx.Client`.
        """
        req1 = make_request()
        req2 = make_request()

        respx.get("https://example.com").respond(status_code=200)

        mock_sync_proxy_client.execute(req1)
        mock_sync_proxy_client.execute(req2)

        assert len(mock_sync_proxy_client._client_pool) == 1

    @respx.mock
    def test_pool_partitions_by_proxy_url(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures requests with different params get different pooled
        clients (because the formatted proxy URL differs).
        """
        req1 = make_request(super=True)
        req2 = make_request(super=False)

        respx.get("https://example.com").respond(status_code=200)

        mock_sync_proxy_client.execute(req1)
        mock_sync_proxy_client.execute(req2)

        assert len(mock_sync_proxy_client._client_pool) == 2

    @respx.mock
    def test_pool_evicts_lru_when_full(
        self,
        mock_env_vars,
        make_request,
        mock_sleep
    ):
        """
        Ensures the LRU entry is evicted (and closed) when the pool
        exceeds `max_pooled_clients`.
        """
        respx.get("https://example.com").respond(status_code=200)

        with ScrapeDoProxyClient(
            api_token="test",
            verify=False,
            max_pooled_clients=2
        ) as client:
            # Three distinct param combinations → three distinct proxy
            # URLs → pool overflow.
            client.execute(make_request(super=True))
            client.execute(make_request(super=False))
            client.execute(make_request(super=True, render=False))

            assert len(client._client_pool) == 2

    @respx.mock
    def test_pool_lru_touch_on_hit(
        self,
        mock_env_vars,
        make_request,
        mock_sleep
    ):
        """
        Ensures a cache hit moves the entry to the back of the LRU
        ordering — so an active key survives a subsequent miss.
        """
        respx.get("https://example.com").respond(status_code=200)

        with ScrapeDoProxyClient(
            api_token="test",
            verify=False,
            max_pooled_clients=2
        ) as client:
            req_a = make_request(super=True)
            req_b = make_request(super=False)
            req_c = make_request(super=True, render=False)

            client.execute(req_a)       # pool: [A]
            client.execute(req_b)       # pool: [A, B]
            client.execute(req_a)       # pool: [B, A]  (A bumped to MRU)
            client.execute(req_c)       # pool: [A, C]  (B evicted, not A)

            pool_keys = list(client._client_pool.keys())
            # Two clients live: A and C. B was the LRU and got evicted.
            assert len(pool_keys) == 2

    @respx.mock
    def test_close_drains_pool(
        self,
        mock_env_vars,
        make_request,
        mock_sleep,
        mocker
    ):
        """
        Ensures close() closes every pooled `httpx.Client` and empties
        the pool.
        """
        respx.get("https://example.com").respond(status_code=200)

        client = ScrapeDoProxyClient(api_token="test", verify=False)
        client.execute(make_request(super=True))
        client.execute(make_request(super=False))

        # Spy on every pooled client's close().
        spies = [
            mocker.spy(c, "close")
            for c in client._client_pool.values()
        ]
        assert len(spies) == 2

        client.close()

        assert len(client._client_pool) == 0
        for spy in spies:
            spy.assert_called_once()

    @respx.mock
    def test_context_manager_drains_pool_on_exit(
        self,
        mock_env_vars,
        make_request,
        mock_sleep,
        mocker
    ):
        """
        Ensures exiting the context manager closes every pooled
        `httpx.Client`.
        """
        respx.get("https://example.com").respond(status_code=200)

        with ScrapeDoProxyClient(
            api_token="test",
            verify=False
        ) as client:
            client.execute(make_request(super=True))
            client.execute(make_request(super=False))
            assert len(client._client_pool) == 2

        # On exit the pool is drained.
        assert len(client._client_pool) == 0


class TestProxyClientRouting:

    @pytest.mark.parametrize(
        "request_kwargs, error_match",
        [
            # **api_kwargs + params
            ({
                "method": "GET",
                "target_url": "https://example.com",
                "params": RequestParameters(url="https://example.com"),
                "render": False
                },
             "Choose one method of configuration"
             ),
        ]
    )
    def test_request_param_constraints(
        self,
        request_kwargs,
        error_match,
        mock_env_vars,
        mock_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures `params` + `**api_kwargs` together raise ValueError.

        Note: unlike the API-mode client, proxy mode doesn't accept raw
        `api.scrape.do` URLs, so there's no smart-routing case for those.
        """
        with patch.object(
            mock_sync_proxy_client,
            "execute",
            autospec=True
        ):
            with pytest.raises(
                ValueError,
                match=error_match
            ):
                mock_sync_proxy_client.request(**request_kwargs)

    def test_get_routing(
        self,
        mock_env_vars,
        mock_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures GET requests route to the request method with method=GET.
        """
        with patch.object(
            mock_sync_proxy_client,
            "request",
            autospec=True
        ) as mock_request:
            mock_sync_proxy_client.get(
                "https://example.com",
                render=False
                )
            args, kwargs = mock_request.call_args
            assert args[0] == "GET"

    def test_post_routing(
        self,
        mock_env_vars,
        mock_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures POST requests route to the request method with method=POST.
        """
        with patch.object(
            mock_sync_proxy_client,
            "request",
            autospec=True
        ) as mock_request:
            mock_sync_proxy_client.post(
                "https://example.com",
                render=False
                )
            args, kwargs = mock_request.call_args
            assert args[0] == "POST"

    def test_post_forwards_session_validator(
        self,
        mock_env_vars,
        mock_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Regression: post() must forward session_validator to request(),
        not drop it (mirrors the bug fix applied to the API-mode sync
        client).
        """
        def _validator(_):
            return False

        with patch.object(
            mock_sync_proxy_client,
            "request",
            autospec=True
        ) as mock_request:
            mock_sync_proxy_client.post(
                "https://example.com",
                session_validator=_validator,
                render=False,
                )
            kwargs = mock_request.call_args.kwargs
            assert kwargs.get("session_validator") is _validator

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
             }
         ]
        )
    def test_request_param_valid_config(
        self,
        request_kwargs,
        mock_env_vars,
        mock_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures `.request()` correctly assembles the
        `PreparedScrapeDoRequest` from both pre-built `params` and
        kwargs paths. Unlike the API-mode client, proxy mode does not
        smart-route raw `api.scrape.do` URLs.
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
            mock_sync_proxy_client,
            "execute",
            autospec=True
        ) as mock_execute:
            mock_sync_proxy_client.request(**request_kwargs)

            args, kwargs = mock_execute.call_args
            real_req: PreparedScrapeDoRequest = args[0]

            assert expected_request == real_req


class TestProxyClientExecutionEngine:

    @respx.mock
    def test_successful_request(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a 200 OK target response passes through without retrying.
        """
        req = make_request()

        route = respx.get("https://example.com").respond(
            status_code=200,
            json={"html": "<html>Success</html>"}
        )

        response = mock_sync_proxy_client.execute(req)

        assert response.scrape_do_status_code == 200
        assert route.call_count == 1

    @respx.mock
    def test_retry_on_gateway_errors_success(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the client retries on Scrape.do gateway errors and
        eventually succeeds.
        """
        req = make_request()

        route = respx.get("https://example.com")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(502),
            httpx.Response(200)
            ]

        response = mock_sync_proxy_client.execute(req)

        assert response.scrape_do_status_code == 200
        assert route.call_count == 3

    @respx.mock
    def test_max_retries_exhausted_returns_error_response(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the client gives up after max_retries and returns the
        final failed response.
        """
        mock_sync_proxy_client.retry_backoff = 10.0

        req = make_request()

        route = respx.get("https://example.com").respond(502)
        response = mock_sync_proxy_client.execute(req)

        assert response.scrape_do_status_code == 502
        assert response.is_proxy_error is True
        assert route.call_count == 4  # 1 initial + 3 retries

    @respx.mock
    def test_non_retryable_error_returns_immediately(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures non-retryable HTTP statuses don't trigger retries.
        """
        req = make_request()

        route = respx.get("https://example.com").respond(403)

        response = mock_sync_proxy_client.execute(req)

        assert response.scrape_do_status_code == 403
        assert route.call_count == 1

    @respx.mock
    def test_network_error_raises_api_connection_error(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures transport failures raise APIConnectionError after
        retries are exhausted.
        """
        mock_sync_proxy_client.max_retries = 1
        req = make_request()

        route = respx.get("https://example.com")
        route.side_effect = [
            httpx.ConnectError("Failed to establish a connection"),
            httpx.ConnectError("Failed to establish a connection")
            ]

        with pytest.raises(APIConnectionError) as exc_info:
            mock_sync_proxy_client.execute(req)

        assert "Network transport failed" in str(exc_info.value)
        assert route.call_count == 2


class TestProxyClientSessionValidator:

    @respx.mock
    def test_validator_true_raises_rotated_session_error(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the SDK raises RotatedSessionError when the validator
        returns True.
        """
        req = make_request(session_id=10)

        respx.get("https://example.com").respond(
            status_code=200,
            json={"html": "<html>Logged out</html>"}
        )

        def detect_logged_out(response):
            return "Logged out" in response.httpx_response.text

        with pytest.raises(RotatedSessionError) as exc_info:
            mock_sync_proxy_client.execute(req, detect_logged_out)

        err = exc_info.value
        assert err.request is req
        assert err.response is not None

    @respx.mock
    def test_validator_false_returns_response(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures a validator that returns False yields the response.
        """
        req = make_request(session_id=10)

        respx.get("https://example.com").respond(status_code=200)

        response = mock_sync_proxy_client.execute(req, lambda _: False)

        assert response.scrape_do_status_code == 200

    @respx.mock
    def test_validator_skipped_when_no_session_id(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the validator is never called when session_id is None.
        """
        req = make_request(session_id=None)

        respx.get("https://example.com").respond(200)

        validator = mocker.MagicMock(return_value=True)
        response = mock_sync_proxy_client.execute(req, validator)

        validator.assert_not_called()
        assert response.scrape_do_status_code == 200


class TestProxyClientEventHooks:

    @respx.mock
    def test_request_hook_fires_once_regardless_of_retries(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the request hook fires exactly once even when retries
        occur underneath.
        """
        req = make_request()
        request_hook = mocker.MagicMock()
        mock_sync_proxy_client.event_hooks = {"request": [request_hook]}

        route = respx.get("https://example.com")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(502),
            httpx.Response(200)
            ]

        mock_sync_proxy_client.execute(req)

        request_hook.assert_called_once_with(req)

    @respx.mock
    def test_response_hook_fires_once_on_success(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the response hook fires exactly once on success.
        """
        req = make_request()
        response_hook = mocker.MagicMock()
        mock_sync_proxy_client.event_hooks = {"response": [response_hook]}

        respx.get("https://example.com").respond(200)

        response = mock_sync_proxy_client.execute(req)

        response_hook.assert_called_once_with(response)

    @respx.mock
    def test_retry_hook_fires_with_response_on_retryable_status(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the retry hook receives (attempt, request, response, None).
        """
        req = make_request()
        retry_hook = mocker.MagicMock()
        mock_sync_proxy_client.event_hooks = {"retry": [retry_hook]}

        route = respx.get("https://example.com")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200)
            ]

        mock_sync_proxy_client.execute(req)

        retry_hook.assert_called_once()
        attempt, hook_request, hook_response, hook_exc = (
            retry_hook.call_args[0]
            )
        assert attempt == 0
        assert hook_request is req
        assert hook_response is not None
        assert hook_exc is None

    @respx.mock
    def test_no_event_hooks_default_does_not_break(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mock_env_vars,
        mock_sleep
    ):
        """
        Regression: a client constructed without event_hooks must
        execute cleanly.
        """
        req = make_request()
        assert mock_sync_proxy_client.event_hooks == {}

        respx.get("https://example.com").respond(200)

        response = mock_sync_proxy_client.execute(req)

        assert response.scrape_do_status_code == 200

    @respx.mock
    def test_retry_hook_fires_with_exception_on_network_error(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures the retry hook receives (attempt, request, None, exc)
        when a transient transport error occurs and a retry follows.
        """
        req = make_request()
        retry_hook = mocker.MagicMock()
        mock_sync_proxy_client.event_hooks = {"retry": [retry_hook]}

        route = respx.get("https://example.com")
        route.side_effect = [
            httpx.ConnectError("transient"),
            httpx.Response(200)
            ]

        mock_sync_proxy_client.execute(req)

        retry_hook.assert_called_once()
        attempt, hook_request, hook_response, hook_exc = (
            retry_hook.call_args[0]
            )
        assert attempt == 0
        assert hook_request is req
        assert hook_response is None
        assert isinstance(hook_exc, httpx.ConnectError)


class TestProxyClientRequestOverrides:
    """
    Per-request overrides and callable-backoff branches that the core
    execution-engine tests don't otherwise touch.
    """

    @respx.mock
    def test_callable_backoff_on_network_error(
        self,
        mock_env_vars,
        make_request,
        mock_sleep
    ):
        """
        Ensures a callable `retry_backoff` is invoked with the attempt
        number on the RequestError path (matching the retryable-status
        branch's behavior).
        """
        backoff_calls = []

        def _backoff(attempt: int) -> float:
            backoff_calls.append(attempt)
            return 0.0

        with ScrapeDoProxyClient(
            api_token="test",
            verify=False,
            max_retries=1,
            retry_backoff=_backoff,
        ) as client:
            req = make_request()
            route = respx.get("https://example.com")
            route.side_effect = [
                httpx.ConnectError("transient"),
                httpx.Response(200),
                ]
            response = client.execute(req)

            assert response.scrape_do_status_code == 200
            assert backoff_calls == [0]

    @respx.mock
    def test_request_level_timeout_override(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures `r_timeout` on `.execute()` overrides the client-level
        timeout for that single call by reaching the pooled client.
        """
        req = make_request()
        respx.get("https://example.com").respond(200)

        # Warm the pool so we have a real pooled client to spy on.
        mock_sync_proxy_client.execute(req)
        pooled_client = next(
            iter(mock_sync_proxy_client._client_pool.values())
            )
        spy = mocker.spy(pooled_client, "request")

        custom_timeout = httpx.Timeout(5.0)
        mock_sync_proxy_client.execute(req, r_timeout=custom_timeout)

        spy.assert_called_once()
        assert spy.call_args.kwargs.get("timeout") == custom_timeout

    @respx.mock
    def test_request_level_extensions_override(
        self,
        mock_sync_proxy_client: ScrapeDoProxyClient,
        make_request,
        mocker,
        mock_env_vars,
        mock_sleep
    ):
        """
        Ensures `extensions` on `.execute()` is forwarded verbatim to
        the underlying httpx request.
        """
        req = make_request()
        respx.get("https://example.com").respond(200)

        mock_sync_proxy_client.execute(req)
        pooled_client = next(
            iter(mock_sync_proxy_client._client_pool.values())
            )
        spy = mocker.spy(pooled_client, "request")

        extensions = {"sni_hostname": "example.com"}
        mock_sync_proxy_client.execute(req, extensions=extensions)

        spy.assert_called_once()
        assert spy.call_args.kwargs.get("extensions") == extensions
