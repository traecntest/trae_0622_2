from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiosqlite

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    title TEXT,
    source_url TEXT,
    text TEXT,
    html TEXT,
    images TEXT,
    tables INTEGER,
    paragraphs INTEGER,
    created_at REAL,
    tags TEXT,
    extra TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT,
    path TEXT,
    status TEXT,
    created_at REAL,
    updated_at REAL,
    meta TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    type TEXT,
    status TEXT,
    payload TEXT,
    result TEXT,
    created_at REAL,
    finished_at REAL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS ai_history (
    id TEXT PRIMARY KEY,
    role TEXT,
    input TEXT,
    output TEXT,
    source TEXT,
    elapsed REAL,
    created_at REAL
);
"""


class LocalDB:
    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or config.DB_PATH)
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("DB not connected. Call connect() first.")
        return self._db

    async def save_material(self, mat) -> bool:
        await self.db.execute(
            """INSERT OR REPLACE INTO materials
            (id, title, source_url, text, html, images, tables, paragraphs,
             created_at, tags, extra)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (mat.id, mat.title, mat.source_url, mat.text, mat.html,
             json.dumps(mat.images, ensure_ascii=False), mat.tables,
             mat.paragraphs, mat.created_at,
             json.dumps(mat.tags, ensure_ascii=False),
             json.dumps(mat.extra, ensure_ascii=False)),
        )
        await self.db.commit()
        return True

    async def list_materials(self) -> list[dict]:
        async with self.db.execute(
            "SELECT id,title,source_url,created_at,tables,paragraphs,extra FROM materials ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_material(self, mid: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM materials WHERE id=?", (mid,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def delete_material(self, mid: str) -> bool:
        await self.db.execute("DELETE FROM materials WHERE id=?", (mid,))
        await self.db.commit()
        return True

    async def save_task(self, task_id: str, ttype: str, status: str,
                        payload: dict, result: dict | None = None,
                        error: str = "") -> bool:
        await self.db.execute(
            """INSERT OR REPLACE INTO tasks
            (id, type, status, payload, result, created_at, finished_at, error)
            VALUES (?,?,?,?,?,?,?,?)""",
            (task_id, ttype, status, json.dumps(payload, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False) if result else None,
             time.time(), time.time() if status in ("done", "failed") else None,
             error),
        )
        await self.db.commit()
        return True

    async def list_tasks(self, limit: int = 50) -> list[dict]:
        async with self.db.execute(
            "SELECT id,type,status,created_at,finished_at,error FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def save_ai_history(self, role: str, input_text: str,
                              output_text: str, source: str,
                              elapsed: float) -> str:
        import hashlib
        hid = hashlib.md5(f"{role}:{time.time()}".encode()).hexdigest()[:16]
        await self.db.execute(
            """INSERT INTO ai_history (id, role, input, output, source, elapsed, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (hid, role, input_text[:5000], output_text[:5000], source,
             elapsed, time.time()),
        )
        await self.db.commit()
        return hid

    async def list_ai_history(self, limit: int = 30) -> list[dict]:
        async with self.db.execute(
            "SELECT id,role,source,elapsed,created_at FROM ai_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def save_document(self, doc_id: str, title: str, path: str,
                            status: str = "draft", meta: dict | None = None) -> bool:
        now = time.time()
        await self.db.execute(
            """INSERT OR REPLACE INTO documents (id,title,path,status,created_at,updated_at,meta)
            VALUES (?,?,?,?,COALESCE((SELECT created_at FROM documents WHERE id=?),?),?,?)""",
            (doc_id, title, path, status, doc_id, now, now,
             json.dumps(meta or {}, ensure_ascii=False)),
        )
        await self.db.commit()
        return True

    async def list_documents(self) -> list[dict]:
        async with self.db.execute(
            "SELECT id,title,path,status,created_at,updated_at FROM documents ORDER BY updated_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


local_db = LocalDB()
