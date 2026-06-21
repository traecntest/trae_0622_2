from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from api.websocket import ws_manager
from core.doc_engine import doc_engine
from core.collector import collector
from core.ai_dispatcher import ai_dispatcher
from core.rule_engine import rule_engine
from core.merger import merger
from storage.local_db import local_db
from tasks.task_queue import task_queue, TaskStatus


@asynccontextmanager
async def lifespan(app: FastAPI):
    await local_db.connect()
    await task_queue.start()
    _register_handlers()
    await ws_manager.broadcast("server.ready", {"version": config.APP_VERSION})
    yield
    await task_queue.stop()
    await local_db.close()


def create_app() -> FastAPI:
    app = FastAPI(title=config.APP_TITLE, version=config.APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_routes(app)
    return app


class CollectRequest(BaseModel):
    html: str
    source_url: str = ""
    title: str = ""
    tags: list[str] = []


class AIRequest(BaseModel):
    text: str
    role: str = "polish"
    style: str | None = None
    extra_instruction: str = ""


class FixRequest(BaseModel):
    file_path: str
    output_path: str | None = None


class MergeRequest(BaseModel):
    file_paths: list[str]
    output_path: str
    with_toc: bool = True


class PipelineRequest(BaseModel):
    html: str
    source_url: str = ""
    style: str = "标准公文"
    output_path: str = ""


def _register_handlers():
    async def _collect_handler(payload: dict, task: Any) -> dict:
        mat = await collector.collect(
            payload["html"], payload.get("source_url", ""),
            payload.get("title", ""), payload.get("tags"),
        )
        await local_db.save_material(mat)
        return mat.to_dict()

    async def _pipeline_handler(payload: dict, task: Any) -> dict:
        result = await doc_engine.full_pipeline(
            payload["html"], payload.get("source_url", ""),
            payload.get("style", "标准公文"), payload.get("output_path", ""),
        )
        return result.to_dict()

    async def _ai_handler(payload: dict, task: Any) -> dict:
        result = await ai_dispatcher.dispatch(
            payload["text"], payload["role"],
            payload.get("style"), payload.get("extra_instruction"),
        )
        await local_db.save_ai_history(
            result.role, payload["text"], result.text, result.source, result.elapsed
        )
        return result.to_dict()

    async def _check_handler(payload: dict, task: Any) -> dict:
        report = doc_engine.check_docx(payload["file_path"])
        return report.to_dict()

    async def _fix_handler(payload: dict, task: Any) -> dict:
        report = doc_engine.fix_docx(payload["file_path"], payload.get("output_path"))
        return report.to_dict()

    async def _merge_handler(payload: dict, task: Any) -> dict:
        result = doc_engine.merge_docs(
            payload["file_paths"], payload["output_path"], payload.get("with_toc", True)
        )
        return result.to_dict()

    task_queue.register("collect", _collect_handler)
    task_queue.register("pipeline", _pipeline_handler)
    task_queue.register("ai", _ai_handler)
    task_queue.register("check", _check_handler)
    task_queue.register("fix", _fix_handler)
    task_queue.register("merge", _merge_handler)


def _broadcast_event(event: str, payload: dict):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.broadcast(event, payload))
    except RuntimeError:
        pass


def _wire_events():
    collector.on_event = lambda e, p: _broadcast_event(e, p)
    ai_dispatcher.on_event = lambda e, p: _broadcast_event(e, p)
    doc_engine.on_event = lambda e, p: _broadcast_event(e, p)
    task_queue.on_event = lambda e, p: _broadcast_event(e, p)


def _register_routes(app: FastAPI):
    _wire_events()

    @app.get("/")
    async def root():
        return {"app": config.APP_TITLE, "version": config.APP_VERSION,
                "ai_available": ai_dispatcher.is_available()}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "ws_clients": ws_manager.client_count,
                "queue_tasks": len(task_queue.list_tasks())}

    @app.post("/api/collect")
    async def collect(req: CollectRequest):
        mat = await collector.collect(req.html, req.source_url, req.title, req.tags)
        await local_db.save_material(mat)
        return mat.to_dict()

    @app.get("/api/materials")
    async def list_materials():
        return await local_db.list_materials()

    @app.get("/api/materials/{mid}")
    async def get_material(mid: str):
        m = await local_db.get_material(mid)
        if not m:
            return {"error": "未找到素材"}
        return m

    @app.delete("/api/materials/{mid}")
    async def delete_material(mid: str):
        await local_db.delete_material(mid)
        collector.delete(mid)
        return {"ok": True}

    @app.get("/api/materials/search/{keyword}")
    async def search(keyword: str):
        return [m.to_dict() for m in collector.search(keyword)]

    @app.post("/api/ai")
    async def ai_process(req: AIRequest):
        result = await ai_dispatcher.dispatch(
            req.text, req.role, req.style, req.extra_instruction
        )
        await local_db.save_ai_history(
            result.role, req.text, result.text, result.source, result.elapsed
        )
        return result.to_dict()

    @app.get("/api/ai/history")
    async def ai_history():
        return await local_db.list_ai_history()

    @app.get("/api/ai/status")
    async def ai_status():
        from core.ai_dispatcher import ai_dispatcher as _disp
        return {
            "available": _disp.is_available(),
            "provider": _disp.cfg.provider,
            "model": _disp.cfg.model,
            "base_url": _disp.cfg.base_url,
            "fallback_local": _disp.cfg.fallback_local,
        }

    @app.post("/api/ai/reload")
    async def ai_reload(body: dict):
        from core.ai_dispatcher import AIDispatcher, ai_dispatcher as _disp
        from core.doc_engine import doc_engine
        cfg = config.AIConfig()
        cfg.provider = body.get("provider", cfg.provider)
        cfg.api_key = body.get("api_key", "")
        cfg.base_url = body.get("base_url", cfg.base_url)
        cfg.model = body.get("model", cfg.model)
        cfg.temperature = float(body.get("temperature", cfg.temperature))
        cfg.max_tokens = int(body.get("max_tokens", cfg.max_tokens))
        cfg.timeout = float(body.get("timeout", cfg.timeout))
        cfg.fallback_local = bool(body.get("fallback_local", cfg.fallback_local))
        config.AIConfig.provider = cfg.provider
        config.AIConfig.api_key = cfg.api_key
        config.AIConfig.base_url = cfg.base_url
        config.AIConfig.model = cfg.model
        config.AIConfig.temperature = cfg.temperature
        config.AIConfig.max_tokens = cfg.max_tokens
        config.AIConfig.timeout = cfg.timeout
        config.AIConfig.fallback_local = cfg.fallback_local
        new_disp = AIDispatcher(cfg, on_event=_disp.on_event)
        _disp.__dict__.update(new_disp.__dict__)
        doc_engine.ai = _disp
        return {"ok": True, "available": _disp.is_available(), "model": cfg.model}

    @app.post("/api/docx/check")
    async def check_docx(req: FixRequest):
        return doc_engine.check_docx(req.file_path).to_dict()

    @app.post("/api/docx/fix")
    async def fix_docx(req: FixRequest):
        return doc_engine.fix_docx(req.file_path, req.output_path).to_dict()

    @app.post("/api/docx/merge")
    async def merge_docx(req: MergeRequest):
        return doc_engine.merge_docs(
            req.file_paths, req.output_path, req.with_toc
        ).to_dict()

    @app.post("/api/docx/upload")
    async def upload_docx(file: UploadFile = File(...)):
        save_path = config.MATERIAL_DIR / file.filename
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
        return {"path": str(save_path), "name": file.filename}

    @app.post("/api/pipeline")
    async def pipeline(req: PipelineRequest):
        result = await doc_engine.full_pipeline(
            req.html, req.source_url, req.style, req.output_path
        )
        return result.to_dict()

    @app.post("/api/tasks")
    async def submit_task(body: dict):
        tid = await task_queue.submit(body["type"], body.get("payload", {}))
        return {"task_id": tid}

    @app.get("/api/tasks")
    async def list_tasks():
        return [t.to_dict() for t in task_queue.list_tasks()]

    @app.get("/api/tasks/{tid}")
    async def get_task(tid: str):
        t = task_queue.get(tid)
        return t.to_dict() if t else {"error": "任务不存在"}

    @app.post("/api/docx/text-check")
    async def text_check(body: dict):
        items = rule_engine.validate_text(body.get("text", ""))
        return {"items": [i.to_dict() for i in items]}

    @app.websocket(config.WS_PATH)
    async def websocket_endpoint(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            while True:
                data = await ws.receive_text()
                await ws_manager.handle_message(ws, data)
        except WebSocketDisconnect:
            await ws_manager.disconnect(ws)
        except Exception:
            await ws_manager.disconnect(ws)


app = create_app()
