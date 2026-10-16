# Qwen Local Subtitles (Preview)

A native Windows desktop app that listens to the current default speaker's playback through Windows loopback audio, transcribes it with Qwen3-ASR, translates locally with Ollama's Qwen3 model, and shows a movable always-on-top subtitle overlay.

Audio and subtitle text stay on this computer. The first run downloads model weights; after that, the app can run offline.

## Current preview scope

- Windows system playback capture (WASAPI loopback via SoundCard); no WPS or browser integration is required.
- Qwen3-ASR 0.6B recognition on the local machine.
- Local translation through Ollama (default model: `qwen3:4b-instruct-2507-q4_K_M`).
- Main control window and always-on-top subtitle overlay.
- The desktop interface uses fixed-height controls, a scrollable layout for smaller windows, Chinese language labels, and a packaged icon shared by the window and Windows shortcuts.
- Drag anywhere on the subtitle panel, including the text; Windows handles the move. Position, target language, caption mode, main-window geometry, subtitle size/color/background opacity are remembered between launches. Expand "字幕外观" to change the appearance.
- The overlay fits the available screen and fades away after 6 seconds without a new caption. It reappears on the next caption while overlay display is enabled.
- Translation receives up to three previous source fragments (at most 600 characters) to help resolve pronouns and terminology. Context is cleared on audio-source reset. This does not repair ASR errors or guarantee translation accuracy.
- The desktop UI defaults to meaning-first segmentation: 450 ms of silence or a 4-second speech limit. Speed-first mode retains 300 ms / 2 seconds. A pause already in progress can finish before submission. After a hard cut, the next recognition includes the previous segment and replaces the displayed caption with a two-segment revision. This repeats some work and can change wording; neither mode guarantees complete sentences or correct idioms.
- A failed or empty translation retains the recognized source and shows a notice. Listening continues and translation is attempted again on the next new segment; it does not repeatedly retry stale subtitles. The translation request has a 2-second connect / 8-second read timeout.
- "暂停" stops capture while retaining the loaded ASR model for faster resume. "释放识别模型" releases that retained model while idle. Keeping it uses GPU memory; Ollama is asked to retain its separate translation model for 30 minutes where resources permit.
- Audio capture runs continuously in 100 ms blocks. Local RMS-based voice activity ends a phrase at a pause or the selected mode's time limit; a bounded 8-second queue prevents slow inference from blocking capture. Startup audio is discarded once models are ready so subtitles start from current playback. This is still chunked recognition rather than token streaming, and latency/voice threshold need real-world tuning.

## Install and run

1. Install Python 3.11 or 3.12 and a current NVIDIA driver (CUDA GPU recommended).
2. Install Ollama and download the translation model once: `ollama pull qwen3:4b-instruct-2507-q4_K_M`.
3. From this repository root, create and activate a virtual environment, install PyTorch for your CUDA version from the official PyTorch selector, then run `pip install -e "desktop-translator[desktop]"`.
4. Start the app with `qwen-local-subtitles`.

On first launch, Qwen3-ASR weights are downloaded from Hugging Face and cached locally. Model downloads require internet; audio processing and translation use local models.

## Notes

- Keep "Follow system default output" selected to follow Windows when switching between speakers and headphones. The device list can also be refreshed for manual selection.
- The status area shows the active capture device and whether audio is arriving; silence on the wrong output device is visible before waiting for a subtitle.
- Headphones avoid capturing room audio from speakers.
- Ollama must be running locally and the selected model must be present.
- Models are separate downloads and retain their own licenses. The ASR code in this repository is Apache-2.0; review each model's card/license before redistribution.
- If the audio queue fills, the app drops the backlog, resets phrase/translation context, and shows a status notice. Results from before the reset are discarded, including work already in flight. GPU memory use depends on the ASR and Ollama model versions. If model loading fails, close other GPU-heavy applications or use CPU mode (slower).






