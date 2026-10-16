from __future__ import annotations

import os
import queue
import threading
from collections import deque
from dataclasses import dataclass

import numpy as np
import requests
import soundcard as sc
import torch
from PySide6.QtCore import QObject, Signal, Slot
from qwen_asr import Qwen3ASRModel


@dataclass(frozen=True)
class EngineConfig:
    target_language: str = "Chinese"
    asr_model: str = os.environ.get("QWEN_ASR_MODEL", "Qwen/Qwen3-ASR-0.6B")
    translation_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_url: str = "http://127.0.0.1:11434"
    sample_rate: int = 16_000
    capture_frame_seconds: float = 0.25
    utterance_silence_seconds: float = 0.55
    max_utterance_seconds: float = 3.0
    min_utterance_seconds: float = 0.55
    voice_rms_threshold: float = 0.006
    max_buffer_seconds: float = 8.0


def available_loopbacks() -> list[tuple[str, str]]:
    """Return (stable id, display name) for WASAPI loopback capture devices."""
    devices = sc.all_microphones(include_loopback=True)
    return [(str(device.id), device.name) for device in devices if device.isloopback]


class SubtitleEngine(QObject):
    status = Signal(str)
    transcript = Signal(str)
    translation = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, device_id: str, config: EngineConfig | None = None) -> None:
        super().__init__()
        self.device_id = device_id
        self.config = config or EngineConfig()
        self._stop_event = threading.Event()
        frame_count = max(1, int(self.config.max_buffer_seconds / self.config.capture_frame_seconds))
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=frame_count)
        self._dropped_frames = 0
        self._error_message: str | None = None

    @Slot()
    def run(self) -> None:
        capture_thread = threading.Thread(
            target=self._capture_audio,
            name="system-audio-capture",
            daemon=True,
        )
        try:
            # Begin capture before loading the model so startup downloads don't freeze the audio path.
            self.status.emit("正在缓存系统音频并加载本地语音识别模型…")
            capture_thread.start()
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            model = Qwen3ASRModel.from_pretrained(
                self.config.asr_model,
                dtype=dtype,
                device_map="cuda:0" if torch.cuda.is_available() else "cpu",
                max_new_tokens=128,
            )
            if self._stop_event.is_set():
                return
            self.status.emit("正在加载本地翻译模型…")
            self._check_ollama()
            if self._stop_event.is_set():
                return
            self.status.emit("正在监听系统播放音频")
            self._transcribe_utterances(model)
        except Exception as exc:
            self._error_message = f"{type(exc).__name__}: {exc}"
            self.error.emit(self._error_message)
        finally:
            self._stop_event.set()
            if capture_thread.is_alive():
                capture_thread.join(timeout=2.0)
            if self._error_message is None:
                self.status.emit("已停止")
            self.finished.emit()

    def stop(self) -> None:
        self._stop_event.set()

    def _capture_audio(self) -> None:
        """Continuously read loopback audio; inference never blocks this reader."""
        try:
            mic = sc.get_microphone(id=self.device_id, include_loopback=True)
            frame_samples = max(
                1,
                int(self.config.sample_rate * self.config.capture_frame_seconds),
            )
            with mic.recorder(samplerate=self.config.sample_rate) as recorder:
                while not self._stop_event.is_set():
                    audio = recorder.record(numframes=frame_samples)
                    if audio.size == 0:
                        continue
                    mono = np.asarray(audio, dtype=np.float32)
                    if mono.ndim == 2:
                        mono = mono.mean(axis=1)
                    try:
                        self._audio_queue.put_nowait(mono)
                    except queue.Full:
                        # Keep the newest sound so subtitles recover close to live after a slow model call.
                        try:
                            self._audio_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self._audio_queue.put_nowait(mono)
                        self._dropped_frames += 1
                        if self._dropped_frames % 20 == 1:
                            self.status.emit("本地模型处理较慢，已丢弃较早音频以保持字幕接近实时")
        except Exception as exc:
            if not self._stop_event.is_set():
                self._error_message = f"系统音频采集失败：{type(exc).__name__}: {exc}"
                self.error.emit(self._error_message)
                self._stop_event.set()

    def _transcribe_utterances(self, model: Qwen3ASRModel) -> None:
        cfg = self.config
        frame_seconds = cfg.capture_frame_seconds
        silence_frames_needed = max(1, int(cfg.utterance_silence_seconds / frame_seconds))
        max_frames = max(1, int(cfg.max_utterance_seconds / frame_seconds))
        min_frames = max(1, int(cfg.min_utterance_seconds / frame_seconds))
        pre_roll: deque[np.ndarray] = deque(maxlen=2)
        utterance: list[np.ndarray] = []
        silent_frames = 0

        while not self._stop_event.is_set():
            try:
                frame = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                # The capture reader can be between 250 ms recording calls; silence frames
                # from the device, rather than a temporarily empty queue, end an utterance.
                continue

            level = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
            if not utterance:
                pre_roll.append(frame)
                if level >= cfg.voice_rms_threshold:
                    utterance = list(pre_roll)
                    silent_frames = 0
                continue

            utterance.append(frame)
            if level < cfg.voice_rms_threshold:
                silent_frames += 1
            else:
                silent_frames = 0

            if silent_frames >= silence_frames_needed or len(utterance) >= max_frames:
                self._transcribe(model, utterance, min_frames)
                utterance = []
                silent_frames = 0
                pre_roll.clear()

        # Flush a final short phrase on user stop.
        if utterance:
            self._transcribe(model, utterance, min_frames)

    def _transcribe(self, model: Qwen3ASRModel, frames: list[np.ndarray], min_frames: int) -> None:
        audio = np.concatenate(frames)
        if len(frames) < min_frames:
            return
        if float(np.sqrt(np.mean(np.square(audio)))) < self.config.voice_rms_threshold:
            return
        result = model.transcribe(audio=(audio, self.config.sample_rate), language=None)
        text = result[0].text.strip() if result else ""
        if not text:
            return
        self.transcript.emit(text)
        translated = self._translate(text)
        if translated:
            self.translation.emit(translated)

    def _check_ollama(self) -> None:
        response = requests.get(f"{self.config.ollama_url}/api/tags", timeout=3)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = {item.get("name", "") for item in models}
        if not any(name == self.config.translation_model or name.startswith(self.config.translation_model + ":") for name in names):
            raise RuntimeError(
                f"本地未找到翻译模型 {self.config.translation_model}。请先在 Ollama 中下载该模型。"
            )
        # Load weights before listening so the first subtitle doesn't pay the cold-load cost.
        preload = requests.post(
            f"{self.config.ollama_url}/api/generate",
            json={
                "model": self.config.translation_model,
                "stream": False,
                "options": {"num_ctx": 2048},
            },
            timeout=(3, 180),
        )
        preload.raise_for_status()

    def _translate(self, text: str) -> str:
        response = requests.post(
            f"{self.config.ollama_url}/api/chat",
            json={
                "model": self.config.translation_model,
                "stream": False,
                "think": False,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Translate the following spoken subtitle into {self.config.target_language}. "
                            "Keep names and meaning accurate. Return only the translation, concise enough "
                            "for a subtitle. Do not explain or add quotation marks."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "options": {"temperature": 0.1, "num_ctx": 2048, "num_predict": 256},
            },
            timeout=45,
        )
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "").strip()
