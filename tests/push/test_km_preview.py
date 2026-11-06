import ast
from pathlib import Path
import re
import sys
import types

import httpx
from nonebot.adapters.onebot.v11.exception import ActionFailed
from push_test.core.helper.push.errors import send_with_media_retry
import pytest

ROOT = Path(__file__).resolve().parents[2]


def kill_url_pattern():
    tree = ast.parse((ROOT / "xiaobawang/plugins/core/command/km.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "KILL_URL":
            return ast.literal_eval(node.value)
    raise AssertionError("KILL_URL not found")


@pytest.mark.parametrize(("text", "kill_id"), [
    ("https://zkillboard.com/kill/139704981/", "139704981"),
    ("https://zkillboard.com/kill/139704981", "139704981"),  # no trailing slash
    ("看这个 https://zkillboard.com/kill/139704981/ 好亏", "139704981"),
    ("http://zkillboard.com/kill/139704981/", "139704981"),
    ("https://www.zkillboard.com/kill/139704981/", "139704981"),
    ("https://zkillboard.com/kill/99999999/", "99999999"),  # older 8-digit id
])
def test_kill_links_are_matched(text, kill_id):
    assert re.search(kill_url_pattern(), text).group(1) == kill_id


def test_other_zkb_pages_are_not_matched():
    assert re.search(kill_url_pattern(), "https://zkillboard.com/character/123/") is None


def failure(message):
    return ActionFailed(status="failed", retcode=1200, data=None, message=message)


class Sender:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


RICH_MEDIA = "invoke failed, { result: -1, errMsg: 'rich media transfer failed' }"


async def test_rich_media_failure_is_retried_until_sent():
    send = Sender(failure(RICH_MEDIA), failure(RICH_MEDIA), "receipt")
    assert await send_with_media_retry(send, delays=(0, 0)) == "receipt"
    assert send.calls == 3


async def test_rich_media_failure_gives_up_after_retries():
    send = Sender(*[failure(RICH_MEDIA)] * 3)
    with pytest.raises(ActionFailed):
        await send_with_media_retry(send, delays=(0, 0))
    assert send.calls == 3


@pytest.mark.parametrize("error", [failure("{ result: 110, errMsg: 'x' }"), TimeoutError()])
async def test_other_failures_are_not_retried(error):
    # A timed-out send may already have been delivered; retrying could duplicate it.
    send = Sender(error)
    with pytest.raises(type(error)):
        await send_with_media_retry(send, delays=(0, 0))
    assert send.calls == 1


@pytest.fixture
def killmail_api(monkeypatch):
    """Load the API module with its cache and HTTP client replaced."""
    client = types.SimpleNamespace()
    cache_module = types.ModuleType("kmtest.utils.common.cache")
    cache_module.cache = types.SimpleNamespace(TIME_HOUR=3600)
    cache_module.cache_result = lambda **_: lambda func: func
    http_module = types.ModuleType("kmtest.utils.common.http_client")
    http_module.get_client = lambda: client
    for name, module in {
        "kmtest": types.ModuleType("kmtest"),
        "kmtest.api": types.ModuleType("kmtest.api"),
        "kmtest.utils": types.ModuleType("kmtest.utils"),
        "kmtest.utils.common": types.ModuleType("kmtest.utils.common"),
        "kmtest.utils.common.cache": cache_module,
        "kmtest.utils.common.http_client": http_module,
    }.items():
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "kmtest.api.killmail", ROOT / "xiaobawang/plugins/core/api/killmail.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "kmtest.api.killmail", module)
    spec.loader.exec_module(module)
    return module, client


def respond(client, *responses):
    remaining = list(responses)

    async def get(url, **kwargs):
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome[0], json=outcome[1], request=httpx.Request("GET", url))

    client.get = get


@pytest.mark.parametrize("zkb_response", [
    httpx.ConnectTimeout("timeout"),
    (429, {}),
    (502, {}),
])
async def test_zkb_failures_raise_the_error_the_handler_catches(killmail_api, zkb_response):
    module, client = killmail_api
    respond(client, zkb_response)
    with pytest.raises(module.KillmailFetchError):
        await module.get_zkb_killmail(139704981)


async def test_successful_fetch_merges_zkb_data(killmail_api):
    module, client = killmail_api
    respond(client, (200, [{"zkb": {"hash": "abc"}}]), (200, {"killmail_id": 139704981}))
    data = await module.get_zkb_killmail(139704981)
    assert data == {"killmail_id": 139704981, "zkb": {"hash": "abc"}}


def test_image_urls_are_rewritten_by_kind():
    from push_test.core.utils.render.image_urls import rewrite_image_urls

    base = "https://images.newdoublex.space"
    html = (
        f'<img src="{base}/types/34/icon?size=32" onerror="this.src=\'{base}/types/670/icon\'">'
        f'<img data-src="{base}/characters/1/portrait?size=64">'
        f'<img src="{base}/corporations/2/logo"><img src="{base}/alliances/3/logo">'
        '<img src="https://example.com/types/1/icon">'
    )
    result = rewrite_image_urls(html, "http://icons:8080/", "https://images.evetech.net")
    assert result == (
        '<img src="http://icons:8080/types/34/icon?size=32" onerror="this.src=\'http://icons:8080/types/670/icon\'">'
        '<img data-src="https://images.evetech.net/characters/1/portrait?size=64">'
        '<img src="https://images.evetech.net/corporations/2/logo">'
        '<img src="https://images.evetech.net/alliances/3/logo">'
        '<img src="https://example.com/types/1/icon">'
    )
