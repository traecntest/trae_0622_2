from __future__ import annotations

from typing import Any

import httpx

import config


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, base: str | None = None):
        self.base = base or f"http://{config.API_HOST}:{config.API_PORT}"
        self._client = httpx.Client(base_url=self.base, timeout=120.0)

    def _post(self, path: str, json_body: dict) -> dict:
        try:
            r = self._client.post(path, json=json_body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ApiError(str(e)) from e

    def _get(self, path: str, **params) -> dict | list:
        try:
            r = self._client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ApiError(str(e)) from e

    def _delete(self, path: str) -> dict:
        try:
            r = self._client.delete(path)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ApiError(str(e)) from e

    def health(self) -> dict:
        try:
            return self._get("/api/health")
        except ApiError:
            return {"status": "offline"}

    def collect(self, html: str, source_url: str = "", title: str = "",
                tags: list | None = None) -> dict:
        return self._post("/api/collect", {
            "html": html, "source_url": source_url,
            "title": title, "tags": tags or [],
        })

    def list_materials(self) -> list:
        return self._get("/api/materials")

    def get_material(self, mid: str) -> dict:
        return self._get(f"/api/materials/{mid}")

    def delete_material(self, mid: str) -> dict:
        return self._delete(f"/api/materials/{mid}")

    def search_materials(self, keyword: str) -> list:
        return self._get(f"/api/materials/search/{keyword}")

    def ai_process(self, text: str, role: str = "polish",
                   style: str | None = None,
                   extra_instruction: str = "") -> dict:
        return self._post("/api/ai", {
            "text": text, "role": role, "style": style,
            "extra_instruction": extra_instruction,
        })

    def ai_history(self) -> list:
        return self._get("/api/ai/history")

    def ai_status(self) -> dict:
        try:
            return self._get("/api/ai/status")
        except ApiError:
            return {"available": False}

    def ai_reload(self, settings: dict) -> dict:
        return self._post("/api/ai/reload", settings)

    def check_docx(self, file_path: str) -> dict:
        return self._post("/api/docx/check", {"file_path": file_path})

    def fix_docx(self, file_path: str, output_path: str | None = None) -> dict:
        return self._post("/api/docx/fix", {"file_path": file_path,
                                            "output_path": output_path})

    def merge_docx(self, file_paths: list[str], output_path: str,
                   with_toc: bool = True) -> dict:
        return self._post("/api/docx/merge", {"file_paths": file_paths,
                                              "output_path": output_path,
                                              "with_toc": with_toc})

    def upload_docx(self, file_path: str) -> dict:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1], f)}
            r = self._client.post("/api/docx/upload", files=files)
            r.raise_for_status()
            return r.json()

    def pipeline(self, html: str, source_url: str = "",
                 style: str = "标准公文", output_path: str = "") -> dict:
        return self._post("/api/pipeline", {
            "html": html, "source_url": source_url,
            "style": style, "output_path": output_path,
        })

    def submit_task(self, ttype: str, payload: dict) -> dict:
        return self._post("/api/tasks", {"type": ttype, "payload": payload})

    def list_tasks(self) -> list:
        return self._get("/api/tasks")

    def get_task(self, tid: str) -> dict:
        return self._get(f"/api/tasks/{tid}")

    def text_check(self, text: str) -> dict:
        return self._post("/api/docx/text-check", {"text": text})

    def close(self):
        self._client.close()


api_client = ApiClient()
