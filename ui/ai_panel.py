from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, QGroupBox,
    QFormLayout, QPlainTextEdit, QTextEdit, QHBoxLayout, QListWidget,
    QListWidgetItem, QProgressBar, QCheckBox, QLineEdit, QMessageBox,
)

from ui.api_client import api_client
from ui.workers import run_api


ROLE_LABELS = {
    "polish": "文本润色",
    "typo": "错别字纠正",
    "complete": "语义补全",
    "style": "风格迁移",
    "summary": "摘要生成",
}

STYLE_PRESETS = ["标准公文", "通知", "报告", "函"]


class AIPanel(QWidget):
    apply_requested = Signal(str)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_result = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        title = QLabel("AI 辅助面板")
        title.setStyleSheet("font-size:15px; font-weight:bold; padding:4px;")
        layout.addWidget(title)

        group = QGroupBox("处理配置")
        form = QFormLayout(group)
        self.role_combo = QComboBox()
        for k, v in ROLE_LABELS.items():
            self.role_combo.addItem(v, k)
        form.addRow("处理类型：", self.role_combo)

        self.style_combo = QComboBox()
        self.style_combo.addItems(STYLE_PRESETS)
        form.addRow("风格预设：", self.style_combo)
        self.style_combo.setEnabled(False)
        self.role_combo.currentIndexChanged.connect(
            lambda: self.style_combo.setEnabled(
                self.role_combo.currentData() == "style"
            )
        )

        self.instruction_edit = QLineEdit()
        self.instruction_edit.setPlaceholderText("附加指令（可选）")
        form.addRow("附加指令：", self.instruction_edit)
        layout.addWidget(group)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("执行 AI 处理")
        self.btn_run.setStyleSheet("padding:6px; font-weight:bold;")
        self.btn_apply = QPushButton("应用结果")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_apply)
        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("AI 处理结果将显示在此处...")
        layout.addWidget(self.result_edit, 1)

        hist_label = QLabel("历史记录")
        hist_label.setStyleSheet("font-weight:bold; color:#444;")
        layout.addWidget(hist_label)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(120)
        self.history_list.itemDoubleClicked.connect(self._on_history_click)
        layout.addWidget(self.history_list)

        self.btn_run.clicked.connect(self._on_run)
        self._load_history()

    def _on_run(self):
        from ui.editor import EditorPanel
        editor = self.parent().findChild(EditorPanel) if self.parent() else None
        if not editor:
            for w in self.parent().findChildren(QWidget) if self.parent() else []:
                pass
        text = ""
        if editor:
            text = editor.get_text()
        if not text.strip():
            QMessageBox.information(self, "提示", "编辑器内容为空，请先输入或粘贴文本")
            return
        role = self.role_combo.currentData()
        style = self.style_combo.currentText() if role == "style" else None
        extra = self.instruction_edit.text().strip() or ""
        self._set_running(True)
        self.status_message.emit(f"正在执行 {ROLE_LABELS[role]}...")
        run_api(
            api_client.ai_process,
            on_ok=self._on_ai_done,
            on_err=self._on_ai_err,
            on_start=lambda l: None,
            label=ROLE_LABELS[role], parent=self,
            text=text, role=role, style=style, extra_instruction=extra,
        )

    def _on_ai_done(self, result: dict):
        self._set_running(False)
        self._current_result = result.get("text", "")
        self.result_edit.setPlainText(self._current_result)
        self.btn_apply.setEnabled(bool(self._current_result))
        src = result.get("source", "ai")
        elapsed = result.get("elapsed", 0)
        if result.get("ok"):
            self.status_message.emit(
                f"AI 处理完成（{src}，{elapsed:.1f}s）"
            )
        else:
            self.status_message.emit(f"AI 处理失败：{result.get('error','')}")
        self._load_history()

    def _on_ai_err(self, err: str):
        self._set_running(False)
        self.result_edit.setPlainText(f"处理失败：{err}")
        self.status_message.emit(f"请求失败：{err}")

    def _set_running(self, on: bool):
        self.progress.setVisible(on)
        self.btn_run.setEnabled(not on)

    def _on_apply(self):
        if self._current_result:
            self.apply_requested.emit(self._current_result)
            role = self.role_combo.currentData()
            self.status_message.emit(f"已应用「{ROLE_LABELS[role]}」结果到编辑器")

    def _load_history(self):
        run_api(
            api_client.ai_history,
            on_ok=self._render_history,
            on_err=lambda e: None,
            label="加载历史", parent=self,
        )

    def _render_history(self, items: list):
        self.history_list.clear()
        for it in items:
            role = it.get("role", "?")
            src = it.get("source", "?")
            label = f"{ROLE_LABELS.get(role, role)} · {src}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, it.get("id"))
            self.history_list.addItem(item)

    def _on_history_click(self, item: QListWidgetItem):
        hid = item.data(Qt.ItemDataRole.UserRole)
        if not hid:
            return
        run_api(
            lambda: self._fetch_history_detail(hid),
            on_ok=lambda r: self.result_edit.setPlainText(r.get("output", "")),
            label="查看历史", parent=self,
        )

    def _fetch_history_detail(self, hid: str) -> dict:
        rows = api_client.ai_history()
        for r in rows:
            if r.get("id") == hid:
                return r
        return {}
