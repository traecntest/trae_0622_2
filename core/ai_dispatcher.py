from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import config


ROLE_POLISH = "polish"
ROLE_TYPO = "typo"
ROLE_COMPLETE = "complete"
ROLE_STYLE = "style"
ROLE_SUMMARY = "summary"

ROLE_PROMPTS = {
    ROLE_POLISH: "你是一名资深公文润色编辑。请对以下文本进行润色，在保持原意的前提下提升表达的准确性、简洁性与规范性，使其符合中国党政机关公文语体。直接输出润色后的文本，不要添加解释。",
    ROLE_TYPO: "你是一名严谨的中文校对专家。请检查并纠正下列文本中的错别字、标点错误与用词不当，保持原文结构与段落。直接输出修正后的全文，不要标注改动。",
    ROLE_COMPLETE: "你是一名公文语义补全助手。请基于下列文本，补全缺失的语义信息，使段落逻辑完整、表意明确。直接输出补全后的文本，不要解释。",
    ROLE_STYLE: "你是一名公文风格迁移专家。请将下列文本转换为标准公文风格，语态庄重、用词规范、结构严谨。直接输出迁移后的文本，不要添加说明。",
    ROLE_SUMMARY: "你是一名公文摘要助手。请用 200 字以内精炼概括下列文本的核心要点。直接输出摘要。",
}

STYLE_PRESETS = {
    "标准公文": "标准党政机关公文语体，庄重规范。",
    "通知": "通知类公文语体，简明扼要、要求明确。",
    "报告": "报告类公文语体，客观陈述、条理清晰。",
    "函": "函件公文语体，礼貌得体、措辞规范。",
}


@dataclass
class AIResult:
    ok: bool
    text: str
    role: str
    elapsed: float
    usage: dict = field(default_factory=dict)
    error: str = ""
    source: str = "ai"

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "text": self.text, "role": self.role,
            "elapsed": self.elapsed, "usage": self.usage,
            "error": self.error, "source": self.source,
        }


class AIDispatcher:
    def __init__(self, cfg: config.AIConfig | None = None, on_event=None):
        self.cfg = cfg or config.AIConfig()
        self.on_event = on_event
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import AsyncOpenAI
            if self.cfg.api_key:
                self._client = AsyncOpenAI(
                    api_key=self.cfg.api_key,
                    base_url=self.cfg.base_url,
                    timeout=self.cfg.timeout,
                )
        except Exception:
            self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    def _emit(self, event: str, payload: dict):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass

    async def dispatch(self, text: str, role: str = ROLE_POLISH,
                       style: str | None = None,
                       extra_instruction: str = "") -> AIResult:
        if not text or not text.strip():
            return AIResult(False, "", role, 0.0, error="输入文本为空")
        start = time.time()
        if self.is_available():
            try:
                result = await self._call_remote(text, role, style, extra_instruction)
                result.elapsed = time.time() - start
                self._emit("ai.completed", {"role": role, "elapsed": result.elapsed})
                return result
            except Exception as e:
                if self.cfg.fallback_local:
                    result = self._local_fallback(text, role, style, error=str(e))
                    result.elapsed = time.time() - start
                    result.source = "local_fallback"
                    return result
                return AIResult(False, "", role, time.time() - start, error=str(e))
        result = self._local_fallback(text, role, style)
        result.elapsed = time.time() - start
        result.source = "local"
        return result

    async def _call_remote(self, text: str, role: str, style: str | None,
                           extra_instruction: str) -> AIResult:
        system_prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS[ROLE_POLISH])
        if style and role == ROLE_STYLE:
            preset = STYLE_PRESETS.get(style, style)
            system_prompt += f"\n风格要求：{preset}。"
        if extra_instruction:
            system_prompt += f"\n附加要求：{extra_instruction}"
        user_content = text
        resp = await self._client.chat.completions.create(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )
        out = resp.choices[0].message.content.strip()
        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
        return AIResult(True, out, role, 0.0, usage=usage, source="ai")

    def _local_fallback(self, text: str, role: str, style: str | None,
                        error: str = "") -> AIResult:
        out = text
        if role == ROLE_TYPO:
            out = self._local_typo_fix(text)
        elif role == ROLE_POLISH:
            out = self._local_polish(text)
        elif role == ROLE_STYLE:
            out = self._local_style(text, style)
        elif role == ROLE_SUMMARY:
            out = self._local_summary(text)
        msg = "本地回退处理"
        if error:
            msg += f"（远端不可用：{error}）"
        self._emit("ai.fallback", {"role": role, "reason": msg})
        return AIResult(True, out, role, 0.0, error=msg, source="local")

    @staticmethod
    def _local_typo_fix(text: str) -> str:
        replacements = {
            "的的": "的", "了了": "了", "在在": "在",
            "登陆": "登录", "帐号": "账号", "另人": "令人",
            "按装": "安装", "既使": "即使", "做为": "作为",
            "做为": "作为", "象": "像", "辨别": "辨别",
            "讯速": "迅速", "部份": "部分", "相互相": "相互",
            "。。": "。", "，，": "，", "，，": "，",
        }
        out = text
        for wrong, right in replacements.items():
            out = out.replace(wrong, right)
        out = re.sub(r"([，。；！？])\1+", r"\1", out)
        out = re.sub(r"[ \t]+", "", out)
        return out

    @staticmethod
    def _local_polish(text: str) -> str:
        out = AIDispatcher._local_typo_fix(text)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()

    @staticmethod
    def _local_style(text: str, style: str | None) -> str:
        out = AIDispatcher._local_polish(text)
        if style == "通知":
            if "现就" not in out and "有关" in out:
                pass
        return out

    @staticmethod
    def _local_summary(text: str) -> str:
        sents = re.split(r"[。！？\n]", text)
        sents = [s.strip() for s in sents if len(s.strip()) > 6]
        if not sents:
            return text[:200]
        total = len(sents)
        take = max(3, total // 3)
        summary = "。".join(sents[:take]) + "。"
        return summary[:200]

    async def batch_dispatch(self, texts: list[str], role: str = ROLE_POLISH,
                             style: str | None = None) -> list[AIResult]:
        sem = asyncio.Semaphore(3)

        async def _one(t):
            async with sem:
                return await self.dispatch(t, role, style)

        return await asyncio.gather(*[_one(t) for t in texts])


ai_dispatcher = AIDispatcher()
