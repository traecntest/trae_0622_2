from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Awaitable

import config


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    type: str
    payload: dict
    status: str = TaskStatus.PENDING
    result: dict = field(default_factory=dict)
    error: str = ""
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class TaskQueue:
    def __init__(self, max_concurrent: int = config.TASK_MAX_CONCURRENT,
                 on_event=None):
        self.max_concurrent = max_concurrent
        self.on_event = on_event
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: dict[str, Task] = {}
        self._workers: list[asyncio.Task] = []
        self._handlers: dict[str, Callable] = {}
        self._running = False
        self._sem = asyncio.Semaphore(max_concurrent)

    def register(self, task_type: str,
                 handler: Callable[[dict, Task], Awaitable[dict]]):
        self._handlers[task_type] = handler

    def _emit(self, event: str, payload: dict):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass

    async def start(self):
        if self._running:
            return
        self._running = True
        for i in range(self.max_concurrent):
            w = asyncio.create_task(self._worker(i))
            self._workers.append(w)
        self._emit("queue.started", {"workers": self.max_concurrent})

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        self._workers.clear()

    async def _worker(self, idx: int):
        while self._running:
            try:
                task = await self._queue.get()
            except asyncio.CancelledError:
                break
            if task is None:
                break
            await self._run_task(task)
            self._queue.task_done()

    async def _run_task(self, task: Task):
        handler = self._handlers.get(task.type)
        task.status = TaskStatus.RUNNING
        self._emit("task.started", {"id": task.id, "type": task.type})
        try:
            if handler is None:
                raise ValueError(f"未注册的任务类型: {task.type}")
            result = await handler(task.payload, task)
            task.result = result or {}
            task.status = TaskStatus.DONE
            task.progress = 1.0
            task.finished_at = time.time()
            self._emit("task.done", {"id": task.id, "type": task.type,
                                     "result": task.result})
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.finished_at = time.time()
            self._emit("task.failed", {"id": task.id, "type": task.type,
                                        "error": str(e)})

    async def submit(self, task_type: str, payload: dict) -> str:
        tid = hashlib.md5(
            f"{task_type}:{time.time()}:{id(payload)}".encode()
        ).hexdigest()[:16]
        task = Task(id=tid, type=task_type, payload=payload)
        self._tasks[tid] = task
        await self._queue.put(task)
        self._emit("task.submitted", {"id": tid, "type": task_type})
        return tid

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def update_progress(self, task_id: str, progress: float):
        t = self._tasks.get(task_id)
        if t:
            t.progress = max(0.0, min(1.0, progress))
            self._emit("task.progress", {"id": task_id, "progress": t.progress})

    async def wait(self, task_id: str, timeout: float = 120) -> Task | None:
        start = time.time()
        while time.time() - start < timeout:
            t = self._tasks.get(task_id)
            if t and t.status in (TaskStatus.DONE, TaskStatus.FAILED):
                return t
            await asyncio.sleep(0.2)
        return self._tasks.get(task_id)


task_queue = TaskQueue()
