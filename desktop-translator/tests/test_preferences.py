import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import QRect, QSettings
from PySide6.QtWidgets import QApplication
from qwen_local_subtitles.app import MainWindow, Overlay


class PreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = QSettings(self.folder.name + '/settings.ini', QSettings.Format.IniFormat)

    def window(self):
        with patch('qwen_local_subtitles.app.available_loopbacks', return_value=[]):
            self.assertIn('settings', __import__('inspect').signature(MainWindow).parameters)
            window = MainWindow(settings=self.settings)
        self.addCleanup(window.close)
        return window

    def test_settings_survive_window_recreation(self):
        first = self.window()
        first.font_size.setValue(32)
        first.subtitle_color.setCurrentIndex(1)
        first.background_opacity.setValue(60)
        first.language.setCurrentIndex(1)
        first.caption_mode.setCurrentIndex(1)
        first.toggle_overlay()
        first.overlay.move(16, 90)
        first.close()
        second = self.window()
        self.assertEqual(second.font_size.value(), 32)
        self.assertEqual(second.subtitle_color.currentData(), '#ffe08a')
        self.assertEqual(second.background_opacity.value(), 60)
        self.assertEqual(second.language.currentData(), 'English')
        self.assertEqual(second.caption_mode.currentData(), 'speed')
        self.assertEqual(second.overlay.pos().x(), 16)

    def test_overlay_fits_small_screen(self):
        overlay = Overlay()
        self.addCleanup(overlay.close)
        area = QRect(100, 50, 500, 400)
        self.assertTrue(hasattr(overlay, 'fit_to_screen'))
        overlay.move(-800, 2000)
        overlay.fit_to_screen(SimpleNamespace(availableGeometry=lambda: area))
        self.assertLessEqual(overlay.width(), 468)
        self.assertTrue(area.contains(overlay.geometry()))

    def test_expired_overlay_reappears_for_new_caption_when_enabled(self):
        window = self.window()
        window.toggle_overlay()
        window.original.setText('face to face')
        window.show_translation('面对面')
        self.assertTrue(window.overlay.isVisible())
        window.overlay.expiry_timer.timeout.emit()
        window.overlay.fade_animation.setCurrentTime(window.overlay.fade_animation.duration())
        self.app.processEvents()
        self.assertFalse(window.overlay.isVisible())
        window.show_translation('下一句')
        self.assertTrue(window.overlay.isVisible())
        self.assertEqual(window.overlay.windowOpacity(), 1.0)

    def test_retained_model_can_be_released_while_idle(self):
        window = self.window()
        model = object()
        window.remember_model(model)
        self.assertIs(window._asr_model, model)
        window.release_model()
        self.assertIsNone(window._asr_model)
        self.assertFalse(window.release_button.isEnabled())


if __name__ == '__main__':
    unittest.main()

