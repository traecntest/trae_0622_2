from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QPushButton, QLabel, QHBoxLayout, QMessageBox,
    QGroupBox, QDialogButtonBox,
)

import config


SETTINGS_PATH = config.BASE_DIR / "data" / "ai_settings.json"


DEFAULT_SETTINGS = {
    "provider": "openai",
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "temperature": 0.4,
    "max_tokens": 2048,
    "timeout": 60,
    "fallback_local": True,
}


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = {**DEFAULT_SETTINGS, **data}
                return merged
        except Exception:
            return dict(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> bool:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def apply_settings_to_config(settings: dict):
    cfg = config.AIConfig
    cfg.provider = settings.get("provider", cfg.provider)
    cfg.api_key = settings.get("api_key", cfg.api_key)
    cfg.base_url = settings.get("base_url", cfg.base_url)
    cfg.model = settings.get("model", cfg.model)
    cfg.temperature = float(settings.get("temperature", cfg.temperature))
    cfg.max_tokens = int(settings.get("max_tokens", cfg.max_tokens))
    cfg.timeout = float(settings.get("timeout", cfg.timeout))
    cfg.fallback_local = bool(settings.get("fallback_local", cfg.fallback_local))


class AISettingsDialog(QDialog):
    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 模型配置")
        self.setMinimumWidth(480)
        self._settings = load_settings()
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "配置大模型参数。未填写 API Key 时系统会自动使用本地回退处理，保证离线可用。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#6366f1; padding:6px; background:#eef2ff; border-radius:4px;")
        layout.addWidget(info)

        group = QGroupBox("模型接口")
        form = QFormLayout(group)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "兼容 OpenAI 协议 (本地/第三方)"])
        form.addRow("服务商：", self.provider_combo)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("例如 https://api.openai.com/v1")
        form.addRow("API Base URL：", self.base_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("输入 API Key（留空则启用本地回退）")
        form.addRow("API Key：", self.api_key_edit)

        self.show_key_cb = QCheckBox("显示 Key")
        self.show_key_cb.toggled.connect(
            lambda on: self.api_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", self.show_key_cb)

        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("例如 gpt-4o-mini、qwen-plus、deepseek-chat")
        form.addRow("模型名称：", self.model_edit)

        layout.addWidget(group)

        group2 = QGroupBox("推理参数")
        form2 = QFormLayout(group2)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setDecimals(2)
        form2.addRow("Temperature：", self.temp_spin)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 32768)
        self.max_tokens_spin.setSingleStep(256)
        form2.addRow("最大输出 Token：", self.max_tokens_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setSuffix(" 秒")
        form2.addRow("请求超时：", self.timeout_spin)

        self.fallback_cb = QCheckBox("无 Key 或请求失败时，自动回退本地处理")
        form2.addRow("", self.fallback_cb)

        layout.addWidget(group2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存并生效")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self):
        s = self._settings
        if s.get("provider") == "openai":
            self.provider_combo.setCurrentIndex(0)
        else:
            self.provider_combo.setCurrentIndex(1)
        self.base_url_edit.setText(s.get("base_url", ""))
        self.api_key_edit.setText(s.get("api_key", ""))
        self.model_edit.setText(s.get("model", ""))
        self.temp_spin.setValue(float(s.get("temperature", 0.4)))
        self.max_tokens_spin.setValue(int(s.get("max_tokens", 2048)))
        self.timeout_spin.setValue(int(s.get("timeout", 60)))
        self.fallback_cb.setChecked(bool(s.get("fallback_local", True)))

    def _collect(self) -> dict:
        provider = "openai" if self.provider_combo.currentIndex() == 0 else "custom"
        return {
            "provider": provider,
            "base_url": self.base_url_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "model": self.model_edit.text().strip() or "gpt-4o-mini",
            "temperature": float(self.temp_spin.value()),
            "max_tokens": int(self.max_tokens_spin.value()),
            "timeout": int(self.timeout_spin.value()),
            "fallback_local": self.fallback_cb.isChecked(),
        }

    def _on_save(self):
        s = self._collect()
        if save_settings(s):
            apply_settings_to_config(s)
            self.settings_saved.emit(s)
            QMessageBox.information(self, "成功", "AI 配置已保存并生效")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", "配置保存失败，请检查写入权限")
