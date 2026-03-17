"""PCM to WAV 핵심 변환 엔진.

GUI와 완전히 독립적으로 동작하는 변환 모듈.
"""

from __future__ import annotations

import array
import contextlib
import logging
import time
import wave
from typing import TYPE_CHECKING, TypeAlias

from pcm2wav.models import ByteOrder, ConversionResult, PcmConversionError, PcmFormat

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable
    from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK_SIZE: int = 262_144  # 256KB

ProgressCallback: TypeAlias = "Callable[[int, int], None]"
"""(bytes_processed, total_bytes) 콜백 타입."""

BatchProgressCallback: TypeAlias = "Callable[[int, int, int, int], None]"
"""(file_index, total_files, bytes_processed, file_total_bytes) 콜백 타입."""


def _aligned_chunk_size(frame_size: int) -> int:
    """프레임 경계에 정렬된 청크 크기 계산.

    Args:
        frame_size: 프레임 크기 (바이트).

    Returns:
        프레임 경계에 정렬된 청크 크기.
    """
    return max(frame_size, (CHUNK_SIZE // frame_size) * frame_size)


def swap_byte_order(data: bytes, sample_width: int) -> bytes:
    """PCM 데이터의 바이트 오더를 스왑하여 little-endian으로 변환.

    Args:
        data: PCM 바이트 데이터 (길이는 sample_width의 배수여야 함).
        sample_width: 샘플당 바이트 수 (1, 2, 3).

    Returns:
        little-endian으로 변환된 바이트 데이터.

    Note:
        - 8-bit (sample_width=1): no-op (1바이트, 엔디언 없음).
        - 16-bit (sample_width=2): array.array('H').byteswap() 사용 (고성능).
        - 24-bit (sample_width=3): bytearray 슬라이스 스왑.
          Python은 RHS 튜플 전체를 평가한 뒤 LHS에 대입하므로 안전함.
    """
    if sample_width == 1:
        return data

    if sample_width == 2:
        arr = array.array("H", data)
        arr.byteswap()
        return arr.tobytes()

    if sample_width == 3:
        ba = bytearray(data)
        ba[0::3], ba[2::3] = ba[2::3], ba[0::3]
        return bytes(ba)

    raise PcmConversionError(f"지원하지 않는 sample_width: {sample_width}")


_SIGNEDNESS_TABLE: bytes = bytes(range(256))[128:] + bytes(range(256))[:128]


def convert_8bit_signedness(data: bytes) -> bytes:
    """8-bit signed PCM -> unsigned PCM (WAV 표준) 변환.

    bytes.translate()로 O(n) 최적화.

    Args:
        data: 8-bit signed PCM 데이터.

    Returns:
        8-bit unsigned PCM 데이터.
    """
    return data.translate(_SIGNEDNESS_TABLE)


def validate_pcm_file(pcm_path: Path, fmt: PcmFormat) -> tuple[list[str], list[str]]:
    """PCM 파일 사전 검증.

    Args:
        pcm_path: PCM 파일 경로.
        fmt: PCM 포맷 파라미터.

    Returns:
        (errors, warnings) 튜플.
        - errors: 변환을 차단하는 심각한 문제 (빈 리스트 = 진행 가능).
        - warnings: 주의사항 (변환은 진행하되 사용자에게 알림).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not pcm_path.exists():
        errors.append(f"파일을 찾을 수 없습니다: {pcm_path}")
        return errors, warnings

    file_size = pcm_path.stat().st_size

    if file_size == 0:
        errors.append("빈 파일입니다 (0 바이트)")
        return errors, warnings

    # 4GB 한계 검증
    # WAV 구조: RIFF header(12) + fmt chunk(24) + data chunk header(8) + data = 44 + data
    # RIFF size field = total_file_size - 8, data subchunk size field = file_size
    # 두 필드 모두 uint32 (최대 0xFFFFFFFF)
    max_uint32 = 0xFFFF_FFFF
    pad_byte = file_size % 2  # RIFF spec: 홀수 크기 data 청크 뒤에 1바이트 패딩
    riff_payload = (
        file_size + 36 + pad_byte
    )  # "WAVE"(4) + fmt chunk(24) + data header(8) + data + pad

    if file_size > max_uint32:
        errors.append(f"PCM 데이터 크기({file_size:,}B)가 WAV data 청크 한계(4GB)를 초과합니다")
    elif riff_payload > max_uint32:
        errors.append(f"출력 WAV RIFF 페이로드({riff_payload:,}B)가 4GB를 초과합니다")

    # 프레임 정렬 검증
    if file_size % fmt.frame_size != 0:
        remainder = file_size % fmt.frame_size
        truncated_frames = file_size // fmt.frame_size
        warnings.append(
            f"파일 크기({file_size:,}B)가 프레임 크기({fmt.frame_size}B)의 "
            f"배수가 아닙니다. "
            f"마지막 {remainder}B는 잘림 처리됩니다 "
            f"(총 {truncated_frames}프레임 변환)."
        )

    return errors, warnings


def convert_pcm_to_wav(
    pcm_path: Path,
    wav_path: Path,
    fmt: PcmFormat,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> ConversionResult:
    """단일 PCM 파일을 WAV로 변환.

    변환 파이프라인:
    1. 입력 파일 존재/읽기 권한 검증
    2. validate_pcm_file()로 사전 검증 (hard error 시 즉시 실패)
    3. wave.open()으로 출력 파일 생성
    4. WAV 파라미터 설정
    5. 청크 루프 (바이트 스왑, 부호 변환, progress callback)
    6. wave 파일 close
    7. ConversionResult 반환

    Args:
        pcm_path: 입력 PCM 파일 경로.
        wav_path: 출력 WAV 파일 경로.
        fmt: PCM 포맷 파라미터.
        progress_callback: (bytes_processed, total_bytes) 콜백.
        cancel_event: 취소 이벤트.

    Returns:
        ConversionResult 인스턴스.

    Raises:
        PcmConversionError: 변환 실패 시.
    """
    start_time = time.monotonic()
    try:
        # 1. 입력 파일 검증
        if not pcm_path.exists():
            raise PcmConversionError(f"입력 파일을 찾을 수 없습니다: {pcm_path}")
        if not pcm_path.is_file():
            raise PcmConversionError(f"파일이 아닙니다: {pcm_path}")

        file_size = pcm_path.stat().st_size
        if file_size == 0:
            raise PcmConversionError(f"빈 파일입니다: {pcm_path}")

        # 2. 사전 검증
        errors, warnings = validate_pcm_file(pcm_path, fmt)
        if errors:
            raise PcmConversionError("; ".join(errors))
        for w in warnings:
            logger.warning(w)

        # 3-4. WAV 출력 파일 생성 + 파라미터 설정
        needs_swap = fmt.byte_order == ByteOrder.BIG_ENDIAN and fmt.sample_width > 1
        needs_sign_convert = fmt.bit_depth == 8 and fmt.signed
        chunk_size = _aligned_chunk_size(fmt.frame_size)

        with (
            open(pcm_path, "rb") as pcm_file,
            wave.open(str(wav_path), "wb") as wav_file,
        ):
            wav_file.setnchannels(fmt.channels)
            wav_file.setsampwidth(fmt.sample_width)
            wav_file.setframerate(fmt.sample_rate)
            wav_file.setnframes(0)  # writeframes()가 자동 누적

            # 5. 청크 루프
            bytes_processed = 0
            while True:
                if cancel_event and cancel_event.is_set():
                    break

                chunk = pcm_file.read(chunk_size)
                if not chunk:
                    break

                if needs_swap:
                    chunk = swap_byte_order(chunk, fmt.sample_width)

                if needs_sign_convert:
                    chunk = convert_8bit_signedness(chunk)

                wav_file.writeframes(chunk)

                bytes_processed += len(chunk)
                if progress_callback:
                    progress_callback(bytes_processed, file_size)

        # 취소 시 부분 파일 삭제
        if cancel_event and cancel_event.is_set():
            _safe_delete(wav_path)
            elapsed = time.monotonic() - start_time
            return ConversionResult(
                input_path=pcm_path,
                output_path=None,
                success=False,
                error_message="사용자에 의해 취소됨",
                elapsed_seconds=elapsed,
            )

        # 성공 결과
        elapsed = time.monotonic() - start_time
        output_size = wav_path.stat().st_size
        frames = file_size // fmt.frame_size
        return ConversionResult(
            input_path=pcm_path,
            output_path=wav_path,
            success=True,
            elapsed_seconds=elapsed,
            frames_written=frames,
            output_size_bytes=output_size,
        )

    except PcmConversionError:
        _safe_delete(wav_path)
        raise
    except Exception as exc:
        _safe_delete(wav_path)
        raise PcmConversionError(f"변환 오류: {exc}") from exc


def _safe_delete(path: Path) -> None:
    """파일이 존재하면 삭제. 실패해도 예외 무시.

    Args:
        path: 삭제할 파일 경로.
    """
    with contextlib.suppress(OSError):
        if path.exists():
            path.unlink()


def batch_convert(
    files: list[tuple[Path, Path]],
    fmt: PcmFormat,
    progress_callback: BatchProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> list[ConversionResult]:
    """다수 파일 배치 변환.

    Args:
        files: (입력 PCM 경로, 출력 WAV 경로) 튜플 리스트.
        fmt: PCM 포맷 파라미터.
        progress_callback: (file_index, total_files, bytes_processed,
            file_total_bytes) 콜백.
        cancel_event: 취소 이벤트. 설정 시 현재 파일 변환 후 중단.

    Returns:
        ConversionResult 리스트. 실패한 파일도 포함 (success=False).
    """
    results: list[ConversionResult] = []
    total_files = len(files)

    for file_index, (pcm_path, wav_path) in enumerate(files):
        if cancel_event and cancel_event.is_set():
            break

        def _make_file_progress(
            idx: int,
        ) -> ProgressCallback | None:
            if progress_callback is None:
                return None

            def _file_progress(bytes_processed: int, file_total: int) -> None:
                progress_callback(idx, total_files, bytes_processed, file_total)

            return _file_progress

        try:
            result = convert_pcm_to_wav(
                pcm_path=pcm_path,
                wav_path=wav_path,
                fmt=fmt,
                progress_callback=_make_file_progress(file_index),
                cancel_event=cancel_event,
            )
            results.append(result)
        except PcmConversionError as exc:
            logger.error("파일 변환 실패: %s - %s", pcm_path, exc)
            results.append(
                ConversionResult(
                    input_path=pcm_path,
                    output_path=None,
                    success=False,
                    error_message=str(exc),
                )
            )

    return results
