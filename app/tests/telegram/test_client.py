import json
import httpx
import pytest
from agentmon.telegram.client import BotClient, TelegramError, inline_keyboard


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


@pytest.mark.asyncio
async def test_ok_false_raises_and_hides_token():
    def handler(request):
        return httpx.Response(200, json={
            "ok": False, "error_code": 403,
            "description": "Forbidden: bot was kicked from the chat"})
    client = BotClient("SECRET_TOKEN", "https://api.telegram.org",
                       transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramError) as ei:
        await client.send_message("111", "x")
    await client.aclose()
    assert "403" in str(ei.value)
    assert "SECRET_TOKEN" not in str(ei.value)


@pytest.mark.asyncio
async def test_http_error_hides_token_in_url():
    def handler(request):
        return httpx.Response(500, text="boom")
    client = BotClient("SECRET_TOKEN", "https://api.telegram.org",
                       transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramError) as ei:
        await client.send_message("111", "x")
    await client.aclose()
    assert "500" in str(ei.value)
    assert "SECRET_TOKEN" not in str(ei.value)
    assert ei.value.__cause__ is None
