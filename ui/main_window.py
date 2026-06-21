from __future__ import annotations

import asyncio
import threading
import time

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QStatusBar, QMenuBar, QToolBar,
    QMessageBox, QLabel, QFileDialog, QInputDialog, QApplication,
)

import config
from ui.api_client import api_client
from ui.document_tree import LeftPanel
from ui.editor import EditorPanel
from ui.ai_panel import AIPanel
from ui.ai_settings import AISettingsDialog, load_settings, apply_settings_to_config
from ui.workers import run_api


class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._server = None
        self._loop = None

    def run(self):
        import uvicorn
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._server = uvicorn.run(
            "api.server:app",
            host=config.API_HOST,
            port=config.API_PORT,
            log_level="warning",
            loop="asyncio",
        )

    def stop(self):
        if self._server:
            try:
                self._server.should_exit = True
            except Exception:
                pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_TITLE)
        self.resize(1280, 820)
        self._server_thread = ServerThread()
        self._server_thread.start()
        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()
        QTimer.singleShot(800, self._post_init)

    def _build_ui(self):
        central = QWidget()
        layout = self._h_layout(central)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel = LeftPanel()
        self.left_panel.setMaximumWidth(320)
        self.left_panel.setMinimumWidth(220)
        self.editor = EditorPanel()
        self.ai_panel = AIPanel()
        self.ai_panel.setMaximumWidth(360)
        self.ai_panel.setMinimumWidth(260)
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.ai_panel)
        self.splitter.setSizes([260, 660, 360])
        layout.addWidget(self.splitter)
        self.setCentralWidget(central)

    def _h_layout(self, parent):
        from PySide6.QtWidgets import QHBoxLayout
        l = QHBoxLayout(parent)
        l.setContentsMargins(0, 0, 0, 0)
        return l

    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("文件(&F)")
        m_file.addAction("导入 DOCX", self._import_docx)
        m_file.addAction("导出 DOCX", self.editor._export_docx)
        m_file.addSeparator()
        m_file.addAction("多源合并", self._merge_docs)
        m_file.addSeparator()
        m_file.addAction("退出", self.close)

        m_edit = mb.addMenu("编辑(&E)")
        m_edit.addAction("全选", self.editor.editor.selectAll)
        m_edit.addAction("清空", self.editor.editor.clear)

        m_ai = mb.addMenu("AI(&A)")
        for role, label in [("polish", "文本润色"), ("typo", "错别字纠正"),
                            ("complete", "语义补全"), ("style", "风格迁移"),
                            ("summary", "摘要生成")]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, r=role: self._quick_ai(r))
            m_ai.addAction(act)

        m_ai.addSeparator()
        act_cfg = QAction("AI 模型配置...", self)
        act_cfg.triggered.connect(self._open_ai_settings)
        m_ai.addAction(act_cfg)

        m_gw = mb.addMenu("公文(&G)")
        m_gw.addAction("格式合规校验", self._check_format)
        m_gw.addAction("批量格式修正", self._fix_format)
        m_gw.addAction("文本规范检查", self._text_check)

        m_help = mb.addMenu("帮助(&H)")
        m_help.addAction("关于", self._about)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.addAction("采集粘贴内容", self._collect_paste)
        tb.addSeparator()
        tb.addAction("润色", lambda: self._quick_ai("polish"))
        tb.addAction("纠错", lambda: self._quick_ai("typo"))
        tb.addAction("风格迁移", lambda: self._quick_ai("style"))
        tb.addAction("摘要", lambda: self._quick_ai("summary"))
        tb.addSeparator()
        tb.addAction("合规校验", self._check_format)
        tb.addAction("批量修正", self._fix_format)
        tb.addAction("多源合并", self._merge_docs)
        tb.addSeparator()
        tb.addAction("一键流水线", self._run_pipeline)
        tb.addSeparator()
        act_ai_cfg = QAction("AI 配置", self)
        act_ai_cfg.triggered.connect(self._open_ai_settings)
        tb.addAction(act_ai_cfg)
        self.addToolBar(tb)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.lbl_conn = QLabel("服务: 连接中...")
        self.lbl_conn.setStyleSheet("color:#d97706; padding:0 8px;")
        self.lbl_ai = QLabel("AI: 未就绪")
        self.lbl_ai.setStyleSheet("color:#cf222e; padding:0 8px;")
        self.lbl_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_ai.mousePressEvent = lambda e: self._open_ai_settings()
        self.lbl_task = QLabel("任务: 0")
        self.lbl_status = QLabel("就绪")
        sb.addWidget(self.lbl_conn)
        sb.addWidget(self.lbl_ai)
        sb.addPermanentWidget(self.lbl_task)
        sb.addPermanentWidget(self.lbl_status)
        self.setStatusBar(sb)
        self.editor.status_message.connect(self.lbl_status.setText)
        self.ai_panel.status_message.connect(self.lbl_status.setText)

    def _connect_signals(self):
        self.left_panel.material_selected.connect(self._load_material)
        self.left_panel.open_docx_requested.connect(self._import_docx)
        self.left_panel.docx_files_dropped.connect(self._on_docs_dropped)
        self.ai_panel.apply_requested.connect(self._apply_ai_result)
        self.editor.material_loaded.connect(self.left_panel.load_document)

    def _post_init(self):
        self._check_server()
        QTimer.singleShot(2000, self.left_panel.refresh_materials)
        QTimer.singleShot(2500, self._apply_saved_ai_settings)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_status)
        self._timer.start(3000)

    def _check_server(self):
        run_api(
            api_client.health,
            on_ok=self._on_health,
            on_err=lambda e: self.lbl_conn.setText(f"服务: 离线({e})"),
            label="健康检查", parent=self,
        )

    def _on_health(self, data: dict):
        if data.get("status") == "ok":
            self.lbl_conn.setText("服务: 已连接")
            self.lbl_conn.setStyleSheet("color:#1a7f37; padding:0 8px;")
        else:
            self.lbl_conn.setText("服务: 离线")
            self.lbl_conn.setStyleSheet("color:#cf222e; padding:0 8px;")

    def _poll_status(self):
        run_api(
            api_client.health,
            on_ok=self._on_health,
            on_err=lambda e: self.lbl_conn.setText("服务: 离线"),
            label="轮询", parent=self,
        )
        run_api(
            api_client.list_tasks,
            on_ok=lambda r: self.lbl_task.setText(f"任务: {len(r)}"),
            on_err=lambda e: None,
            label="任务列表", parent=self,
        )
        self._refresh_ai_status()

    def _refresh_ai_status(self):
        run_api(
            api_client.ai_status,
            on_ok=self._on_ai_status,
            on_err=lambda e: self._on_ai_status({"available": False}),
            label="AI 状态", parent=self,
        )

    def _on_ai_status(self, data: dict):
        if data.get("available"):
            model = data.get("model", "?")
            self.lbl_ai.setText(f"AI: {model}")
            self.lbl_ai.setStyleSheet("color:#1a7f37; padding:0 8px;")
            self.lbl_ai.setToolTip(f"模型就绪: {data.get('base_url','')}")
        else:
            self.lbl_ai.setText("AI: 本地回退（未配置）")
            self.lbl_ai.setStyleSheet("color:#d97706; padding:0 8px;")
            self.lbl_ai.setToolTip("点击配置 AI 模型")

    def _apply_saved_ai_settings(self):
        s = load_settings()
        if s.get("api_key"):
            apply_settings_to_config(s)
            run_api(
                api_client.ai_reload,
                on_ok=lambda r: self._refresh_ai_status(),
                on_err=lambda e: None,
                label="应用 AI 配置", parent=self,
                settings=s,
            )
        else:
            self._refresh_ai_status()

    def _open_ai_settings(self):
        dlg = AISettingsDialog(self)
        dlg.settings_saved.connect(self._on_ai_reloaded)
        dlg.exec()

    def _on_ai_reloaded(self, settings: dict):
        run_api(
            api_client.ai_reload,
            on_ok=lambda r: self._refresh_ai_status(),
            on_err=lambda e: QMessageBox.warning(self, "失败", f"配置生效失败: {e}"),
            label="重载 AI 配置", parent=self,
            settings=settings,
        )

    def _load_material(self, mid: str):
        run_api(
            api_client.get_material,
            on_ok=self._on_material_loaded,
            on_err=lambda e: QMessageBox.warning(self, "加载失败", e),
            label="加载素材", parent=self, mid=mid,
        )

    def _on_material_loaded(self, data: dict):
        if "error" in data:
            QMessageBox.warning(self, "提示", data["error"])
            return
        import json
        text = data.get("text", "")
        self.editor.load_material_text(text)
        self.lbl_status.setText(f"已载入素材：{data.get('title','')}")

    def _collect_paste(self):
        from utils.dom_cleaner import dom_cleaner
        clip = QApplication.clipboard()
        mime = clip.mimeData()
        raw_html = ""
        raw_text = ""
        if mime.hasHtml():
            raw_html = mime.html() or ""
        if mime.hasText():
            raw_text = mime.text() or ""

        cleaned_text = ""
        source_html = raw_html
        if raw_html:
            cleaned = dom_cleaner.clean(raw_html)
            cleaned_text = cleaned.text.strip()
        if not cleaned_text and raw_text:
            source_html = raw_text
            cleaned_text = raw_text.strip()

        if not cleaned_text:
            QMessageBox.information(self, "提示", "剪贴板没有可采集的文本内容")
            return

        title, ok = QInputDialog.getText(self, "采集素材", "素材标题：")
        if not ok:
            return
        self.lbl_status.setText("正在采集并清洗...")
        run_api(
            api_client.collect,
            on_ok=self._on_collected,
            on_err=lambda e: QMessageBox.warning(self, "采集失败", e),
            label="采集素材", parent=self,
            html=source_html, source_url="", title=title or "采集素材", tags=[],
        )

    def _on_collected(self, data: dict):
        self.editor.load_material_text(data.get("text", ""))
        self.left_panel.refresh_materials()
        self.lbl_status.setText(f"已采集素材：{data.get('title','')}")

    def _quick_ai(self, role: str):
        self.ai_panel.role_combo.setCurrentIndex(
            self.ai_panel.role_combo.findData(role)
        )
        self.ai_panel._on_run()

    def _apply_ai_result(self, result: str):
        self.editor.apply_ai_result(result, self.ai_panel.role_combo.currentData())

    def _import_docx(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 DOCX", "", "Word 文档 (*.docx)"
        )
        if path:
            self.editor.load_docx(path)
            self.left_panel.load_document(path)

    def _on_docs_dropped(self, files: list):
        if len(files) >= 2:
            self._merge_with_files(files)
        else:
            self.left_panel.load_document(files[0])
            self.editor.load_docx(files[0])

    def _merge_docs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择待合并的 DOCX 文件", "", "Word 文档 (*.docx)"
        )
        if len(paths) < 2:
            QMessageBox.information(self, "提示", "请至少选择 2 个文件进行合并")
            return
        self._merge_with_files(paths)

    def _merge_with_files(self, paths: list):
        out, _ = QFileDialog.getSaveFileName(
            self, "合并输出路径", "合并文档.docx", "Word 文档 (*.docx)"
        )
        if not out:
            return
        self.lbl_status.setText("正在合并多源文档...")
        run_api(
            api_client.merge_docx,
            on_ok=self._on_merged,
            on_err=lambda e: QMessageBox.warning(self, "合并失败", e),
            label="多源合并", parent=self,
            file_paths=paths, output_path=out, with_toc=True,
        )

    def _on_merged(self, result: dict):
        if result.get("ok"):
            self.left_panel.load_document(result.get("output_path", ""))
            n = result.get("heading_count", 0)
            self.lbl_status.setText(
                f"合并完成：{n}个标题，解决{result.get('style_conflicts_resolved',0)}处样式冲突"
            )
        else:
            QMessageBox.warning(self, "合并失败", result.get("error", "未知错误"))

    def _check_format(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 DOCX 校验", "", "Word 文档 (*.docx)"
        )
        if not path:
            return
        self.lbl_status.setText("正在执行公文格式合规校验...")
        run_api(
            api_client.check_docx,
            on_ok=self._on_checked,
            on_err=lambda e: QMessageBox.warning(self, "校验失败", e),
            label="格式校验", parent=self,
            file_path=path,
        )

    def _on_checked(self, result: dict):
        ok = result.get("ok")
        errors = result.get("error_count", 0)
        warns = result.get("warn_count", 0)
        items = result.get("items", [])
        detail = "\n".join(
            f"[{i.get('severity','')}] {i.get('name','')}: {i.get('message','')}"
            for i in items
        )
        self.editor.diff_viewer.setPlainText(detail)
        self.lbl_status.setText(
            f"校验完成：{'合规' if ok else '不合规'}，{errors}错误 / {warns}警告"
        )
        if errors > 0:
            QMessageBox.warning(
                self, "格式校验",
                f"发现 {errors} 项不合规，{warns} 项警告。\n\n{detail}"
            )
        else:
            QMessageBox.information(self, "格式校验", "公文格式合规通过！")

    def _fix_format(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 DOCX 批量修正", "", "Word 文档 (*.docx)"
        )
        if not path:
            return
        self.lbl_status.setText("正在批量修正公文格式...")
        run_api(
            api_client.fix_docx,
            on_ok=self._on_fixed,
            on_err=lambda e: QMessageBox.warning(self, "修正失败", e),
            label="批量修正", parent=self,
            file_path=path, output_path=None,
        )

    def _on_fixed(self, result: dict):
        fixed = result.get("fixed_count", 0)
        self.lbl_status.setText(f"批量修正完成，共修正 {fixed} 项")
        QMessageBox.information(self, "批量修正", f"已修正 {fixed} 项格式问题")

    def _text_check(self):
        text = self.editor.get_text()
        if not text.strip():
            QMessageBox.information(self, "提示", "编辑器内容为空")
            return
        run_api(
            api_client.text_check,
            on_ok=self._on_text_checked,
            on_err=lambda e: QMessageBox.warning(self, "检查失败", e),
            label="文本检查", parent=self,
            text=text,
        )

    def _on_text_checked(self, result: dict):
        items = result.get("items", [])
        detail = "\n".join(
            f"[{i.get('severity','')}] {i.get('name','')}: {i.get('message','')}"
            for i in items
        )
        self.editor.diff_viewer.setPlainText(detail)
        self.lbl_status.setText(f"文本检查完成，发现 {len(items)} 项建议")

    def _run_pipeline(self):
        text = self.editor.get_text()
        if not text.strip():
            QMessageBox.information(self, "提示", "编辑器内容为空")
            return
        self.lbl_status.setText("正在执行全流程流水线...")
        run_api(
            api_client.pipeline,
            on_ok=self._on_pipeline,
            on_err=lambda e: QMessageBox.warning(self, "流水线失败", e),
            label="一键流水线", parent=self,
            html=text, source_url="", style="标准公文", output_path="",
        )

    def _on_pipeline(self, result: dict):
        if result.get("ok"):
            data = result.get("data", {})
            final = data.get("final_text", "")
            self.editor.set_text(final, text="")
            self.left_panel.refresh_materials()
            self.lbl_status.setText("全流程完成：采集→润色→纠错→校验")
        else:
            QMessageBox.warning(self, "流水线", result.get("error", "失败"))

    def _about(self):
        QMessageBox.about(
            self, "关于 智文公文工作台",
            f"<h3>{config.APP_TITLE}</h3>"
            f"<p>版本 {config.APP_VERSION}</p>"
            f"<p>面向职场办公人群与内容运营人员的桌面端智能公文处理系统。</p>"
            f"<p>双端协同 · DOM清洗 · AI润色 · 公文合规 · 多源合并</p>"
            f"<p>API: http://{config.API_HOST}:{config.API_PORT}</p>"
        )

    def closeEvent(self, event):
        self._server_thread.stop()
        api_client.close()
        event.accept()
