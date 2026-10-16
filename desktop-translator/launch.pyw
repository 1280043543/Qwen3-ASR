"""Windowed launcher used by the installed desktop shortcut."""
from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / ".local" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
if sys.stdout is None or sys.stderr is None:
    output_log = open(LOG_DIR / "output.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = output_log
    sys.stderr = output_log
logging.basicConfig(
    filename=LOG_DIR / "client.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def ensure_ollama() -> None:
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=2):
            return
    except OSError:
        pass
    executable = shutil.which("ollama")
    if not executable:
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise RuntimeError("未找到本地翻译服务 Ollama，请先安装 Ollama。")
    log = open(LOG_DIR / "ollama.log", "a", encoding="utf-8")
    subprocess.Popen(
        [executable, "serve"],
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log.close()
    for _ in range(40):
        time.sleep(0.25)
        try:
            with urlopen("http://127.0.0.1:11434/api/tags", timeout=1):
                return
        except OSError:
            continue
    raise RuntimeError("本地翻译服务启动超时，请稍后重试。")


def launch() -> None:
    os.chdir(ROOT)
    from qwen_local_subtitles.windows_shell import set_process_app_id
    set_process_app_id()
    model_dir = ROOT / ".models" / "Qwen3-ASR-0.6B"
    if (model_dir / "config.json").is_file():
        os.environ["QWEN_ASR_MODEL"] = str(model_dir)
        os.environ["HF_HUB_OFFLINE"] = "1"
    ensure_ollama()
    from qwen_local_subtitles.app import main
    main()


if __name__ == "__main__":
    try:
        launch()
    except Exception as exc:
        logging.exception("Client startup failed")
        ctypes.windll.user32.MessageBoxW(
            None,
            f"启动失败：{exc}\n\n日志位置：{LOG_DIR / 'client.log'}",
            "本地实时字幕",
            0x10,
        )

