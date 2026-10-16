# Desktop subtitle improvements

Scope approved in chat: improve phrase boundaries, recover from translation failures, reset on dropped audio, retain the ASR model while paused, remember subtitle preferences, and adapt/expire the overlay. Local processing and existing models remain unchanged. No muted capture or video-cache integration.

1. Engine continuity and recovery (`qwen_local_subtitles/engine.py`).
   - Reproduce timeout stopping recognition and overflow losing the continuity marker.
   - Reset both audio fragments and translation context on a gap; reject in-flight results from an old audio generation.
   - Carry only the immediately preceding hard-cut segment into the next recognition, replacing the displayed caption with a bounded two-segment revision. Reset carry at a pause or gap.
   - Translation request failures show a fallback caption and retry only on the next new segment, with a bounded read timeout.
   - Check with synthetic frames and mocked inference/service failures; no hardware benchmark claims.
2. Pause and model lifecycle (`engine.py`, `app.py`).
   - Pass the loaded ASR object back to the window and reuse it on resume. An explicit release action is available only while idle. Ollama retains its model for 30 minutes where resources permit.
   - Check that repeated starts reuse the model and release removes the retained reference.
3. Overlay/preferences (`app.py`).
   - Remember target language, mode, subtitle size/color/background opacity, main geometry and overlay position using QSettings.
   - Fit the subtitle width/position to the available screen and fade stale captions after 6 seconds; new captions reappear when the overlay is enabled.
   - Check settings round trips with a temporary settings file, expiration, and screen constraints. Render a native UI preview.
4. Run the desktop test suite and inspect the changed code. Publish the exact files to the user's existing GitHub branch, sync the installed checkout, and reopen the client.

Trade-offs: overlapping recognition repeats some work and captions can revise their wording. This reduces loss of phrase context; it does not guarantee correct recognition or translation. Retaining the ASR model uses GPU memory until explicitly released or the application exits.

