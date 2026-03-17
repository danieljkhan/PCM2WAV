"""PCM 변환에 필요한 데이터 타입 정의."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ByteOrder(Enum):
    """PCM 데이터의 바이트 오더."""

    LITTLE_ENDIAN = "little"
    BIG_ENDIAN = "big"


class PcmConversionError(Exception):
    """변환 실패 커스텀 예외."""


VALID_BIT_DEPTHS: frozenset[int] = frozenset({8, 16, 24})
MIN_SAMPLE_RATE: int = 1
MAX_SAMPLE_RATE: int = 384_000
VALID_CHANNELS: frozenset[int] = frozenset({1, 2})


@dataclass(frozen=True)
class PcmFormat:
    """PCM 포맷 파라미터.

    Attributes:
        sample_rate: 샘플레이트 (Hz). 1~384,000 범위.
        bit_depth: 비트 깊이. 8, 16, 24만 허용 (v1).
        channels: 채널 수. 1(mono) 또는 2(stereo).
        byte_order: 바이트 오더. 8-bit에서는 무시됨.
        signed: 8-bit 부호 여부. bit_depth > 8이면 반드시 True.
    """

    sample_rate: int = 44100
    bit_depth: int = 16
    channels: int = 1
    byte_order: ByteOrder = ByteOrder.LITTLE_ENDIAN
    signed: bool = True

    def __post_init__(self) -> None:
        """포맷 파라미터 유효성 검증."""
        if self.bit_depth not in VALID_BIT_DEPTHS:
            raise ValueError(
                f"bit_depth must be one of {sorted(VALID_BIT_DEPTHS)}, got {self.bit_depth}"
            )
        if not (MIN_SAMPLE_RATE <= self.sample_rate <= MAX_SAMPLE_RATE):
            raise ValueError(
                f"sample_rate must be {MIN_SAMPLE_RATE}~{MAX_SAMPLE_RATE}, got {self.sample_rate}"
            )
        if self.channels not in VALID_CHANNELS:
            raise ValueError(
                f"channels must be one of {sorted(VALID_CHANNELS)}, got {self.channels}"
            )
        if self.bit_depth > 8 and not self.signed:
            raise ValueError(
                "WAV standard requires 16/24-bit PCM to be signed. "
                "unsigned is only valid for 8-bit."
            )

    @property
    def sample_width(self) -> int:
        """Bytes per sample per channel."""
        return self.bit_depth // 8

    @property
    def frame_size(self) -> int:
        """Bytes per frame (all channels)."""
        return self.sample_width * self.channels


@dataclass
class ConversionResult:
    """단일 파일 변환 결과 (mutable -- 변환 과정에서 필드가 채워짐).

    Attributes:
        input_path: 입력 PCM 파일 경로.
        output_path: 출력 WAV 파일 경로 (실패 시 None).
        success: 변환 성공 여부.
        error_message: 실패 시 오류 메시지 (성공 시 None).
        elapsed_seconds: 변환 소요 시간 (초).
        frames_written: 기록된 오디오 프레임 수.
        output_size_bytes: 출력 파일 크기 (바이트).
    """

    input_path: Path
    output_path: Path | None
    success: bool
    error_message: str | None = None
    elapsed_seconds: float = 0.0
    frames_written: int = 0
    output_size_bytes: int = 0
