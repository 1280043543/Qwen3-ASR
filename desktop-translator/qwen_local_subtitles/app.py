from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .engine import EngineConfig, SubtitleEngine, available_loopbacks


STYLE = """
QWidget { background: #111722; color: #e8edf4; font-family: 'Segoe UI'; font-size: 14px; }
QMainWindow { background: #111722; }
QLabel#title { font-size: 25px; font-weight: 700; color: #f8fafc; }
QLabel#muted { color: #9aa8bb; }
QLabel#section { color: #91a0b5; font-size: 12px; font-weight: 700; }
QFrame#card { background: #1a2330; border: 1px solid #2b394c; border-radius: 12px; }
QComboBox { background: #202c3b; border: 1px solid #394a60; border-radius: 7px; padding: 10px; }
QPushButton { background: #26354a; border: 0; border-radius: 8px; padding: 11px 18px; font-weight: 600; }
QPushButton#start { background: #4c83f1; color: white; }
QPushButton:disabled { color: #78869a; background: #202a38; }
"""


class Overlay(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(720)
        self.setWindowTitle("Qwen Local Subtitles")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        self.original = QLabel("等待播放音频…")
        self.original.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.original.setStyleSheet("color:#dce4ef;font-size:17px;background:transparent;")
        self.translated = QLabel("本地翻译字幕会显示在这里")
        self.translated.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.translated.setWordWrap(True)
        self.translated.setStyleSheet("color:white;font-size:25px;font-weight:700;background:transparent;")
        for label in (self.original, self.translated):
            layout.addWidget(label)
        self.setStyleSheet("background:rgba(8,12,18,210);border:1px solid rgba(255,255,255,36);border-radius:12px;")
        self._drag_offset = None

    def set_text(self, original: str, translated: str) -> None:
        self.original.setText(original)
        self.translated.setText(translated)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Qwen 本地实时字幕")
        self.setMinimumSize(680, 590)
        self.setStyleSheet(STYLE)
        self.overlay = Overlay()
        self.thread: QThread | None = None
        self.engine: SubtitleEngine | None = None
        self._close_requested = False

        root = QWidget()
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(28, 26, 28, 24)
        page.setSpacing(18)

        heading = QLabel("本地实时字幕")
        heading.setObjectName("title")
        page.addWidget(heading)
        desc = QLabel("捕获 Windows 正在播放的声音，离线识别并翻译成字幕")
        desc.setObjectName("muted")
        page.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)
        device_label = QLabel("系统播放设备")
        device_label.setObjectName("section")
        card_layout.addWidget(device_label)
        self.devices = QComboBox()
        try:
            self.loopbacks = available_loopbacks()
            for device_id, name in self.loopbacks:
                self.devices.addItem(name, device_id)
        except Exception as exc:
            self.loopbacks = []
            self.devices.addItem(f"读取设备失败：{exc}", "")
        if not self.loopbacks:
            self.devices.addItem("未找到系统回环设备", "")
        card_layout.addWidget(self.devices)

        language_label = QLabel("翻译成")
        language_label.setObjectName("section")
        card_layout.addWidget(language_label)
        self.language = QComboBox()
        self.language.addItems(["Chinese", "English", "Japanese", "Korean", "French", "German", "Spanish"])
        card_layout.addWidget(self.language)
        page.addWidget(card)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("开始监听")
        self.start_button.setObjectName("start")
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_capture)
        self.overlay_button = QPushButton("显示字幕")
        self.overlay_button.clicked.connect(self.toggle_overlay)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        buttons.addWidget(self.overlay_button)
        page.addLayout(buttons)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(18, 14, 18, 14)
        status_label = QLabel("状态")
        status_label.setObjectName("section")
        self.status = QLabel("就绪。选择播放设备后，点击“开始监听”。")
        self.status.setWordWrap(True)
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status)
        page.addWidget(status_card)

        text_card = QFrame()
        text_card.setObjectName("card")
        text_layout = QVBoxLayout(text_card)
        text_layout.setContentsMargins(18, 14, 18, 14)
        original_title = QLabel("识别原文")
        original_title.setObjectName("section")
        self.original = QLabel("播放视频后，识别内容会显示在这里。")
        self.original.setWordWrap(True)
        translated_title = QLabel("翻译字幕")
        translated_title.setObjectName("section")
        self.translated = QLabel("—")
        self.translated.setWordWrap(True)
        self.translated.setStyleSheet("font-size:19px;font-weight:600;color:#9fc0ff;")
        for widget in (original_title, self.original, translated_title, self.translated):
            text_layout.addWidget(widget)
        page.addWidget(text_card, 1)

        note = QLabel("音频与文本在本机处理。模型首次下载后可离线使用。")
        note.setObjectName("muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page.addWidget(note)

    def start_capture(self) -> None:
        device_id = self.devices.currentData()
        if not device_id:
            self.status.setText("未找到系统回环设备，请确认 Windows 音频设备正常后重启应用。")
            return
        self.start_button.setEnabled(False)
        self.devices.setEnabled(False)
        self.language.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("正在启动本地识别…")
        self.thread = QThread(self)
        self.engine = SubtitleEngine(device_id, EngineConfig(target_language=self.language.currentText()))
        self.engine.moveToThread(self.thread)
        self.thread.started.connect(self.engine.run)
        self.engine.status.connect(self.status.setText)
        self.engine.transcript.connect(self.original.setText)
        self.engine.translation.connect(self.show_translation)
        self.engine.error.connect(self.show_error)
        self.engine.finished.connect(self.thread.quit)
        self.engine.finished.connect(self.engine.deleteLater)
        self.thread.finished.connect(self.capture_finished)
        self.thread.start()

    def stop_capture(self) -> None:
        if self.engine:
            self.engine.stop()
        self.stop_button.setEnabled(False)
        self.status.setText("正在停止，等待当前识别任务结束…")

    def capture_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.devices.setEnabled(True)
        self.language.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.thread = None
        self.engine = None
        if self._close_requested:
            self._close_requested = False
            self.close()

    def show_translation(self, text: str) -> None:
        self.translated.setText(text)
        self.overlay.set_text(self.original.text(), text)

    def show_error(self, message: str) -> None:
        self.status.setText(message)

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
            self.overlay_button.setText("显示字幕")
        else:
            self.overlay.show()
            self.overlay.move(300, 720)
            self.overlay_button.setText("隐藏字幕")

    def closeEvent(self, event) -> None:
        if self.thread and self.thread.isRunning():
            self._close_requested = True
            self.stop_capture()
            event.ignore()
            return
        self.overlay.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
