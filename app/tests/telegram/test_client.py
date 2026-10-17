import json
import httpx
import pytest
from agentmon.telegram.client import BotClient, inline_keyboard


def _transport(capture):
    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(request)
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})
    return httpx.MockTransport(handler)


def test_inline_keyboard_shape():
    kb = inline_keyboard([[("OK", "ok:1"), ("Нет", "no:1")]])
    assert kb == {"inline_keyboard": [[
        {"text": "OK", "callback_data": "ok:1"},
        {"text": "Нет", "callback_data": "no:1"},
    ]]}


@pytest.mark.asyncio
async def test_get_updates_calls_api_with_offset():
    cap = []
    client = BotClient("TOK", "https://api.telegram.org", transport=_transport(cap))
    res = await client.get_updates(offset=100, timeout=0)
    await client.aclose()
    assert res == [{"update_id": 7}]
    req = cap[0]
    assert "/botTOK/getUpdates" in str(req.url)
    body = json.loads(req.content)
    assert body["offset"] == 100


@pytest.mark.asyncio
async def test_send_message_includes_markup():
    cap = []
    client = BotClient("TOK", "https://api.telegram.org", transport=_transport(cap))
    await client.send_message("111", "привет", reply_markup=inline_keyboard([[("A", "a")]]))
    await client.aclose()
    body = json.loads(cap[0].content)
    assert body["chat_id"] == "111"
    assert body["text"] == "привет"
    assert body["reply_markup"]["inline_keyboard"][0][0]["text"] == "A"
