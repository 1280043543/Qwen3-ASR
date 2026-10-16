# Qwen Local Subtitles (Preview)

A native Windows desktop app that listens to the current default speaker's playback through Windows loopback audio, transcribes it with Qwen3-ASR, translates locally with Ollama's Qwen3 model, and shows a movable always-on-top subtitle overlay.

Audio and subtitle text stay on this computer. The first run downloads model weights; after that, the app can run offline.

## Current preview scope

- Windows system playback capture (WASAPI loopback via SoundCard); no WPS or browser integration is required.
- Qwen3-ASR 0.6B recognition on the local machine.
- Local translation through Ollama (default model: `qwen3:4b`).
- Main control window and always-on-top subtitle overlay.
- Short fixed audio windows are used in this first preview. This is not yet sentence-aware streaming; latency and duplicate/partial captions need real-world tuning.

## Install and run

1. Install Python 3.11 or 3.12 and a current NVIDIA driver (CUDA GPU recommended).
2. Install Ollama and download the translation model once: `ollama pull qwen3:4b`.
3. From this repository root, create and activate a virtual environment, install PyTorch for your CUDA version from the official PyTorch selector, then run `pip install -e "desktop-translator[desktop]"`.
4. Start with `python -m qwen_asr.desktop_translator`.

On first launch, Qwen3-ASR weights are downloaded from Hugging Face and cached locally. Model downloads require internet; audio processing and translation use local models.

## Notes

- The app captures the default Windows output device. Switch Windows output before starting if needed.
- Headphones avoid capturing room audio from speakers.
- Ollama must be running locally and the selected model must be present.
- Models are separate downloads and retain their own licenses. The ASR code in this repository is Apache-2.0; review each model's card/license before redistribution.
- This is an early preview. GPU memory use depends on the ASR and Ollama model versions. If model loading fails, close other GPU-heavy applications or use CPU mode (slower).
