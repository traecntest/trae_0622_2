from __future__ import annotations

import difflib

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTextCharFormat, QFont, QAction, QClipboard
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel,
    QComboBox, QFontComboBox, QToolBar, QFileDialog, QMessageBox, QSplitter,
    QPlainTextEdit, QCheckBox, QSpinBox,
)

from utils.dom_cleaner import DOMCleaner
from ui.api_client import api_client
from ui.workers import run_api


class RichEditor(QTextEdit):
    paste_cleaned = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.dom_cleaner = DOMCleaner()
        self._auto_clean = True
        self._raw_clipboard = ""

    def set_auto_clean(self, on: bool):
        self._auto_clean = on

    def insertFromMimeData(self, mime_data):
        if mime_data.hasHtml() and self._auto_clean:
            raw_html = mime_data.html()
            cleaned = self.dom_cleaner.clean(raw_html)
            self.insertHtml(cleaned.html)
            self.paste_cleaned.emit(cleaned.text)
            return
        if mime_data.hasText():
            text = mime_data.text()
            self.insertPlainText(text)
            self.paste_cleaned.emit(text)
            return
        super().insertFromMimeData(mime_data)


class DiffViewer(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(220)
        self.setStyleSheet("background:#fafafa; font-family: monospace;")

    def show_diff(self, original: str, revised: str):
        self.clear()
        if not original and not revised:
            return
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            revised.splitlines(keepends=True),
            fromfile="原文", tofile="修订", lineterm="",
        )
        lines = []
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(f'<span style="color:#1a7f37">{line.rstrip()}</span>')
            elif line.startswith("-") and not line.startswith("---"):
                lines.append(f'<span style="color:#cf222e">{line.rstrip()}</span>')
            elif line.startswith("@"):
                lines.append(f'<span style="color:#6e7781">{line.rstrip()}</span>')
            else:
                lines.append(line.rstrip())
        self.appendHtml("<br>".join(lines))


class EditorPanel(QWidget):
    text_changed = Signal(str)
    status_message = Signal(str)
    material_loaded = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor = RichEditor()
        self.editor.setFont(QFont("微软雅黑", 11))
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.paste_cleaned.connect(self._on_paste_cleaned)

        toolbar = QToolBar()
        self._build_toolbar(toolbar)
        layout.addWidget(toolbar)

        diff_label = QLabel("修改差异预览")
        diff_label.setStyleSheet("font-weight:bold; color:#444; padding:2px 4px;")
        self.diff_viewer = DiffViewer()
        diff_container = QWidget()
        dc_layout = QVBoxLayout(diff_container)
        dc_layout.setContentsMargins(2, 2, 2, 2)
        dc_layout.setSpacing(2)
        dc_layout.addWidget(diff_label)
        dc_layout.addWidget(self.diff_viewer)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(diff_container)
        self.splitter.setSizes([500, 180])
        layout.addWidget(self.splitter)

        self._original_text = ""

    def _build_toolbar(self, tb: QToolBar):
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont("仿宋"))
        self.font_combo.currentFontChanged.connect(self._set_font)
        tb.addWidget(self.font_combo)

        self.size_combo = QSpinBox()
        self.size_combo.setRange(8, 72)
        self.size_combo.setValue(16)
        self.size_combo.valueChanged.connect(self._set_font_size)
        tb.addWidget(self.size_combo)

        tb.addSeparator()
        tb.addAction("加粗", self._toggle_bold)
        tb.addAction("斜体", self._toggle_italic)
        tb.addAction("下划线", self._toggle_underline)
        tb.addSeparator()

        align_left = QAction("左对齐", self)
        align_left.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignLeft))
        tb.addAction(align_left)
        align_center = QAction("居中", self)
        align_center.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter))
        tb.addAction(align_center)

        tb.addSeparator()
        self.auto_clean_cb = QCheckBox("粘贴自动清洗")
        self.auto_clean_cb.setChecked(True)
        self.auto_clean_cb.toggled.connect(self.editor.set_auto_clean)
        tb.addWidget(self.auto_clean_cb)

        tb.addSeparator()
        tb.addAction("导入DOCX", self._import_docx)
        tb.addAction("导出DOCX", self._export_docx)
        tb.addAction("清空", self.editor.clear)

    def load_docx(self, file_path: str) -> bool:
        try:
            from docx import Document
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.set_text(text, "")
            self.material_loaded.emit(file_path)
            self.status_message.emit(f"已导入 {file_path.split('/')[-1]}")
            return True
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return False

    def _import_docx(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 DOCX", "", "Word 文档 (*.docx)"
        )
        if not path:
            return
        self.load_docx(path)

    def _set_font(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFont(font)
        self.editor.mergeFormatOnSelectionOrDocument(fmt)

    def _set_font_size(self, size: int):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self.editor.mergeFormatOnSelectionOrDocument(fmt)

    def _toggle_bold(self):
        self.editor.setFontWeight(
            QFont.Weight.Bold if self.editor.fontWeight() < QFont.Weight.Bold
            else QFont.Weight.Normal
        )

    def _toggle_italic(self):
        self.editor.setFontItalic(not self.editor.fontItalic())

    def _toggle_underline(self):
        self.editor.setFontUnderline(not self.editor.fontUnderline())

    def _on_text_changed(self):
        self.text_changed.emit(self.editor.toPlainText())

    def _on_paste_cleaned(self, text: str):
        self.status_message.emit("已自动执行 DOM 清洗，剥离超链接/内联样式/脚本")

    def set_text(self, text: str, original: str = ""):
        self._original_text = original or self.editor.toPlainText()
        self.editor.setPlainText(text)
        self.diff_viewer.show_diff(self._original_text, text)

    def get_text(self) -> str:
        return self.editor.toPlainText()

    def get_html(self) -> str:
        return self.editor.toHtml()

    def apply_ai_result(self, result_text: str, role: str = ""):
        original = self.editor.toPlainText()
        self._original_text = original
        self.editor.setPlainText(result_text)
        self.diff_viewer.show_diff(original, result_text)
        self.status_message.emit(f"AI 处理完成（{role}），差异已预览")

    def _import_docx(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 DOCX", "", "Word 文档 (*.docx)"
        )
        if not path:
            return
        try:
            from docx import Document
            doc = Document(path)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.set_text(text, "")
            self.material_loaded.emit(path)
            self.status_message.emit(f"已导入 {path.split('/')[-1]}")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _export_docx(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 DOCX", "公文.docx", "Word 文档 (*.docx)"
        )
        if not path:
            return
        run_api(
            lambda: self._do_export(path),
            on_ok=lambda r: self.status_message.emit(f"已导出至 {path}"),
            on_err=lambda e: QMessageBox.warning(self, "导出失败", e),
            label="导出 DOCX", parent=self,
        )

    def _do_export(self, path: str):
        from docx import Document
        from docx.shared import Pt, Cm
        from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
        import config as _cfg
        doc = Document()
        sec = doc.sections[0]
        cfg = _cfg.GWFormatConfig()
        sec.page_width = Cm(cfg.page_width_cm)
        sec.page_height = Cm(cfg.page_height_cm)
        sec.top_margin = Cm(cfg.margin_top_cm)
        sec.bottom_margin = Cm(cfg.margin_bottom_cm)
        sec.left_margin = Cm(cfg.margin_left_cm)
        sec.right_margin = Cm(cfg.margin_right_cm)
        style = doc.styles["Normal"]
        style.font.name = cfg.body_font_cn
        style.font.size = Pt(cfg.body_font_size_pt)
        style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        style.paragraph_format.line_spacing = Pt(cfg.body_line_spacing_lines)
        for line in self.editor.toPlainText().split("\n"):
            line = line.strip()
            if line:
                p = doc.add_paragraph(line)
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                for run in p.runs:
                    run.font.name = cfg.body_font_cn
                    run.font.size = Pt(cfg.body_font_size_pt)
        doc.save(path)
        return {"path": path}

    def load_material_text(self, text: str):
        self.set_text(text, "")
        self.status_message.emit("已载入素材到编辑器")
