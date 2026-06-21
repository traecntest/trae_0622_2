from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._on_message_handlers: list = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        await self.broadcast("client.connected", {"count": len(self._clients)})

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._clients.discard(ws)
        await self.broadcast("client.disconnected", {"count": len(self._clients)})

    async def send(self, ws: WebSocket, event: str, payload: dict):
        try:
            await ws.send_text(json.dumps(
                {"event": event, "payload": payload, "ts": time.time()},
                ensure_ascii=False,
            ))
        except Exception:
            await self.disconnect(ws)

    async def broadcast(self, event: str, payload: dict):
        data = json.dumps(
            {"event": event, "payload": payload, "ts": time.time()},
            ensure_ascii=False,
        )
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def on_message(self, handler):
        self._on_message_handlers.append(handler)
        return handler

    async def handle_message(self, ws: WebSocket, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            await self.send(ws, "error", {"message": "无效的 JSON 消息"})
            return
        event = msg.get("event", "")
        payload = msg.get("payload", {})
        for handler in self._on_message_handlers:
            try:
                result = handler(event, payload)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is not None:
                    await self.send(ws, f"{event}.response", result)
            except Exception as e:
                await self.send(ws, "error", {"event": event, "message": str(e)})

    @property
    def client_count(self) -> int:
        return len(self._clients)


ws_manager = WSManager()
