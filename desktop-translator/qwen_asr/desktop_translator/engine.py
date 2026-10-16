from __future__ import annotations

import time
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
    asr_model: str = "Qwen/Qwen3-ASR-0.6B"
    translation_model: str = "qwen3:4b"
    chunk_seconds: float = 4.0
    ollama_url: str = "http://127.0.0.1:11434"


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
        self._stopping = False

    @Slot()
    def run(self) -> None:
        try:
            self.status.emit("正在加载本地语音识别模型…首次运行会下载模型")
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            model = Qwen3ASRModel.from_pretrained(
                self.config.asr_model,
                dtype=dtype,
                device_map="cuda:0" if torch.cuda.is_available() else "cpu",
                max_new_tokens=128,
            )
            self.status.emit("连接本地翻译模型…")
            self._check_ollama()
            mic = sc.get_microphone(id=self.device_id, include_loopback=True)
            rate = 16_000
            frames = int(rate * self.config.chunk_seconds)
            self.status.emit(f"正在监听：{mic.name}")
            with mic.recorder(samplerate=rate) as recorder:
                while not self._stopping:
                    audio = recorder.record(numframes=frames)
                    if audio.size == 0:
                        continue
                    mono = np.asarray(audio, dtype=np.float32)
                    if mono.ndim == 2:
                        mono = mono.mean(axis=1)
                    # Ignore near-silence to avoid translating noise and empty model outputs.
                    if float(np.sqrt(np.mean(np.square(mono)))) < 0.003:
                        continue
                    result = model.transcribe(audio=(mono, rate), language=None)
                    text = result[0].text.strip() if result else ""
                    if not text:
                        continue
                    self.transcript.emit(text)
                    translated = self._translate(text)
                    if translated:
                        self.translation.emit(translated)
            self.status.emit("已停止")
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()

    def stop(self) -> None:
        self._stopping = True

    def _check_ollama(self) -> None:
        response = requests.get(f"{self.config.ollama_url}/api/tags", timeout=3)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = {item.get("name", "") for item in models}
        if not any(name == self.config.translation_model or name.startswith(self.config.translation_model + ":") for name in names):
            raise RuntimeError(
                f"本地未找到翻译模型 {self.config.translation_model}。请先在 Ollama 中下载该模型。"
            )

    def _translate(self, text: str) -> str:
        response = requests.post(
            f"{self.config.ollama_url}/api/chat",
            json={
                "model": self.config.translation_model,
                "stream": False,
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
                "options": {"temperature": 0.1},
            },
            timeout=45,
        )
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "").strip()
