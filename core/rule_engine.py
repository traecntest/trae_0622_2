from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from typing import Any

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

import config


SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


@dataclass
class CheckItem:
    name: str
    severity: str
    actual: str
    expected: str
    fixed: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckReport:
    ok: bool
    items: list[CheckItem] = field(default_factory=list)
    error_count: int = 0
    warn_count: int = 0
    fixed_count: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_count": self.error_count,
            "warn_count": self.warn_count,
            "fixed_count": self.fixed_count,
            "items": [i.to_dict() for i in self.items],
        }


def _cm_to_emu(cm: float) -> int:
    return Cm(cm).emu if hasattr(Cm(cm), "emu") else int(cm * 360000)


class RuleEngine:
    def __init__(self, cfg: config.GWFormatConfig | None = None):
        self.cfg = cfg or config.GWFormatConfig()

    def _section(self, doc: Document):
        return doc.sections[0] if doc.sections else doc.add_section()

    def check_margins(self, doc: Document) -> list[CheckItem]:
        sec = self._section(doc)
        cfg = self.cfg
        items: list[CheckItem] = []
        checks = [
            ("margin_top", sec.top_margin, cfg.margin_top_cm, "上边距"),
            ("margin_bottom", sec.bottom_margin, cfg.margin_bottom_cm, "下边距"),
            ("margin_left", sec.left_margin, cfg.margin_left_cm, "左边距"),
            ("margin_right", sec.right_margin, cfg.margin_right_cm, "右边距"),
        ]
        for _, actual, expected_cm, label in checks:
            actual_cm = actual.cm if actual else 0
            if abs(actual_cm - expected_cm) > 0.05:
                items.append(CheckItem(
                    name=f"{label}",
                    severity=SEVERITY_ERROR,
                    actual=f"{actual_cm:.2f}cm",
                    expected=f"{expected_cm:.2f}cm",
                    message=f"{label}不符合标准，应为 {expected_cm:.2f}cm",
                ))
        return items

    def fix_margins(self, doc: Document) -> int:
        sec = self._section(doc)
        cfg = self.cfg
        sec.top_margin = Cm(cfg.margin_top_cm)
        sec.bottom_margin = Cm(cfg.margin_bottom_cm)
        sec.left_margin = Cm(cfg.margin_left_cm)
        sec.right_margin = Cm(cfg.margin_right_cm)
        sec.page_width = Cm(cfg.page_width_cm)
        sec.page_height = Cm(cfg.page_height_cm)
        return 4

    def _set_run_font(self, run, font_cn: str, size_pt: float):
        run.font.size = Pt(size_pt)
        run.font.name = font_cn
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        rFonts.set(qn("w:eastAsia"), font_cn)
        rFonts.set(qn("w:ascii"), font_cn)
        rFonts.set(qn("w:hAnsi"), font_cn)

    def _para_font_spec(self, para) -> tuple[str, float]:
        text = para.text or ""
        style_name = (para.style.name or "").lower() if para.style else ""
        if "heading 1" in style_name or "title" in style_name:
            return self.cfg.heading1_font_cn, self.cfg.heading1_font_size_pt
        if "heading 2" in style_name:
            return self.cfg.heading2_font_cn, self.cfg.heading2_font_size_pt
        if "heading 3" in style_name:
            return self.cfg.heading3_font_cn, self.cfg.heading3_font_size_pt
        return self.cfg.body_font_cn, self.cfg.body_font_size_pt

    def check_fonts(self, doc: Document) -> list[CheckItem]:
        items: list[CheckItem] = []
        cfg = self.cfg
        for idx, para in enumerate(doc.paragraphs):
            if not para.text.strip():
                continue
            font_cn, size_pt = self._para_font_spec(para)
            for run in para.runs:
                if not run.text.strip():
                    continue
                if run.font.name and run.font.name != font_cn:
                    ea = run._element.find(qn("w:rPr"))
                    ea_font = ""
                    if ea is not None:
                        rf = ea.find(qn("w:rFonts"))
                        if rf is not None:
                            ea_font = rf.get(qn("w:eastAsia")) or ""
                    if ea_font and ea_font != font_cn:
                        items.append(CheckItem(
                            name="字体",
                            severity=SEVERITY_WARN,
                            actual=ea_font,
                            expected=font_cn,
                            message=f"第{idx+1}段字体「{ea_font}」应为「{font_cn}」",
                        ))
                        break
                actual_size = run.font.size.pt if run.font.size else None
                if actual_size and abs(actual_size - size_pt) > 0.5:
                    items.append(CheckItem(
                        name="字号",
                        severity=SEVERITY_WARN,
                        actual=f"{actual_size}pt",
                        expected=f"{size_pt}pt",
                        message=f"第{idx+1}段字号{actual_size}pt应为{size_pt}pt",
                    ))
                    break
        return items

    def fix_fonts(self, doc: Document) -> int:
        count = 0
        for para in doc.paragraphs:
            if not para.text.strip():
                continue
            font_cn, size_pt = self._para_font_spec(para)
            for run in para.runs:
                if run.text.strip():
                    self._set_run_font(run, font_cn, size_pt)
                    count += 1
        return count

    def check_line_spacing(self, doc: Document) -> list[CheckItem]:
        items: list[CheckItem] = []
        expected = self.cfg.body_line_spacing_lines
        for idx, para in enumerate(doc.paragraphs):
            if not para.text.strip():
                continue
            pf = para.paragraph_format
            if pf.line_spacing_rule == WD_LINE_SPACING.MULTIPLE:
                actual = pf.line_spacing
                if actual and abs(actual - 1.0) > 0.01:
                    continue
            if pf.line_spacing is not None:
                pass
            try:
                pPr = para._p.get_or_add_pPr()
                spacing = pPr.find(qn("w:spacing"))
                if spacing is not None:
                    line = spacing.get(qn("w:line"))
                    line_rule = spacing.get(qn("w:lineRule"))
                    if line and line_rule == "exact":
                        items.append(CheckItem(
                            name="行距",
                            severity=SEVERITY_WARN,
                            actual=f"{line}/exact",
                            expected=f"{expected}磅固定值",
                            message=f"第{idx+1}段行距非标准固定值",
                        ))
            except Exception:
                pass
        return items

    def fix_line_spacing(self, doc: Document) -> int:
        count = 0
        expected_pt = self.cfg.body_line_spacing_lines
        for para in doc.paragraphs:
            if not para.text.strip():
                continue
            pf = para.paragraph_format
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(expected_pt)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            count += 1
        return count

    def check_page_number(self, doc: Document) -> list[CheckItem]:
        items: list[CheckItem] = []
        sec = self._section(doc)
        footer = sec.footer
        footer_text = footer.paragraphs[0].text if footer.paragraphs else ""
        has_field = False
        for para in footer.paragraphs:
            for run in para.runs:
                fld = run._element.findall(qn("w:fldChar"))
                if fld:
                    has_field = True
        pPr_check = False
        for para in footer.paragraphs:
            if para.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                pPr_check = True
        if not has_field and not footer_text.strip():
            items.append(CheckItem(
                name="页码",
                severity=SEVERITY_ERROR,
                actual="无",
                expected="页脚居中页码",
                message="未检测到页码字段，公文需在页脚居中插入页码",
            ))
        elif not pPr_check:
            items.append(CheckItem(
                name="页码位置",
                severity=SEVERITY_WARN,
                actual="未居中",
                expected="居中",
                message="页码未居中显示",
            ))
        return items

    def fix_page_number(self, doc: Document) -> int:
        sec = self._section(doc)
        footer = sec.footer
        footer.is_linked_to_previous = False
        if not footer.paragraphs:
            footer.add_paragraph()
        para = footer.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in list(para.runs):
            r.text = ""
        run = para.add_run()
        self._set_run_font(
            run, self.cfg.page_number_font_cn, self.cfg.page_number_font_size_pt
        )
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = " PAGE "
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run._element.append(fld_begin)
        run._element.append(instr)
        run._element.append(fld_end)
        return 1

    def check_header_footer(self, doc: Document) -> list[CheckItem]:
        items: list[CheckItem] = []
        sec = self._section(doc)
        header_text = sec.header.paragraphs[0].text if sec.header.paragraphs else ""
        if header_text.strip() and not header_text.strip().isprintable():
            items.append(CheckItem(
                name="页眉",
                severity=SEVERITY_INFO,
                actual=header_text[:20],
                expected="规范页眉",
                message="页眉存在内容，请确认符合公文规范",
            ))
        return items

    def check_all(self, doc: Document) -> CheckReport:
        items: list[CheckItem] = []
        items += self.check_margins(doc)
        items += self.check_fonts(doc)
        items += self.check_line_spacing(doc)
        items += self.check_page_number(doc)
        items += self.check_header_footer(doc)
        error_count = sum(1 for i in items if i.severity == SEVERITY_ERROR)
        warn_count = sum(1 for i in items if i.severity == SEVERITY_WARN)
        ok = error_count == 0
        return CheckReport(
            ok=ok, items=items, error_count=error_count,
            warn_count=warn_count, fixed_count=0,
        )

    def fix_all(self, doc: Document) -> CheckReport:
        fixed = 0
        fixed += self.fix_margins(doc)
        fixed += self.fix_fonts(doc)
        fixed += self.fix_line_spacing(doc)
        fixed += self.fix_page_number(doc)
        report = self.check_all(doc)
        report.fixed_count = fixed
        for it in report.items:
            it.fixed = True
        return report

    def validate_text(self, text: str) -> list[CheckItem]:
        items: list[CheckItem] = []
        if "此致" in text and "敬礼" not in text:
            items.append(CheckItem(
                name="公文用语",
                severity=SEVERITY_WARN,
                actual="缺少「敬礼」",
                expected="此致敬礼",
                message="出现「此致」但未搭配「敬礼」",
            ))
        import re
        nums = re.findall(r"\d+年\d+月\d+日", text)
        if not nums:
            items.append(CheckItem(
                name="落款日期",
                severity=SEVERITY_INFO,
                actual="无",
                expected="X年X月X日",
                message="未检测到标准落款日期",
            ))
        return items


rule_engine = RuleEngine()
