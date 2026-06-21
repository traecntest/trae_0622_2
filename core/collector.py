from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from utils.dom_cleaner import DOMCleaner, CleanResult


@dataclass
class Material:
    id: str
    title: str
    source_url: str
    text: str
    html: str
    images: list = field(default_factory=list)
    tables: int = 0
    paragraphs: int = 0
    created_at: float = 0.0
    tags: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Material":
        return cls(**d)


class Collector:
    def __init__(self, cleaner: DOMCleaner | None = None,
                 on_event=None):
        self.cleaner = cleaner or DOMCleaner()
        self.on_event = on_event
        self._materials: dict[str, Material] = {}

    def _emit(self, event: str, payload: dict):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass

    async def collect(self, raw_html: str, source_url: str = "",
                      title: str = "", tags: list | None = None) -> Material:
        loop = asyncio.get_event_loop()
        result: CleanResult = await loop.run_in_executor(
            None, self.cleaner.clean, raw_html, source_url
        )
        mid = hashlib.md5(
            f"{source_url}:{result.title}:{time.time()}".encode()
        ).hexdigest()[:16]

        mat = Material(
            id=mid,
            title=title or result.title or "未命名素材",
            source_url=source_url,
            text=result.text,
            html=result.html,
            images=result.images,
            tables=result.tables,
            paragraphs=result.paragraphs,
            created_at=time.time(),
            tags=tags or [],
            extra={"word_count": len(result.text)},
        )
        self._materials[mid] = mat
        self._emit("material.collected", {"id": mid, "title": mat.title})
        return mat

    async def collect_many(self, items: list[dict]) -> list[Material]:
        tasks = [self.collect(i["html"], i.get("url", ""), i.get("title", ""),
                              i.get("tags")) for i in items]
        return await asyncio.gather(*tasks)

    def list_materials(self) -> list[Material]:
        return list(self._materials.values())

    def get(self, mid: str) -> Material | None:
        return self._materials.get(mid)

    def delete(self, mid: str) -> bool:
        return self._materials.pop(mid, None) is not None

    def search(self, keyword: str) -> list[Material]:
        kw = keyword.lower()
        return [
            m for m in self._materials.values()
            if kw in m.title.lower() or kw in m.text.lower()
            or any(kw in t.lower() for t in m.tags)
        ]

    def preview(self, mid: str, max_chars: int = 500) -> str:
        m = self._materials.get(mid)
        if not m:
            return ""
        return m.text[:max_chars] + ("..." if len(m.text) > max_chars else "")

    def stats(self) -> dict[str, Any]:
        mats = list(self._materials.values())
        return {
            "count": len(mats),
            "total_words": sum(len(m.text) for m in mats),
            "total_images": sum(len(m.images) for m in mats),
            "total_tables": sum(m.tables for m in mats),
        }


collector = Collector()
