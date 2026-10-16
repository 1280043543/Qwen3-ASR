import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from qwen_local_subtitles.engine import SubtitleEngine


class DefaultOutputCaptureTests(unittest.TestCase):
    def test_follows_output_change_while_listening(self):
        engine = SubtitleEngine('__system_default__')
        state = {'output': 'speakers', 'old_frames': 0}
        opened = []

        class Recorder:
            def __init__(self, device):
                self.device = device

            def __enter__(self):
                opened.append(self.device)
                return self

            def __exit__(self, *args):
                return False

            def record(self, numframes):
                if self.device == 'speakers':
                    state['old_frames'] += 1
                    state['output'] = 'headphones'
                    if state['old_frames'] > 12:
                        engine.stop()
                else:
                    engine.stop()
                return np.full((numframes, 2), 0.1, dtype=np.float32)

        def get_microphone(id, include_loopback):
            if id not in ('speakers', 'headphones'):
                raise ValueError('Unresolved default output')
            return SimpleNamespace(name=id, recorder=lambda samplerate: Recorder(id))

        with patch('qwen_local_subtitles.engine.sc.default_speaker',
                   side_effect=lambda: SimpleNamespace(id=state['output'])), \
             patch('qwen_local_subtitles.engine.sc.get_microphone', side_effect=get_microphone):
            engine._capture_audio()

        self.assertEqual(opened, ['speakers', 'headphones'],
                         'Listening must reopen capture when Windows changes its default output')


    def test_window_defaults_to_system_output_and_refreshes_new_devices(self):
        import os
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        from qwen_local_subtitles.app import MainWindow
        app = QApplication.instance() or QApplication([])
        devices = [('speakers', 'Speakers')]
        with patch('qwen_local_subtitles.app.available_loopbacks', side_effect=lambda: list(devices)):
            window = MainWindow()
            self.assertEqual(window.devices.currentData(), '__system_default__')
            devices.append(('headphones', 'Headphones'))
            window.refresh_devices()
            self.assertGreaterEqual(window.devices.findData('headphones'), 0)
            self.assertEqual(window.devices.currentData(), '__system_default__')
            window.close()
        app.processEvents()

if __name__ == '__main__':
    unittest.main()


