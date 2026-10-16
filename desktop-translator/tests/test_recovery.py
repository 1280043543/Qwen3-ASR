import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import requests

from qwen_local_subtitles.engine import EngineConfig, SubtitleEngine


class RecoveryTests(unittest.TestCase):
    def frames(self, value=0.1, count=10):
        return [np.full(1600, value, dtype=np.float32) for _ in range(count)]

    def test_translation_timeout_keeps_listening_and_recovers_next_segment(self):
        engine = SubtitleEngine('unused')
        subtitles, statuses = [], []
        engine.translation.connect(subtitles.append)
        engine.status.connect(statuses.append)
        model = SimpleNamespace(transcribe=lambda **kw: [SimpleNamespace(text='face to face')])
        with patch.object(engine, '_translate', side_effect=[requests.Timeout('slow'), '面对面']), \
             self.assertLogs('qwen_local_subtitles.engine', level='WARNING'):
            try:
                engine._transcribe(model, self.frames(), 5)
                engine._transcribe(model, self.frames(), 5)
            except requests.Timeout:
                self.fail('A single translation timeout must not stop listening')
        self.assertEqual(subtitles[-1], '面对面')
        self.assertIn('翻译暂不可用', subtitles[0])
        self.assertTrue(any('继续' in text for text in statuses))
        self.assertFalse(engine._stop_event.is_set())

    def test_overflow_inserts_gap_before_new_audio(self):
        engine = SubtitleEngine('unused')
        engine._audio_queue = queue.Queue(maxsize=3)
        old = self.frames(count=1)[0]
        for _ in range(3):
            engine._audio_queue.put(old)
        new = old * 2
        self.assertTrue(hasattr(engine, '_enqueue_audio'), 'Overflow needs a shared enqueue path')
        engine._enqueue_audio(new)
        self.assertIsNone(engine._audio_queue.get_nowait())
        np.testing.assert_array_equal(engine._audio_queue.get_nowait(), new)
        self.assertTrue(engine._audio_queue.empty())

    def test_old_source_result_is_not_displayed_after_reset(self):
        engine = SubtitleEngine('unused')
        subtitles, originals = [], []
        engine.translation.connect(subtitles.append)
        engine.transcript.connect(originals.append)
        def transcribe(**kwargs):
            engine._reset_audio_buffer()
            return [SimpleNamespace(text='old device')]
        model = SimpleNamespace(transcribe=transcribe)
        with patch.object(engine, '_translate', return_value='旧设备'):
            engine._transcribe(model, self.frames(), 5)
        self.assertEqual(originals, [])
        self.assertEqual(subtitles, [])

    def test_hard_cut_is_revised_with_following_audio(self):
        cfg = EngineConfig(sample_rate=100, capture_frame_seconds=0.1,
                           max_utterance_seconds=0.5, min_utterance_seconds=0.1)
        engine = SubtitleEngine('unused', cfg)
        for frame in [np.full(10, 0.1, np.float32) for _ in range(16)]:
            engine._audio_queue.put(frame)
        sizes = []
        def transcribe(**kwargs):
            sizes.append(len(kwargs['audio'][0]))
            if len(sizes) == 3:
                engine.stop()
            return [SimpleNamespace(text='meet face to face')]
        with patch.object(engine, '_translate', return_value='面对面交流'):
            engine._transcribe_utterances(SimpleNamespace(transcribe=transcribe))
        self.assertEqual(sizes, [50, 100, 100], 'Only two adjacent segments should overlap')

    def test_loaded_model_is_reused(self):
        model = object()
        self.assertIn('model', __import__('inspect').signature(SubtitleEngine).parameters,
                      'A retained model must be accepted on resume')
        engine = SubtitleEngine('unused', model=model)
        with patch.object(engine, '_capture_audio'), patch.object(engine, '_check_ollama'), \
             patch.object(engine, '_transcribe_utterances') as listen, \
             patch('qwen_local_subtitles.engine.Qwen3ASRModel.from_pretrained') as load:
            engine.run()
        load.assert_not_called()
        self.assertIs(listen.call_args.args[0], model)

    def test_gap_clears_audio_revision_and_translation_context(self):
        cfg = EngineConfig(sample_rate=100, max_utterance_seconds=0.5, min_utterance_seconds=0.1)
        engine = SubtitleEngine('unused', cfg)
        for _ in range(5):
            engine._audio_queue.put(np.full(10, 0.1, np.float32))
        engine._audio_queue.put(None)
        for _ in range(5):
            engine._audio_queue.put(np.full(10, 0.2, np.float32))
        sizes = []
        def transcribe(**kwargs):
            sizes.append(len(kwargs['audio'][0]))
            if len(sizes) == 1:
                engine._translation_context.append('old source')
            else:
                self.assertEqual(list(engine._translation_context), [])
                engine.stop()
            return [SimpleNamespace(text='new speech')]
        with patch.object(engine, '_translate', return_value='字幕'):
            engine._transcribe_utterances(SimpleNamespace(transcribe=transcribe))
        self.assertEqual(sizes, [50, 50])

    def test_translation_from_old_generation_is_discarded(self):
        engine = SubtitleEngine('unused')
        subtitles = []
        engine.translation.connect(subtitles.append)
        def translate(text):
            engine._reset_audio_buffer()
            return '旧来源'
        model = SimpleNamespace(transcribe=lambda **kw: [SimpleNamespace(text='old source')])
        with patch.object(engine, '_translate', side_effect=translate):
            engine._transcribe(model, self.frames(), 5)
        self.assertEqual(subtitles, [])

    def test_pause_does_not_publish_inflight_result(self):
        engine = SubtitleEngine('unused')
        originals = []
        engine.transcript.connect(originals.append)
        def transcribe(**kwargs):
            engine.stop()
            return [SimpleNamespace(text='unfinished')]
        engine._transcribe(SimpleNamespace(transcribe=transcribe), self.frames(), 5)
        self.assertEqual(originals, [])


if __name__ == '__main__':
    unittest.main()

