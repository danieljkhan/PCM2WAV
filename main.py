"""PCM to WAV Converter -- 실행 진입점."""

from __future__ import annotations

import contextlib
import ctypes
import logging
import sys


def main() -> None:
    """앱 실행."""
    if sys.platform == "win32":
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(1)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )

    from pcm2wav.app import Pcm2WavApp

    app = Pcm2WavApp()
    app.run()


if __name__ == "__main__":
    main()
