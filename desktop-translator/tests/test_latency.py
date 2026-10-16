import math
import queue
import unittest
from unittest.mock import patch
import numpy as np
from qwen_local_subtitles.engine import EngineConfig, SubtitleEngine


class LatencyTests(unittest.TestCase):
    def run_first_segment(self, speech_seconds, silence_seconds):
        cfg=EngineConfig()
        engine=SubtitleEngine('unused',cfg)
        engine._audio_queue=queue.Queue()
        n=int(cfg.sample_rate*cfg.capture_frame_seconds)
        speech_frames=math.ceil(speech_seconds/cfg.capture_frame_seconds)
        for _ in range(speech_frames):
            engine._audio_queue.put(np.full(n,0.1,dtype=np.float32))
        for _ in range(math.ceil(silence_seconds/cfg.capture_frame_seconds)):
            engine._audio_queue.put(np.zeros(n,dtype=np.float32))
        durations=[]
        def recognize(model,frames,min_frames):
            durations.append(sum(len(f) for f in frames)/cfg.sample_rate)
            engine.stop()
        engine._transcribe=recognize
        engine._transcribe_utterances(object())
        return durations[0],speech_frames*cfg.capture_frame_seconds

    def test_continuous_speech_is_submitted_within_two_seconds(self):
        duration,_=self.run_first_segment(4.0,0.0)
        self.assertLessEqual(duration,2.001)
        self.assertGreaterEqual(duration,0.5)

    def test_short_phrase_waits_no_more_than_350ms_after_pause(self):
        duration,speech=self.run_first_segment(0.6,1.0)
        self.assertLessEqual(duration-speech,0.351)

    def test_model_startup_audio_is_discarded_before_listening(self):
        engine=SubtitleEngine('unused')
        seen=[]
        def slow_startup():
            engine._audio_queue.put(np.full(4000,0.1,dtype=np.float32))
        def listen(model):
            while not engine._audio_queue.empty():
                seen.append(engine._audio_queue.get_nowait())
        with patch.object(engine,'_capture_audio',return_value=None), \
             patch.object(engine,'_check_ollama',side_effect=slow_startup), \
             patch.object(engine,'_transcribe_utterances',side_effect=listen), \
             patch('qwen_local_subtitles.engine.Qwen3ASRModel.from_pretrained',return_value=object()):
            engine.run()
        self.assertFalse(any(frame is not None for frame in seen),
                         'Old startup audio must not delay the first live subtitle')


if __name__=='__main__':
    unittest.main()

