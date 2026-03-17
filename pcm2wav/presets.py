"""PCM 포맷 프리셋 정의.

순수 데이터 모듈. GUI 드롭다운에서 사용.
dict 삽입 순서가 GUI 표시 순서를 결정 (Python 3.7+ 보장).
"""

from __future__ import annotations

from pcm2wav.models import PcmFormat

PRESETS: dict[str, PcmFormat | None] = {
    "CD Quality (44100Hz, 16-bit, Stereo)": PcmFormat(44100, 16, 2),
    "CD Quality Mono (44100Hz, 16-bit, Mono)": PcmFormat(44100, 16, 1),
    "DVD Quality (48000Hz, 24-bit, Stereo)": PcmFormat(48000, 24, 2),
    "Telephony (8000Hz, 16-bit, Mono)": PcmFormat(8000, 16, 1),
    "Wideband Telephony (16000Hz, 16-bit, Mono)": PcmFormat(16000, 16, 1),
    "Voice Recording (22050Hz, 16-bit, Mono)": PcmFormat(22050, 16, 1),
    "DAT Quality (48000Hz, 16-bit, Stereo)": PcmFormat(48000, 16, 2),
    "Custom": None,
}

DEFAULT_PRESET_NAME: str = "CD Quality Mono (44100Hz, 16-bit, Mono)"
