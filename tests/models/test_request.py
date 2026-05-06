import pytest
from pydantic import ValidationError
from scrape_do.models import (
    RequestParameters,
    PreparedScrapeDoRequest,
)


class TestPreparedScrapeDoRequestValidation:

    @pytest.mark.parametrize(
        "method",
        ["GET",
         "POST",
         "PUT",
         "PATCH",
         "DELETE",
         "HEAD",
         "OPTIONS"
         ]
    )
    @staticmethod
    def test_render_method(method, example_url):
        """
        Ensures that only the "GET" method is allowed when `render=True`
        """
        params = RequestParameters(url=example_url, render=True)

        if method == "GET":
            PreparedScrapeDoRequest(
                api_params=params,
                method=method
            )
        else:

            with pytest.raises(
                ValidationError,
                match="'GET' method"
            ):
                PreparedScrapeDoRequest(
                    api_params=params,
                    method=method
                )

    @staticmethod
    def test_get_body_warning(example_url):
        """
        Ensures supplying a payload body with a GET request raises
        a UserWarning.
        """
        params = RequestParameters(url=example_url)

        with pytest.warns(
            UserWarning,
            match="violates standard HTTP specifications"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                method="GET",
                body={"search": "shoes"}
            )

    @staticmethod
    def test_orphaned_headers(example_url):
        """
        Ensures passing headers without enabling a header flag throws an error.
        """
        params = RequestParameters(url=example_url)

        with pytest.raises(
            ValidationError,
            match="no header routing flag"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                headers={"Authorization": "Bearer secret"}
            )

    @pytest.mark.parametrize(
        "header_field",
        [{"custom_headers": True},
         {"extra_headers": True},
         {"forward_headers": True}
         ]
        )
    @staticmethod
    def test_missing_headers_for_flag(header_field, example_url):
        """
        Ensures enabling a header flag without providing headers throws
        an error.
        """
        params = RequestParameters(
            url=example_url,
            **header_field
            )

        with pytest.raises(
            ValidationError,
            match="no 'headers' were provided"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
            )

    @staticmethod
    def test_invalid_extra_headers(example_url):
        """
        Ensures extra_headers enforce the strict 'sd-' prefix rule.
        """
        params = RequestParameters(
            url=example_url,
            extra_headers=True
            )

        with pytest.raises(
            ValidationError,
            match="prefixed with 'sd-'"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                headers={
                    "sd-Authorization": "Bearer secret",
                    "User-Agent": "MyBot"
                }
            )

    @staticmethod
    def test_valid_extra_headers(example_url):
        """
        Ensures properly prefixed extra_headers pass validation.
        """
        params = RequestParameters(
            url=example_url,
            extra_headers=True
            )

        req = PreparedScrapeDoRequest(
            api_params=params,
            headers={"sd-User-Agent": "MyBot", "sd-Accept": "application/json"}
        )

        assert req.headers["sd-User-Agent"] == "MyBot"
        assert req.headers["sd-Accept"] == "application/json"

    @pytest.mark.parametrize(
        "payload_type, body, att_name",
        [("form", {"user": "test"}, "data"),
         ("json", {"user": "test"}, "json"),
         ("raw", b"raw_bytes", "content")
         ]
        )
    @staticmethod
    def test_payload_routing(payload_type, body, att_name, example_url):
        """
        Ensures payloads are routed to the correct httpx argument based on
        payload_type.
        """
        params = RequestParameters(url=example_url)

        req_form = PreparedScrapeDoRequest(
            api_params=params,
            method="POST",
            body=body,
            payload_type=payload_type
        )
        assert att_name in req_form.to_httpx_kwargs()

    @pytest.mark.parametrize(
        "payload_type, body, error_msg",
        [("json", "<xml></xml>", "must be a Python dictionary"),
         ("raw", {"key": "value"}, "must be a string or bytes")
         ]
    )
    @staticmethod
    def test_payload_type_mismatch(payload_type, body, error_msg, example_url):
        """
        Ensures mismatched bodies and payload_types crash before execution.
        """
        params = RequestParameters(url=example_url)

        with pytest.raises(
            ValidationError,
            match=error_msg
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                method="POST",
                body=body,
                payload_type=payload_type
            )

    @staticmethod
    def test_token_insertion(example_url):
        """
        Ensures Scrape.do API key is optionally included if `token` parameter
        is provided
        """
        params = RequestParameters(url=example_url)

        req = PreparedScrapeDoRequest(
            api_params=params,
            method="GET"
            )

        token_included = req.to_httpx_kwargs("API_KEY")
        no_token = req.to_httpx_kwargs()

        assert "token" in token_included["params"]
        assert "token" not in no_token["params"]


class TestPreparedScrapeDoRequestSerialization:

    @staticmethod
    def test_serialize_header_to_httpx_kwargs(example_url):
        """
        Ensures custom headers are correctly serialized by the
        `to_httpx_kwargs` method
        """
        custom_headers = {"Header1": "Example", "Header2": "Example"}

        params = RequestParameters(
            url=example_url,
            render=True,
            custom_headers=True
            )

        req = PreparedScrapeDoRequest(
            method="GET",
            headers=custom_headers,
            api_params=params
            )

        httpx_kwargs = req.to_httpx_kwargs()

        assert httpx_kwargs["method"] == "GET"
        assert httpx_kwargs["headers"] == custom_headers
        assert httpx_kwargs["params"] == params.to_api_params()
        assert httpx_kwargs["url"] == "https://api.scrape.do/"
        assert "json" not in httpx_kwargs
        assert "content" not in httpx_kwargs
        assert "data" not in httpx_kwargs
