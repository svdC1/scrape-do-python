import pytest
import json
from pydantic import ValidationError
from scrape_do.models import (
    ClickAction,
    WaitAction,
    FillAction,
    ExecuteAction,
    ScrollToAction,
    ScrollXAction,
    ScrollYAction,
    ScreenShotAction,
    WaitForRequestCompletionAction,
    WaitSelectorAction,
    RequestParameters
    )

pytestmark = pytest.mark.unit


class TestBrowserActionValidation:
    @staticmethod
    def test_screenshot_validation():
        """
        Ensures the mutually exclusive parameters of the ScreenShot action
        can't be used together.
        """
        with pytest.raises(
            ValidationError,
            match="simultaneously"
        ):
            ScreenShotAction(
                full_screenshot=True,
                particular_screenshot="#example"
            )


class TestBrowserActionSerialization:

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
