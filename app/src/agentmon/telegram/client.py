"""Тонкий async-клиент Telegram Bot API поверх httpx."""
import httpx


def inline_keyboard(rows):
    """rows: list[list[(text, callback_data)]] → разметка inline-клавиатуры."""
    return {"inline_keyboard": [
        [{"text": t, "callback_data": cb} for (t, cb) in row] for row in rows
    ]}


class BotClient:
    def __init__(self, token: str, api_base: str, transport=None):
        self._base = f"{api_base}/bot{token}"
        kwargs = {"timeout": httpx.Timeout(60.0)}
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**kwargs)

    async def _call(self, method: str, payload: dict) -> dict:
        resp = await self._http.post(f"{self._base}/{method}", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_updates(self, offset=None, timeout: int = 25) -> list[dict]:
        payload = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        data = await self._call("getUpdates", payload)
        return data.get("result", [])

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> dict:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def answer_callback(self, callback_query_id: str, text=None) -> dict:
        payload = {"callback_query_id": callback_query_id}
        if text is not None:
            payload["text"] = text
        return await self._call("answerCallbackQuery", payload)

    async def aclose(self) -> None:
        await self._http.aclose()
