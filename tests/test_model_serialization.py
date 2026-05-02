import pytest
import json
import httpx
from scrape_do.models import (
    ClickAction,
    WaitAction,
    WaitSelectorAction,
    ScreenShotAction,
    FillAction,
    ScrollToAction,
    ScrollXAction,
    ScrollYAction,
    ExecuteAction,
    WaitForRequestCompletionAction,
    RequestParameters,
    ScrapeDoResponse,
    PreparedScrapeDoRequest
    )


class TestRequestParametersSerialization:

    @staticmethod
    def test_serialize_minimal_request(example_url):
        """
        Ensures default/None parameters are cleanly dropped
        (exclude_none=True).
        """
        params = RequestParameters(url=example_url)
        payload = params.to_api_params()

        assert payload == {"url": example_url}

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"wait_until": "networkidle0"},
          {"waitUntil": "networkidle0"}
          ),
         ({"custom_wait": 5000},
          {"customWait": 5000}
          ),
         ({"wait_selector": "#example"},
          {"waitSelector": "#example"}
          ),
         ({"width": 1920},
          {"width": 1920}
          ),
         ({"height": 1080},
          {"height": 1080}
          ),
         ({"return_json": True},
          {"returnJSON": "true"}
          ),
         ({"block_resources": True},
          {"blockResources": "true"}
          ),
         ({"screenshot": True, "return_json": "true"},
          {"screenShot": "true", "returnJSON": "true"}
          ),
         ({"full_screenshot": True, "return_json": True},
          {"fullScreenShot": "true", "returnJSON": "true"}
          ),
         ({"particular_screenshot": "#example", "return_json": True},
          {"particularScreenShot": "#example", "returnJSON": "true"}
          ),
         ({"show_frames": True, "return_json": True},
          {"showFrames": "true", "returnJSON": "true"}
          ),
         ({"show_websocket_requests": True, "return_json": True},
          {"showWebsocketRequests": "true", "returnJSON": "true"})
         ]
        )
    @staticmethod
    def test_serialize_render_params(field_dict, expected_dict, example_url):
        """
        Ensures render-dependent fields are serialized
        correctly
        """
        params = RequestParameters(
            url=example_url,
            render=True,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url, "render": "true"}
        expected_payload.update(expected_dict)
        assert payload == expected_payload

    @pytest.mark.parametrize(
        "action, args, expected_dict",
        [(ClickAction,
          {"selector": "#example"},
          {"Action": "Click", "Selector": "#example"},
          ),
         (WaitAction,
          {"timeout": 5000},
          {"Action": "Wait", "Timeout": 5000}
          ),
         (WaitSelectorAction,
          {"wait_selector": "#example", "timeout": 5000},
          {"Action": "WaitSelector", "WaitSelector": "#example",
           "Timeout": 5000}
          ),
         (ScreenShotAction,
          {},
          {"Action": "ScreenShot"}
          ),
         (ScreenShotAction,
          {"full_screenshot": "true"},
          {"Action": "ScreenShot", "fullScreenShot": "true"}
          ),
         (ScreenShotAction,
          {"particular_screenshot": "#example"},
          {"Action": "ScreenShot", "particularScreenShot": "#example"}
          ),
         (FillAction,
          {"selector": "#example", "value": "example"},
          {"Action": "Fill", "Selector": "#example", "Value": "example"}
          ),
         (ScrollToAction,
          {"selector": "#example"},
          {"Action": "ScrollTo", "Selector": "#example"}
          ),
         (ScrollXAction,
          {"value": 100},
          {"Action": "ScrollX", "Value": 100}
          ),
         (ScrollYAction,
          {"value": 100},
          {"Action": "ScrollY", "Value": 100}
          ),
         (ExecuteAction,
          {"execute": "example"},
          {"Action": "Execute", "Execute": "example"}
          ),
         (WaitForRequestCompletionAction,
          {"url_pattern": "example", "timeout": 1000},
          {"Action": "WaitForRequestCompletion", "UrlPattern": "example",
           "Timeout": 1000}
          )
         ]
        )
    @staticmethod
    def test_serialize_play_with_browser(
        action,
        args,
        expected_dict,
        example_url
    ):
        """
        Ensures playWithBrowser actions are serialized correctly
        """
        actions = [action(**args)]
        params = RequestParameters(
            url=example_url,
            render=True,
            return_json=True,
            play_with_browser=actions
        )
        payload = params.to_api_params()

        parsed_actions = json.loads(payload["playWithBrowser"])
        assert parsed_actions[0] == expected_dict

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"custom_headers": True}, {"customHeaders": "true"}),
         ({"extra_headers": True}, {"extraHeaders": "true"}),
         ({"forward_headers": True}, {"forwardHeaders": "true"}),
         ({"set_cookies": "cookie1=value"}, {"setCookies": "cookie1=value"})
         ]
        )
    @staticmethod
    def test_serialize_header_and_cookies(
        field_dict,
        expected_dict,
        example_url
    ):
        """
        Ensures that headers and cookies parameters are serialized correctly
        """
        params = RequestParameters(
            url=example_url,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url}
        expected_payload.update(expected_dict)
        assert payload == expected_payload

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"disable_redirection": True}, {"disableRedirection": "true"}),
         ({"timeout": 5000}, {"timeout": 5000}),
         ({"retry_timeout": 5000}, {"retryTimeout": 5000}),
         ({"disable_retry": False}, {"disableRetry": "false"}),
         ({"super": True}, {"super": "true"}),
         ({"session_id": 1000}, {"sessionId": 1000}),
         ({"device": "desktop"}, {"device": "desktop"}),
         ({"transparent_response": True}, {"transparentResponse": "true"}),
         ({"pure_cookies": True}, {"pureCookies": "true"}),
         ({"output": "raw"}, {"output": "raw"})
         ]
        )
    @staticmethod
    def test_serialize_network_and_output_parameters(
        field_dict,
        expected_dict,
        example_url
    ):
        """
        Ensures network, routing and output parameters are serialized correctly
        """
        params = RequestParameters(
            url=example_url,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url}
        expected_payload.update(expected_dict)
        assert payload == expected_payload

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"geo_code": "us"}, {"geoCode": "us"}),
         ({"regional_geo_code": "europe"}, {"regionalGeoCode": "europe"}),
         ({"geo_code": "us", "postal_code": "90210"},
          {"geoCode": "us", "postalcode": "90210"}
          )
         ]
        )
    @staticmethod
    def test_serialize_location_parameters(
        field_dict,
        expected_dict,
        example_url
    ):
        """
        Ensures that geo-targeting parameters are serialized correctly
        """
        params = RequestParameters(
            url=example_url,
            super=True,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url, "super": "true"}
        expected_payload.update(expected_dict)
        assert payload == expected_payload


class TestScrapeDoResponseSerialization:

    @staticmethod
    def test_lazy_json_parsing_nested_models(example_url, mock_json_payload):
        """
        Validates that the model correctly deserializes camelCase JSON payloads
        into Pydantic models.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True
                ),
            method="GET"
        )

        http_resp = httpx.Response(200, json=mock_json_payload)
        response = ScrapeDoResponse(request=req, response=http_resp)

        # Network Requests Extraction
        net_reqs = response.network_requests
        assert net_reqs is not None
        assert len(net_reqs) == 1
        assert str(net_reqs[0].url) == "https://example.com/api"
        assert net_reqs[0].method == "POST"

        # WebSocket Extraction
        ws_reqs = response.websocket_requests
        assert ws_reqs is not None
        assert len(ws_reqs) == 1
        assert ws_reqs[0].type == "received"
        assert ws_reqs[0].is_text is True
        assert (
            ws_reqs[0].event.response.payload_data ==
            '{"live_price": 65000.00}'
            )

        # Action Results Extraction
        actions = response.action_results
        assert actions is not None
        assert len(actions) == 2
        assert actions[0].action == "Click"
        assert actions[0].success is False

        # Screenshots Extraction
        shots = response.screenshots
        assert len(shots) == 1
        assert shots[0].screenshot_type == "FullScreenShot"

        # Frames Extraction
        frames = response.frames
        assert len(frames) == 1
        assert frames[0].content == "<html>Iframe Content</html>"

    @staticmethod
    def test_missing_optional_json_arrays_safe_fallback(example_url):
        """
        Ensures the properties return None when the arrays are missing
        from the payload.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True
                ),
            method="GET"
        )
        http_resp = httpx.Response(
            200, json={"statusCode": 200, "content": "<html>Data</html>"}
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert response.network_requests is None
        assert response.websocket_requests is None
        assert response.action_results is None
        assert response.screenshots is None
        assert response.frames is None
