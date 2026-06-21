from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt, QMimeData
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QHBoxLayout, QTabWidget, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QSplitter,
)

from ui.api_client import api_client
from ui.workers import run_api


class MaterialList(QListWidget):
    material_selected = Signal(str)
    materials_refreshed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def load_materials(self, items: list[dict]):
        self.clear()
        for m in items:
            title = m.get("title", "未命名素材")
            wc = ""
            extra = m.get("extra")
            if isinstance(extra, str):
                import json
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}
            if isinstance(extra, dict):
                wc = extra.get("word_count", "")
            label = f"{title}" + (f"  ·{wc}字" if wc else "")
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, m.get("id"))
            it.setToolTip(m.get("source_url", "") or title)
            self.addItem(it)

    def _on_double_click(self, item: QListWidgetItem):
        mid = item.data(Qt.ItemDataRole.UserRole)
        if mid:
            self.material_selected.emit(mid)

    def _on_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        item = self.itemAt(pos)
        if not item:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        act_open = menu.addAction("载入到编辑器")
        act_del = menu.addAction("删除素材")
        act = menu.exec(self.mapToGlobal(pos))
        if act == act_open:
            self.material_selected.emit(mid)
        elif act == act_del:
            run_api(api_client.delete_material,
                    on_ok=lambda r: self.refresh(),
                    label="删除素材", parent=self, mid=mid)
            run_api(api_client.list_materials,
                    on_ok=self.load_materials,
                    label="刷新素材", parent=self)

    def refresh(self):
        run_api(api_client.list_materials,
                on_ok=self.load_materials,
                on_err=lambda e: None,
                label="刷新素材列表", parent=self)
        self.materials_refreshed.emit()


class DocumentTree(QTreeWidget):
    document_selected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["文档结构"])
        self.setAlternatingRowColors(True)
        self.itemDoubleClicked.connect(self._on_double_click)

    def load_from_path(self, docx_path: str):
        self.clear()
        from docx import Document
        from core.merger import DocMerger
        m = DocMerger()
        try:
            doc = Document(docx_path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        root = QTreeWidgetItem([Path(docx_path).name])
        root.setData(0, Qt.ItemDataRole.UserRole, ("file", docx_path))
        self.addTopLevelItem(root)
        for idx, para in enumerate(doc.paragraphs):
            lvl = m._detect_heading_level(para)
            if lvl and para.text.strip():
                node = QTreeWidgetItem([para.text.strip()])
                node.setData(0, Qt.ItemDataRole.UserRole,
                             ("para", para.text.strip()))
                _insert_by_level(root, node, lvl)
        self.expandAll()

    def _on_double_click(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.document_selected.emit(data[0], data[1])


def _insert_by_level(root: QTreeWidgetItem, node: QTreeWidgetItem, level: int):
    target = root
    for _ in range(level - 1):
        if target.childCount() == 0:
            break
        target = target.child(target.childCount() - 1)
    target.addChild(node)


class LeftPanel(QWidget):
    material_selected = Signal(str)
    docx_files_dropped = Signal(list)
    open_docx_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        tabs = QTabWidget()
        self.doc_tab = QWidget()
        self.mat_tab = QWidget()
        tabs.addTab(self.doc_tab, "文档树")
        tabs.addTab(self.mat_tab, "素材库")
        layout.addWidget(tabs)

        d_layout = QVBoxLayout(self.doc_tab)
        d_layout.setContentsMargins(2, 2, 2, 2)
        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("打开 DOCX")
        self.btn_open.clicked.connect(self.open_docx_requested.emit)
        btn_row.addWidget(self.btn_open)
        d_layout.addLayout(btn_row)
        self.doc_tree = DocumentTree()
        d_layout.addWidget(self.doc_tree)

        m_layout = QVBoxLayout(self.mat_tab)
        m_layout.setContentsMargins(2, 2, 2, 2)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索素材...")
        self.search.textChanged.connect(self._on_search)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(lambda: self.material_list.refresh())
        search_row.addWidget(self.search)
        search_row.addWidget(self.btn_refresh)
        m_layout.addLayout(search_row)
        self.material_list = MaterialList()
        self.material_list.material_selected.connect(self.material_selected.emit)
        m_layout.addWidget(self.material_list)

        self.stats_label = QLabel("素材：0 | 字数：0")
        self.stats_label.setStyleSheet("color:#666; padding:2px;")
        m_layout.addWidget(self.stats_label)

    def load_materials(self, items: list[dict]):
        self.material_list.load_materials(items)
        total = len(items)
        words = 0
        for it in items:
            extra = it.get("extra")
            if isinstance(extra, str):
                import json
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}
            if isinstance(extra, dict):
                words += extra.get("word_count", 0) or 0
        self.stats_label.setText(f"素材：{total} | 字数：{words}")

    def refresh_materials(self):
        self.material_list.refresh()

    def _on_search(self, text: str):
        text = text.strip()
        if not text:
            self.refresh_materials()
        else:
            run_api(api_client.search_materials,
                    on_ok=lambda r: self.material_list.load_materials(
                        [{"id": m.get("id"), "title": m.get("title"),
                          "source_url": m.get("source_url"),
                          "extra": m.get("extra")} for m in r]),
                    label="搜索素材", parent=self, keyword=text)

    def load_document(self, path: str):
        self.doc_tree.load_from_path(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls
                 if u.toLocalFile().lower().endswith(".docx")]
        if files:
            self.docx_files_dropped.emit(files)
            event.acceptProposedAction()
