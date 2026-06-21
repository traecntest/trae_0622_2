from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, asdict
from typing import Any

from docx import Document

from core.ai_dispatcher import AIDispatcher, AIResult, ai_dispatcher
from core.rule_engine import RuleEngine, CheckReport, rule_engine
from core.merger import DocMerger, MergeResult, merger
from core.collector import Collector, collector


@dataclass
class ProcessResult:
    ok: bool
    stage: str
    data: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DocEngine:
    def __init__(self,
                 ai: AIDispatcher | None = None,
                 rules: RuleEngine | None = None,
                 mrgr: DocMerger | None = None,
                 cltr: Collector | None = None,
                 on_event=None):
        self.ai = ai or ai_dispatcher
        self.rules = rules or rule_engine
        self.merger = mrgr or merger
        self.collector = cltr or collector
        self.on_event = on_event

    def _emit(self, event: str, payload: dict):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass

    async def polish_text(self, text: str, style: str | None = None) -> AIResult:
        self._emit("engine.stage", {"stage": "polish", "status": "start"})
        result = await self.ai.dispatch(text, role="polish", style=style)
        self._emit("engine.stage", {"stage": "polish", "status": "done"})
        return result

    async def fix_typos(self, text: str) -> AIResult:
        return await self.ai.dispatch(text, role="typo")

    async def complete_text(self, text: str) -> AIResult:
        return await self.ai.dispatch(text, role="complete")

    async def transfer_style(self, text: str, style: str = "标准公文") -> AIResult:
        return await self.ai.dispatch(text, role="style", style=style)

    async def summarize(self, text: str) -> AIResult:
        return await self.ai.dispatch(text, role="summary")

    def check_docx(self, file_path: str) -> CheckReport:
        doc = Document(file_path)
        report = self.rules.check_all(doc)
        self._emit("engine.stage", {
            "stage": "check", "status": "done",
            "errors": report.error_count, "warns": report.warn_count,
        })
        return report

    def fix_docx(self, file_path: str, output_path: str | None = None) -> CheckReport:
        doc = Document(file_path)
        report = self.rules.fix_all(doc)
        out = output_path or file_path
        doc.save(out)
        self._emit("engine.stage", {
            "stage": "fix", "status": "done",
            "fixed": report.fixed_count,
        })
        return report

    def merge_docs(self, file_paths: list[str], output_path: str,
                   with_toc: bool = True) -> MergeResult:
        result = self.merger.merge(file_paths, output_path, with_toc)
        self._emit("engine.stage", {
            "stage": "merge", "status": "done" if result.ok else "error",
            "headings": result.heading_count,
        })
        return result

    async def full_pipeline(self, raw_html: str, source_url: str = "",
                            style: str = "标准公文",
                            output_path: str = "") -> ProcessResult:
        self._emit("engine.stage", {"stage": "collect", "status": "start"})
        mat = await self.collector.collect(raw_html, source_url)
        self._emit("engine.stage", {"stage": "collect", "status": "done"})

        self._emit("engine.stage", {"stage": "polish", "status": "start"})
        polished = await self.ai.dispatch(mat.text, role="polish", style=style)
        self._emit("engine.stage", {"stage": "polish", "status": "done"})

        self._emit("engine.stage", {"stage": "typo", "status": "start"})
        typo_fixed = await self.ai.dispatch(polished.text, role="typo")
        self._emit("engine.stage", {"stage": "typo", "status": "done"})

        text_items = typo_fixed.text.split("\n\n")
        text_items = [t for t in text_items if t.strip()]
        text_checks = self.rules.validate_text(typo_fixed.text)

        data = {
            "material": mat.to_dict(),
            "polished": polished.to_dict(),
            "final_text": typo_fixed.text,
            "text_checks": [c.to_dict() for c in text_checks],
            "output_path": output_path,
        }
        self._emit("engine.pipeline_done", {"ok": True})
        return ProcessResult(ok=True, stage="full_pipeline", data=data)


doc_engine = DocEngine()
