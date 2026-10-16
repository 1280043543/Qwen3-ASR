from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .engine import EngineConfig, SubtitleEngine, SYSTEM_DEFAULT_DEVICE, available_loopbacks


STYLE = """
QWidget { color: #e6edf8; font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 14px; }
QMainWindow, QWidget#appRoot, QScrollArea { background: #101621; }
QScrollArea { border: 0; }
QLabel { background: transparent; border: 0; padding: 0; }
QLabel#title { font-size: 26px; font-weight: 700; color: #f5f8ff; }
QLabel#muted { color: #96a5bc; font-size: 13px; }
QLabel#section { color: #adbbd0; font-size: 13px; font-weight: 600; }
QFrame#card { background: #192231; border: 1px solid #2b394e; border-radius: 14px; }
QComboBox { background: #202d40; border: 1px solid #3a4c65; border-radius: 8px; padding: 0 12px; selection-background-color: #3954a0; }
QComboBox:hover { border-color: #7898ed; }
QComboBox:focus { border: 1px solid #8ba7ff; }
QComboBox:disabled { color: #8391a7; background: #1a2535; }
QComboBox::drop-down { width: 30px; border: 0; }
QComboBox::down-arrow { image: url('__CHEVRON__'); width: 14px; height: 14px; }
QComboBox QAbstractItemView { background: #202d40; color: #e6edf8; border: 1px solid #4a5d7a; selection-background-color: #3954a0; padding: 6px; outline: 0; }
QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px 8px; }
QPushButton { background: #293a52; border: 1px solid #3a4c66; border-radius: 8px; padding: 0 18px; font-weight: 600; }
QPushButton:hover { background: #354a68; border-color: #6b88bc; }
QPushButton:pressed { background: #21324a; }
QPushButton#start { background: #6389f5; border-color: #6389f5; color: #ffffff; }
QPushButton#start:hover { background: #789bff; }
QPushButton:disabled { color: #74839a; background: #1c2839; border-color: #29374a; }
QScrollBar:vertical { background: #101621; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a4a63; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
ASSET_DIR = Path(__file__).resolve().parent / "assets"


class Overlay(QFrame):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("subtitleOverlay")
        self.setMinimumWidth(720)
        self.resize(800, 180)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setWindowTitle("Qwen Local Subtitles")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        self.drag_hint = QLabel("⠿  按住字幕区域任意位置拖动")
        self.drag_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.drag_hint.setStyleSheet("color:#9aa8bb;font-size:12px;background:transparent;border:0;")
        layout.addWidget(self.drag_hint)
        self.original = QLabel("等待播放音频…")
        self.original.setWordWrap(True)
        self.original.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.original.setStyleSheet("color:#dce4ef;font-size:17px;background:transparent;")
        self.translated = QLabel("本地翻译字幕会显示在这里")
        self.translated.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.translated.setWordWrap(True)
        self.translated.setStyleSheet("color:white;font-size:25px;font-weight:700;background:transparent;")
        for label in (self.drag_hint, self.original, self.translated):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setTextFormat(Qt.TextFormat.PlainText)
        for label in (self.original, self.translated):
            layout.addWidget(label)
        self.setStyleSheet("QFrame#subtitleOverlay { background:rgba(8,12,18,225);border:1px solid rgba(255,255,255,36);border-radius:12px; }")
        self._drag_offset = None

    def set_text(self, original: str, translated: str) -> None:
        self.original.setText(original)
        self.translated.setText(translated)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Let Windows own the drag so it continues smoothly outside the overlay.
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                self._drag_offset = None
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Qwen 本地实时字幕")
        self.setMinimumSize(620, 520)
        self.resize(800, 820)
        self.setStyleSheet(STYLE.replace("__CHEVRON__", (ASSET_DIR / "chevron.svg").as_posix()))
        self.overlay = Overlay()
        self._overlay_positioned = False
        self.thread: QThread | None = None
        self.engine: SubtitleEngine | None = None
        self._close_requested = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll)
        root = QWidget()
        root.setObjectName("appRoot")
        scroll.setWidget(root)
        page = QVBoxLayout(root)
        page.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        page.setContentsMargins(28, 26, 28, 24)
        page.setSpacing(18)

        header = QHBoxLayout()
        brand = QLabel()
        brand.setFixedSize(52, 52)
        brand.setPixmap(QPixmap(str(ASSET_DIR / "app-icon.png")).scaled(
            52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(brand)
        header.addSpacing(4)
        heading = QLabel("本地实时字幕")
        heading.setObjectName("title")
        header.addWidget(heading, 1)
        page.addLayout(header)
        desc = QLabel("让每一段视频，都有你看得懂的字幕。")
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
        self.devices.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.refresh_devices()
        device_row = QHBoxLayout()
        device_row.addWidget(self.devices, 1)
        self.refresh_button = QPushButton("刷新设备")
        self.refresh_button.clicked.connect(self.refresh_devices)
        device_row.addWidget(self.refresh_button)
        card_layout.addLayout(device_row)

        language_label = QLabel("翻译成")
        language_label.setObjectName("section")
        card_layout.addWidget(language_label)
        self.language = QComboBox()
        for title, code in [("简体中文", "Chinese"), ("英语", "English"), ("日语", "Japanese"),
                            ("韩语", "Korean"), ("法语", "French"), ("德语", "German"), ("西班牙语", "Spanish")]:
            self.language.addItem(title, code)
        self.caption_mode = QComboBox()
        self.caption_mode.addItem("语义优先 · 完整表达", "meaning")
        self.caption_mode.addItem("速度优先 · 更快显示", "speed")
        self.caption_mode.setToolTip("语义优先：最多收集 4 秒音频；速度优先：最多收集 2 秒。遇到停顿会提前提交。")
        # Place both fields in a row; explicit control heights prevent layout compression.
        card_layout.removeWidget(language_label)
        fields = QHBoxLayout()
        fields.setSpacing(16)
        language_column = QVBoxLayout()
        language_column.addWidget(language_label)
        language_column.addWidget(self.language)
        mode_column = QVBoxLayout()
        mode_label = QLabel("字幕模式")
        mode_label.setObjectName("section")
        mode_column.addWidget(mode_label)
        mode_column.addWidget(self.caption_mode)
        fields.addLayout(language_column, 1)
        fields.addLayout(mode_column, 2)
        card_layout.addLayout(fields)
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
        self.audio_status = QLabel("声音输入：未监听")
        status_layout.addWidget(self.audio_status)
        page.addWidget(status_card)

        text_card = QFrame()
        text_card.setObjectName("card")
        text_layout = QVBoxLayout(text_card)
        text_layout.setContentsMargins(18, 14, 18, 14)
        original_title = QLabel("识别原文")
        original_title.setObjectName("section")
        self.original = QLabel("播放视频后，识别内容会显示在这里。")
        self.original.setWordWrap(True)
        self.original.setMinimumHeight(32)
        self.original.setTextFormat(Qt.TextFormat.PlainText)
        translated_title = QLabel("翻译字幕")
        translated_title.setObjectName("section")
        self.translated = QLabel("—")
        self.translated.setWordWrap(True)
        self.translated.setMinimumHeight(48)
        self.translated.setTextFormat(Qt.TextFormat.PlainText)
        self.translated.setStyleSheet("font-size:21px;font-weight:600;color:#b5caff;")
        for widget in (original_title, self.original, translated_title, self.translated):
            text_layout.addWidget(widget)
        page.addWidget(text_card, 1)

        note = QLabel("本地处理  ·  离线识别与翻译  ·  音频不上传")
        note.setObjectName("muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page.addWidget(note)
        for combo in (self.devices, self.language, self.caption_mode):
            combo.setFixedHeight(44)
            combo.view().setMinimumWidth(280)
        for button in (self.refresh_button, self.start_button, self.stop_button, self.overlay_button):
            button.setFixedHeight(44)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        for label in (device_label, language_label, mode_label, status_label, original_title, translated_title):
            label.setMinimumHeight(24)

    def refresh_devices(self) -> None:
        selected = self.devices.currentData()
        self.devices.clear()
        self.devices.addItem("跟随系统默认播放设备（推荐）", SYSTEM_DEFAULT_DEVICE)
        try:
            self.loopbacks = available_loopbacks()
            for device_id, name in self.loopbacks:
                self.devices.addItem(name, device_id)
        except Exception:
            self.loopbacks = []
        index = self.devices.findData(selected)
        self.devices.setCurrentIndex(index if index >= 0 else 0)

    def start_capture(self) -> None:
        self.refresh_devices()
        device_id = self.devices.currentData()
        if not device_id:
            self.status.setText("未找到系统回环设备，请确认 Windows 音频设备正常后重启应用。")
            return
        self.start_button.setEnabled(False)
        self.devices.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.language.setEnabled(False)
        self.caption_mode.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("正在启动本地识别…")
        self.thread = QThread(self)
        meaning_first = self.caption_mode.currentData() == "meaning"
        self.engine = SubtitleEngine(device_id, EngineConfig(
            target_language=self.language.currentData(),
            max_utterance_seconds=4.0 if meaning_first else 2.0,
            utterance_silence_seconds=0.45 if meaning_first else 0.3,
        ))
        self.engine.moveToThread(self.thread)
        self.thread.started.connect(self.engine.run)
        self.engine.status.connect(self.status.setText)
        self.engine.transcript.connect(self.original.setText)
        self.engine.translation.connect(self.show_translation)
        self.engine.error.connect(self.show_error)
        self.engine.audio_level.connect(self.show_audio_level)
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
        self.refresh_button.setEnabled(True)
        self.language.setEnabled(True)
        self.caption_mode.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.thread = None
        self.engine = None
        self.audio_status.setText("声音输入：未监听")
        if self._close_requested:
            self._close_requested = False
            self.close()

    def show_translation(self, text: str) -> None:
        self.translated.setText(text)
        self.overlay.set_text(self.original.text(), text)

    def show_audio_level(self, level: float) -> None:
        self.audio_status.setText("声音输入：有声音" if level >= 0.006 else "声音输入：安静或无声音")

    def show_error(self, message: str) -> None:
        self.status.setText(message)

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
            self.overlay_button.setText("显示字幕")
        else:
            if not self._overlay_positioned:
                screen = self.screen().availableGeometry()
                self.overlay.move(
                    screen.x() + (screen.width() - self.overlay.width()) // 2,
                    screen.bottom() - self.overlay.height() - 60,
                )
                self._overlay_positioned = True
            self.overlay.show()
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
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Qwen.LocalSubtitles.Desktop")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(QIcon(str(ASSET_DIR / "app-icon.ico")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()




